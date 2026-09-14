"""Node adjacency from the edge collection — parity across backends.

Adjacency always lives in the edge collection (indexed on ``source`` /
``target``). Node rows never carry an ``edges`` array. Every scenario runs on
each reachable backend; results must match, and ``connect()`` must never lock
or rewrite a node row.

Postgres runs when ``JVSPATIAL_POSTGRES_TEST_DSN`` is reachable, MongoDB when
``JVSPATIAL_MONGODB_TEST_URI`` is set and reachable; otherwise those params skip.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, Dict, List, Tuple

import pytest

from jvspatial.cli import _run_strip_node_edges, build_parser
from jvspatial.core import context as context_module
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Edge, Node, Root
from jvspatial.core.graph_expansion import expand_node
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.sqlite import SQLiteDB

pytestmark = pytest.mark.asyncio(loop_scope="module")

_PG_DSN = os.getenv(
    "JVSPATIAL_POSTGRES_TEST_DSN",
    "postgresql://jvspatial:jvspatial@localhost:5432/jvspatial",
)
_MONGO_URI = os.getenv("JVSPATIAL_MONGODB_TEST_URI")


class DerivePerson(Node):
    name: str = ""


class DeriveKnows(Edge):
    pass


class DeriveLikes(Edge):
    pass


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


_BACKENDS = ("json", "sqlite", "postgres", "mongodb")


@pytest.fixture(params=_BACKENDS, ids=list(_BACKENDS))
async def graph(request, tmp_path):
    """Yield ``(ctx, db, backend)`` with a fresh database."""
    backend = request.param
    cleanup: List[Any] = []
    if backend == "json":
        db: Any = JsonDB(base_path=str(tmp_path / "json"))
    elif backend == "sqlite":
        db = SQLiteDB(db_path=str(tmp_path / "graph.db"))
    elif backend == "postgres":
        from jvspatial.db.postgres import PostgresDB

        admin = await _pg_admin()
        schema = f"t_derive_{uuid.uuid4().hex[:10]}"
        await admin.execute(f"CREATE SCHEMA {schema}")
        db = PostgresDB(dsn=_PG_DSN, schema_name=schema, min_size=1, max_size=8)

        async def _drop_pg() -> None:
            await admin.execute(f"DROP SCHEMA {schema} CASCADE")
            await admin.close()

        cleanup.append(_drop_pg)
    else:
        from jvspatial.db.mongodb import MongoDB

        client = await _mongo_client()
        name = f"jvs_derive_{uuid.uuid4().hex[:10]}"
        db = MongoDB(uri=_MONGO_URI, db_name=name)

        async def _drop_mongo() -> None:
            await client.drop_database(name)
            client.close()

        cleanup.append(_drop_mongo)

    ctx = GraphContext(database=db)
    set_default_context(ctx)
    context_module._ensured_indexes.clear()
    try:
        yield ctx, db, backend
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


async def _fresh(ctx: GraphContext, node: Node) -> Node:
    """Re-read ``node`` from the database, bypassing the entity cache."""
    await ctx.clear_cache()
    loaded = await ctx.get(type(node), node.id)
    assert loaded is not None
    return loaded


async def _triangle() -> (
    Tuple[DerivePerson, DerivePerson, DerivePerson, Dict[str, str]]
):
    a = await DerivePerson.create(name="a")
    b = await DerivePerson.create(name="b")
    c = await DerivePerson.create(name="c")
    ab = await a.connect(b, edge=DeriveKnows)
    ac = await a.connect(c, edge=DeriveLikes)
    cb = await c.connect(b, edge=DeriveKnows)
    return a, b, c, {"ab": ab.id, "ac": ac.id, "cb": cb.id}


async def _dangling_edges(db: Any) -> List[str]:
    node_ids = {n["id"] for n in await db.find("node", {})}
    return [
        e["id"]
        for e in await db.find("edge", {})
        if e.get("source") not in node_ids or e.get("target") not in node_ids
    ]


async def test_connect_and_read_parity(graph):
    ctx, _db, _backend = graph
    a, b, c, eids = await _triangle()

    assert {e.target for e in await a.edges("out")} == {b.id, c.id}
    assert {e.source for e in await b.edges("in")} == {a.id, c.id}
    assert {e.id for e in await c.edges()} == {eids["ac"], eids["cb"]}
    assert len(await a.edges(limit=1)) == 1

    for node, degree in ((a, 2), (b, 2), (c, 2)):
        assert await node.connection_count() == degree
        assert await (await _fresh(ctx, node)).connection_count() == degree

    a = await _fresh(ctx, a)
    assert {n.id for n in await a.nodes()} == {b.id, c.id}
    assert {n.id for n in await a.nodes(edge=DeriveKnows)} == {b.id}
    assert {n.id for n in await b.nodes(direction="in")} == {a.id, c.id}

    again = await a.connect(b, edge=DeriveKnows)
    assert again.id == eids["ab"]
    assert await a.connection_count() == 2


async def test_disconnect_parity(graph):
    ctx, db, _backend = graph
    a, b, c, eids = await _triangle()

    assert await a.disconnect(b) is True
    assert await db.get("edge", eids["ab"]) is None
    assert await (await _fresh(ctx, a)).connection_count() == 1
    assert await (await _fresh(ctx, b)).connection_count() == 1
    assert {n.id for n in await a.nodes()} == {c.id}


async def test_save_never_writes_edges_array(graph):
    _ctx, db, _backend = graph
    a, _b, _c, _eids = await _triangle()
    a.name = "renamed"
    await a.save()

    raw = await db.get("node", a.id)
    assert raw["context"]["name"] == "renamed"
    assert "edges" not in raw


async def test_connect_takes_no_node_row_lock(graph, monkeypatch):
    _ctx, db, _backend = graph
    hub = await DerivePerson.create(name="hub")
    leaves = [await DerivePerson.create(name=f"l{i}") for i in range(3)]

    node_writes: List[str] = []
    real_save = db.save

    async def _spy_find_one_and_update(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("connect() must not read-modify-write a node row")

    async def _spy_save(collection: str, data: Dict[str, Any]) -> Any:
        if collection == "node":
            node_writes.append(data["id"])
        return await real_save(collection, data)

    monkeypatch.setattr(db, "find_one_and_update", _spy_find_one_and_update)
    monkeypatch.setattr(db, "save", _spy_save)
    for leaf in leaves:
        await hub.connect(leaf, edge=DeriveKnows)
    await asyncio.gather(*(hub.connect(leaf, edge=DeriveLikes) for leaf in leaves))
    await hub.disconnect(leaves[0])

    assert node_writes == []
    assert await hub.connection_count() == 4


async def test_concurrent_connect_to_one_hub(graph):
    ctx, _db, _backend = graph
    hub = await DerivePerson.create(name="hub")
    leaves = [await DerivePerson.create(name=f"l{i}") for i in range(12)]
    await asyncio.gather(*(hub.connect(leaf, edge=DeriveKnows) for leaf in leaves))

    assert await (await _fresh(ctx, hub)).connection_count() == 12
    assert {n.id for n in await hub.nodes()} == {leaf.id for leaf in leaves}


async def test_legacy_edges_array_is_ignored(graph):
    ctx, db, _backend = graph
    a = await DerivePerson.create(name="a")
    b = await DerivePerson.create(name="b")
    await a.connect(b, edge=DeriveKnows)

    raw = await db.get("node", a.id)
    raw["edges"] = ["e.DeriveKnows.stale000000000000000000"]
    await db.save("node", raw)

    legacy = await _fresh(ctx, a)
    assert await legacy.connection_count() == 1
    assert {n.id for n in await legacy.nodes()} == {b.id}

    legacy.name = "resaved"
    await legacy.save()
    assert "edges" not in await db.get("node", a.id)


async def test_cascade_delete_parity(graph):
    ctx, db, _backend = graph
    parent = await DerivePerson.create(name="parent")
    a = await DerivePerson.create(name="a")
    only_via_a = await DerivePerson.create(name="b")
    shared = await DerivePerson.create(name="c")
    outsider = await DerivePerson.create(name="x")
    await parent.connect(a, edge=DeriveKnows)
    await a.connect(only_via_a, edge=DeriveKnows)
    await a.connect(shared, edge=DeriveKnows)
    await outsider.connect(shared, edge=DeriveKnows)

    await a.delete(cascade=True)
    await ctx.clear_cache()

    assert await db.get("node", a.id) is None
    assert await db.get("node", only_via_a.id) is None
    for survivor in (parent, shared, outsider):
        assert await db.get("node", survivor.id) is not None
    assert await (await _fresh(ctx, parent)).connection_count() == 0
    assert await (await _fresh(ctx, shared)).connection_count() == 1
    assert await _dangling_edges(db) == []


async def test_context_delete_without_cascade_removes_edges(graph):
    ctx, db, _backend = graph
    a = await DerivePerson.create(name="a")
    b = await DerivePerson.create(name="b")
    await a.connect(b, edge=DeriveKnows)

    await ctx.delete(a)

    assert await db.get("node", a.id) is None
    assert await (await _fresh(ctx, b)).connection_count() == 0
    assert await _dangling_edges(db) == []


async def test_root_rehydrates(graph):
    _ctx, _db, _backend = graph
    root = await Root.get()
    app = await DerivePerson.create(name="app")
    await root.connect(app, edge=DeriveKnows)

    again = await Root.get()
    assert {n.id for n in await again.nodes()} == {app.id}
    assert await again.connection_count() == 1


async def test_expand_node_pages_from_edge_collection(graph):
    ctx, _db, _backend = graph
    hub = await DerivePerson.create(name="hub")
    kids = [await DerivePerson.create(name=f"k{i}") for i in range(5)]
    for kid in kids:
        await hub.connect(kid, edge=DeriveKnows)

    p1 = await expand_node(ctx, hub.id, limit=2)
    assert p1["pagination"]["total_edge_count"] == 5
    assert p1["pagination"]["has_more"] is True
    assert p1["pagination"]["next_cursor"] == 2
    center = next(n for n in p1["nodes"] if n["id"] == hub.id)
    assert center["degree"] == 5
    assert all(n["degree"] == 1 for n in p1["nodes"] if n["id"] != hub.id)

    seen = [e["id"] for e in p1["edges"]]
    after = p1["pagination"]["next_after"]
    while after:
        page = await expand_node(ctx, hub.id, limit=2, after=after)
        seen += [e["id"] for e in page["edges"]]
        after = page["pagination"]["next_after"]
    assert len(seen) == len(set(seen)) == 5

    offset = await expand_node(ctx, hub.id, limit=10, cursor=4)
    assert offset["pagination"]["returned_edges"] == 1
    assert offset["pagination"]["has_more"] is False


async def test_strip_node_edges_migration(graph):
    ctx, db, backend = graph
    if backend not in ("postgres", "mongodb", "json"):
        pytest.skip("strip_node_edges is implemented on Postgres/MongoDB/JsonDB")
    a, b, c, _eids = await _triangle()
    before = {n.id for n in await a.nodes()}

    # Inject legacy ``edges`` arrays onto existing node rows.
    for node in (a, b, c):
        raw = await db.get("node", node.id)
        raw["edges"] = [f"e.legacy.{node.id}"]
        await db.save("node", raw)
        assert "edges" in await db.get("node", node.id)

    assert await db.strip_node_edges(dry_run=True) == 3
    assert await db.strip_node_edges(batch_size=2) == 3
    assert await db.strip_node_edges() == 0
    for node in (a, b, c):
        assert "edges" not in await db.get("node", node.id)

    fresh_a = await _fresh(ctx, a)
    assert {n.id for n in await fresh_a.nodes()} == before
    assert await fresh_a.connection_count() == 2

    if backend not in ("postgres", "mongodb"):
        return

    # CLI: dry run by default, --apply strips.
    raw = await db.get("node", b.id)
    raw["edges"] = ["e.DeriveKnows.legacy"]
    await db.save("node", raw)
    target = (
        ["--dsn", _PG_DSN, "--schema", db.schema_name]
        if backend == "postgres"
        else ["--dsn", _MONGO_URI, "--db-name", db.db_name]
    )
    parser = build_parser()
    dry = parser.parse_args(["migrate", "strip-node-edges", *target])
    assert await _run_strip_node_edges(dry) == 0
    assert "edges" in await db.get("node", b.id)
    apply = parser.parse_args(["migrate", "strip-node-edges", *target, "--apply"])
    assert await _run_strip_node_edges(apply) == 0
    assert "edges" not in await db.get("node", b.id)
