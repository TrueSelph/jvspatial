"""Neighbour-query pushdown — ``nodes()`` / ``count_nodes()`` / ``nodes_page()``.

Every filter shape ``nodes()`` accepts (single / list / string / class /
``{name: criteria}``, node and edge side, plus property kwargs) runs against
every reachable backend and is compared with a pure-Python reference over the
raw records. On Postgres, type-only filters must cost exactly one round trip
and the join must not sequentially scan the edge table.

Postgres runs when ``JVSPATIAL_POSTGRES_TEST_DSN`` is reachable, MongoDB when
``JVSPATIAL_MONGODB_TEST_URI`` is set and reachable; otherwise those skip.
"""

from __future__ import annotations

import asyncio
import itertools
import json
import os
import uuid
from typing import Any, Dict, List, Optional, Set

import pytest

from jvspatial.core import context as context_module
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Edge, Node
from jvspatial.core.utils import generate_id
from jvspatial.db._observable import ObservableDatabase
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.sqlite import SQLiteDB
from jvspatial.observability import db_op_counter

pytestmark = pytest.mark.asyncio(loop_scope="module")

_PG_DSN = os.getenv(
    "JVSPATIAL_POSTGRES_TEST_DSN",
    "postgresql://jvspatial:jvspatial@localhost:5432/jvspatial",
)
_MONGO_URI = os.getenv("JVSPATIAL_MONGODB_TEST_URI")


class QHub(Node):
    name: str = ""


class QAlpha(Node):
    name: str = ""
    score: int = 0


class QAlphaSub(QAlpha):
    pass


class QBeta(Node):
    name: str = ""
    score: int = 0


class QKnows(Edge):
    weight: int = 0


class QLikes(Edge):
    weight: int = 0


_NODE_CLASSES = {"QHub": QHub, "QAlpha": QAlpha, "QAlphaSub": QAlphaSub, "QBeta": QBeta}


# ---- backends ---------------------------------------------------------------


async def _pg_admin() -> Any:
    try:
        import asyncpg
    except ImportError:
        pytest.skip("asyncpg not installed")
    try:
        return await asyncio.wait_for(asyncpg.connect(dsn=_PG_DSN), timeout=2.0)
    except Exception:
        pytest.skip(f"Postgres unreachable at {_PG_DSN}")


async def _mongo_client() -> Any:
    if not _MONGO_URI:
        pytest.skip("JVSPATIAL_MONGODB_TEST_URI not set")
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(_MONGO_URI, serverSelectionTimeoutMS=2000)
    try:
        await client.admin.command("ping")
    except Exception:
        client.close()
        pytest.skip(f"MongoDB unreachable at {_MONGO_URI}")
    return client


@pytest.fixture(params=["json", "sqlite", "postgres", "mongodb"])
async def graph(request, tmp_path):
    """Yield ``(ctx, db, backend, extras)`` on a fresh store."""
    backend = request.param
    cleanup: List[Any] = []
    extras: Dict[str, Any] = {}
    if backend == "json":
        db: Any = JsonDB(base_path=str(tmp_path / "json"))
    elif backend == "sqlite":
        db = SQLiteDB(db_path=str(tmp_path / "graph.db"))
    elif backend == "postgres":
        from jvspatial.db.postgres import PostgresDB

        admin = await _pg_admin()
        schema = f"t_push_{uuid.uuid4().hex[:10]}"
        await admin.execute(f"CREATE SCHEMA {schema}")
        db = PostgresDB(dsn=_PG_DSN, schema_name=schema, min_size=1, max_size=8)
        extras.update(admin=admin, schema=schema)

        async def _drop_pg() -> None:
            await admin.execute(f"DROP SCHEMA {schema} CASCADE")
            await admin.close()

        cleanup.append(_drop_pg)
    else:
        from jvspatial.db.mongodb import MongoDB

        client = await _mongo_client()
        name = f"jvs_push_{uuid.uuid4().hex[:10]}"
        db = MongoDB(uri=_MONGO_URI, db_name=name)

        async def _drop_mongo() -> None:
            await client.drop_database(name)
            client.close()

        cleanup.append(_drop_mongo)

    ctx = GraphContext(database=db)
    set_default_context(ctx)
    context_module._ensured_indexes.clear()
    try:
        yield ctx, db, backend, extras
    finally:
        set_default_context(None)
        context_module._ensured_indexes.clear()
        close = getattr(db, "close", None)
        if callable(close):
            result = close()
            if asyncio.iscoroutine(result):
                await result
        for fn in cleanup:
            await fn()


# ---- fixture graph + reference ------------------------------------------------


async def _seed() -> Dict[str, Node]:
    """Hub with mixed edge / neighbour types, a subclass, and both-way links."""
    n: Dict[str, Node] = {"hub": await QHub.create(name="hub")}
    for key, cls, score in (
        ("a1", QAlpha, 1),
        ("a2", QAlpha, 5),
        ("s1", QAlphaSub, 3),
        ("b1", QBeta, 2),
        ("b2", QBeta, 7),
        ("x", QBeta, 4),
        ("z", QAlpha, 9),
    ):
        n[key] = await cls.create(name=key, score=score)
    hub = n["hub"]
    for target, edge, weight in (
        ("a1", QKnows, 1),
        ("a2", QKnows, 3),
        ("s1", QLikes, 2),
        ("b1", QKnows, 5),
        ("b2", QLikes, 1),
        ("z", QKnows, 2),
    ):
        await hub.connect(n[target], edge=edge, weight=weight)
    for source, edge, weight in (("x", QKnows, 4), ("z", QLikes, 6), ("b1", QLikes, 3)):
        await n[source].connect(hub, edge=edge, weight=weight)
    return n


def _crit_ok(values: Dict[str, Any], criteria: Dict[str, Any]) -> bool:
    for key, cond in criteria.items():
        value = values.get(key.split(".", 1)[1] if key.startswith("context.") else key)
        if isinstance(cond, dict):
            for op, operand in cond.items():
                if value is None:
                    return False
                ok = {
                    "$gt": lambda: value > operand,
                    "$gte": lambda: value >= operand,
                    "$lt": lambda: value < operand,
                    "$in": lambda: value in operand,
                }[op]()
                if not ok:
                    return False
        elif value != cond:
            return False
    return True


def _entity_ok(
    entity: str, flt: Any, criteria_values: Dict[str, Any], node: bool
) -> bool:
    if flt is None:
        return True
    items = flt if isinstance(flt, list) else [flt]
    if not items and not node:
        return True
    for item in items:
        if isinstance(item, str) and entity == item:
            return True
        if isinstance(item, type):
            if node and issubclass(_NODE_CLASSES[entity], item):
                return True
            if not node and entity == item.__name__:
                return True
        if isinstance(item, dict):
            for name, criteria in item.items():
                if entity == name and _crit_ok(criteria_values, criteria):
                    return True
    return False


async def _reference(
    db: Any, hub_id: str, direction: str, node_f: Any, edge_f: Any, props: Dict
) -> Set[str]:
    edges = await db.find("edge", {})
    nodes = {r["id"]: r for r in await db.find("node", {})}
    out: Set[str] = set()
    for e in edges:
        if not _entity_ok(e["entity"], edge_f, e.get("context", {}), node=False):
            continue
        far = []
        if direction in ("out", "both") and e["source"] == hub_id:
            far.append(e["target"])
        if direction in ("in", "both") and e["target"] == hub_id:
            far.append(e["source"])
        for nid in far:
            rec = nodes.get(nid)
            if rec is None:
                continue
            ctx = rec.get("context", {})
            if _entity_ok(rec["entity"], node_f, ctx, node=True) and _crit_ok(
                ctx, props
            ):
                out.add(nid)
    return out


_EDGE_FILTERS: List[Any] = [
    None,
    QKnows,
    [QKnows],
    "QKnows",
    ["QKnows", "QLikes"],
    [{"QKnows": {"weight": {"$gte": 2}}}],
    [QLikes, {"QKnows": {"weight": {"$gte": 3}}}],
]
_NODE_FILTERS: List[Any] = [
    None,
    QAlpha,
    [QAlpha],
    "QAlpha",
    ["QAlpha", "QBeta"],
    [{"QAlpha": {"score": {"$gt": 1}}}],
    [QBeta, {"QAlpha": {"score": {"$gte": 5}}}],
]
_PROPS: List[Dict[str, Any]] = [{}, {"score": {"$gte": 3}}]


def _type_only(flt: Any) -> bool:
    items = flt if isinstance(flt, list) else [flt]
    return all(not isinstance(i, dict) for i in items)


# ---- tests ------------------------------------------------------------------


async def test_nodes_matches_reference_for_every_filter_shape(graph):
    ctx, db, backend, _ = graph
    n = await _seed()
    hub = n["hub"]
    failures: List[str] = []
    for edge_f, node_f, direction, props in itertools.product(
        _EDGE_FILTERS, _NODE_FILTERS, ("out", "in", "both"), _PROPS
    ):
        expected = await _reference(db, hub.id, direction, node_f, edge_f, props)
        for limit in (None, 1, 5):
            await ctx.clear_cache()
            got = await hub.nodes(
                direction=direction, node=node_f, edge=edge_f, limit=limit, **props
            )
            ids = [x.id for x in got]
            ok = len(ids) == len(set(ids)) and (
                set(ids) == expected
                if limit is None
                else set(ids) <= expected and len(ids) == min(limit, len(expected))
            )
            if isinstance(node_f, type) or (
                isinstance(node_f, list) and node_f and isinstance(node_f[0], type)
            ):
                ok = ok and all(
                    isinstance(x, (QAlpha, QBeta)) for x in got
                )  # hydrated as concrete classes, subclass included
            if not ok:
                failures.append(
                    f"{direction} edge={edge_f!r} node={node_f!r} props={props} "
                    f"limit={limit}: got {sorted(ids)} expected {sorted(expected)}"
                )
        count = await hub.count_nodes(
            direction=direction, node=node_f, edge=edge_f, **props
        )
        if count != len(expected):
            failures.append(
                f"count_nodes {direction} edge={edge_f!r} node={node_f!r} "
                f"props={props}: {count} != {len(expected)}"
            )
    assert not failures, f"{backend}: {len(failures)} mismatches, e.g.\n" + "\n".join(
        failures[:10]
    )


async def test_subclass_filter_hydrates_subclass_instances(graph):
    _ctx, _db, _backend, _ = graph
    n = await _seed()
    got = await n["hub"].nodes(node=QAlpha, direction="out")
    assert {x.id for x in got} == {n["a1"].id, n["a2"].id, n["s1"].id, n["z"].id}
    assert any(type(x) is QAlphaSub for x in got)
    exact = await n["hub"].nodes(node="QAlpha", direction="out")
    assert n["s1"].id not in {x.id for x in exact}


async def test_type_only_queries_are_one_round_trip_on_postgres(graph):
    ctx, db, backend, _ = graph
    if backend != "postgres":
        pytest.skip("round-trip contract is Postgres-specific")
    n = await _seed()
    wrapped = ObservableDatabase(db, slow_query_ms=1e9)
    await ctx.set_database(wrapped)
    hub = n["hub"]
    for edge_f, node_f, direction, limit in itertools.product(
        [f for f in _EDGE_FILTERS if _type_only(f)],
        [f for f in _NODE_FILTERS if _type_only(f)],
        ("out", "in", "both"),
        (None, 3),
    ):
        await ctx.clear_cache()
        token = db_op_counter.set(0)
        try:
            await hub.nodes(direction=direction, node=node_f, edge=edge_f, limit=limit)
            assert db_op_counter.get() == 1, (direction, edge_f, node_f, limit)
            db_op_counter.set(0)
            await hub.count_nodes(direction=direction, node=node_f, edge=edge_f)
            assert db_op_counter.get() == 1, ("count", direction, edge_f, node_f)
        finally:
            db_op_counter.reset(token)


async def test_postgres_join_uses_edge_indexes(graph):
    ctx, db, backend, extras = graph
    if backend != "postgres":
        pytest.skip("EXPLAIN check is Postgres-specific")
    await _seed()  # creates the Edge indexes through the normal save path
    records = []
    for s in range(50):
        src = generate_id("n", "QHub")
        for _ in range(60):
            records.append(
                {
                    "id": generate_id("e", "QKnows"),
                    "entity": "QKnows",
                    "context": {"weight": 1},
                    "source": src,
                    "target": generate_id("n", "QAlpha"),
                    "bidirectional": False,
                }
            )
    await db.bulk_save_detailed("edge", records)
    admin, schema = extras["admin"], extras["schema"]
    await admin.execute(f"ANALYZE {schema}.edge")
    await admin.execute(f"ANALYZE {schema}.node")
    hub_id = records[0]["source"]
    for direction in ("out", "in"):
        sql, params = db._connected_nodes_sql(
            "node",
            "edge",
            hub_id,
            direction=direction,
            edge_entities=["QKnows"],
            node_entities=["QAlpha"],
            limit=20,
        )
        plan = await admin.fetchval(f"EXPLAIN (FORMAT JSON) {sql}", *params)
        plan_json = json.loads(plan) if isinstance(plan, str) else plan

        def _nodes(p: Any) -> List[Dict[str, Any]]:
            found = [p]
            for child in p.get("Plans", []):
                found += _nodes(child)
            return found

        scans = [
            p
            for p in _nodes(plan_json[0]["Plan"])
            if p.get("Node Type") == "Seq Scan" and p.get("Relation Name") == "edge"
        ]
        assert not scans, f"{direction}: sequential scan on edge\n{plan_json}"


async def test_nodes_page_walks_every_neighbour_once(graph):
    ctx, _db, _backend, _ = graph
    hub = await QHub.create(name="hub")
    kids = []
    for i in range(23):
        kid = await QAlpha.create(name=f"n{i:02d}", score=i)
        kids.append(kid)
        await hub.connect(kid, edge=QKnows, weight=i)
    other = await QBeta.create(name="beta")
    await hub.connect(other, edge=QKnows)

    for order in (1, -1):
        seen: List[str] = []
        cursor: Optional[str] = None
        while True:
            page, cursor = await hub.nodes_page(
                node=QAlpha,
                edge=[QKnows],
                sort=[("context.name", order)],
                cursor=cursor,
                limit=5,
            )
            seen += [x.name for x in page]
            if cursor is None:
                break
        assert seen == sorted((k.name for k in kids), reverse=order == -1)


async def test_nodes_page_cursor_is_stable_under_inserts(graph):
    ctx, _db, _backend, _ = graph
    hub = await QHub.create(name="hub")
    for i in range(10):
        await hub.connect(await QAlpha.create(name=f"n{i:02d}"), edge=QKnows)

    first, cursor = await hub.nodes_page(sort=[("context.name", 1)], limit=4)
    assert [x.name for x in first] == ["n00", "n01", "n02", "n03"]
    # One neighbour lands before the cursor, one after.
    await hub.connect(await QAlpha.create(name="n01x"), edge=QKnows)
    await hub.connect(await QAlpha.create(name="n07x"), edge=QKnows)

    rest: List[str] = []
    while cursor:
        page, cursor = await hub.nodes_page(
            sort=[("context.name", 1)], cursor=cursor, limit=4
        )
        rest += [x.name for x in page]
    assert rest == ["n04", "n05", "n06", "n07", "n07x", "n08", "n09"]


async def test_nodes_bulk_limit_per_source(graph):
    _ctx, _db, _backend, _ = graph
    hubs = [await QHub.create(name=f"h{i}") for i in range(3)]
    for hub in hubs:
        for j in range(4):
            await hub.connect(await QAlpha.create(name=f"{hub.name}-{j}"), edge=QKnows)
    capped = await Node.nodes_bulk(
        [h.id for h in hubs], edge=[QKnows], limit_per_source=2
    )
    assert all(len(capped[h.id]) == 2 for h in hubs)
    full = await Node.nodes_bulk([h.id for h in hubs], edge=[QKnows])
    assert all(len(full[h.id]) == 4 for h in hubs)
    assert {x.id for x in capped[hubs[0].id]} <= {x.id for x in full[hubs[0].id]}
