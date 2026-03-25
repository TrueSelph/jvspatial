"""Node.save via GraphContext merges persisted edges with in-memory export.

Prevents lost updates when edge IDs were added via atomic_add_edge_id or another
writer but the in-memory instance still has a stale edge_ids list.
"""

import asyncio
import tempfile

import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Node
from jvspatial.db.jsondb import JsonDB


class Widget(Node):
    """Minimal node for persistence tests."""

    name: str = ""


@pytest.fixture
async def graph_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = JsonDB(base_path=tmpdir)
        ctx = GraphContext(database=db)
        set_default_context(ctx)
        yield ctx, db


@pytest.mark.asyncio
async def test_save_merges_db_only_edges_into_record(graph_context):
    ctx, db = graph_context
    w = await Widget.create(name="a")
    assert w.edge_ids == []

    raw = await db.get("node", w.id)
    assert raw is not None
    raw["edges"] = ["e.only.on.disk"]
    await db.save("node", raw)

    assert w.edge_ids == []
    w.name = "b"
    await ctx.save(w)

    raw_after = await db.get("node", w.id)
    assert raw_after is not None
    assert set(raw_after.get("edges") or []) == {"e.only.on.disk"}
    assert set(w.edge_ids) == {"e.only.on.disk"}


@pytest.mark.asyncio
async def test_save_unions_in_memory_and_db_edges(graph_context):
    ctx, db = graph_context
    w = await Widget.create(name="a")
    w.edge_ids = ["e.mem"]
    await ctx.save(w)

    raw = await db.get("node", w.id)
    raw["edges"] = list(set(raw.get("edges") or []) | {"e.db"})
    await db.save("node", raw)

    w.edge_ids = ["e.mem"]
    w.name = "b"
    await ctx.save(w)

    raw_after = await db.get("node", w.id)
    assert set(raw_after.get("edges") or []) == {"e.mem", "e.db"}


@pytest.mark.asyncio
async def test_concurrent_save_and_atomic_add_preserves_atomic_edges(graph_context):
    ctx, db = graph_context
    w = await Widget.create(name="c")
    n_atomic = 15

    async def touch_save():
        for i in range(20):
            w.name = f"t{i}"
            await ctx.save(w)
            await asyncio.sleep(0)

    async def add_edges():
        for i in range(n_atomic):
            await ctx.atomic_add_edge_id(w.id, f"e.atomic.{i}")
            await asyncio.sleep(0)

    await asyncio.gather(touch_save(), add_edges())

    raw = await db.get("node", w.id)
    assert raw is not None
    edges = set(raw.get("edges") or [])
    for i in range(n_atomic):
        assert f"e.atomic.{i}" in edges, f"missing e.atomic.{i} after concurrent ops"
