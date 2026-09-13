"""Index hygiene and full-text search.

* Per-class (annotation-declared) indexes on Postgres are entity-scoped:
  ``entity``-leading by default, ``WHERE entity = ...`` on request, and they
  replace the unscoped pre-0.0.18 index of the same fields.
* ``create_index`` indexes top-level columns as columns, emits
  ``DESC NULLS LAST``, and rebuilds indexes defined by the old rules.
* The whole-document GIN is optional (``gin_index`` / ``JVSPATIAL_PG_GIN_INDEX``).
* ``$text`` pushes down to ``to_tsvector('simple', ...) @@ plainto_tsquery``
  on Postgres and matches the in-memory evaluation everywhere else.

Postgres tests run when ``JVSPATIAL_POSTGRES_TEST_DSN`` is reachable.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import uuid
from typing import Any, AsyncIterator, Dict, List, Tuple

import pytest

from jvspatial.core import context as context_module
from jvspatial.core.annotations import attribute, compound_index, fulltext_index
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Edge, Node
from jvspatial.core.utils import generate_id
from jvspatial.db import escape_regex
from jvspatial.db._postgres_translate import translate_query, translate_sort
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.mongodb import _native_query
from jvspatial.db.query import QueryEngine
from jvspatial.db.sqlite import SQLiteDB
from jvspatial.exceptions import QueryError

pytestmark = pytest.mark.asyncio(loop_scope="module")

_PG_DSN = os.getenv(
    "JVSPATIAL_POSTGRES_TEST_DSN",
    "postgresql://jvspatial:jvspatial@localhost:5432/jvspatial",
)


@compound_index([("group_id", 1), ("created_at", -1)], name="group_recent")
class IdxEntry(Node):
    group_id: str = attribute(indexed=True, default="")
    created_at: str = ""
    note: str = attribute(indexed=True, index_partial_by_entity=True, default="")


@fulltext_index(["title", "body"])
class IdxArticle(Node):
    title: str = ""
    body: str = ""
    summary: str = attribute(fulltext=True, default="")


class IdxLink(Edge):
    pass


@pytest.fixture(autouse=True)
def _auto_indexes(monkeypatch):
    monkeypatch.setenv("JVSPATIAL_AUTO_CREATE_INDEXES", "true")


@contextlib.asynccontextmanager
async def _pg(**db_kwargs: Any) -> AsyncIterator[Tuple[GraphContext, Any, Any, str]]:
    try:
        import asyncpg

        from jvspatial.db.postgres import PostgresDB
    except ImportError:
        pytest.skip("asyncpg not installed")
    try:
        admin = await asyncio.wait_for(asyncpg.connect(dsn=_PG_DSN), timeout=2.0)
    except Exception:
        pytest.skip(f"Postgres unreachable at {_PG_DSN}")
    schema = f"t_idx_{uuid.uuid4().hex[:10]}"
    await admin.execute(f"CREATE SCHEMA {schema}")
    db = PostgresDB(
        dsn=_PG_DSN, schema_name=schema, min_size=1, max_size=4, **db_kwargs
    )
    ctx = GraphContext(database=db)
    set_default_context(ctx)
    context_module._ensured_indexes.clear()
    try:
        yield ctx, db, admin, schema
    finally:
        set_default_context(None)
        context_module._ensured_indexes.clear()
        await db.close()
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


async def _indexes(admin: Any, schema: str, table: str) -> Dict[str, str]:
    rows = await admin.fetch(
        "SELECT indexname, indexdef FROM pg_indexes "
        "WHERE schemaname = $1 AND tablename = $2",
        schema,
        table,
    )
    return {r["indexname"]: r["indexdef"] for r in rows}


def _plan_nodes(plan: Any) -> List[Dict[str, Any]]:
    found = [plan]
    for child in plan.get("Plans", []):
        found += _plan_nodes(child)
    return found


async def _explain(admin: Any, sql: str, params: List[Any]) -> List[Dict[str, Any]]:
    raw = await admin.fetchval(f"EXPLAIN (FORMAT JSON) {sql}", *params)
    plan = json.loads(raw) if isinstance(raw, str) else raw
    return _plan_nodes(plan[0]["Plan"])


# ---- entity-scoped per-class indexes ------------------------------------------


async def test_per_class_indexes_are_entity_scoped():
    async with _pg() as (ctx, db, admin, schema):
        await db.create_index("node", "context.group_id")  # pre-0.0.18 unscoped
        assert "node_context_group_id_idx" in await _indexes(admin, schema, "node")

        await ctx.ensure_indexes(IdxEntry)
        idx = await _indexes(admin, schema, "node")

        single = idx["node_entity_context_group_id_idx"]
        assert "(entity, ((data #>> '{context,group_id}'::text[])))" in single
        compound = idx["node_entity_context_group_id_context_created_at_idx"]
        assert compound.startswith("CREATE INDEX")
        assert "DESC NULLS LAST" in compound
        partial = idx["node_idxentry_context_note_idx"]
        assert "WHERE (entity = 'IdxEntry'::text)" in partial
        assert "node_context_group_id_idx" not in idx  # legacy replaced


async def test_stale_edge_index_is_rebuilt_on_entity_column():
    async with _pg() as (ctx, db, admin, schema):
        await ctx.save(IdxEntry(group_id="t"))  # bootstraps the tables
        await db._bootstrap_collection("edge")
        await admin.execute(
            f"CREATE UNIQUE INDEX edge_source_target_entity_uniq ON {schema}.edge "
            "((data #>> '{source}'), (data #>> '{target}'), (data #>> '{entity}'))"
        )
        await ctx.ensure_indexes(IdxLink)
        fixed = (await _indexes(admin, schema, "edge"))[
            "edge_source_target_entity_uniq"
        ]
        assert fixed.startswith("CREATE UNIQUE INDEX")
        assert "'{entity}'" not in fixed and ", entity)" in fixed


async def test_typed_sorted_find_walks_the_entity_leading_index():
    async with _pg(gin_index="off") as (ctx, db, admin, schema):
        await ctx.ensure_indexes(IdxEntry)
        records = [
            {
                "id": generate_id("n", entity),
                "entity": entity,
                "context": {"group_id": f"t{i % 40}", "created_at": f"2026-01-{i:05d}"},
            }
            for entity in ("IdxEntry", "Other1", "Other2", "Other3", "Other4")
            for i in range(1500)
        ]
        await db.bulk_save_detailed("node", records)
        await admin.execute(f"ANALYZE {schema}.node")

        where, params = translate_query(
            {"entity": "IdxEntry", "context.group_id": "t7"}
        )
        order = translate_sort([("context.created_at", -1)])
        await admin.execute(f"SET search_path TO {schema}")
        plan = await _explain(
            admin,
            f"SELECT data FROM node WHERE {where} ORDER BY {order} LIMIT 20",
            params,
        )
        names = {p.get("Index Name") for p in plan}
        assert "node_entity_context_group_id_context_created_at_idx" in names, plan
        assert not any(p["Node Type"] == "Sort" for p in plan), plan

        found = await db.find(
            "node",
            {"entity": "IdxEntry", "context.group_id": "t7"},
            sort=[("context.created_at", -1)],
            limit=20,
        )
        stamps = [r["context"]["created_at"] for r in found]
        assert len(found) == 20 and stamps == sorted(stamps, reverse=True)


# ---- optional whole-document GIN ----------------------------------------------


async def test_gin_index_can_be_turned_off(monkeypatch, caplog):
    async with _pg() as (ctx, db, admin, schema):
        await ctx.save(IdxEntry(group_id="t"))
        assert "node_data_gin" in await _indexes(admin, schema, "node")

    async with _pg(gin_index="off") as (ctx, db, admin, schema):
        await ctx.save(IdxEntry(group_id="t"))
        assert "node_data_gin" not in await _indexes(admin, schema, "node")
        with caplog.at_level(logging.WARNING, logger="jvspatial.db.postgres"):
            await db.find("node", {"context.tags": {"$all": ["a"]}})
            await db.find("node", {"context.tags": {"$all": ["b"]}})
        warnings = [r for r in caplog.records if "gin_index='off'" in r.getMessage()]
        assert len(warnings) == 1

    monkeypatch.setenv("JVSPATIAL_PG_GIN_INDEX", "off")
    from jvspatial.db.postgres import PostgresDB

    assert PostgresDB(dsn=_PG_DSN).gin_index == "off"
    with pytest.raises(ValueError):
        PostgresDB(dsn=_PG_DSN, gin_index="partial")


# ---- full-text search -----------------------------------------------------------


_ARTICLES = [
    ("Graph databases at scale", "Hub nodes and fan-out", "graph"),
    ("The vector store", "Embeddings next to the graph", "vectors"),
    ("Scaling Postgres", "DATABASE design for large tables", "postgres"),
    ("Cooking notes", "Nothing about data here", "food"),
]
_TEXT_QUERIES = [
    {"$search": "graph", "$fields": ["context.title", "context.body"]},
    {"$search": "Graph DATABASE", "$fields": ["context.title", "context.body"]},
    {"$search": "database", "$fields": ["context.title"]},
    {"$search": "vector graph", "$fields": ["context.title", "context.body"]},
    {"$search": "missing", "$fields": ["context.title", "context.body"]},
    {"$search": "fan", "$fields": ["context.title", "context.body"]},
]


def _article_records() -> List[Dict[str, Any]]:
    return [
        {
            "id": f"n.IdxArticle.a{i}",
            "entity": "IdxArticle",
            "context": {"title": title, "body": body, "summary": summary},
        }
        for i, (title, body, summary) in enumerate(_ARTICLES)
    ]


async def test_fulltext_indexes_and_text_pushdown():
    async with _pg(gin_index="off") as (ctx, db, admin, schema):
        await ctx.ensure_indexes(IdxArticle)
        idx = await _indexes(admin, schema, "node")
        both = idx["node_idxarticle_context_title_context_body_fts"]
        assert "USING gin (to_tsvector('simple'::regconfig" in both
        assert "WHERE (entity = 'IdxArticle'::text)" in both
        assert "node_idxarticle_context_summary_fts" in idx

        await db.bulk_save_detailed("node", _article_records())
        query = {"entity": "IdxArticle", "$text": _TEXT_QUERIES[0]}  # "graph"
        got = {r["id"] for r in await db.find("node", query)}
        assert got == {"n.IdxArticle.a0", "n.IdxArticle.a1"}
        # 'simple' does not stem: "database" does not match "databases".
        miss = {"entity": "IdxArticle", "$text": _TEXT_QUERIES[1]}
        assert await db.find("node", miss) == []

        # Enough non-matching rows that the planner prefers the GIN over
        # scanning every IdxArticle row through the plain entity index.
        await db.bulk_save_detailed(
            "node",
            [
                {
                    "id": f"n.IdxArticle.f{i}",
                    "entity": "IdxArticle",
                    "context": {"title": f"filler {i}", "body": "lorem ipsum"},
                }
                for i in range(3000)
            ],
        )
        await admin.execute(f"ANALYZE {schema}.node")
        where, params = translate_query(query)
        await admin.execute(f"SET search_path TO {schema}")
        await admin.execute("SET enable_seqscan = off")
        plan = await _explain(admin, f"SELECT data FROM node WHERE {where}", params)
        assert any(
            p.get("Index Name") == "node_idxarticle_context_title_context_body_fts"
            for p in plan
        ), plan


@pytest.mark.parametrize("backend", ["json", "sqlite", "postgres"])
async def test_text_matches_in_memory_evaluation(backend, tmp_path):
    records = _article_records()
    expected = [
        {r["id"] for r in records if QueryEngine.match(r, {"$text": q})}
        for q in _TEXT_QUERIES
    ]
    assert expected[0] == {"n.IdxArticle.a0", "n.IdxArticle.a1"}

    async def check(db: Any) -> None:
        for record in records:
            await db.save("node", dict(record))
        for q, want in zip(_TEXT_QUERIES, expected):
            got = {r["id"] for r in await db.find("node", {"$text": q})}
            assert got == want, (q, got, want)
            assert await db.count("node", {"$text": q}) == len(want)

    if backend == "json":
        await check(JsonDB(base_path=str(tmp_path / "j")))
    elif backend == "sqlite":
        db = SQLiteDB(db_path=str(tmp_path / "s.db"))
        await check(db)
        await db.close()
    else:
        async with _pg() as (_ctx, db, _admin, _schema):
            await check(db)


def test_text_translation_and_fallbacks():
    sql, params = translate_query(
        {"$text": {"$search": "a b", "$fields": ["context.title", "context.body"]}},
        table="n",
    )
    assert sql == (
        "to_tsvector('simple'::regconfig, coalesce(n.data #>> '{context,title}', '')"
        " || ' ' || coalesce(n.data #>> '{context,body}', '')) "
        "@@ plainto_tsquery('simple'::regconfig, $1)"
    )
    assert params == ["a b"]
    assert translate_query({"$text": {"$search": "a"}}) is None  # no $fields
    assert (
        translate_query({"$text": {"$search": "a", "$fields": ["x"], "$x": 1}}) is None
    )
    assert _native_query({"$text": {"$search": "a", "$fields": ["x"]}}) == {
        "$text": {"$search": "a"}
    }


def test_in_memory_text_semantics():
    doc = {"context": {"title": "Graph Databases", "tags": ["alpha", "Beta"]}}
    fields = ["context.title"]
    assert QueryEngine.match(doc, {"$text": {"$search": "graph", "$fields": fields}})
    assert QueryEngine.match(
        doc, {"$text": {"$search": "DATABASES graph", "$fields": fields}}
    )
    assert not QueryEngine.match(
        doc, {"$text": {"$search": "database", "$fields": fields}}
    )
    assert not QueryEngine.match(doc, {"$text": {"$search": "  ", "$fields": fields}})
    assert QueryEngine.match(doc, {"$text": {"$search": "beta graph"}})  # every string
    with pytest.raises(QueryError):
        QueryEngine.match(doc, {"$text": "graph"})


# ---- $regex escaping, find_edges_between(limit) --------------------------------


_METACHAR_VALUES = ["a.b(c)*", "1+1=2?", "[x]{y}^$|\\z", "plain words"]


@pytest.mark.parametrize("backend", ["memory", "postgres"])
async def test_escape_regex_matches_literally(backend):
    records = [
        {"id": f"n.Idx.{i}", "entity": "Idx", "context": {"v": v}}
        for i, v in enumerate(_METACHAR_VALUES)
    ]
    if backend == "memory":
        for rec in records:
            q = {"context.v": {"$regex": f"^{escape_regex(rec['context']['v'])}$"}}
            assert [r["id"] for r in records if QueryEngine.match(r, q)] == [rec["id"]]
        return
    async with _pg() as (_ctx, db, _admin, _schema):
        for rec in records:
            await db.save("node", rec)
        for rec in records:
            q = {"context.v": {"$regex": f"^{escape_regex(rec['context']['v'])}$"}}
            assert [r["id"] for r in await db.find("node", q)] == [rec["id"]]


async def test_find_edges_between_limit(tmp_path):
    ctx = GraphContext(database=JsonDB(base_path=str(tmp_path / "j")))
    set_default_context(ctx)
    try:
        hub = await IdxEntry.create(group_id="hub")
        for i in range(5):
            await hub.connect(await IdxEntry.create(group_id=f"l{i}"), edge=IdxLink)
        assert len(await ctx.find_edges_between(hub.id, edge_class=IdxLink)) == 5
        assert (
            len(await ctx.find_edges_between(hub.id, edge_class=IdxLink, limit=2)) == 2
        )
    finally:
        set_default_context(None)
