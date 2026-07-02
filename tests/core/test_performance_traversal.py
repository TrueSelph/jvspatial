"""Traversal performance features: neighborhood, walker prefetch, observability."""

from __future__ import annotations

import pytest

from jvspatial.core import on_visit
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities.node import Node
from jvspatial.core.entities.walker import Walker
from jvspatial.db._observable import ObservableDatabase
from jvspatial.db.jsondb import JsonDB
from jvspatial.observability import db_op_counter


@pytest.fixture
async def graph_context(tmp_path):
    db = JsonDB(base_path=str(tmp_path))
    ctx = GraphContext(database=db)
    set_default_context(ctx)
    yield ctx


async def _seed_small_tree(ctx: GraphContext) -> Node:
    root = Node(id="n.root")
    a = Node(id="n.a")
    b = Node(id="n.b")
    c = Node(id="n.c")
    for node in (root, a, b, c):
        await ctx.save(node)
    await root.connect(a)
    await a.connect(b)
    await a.connect(c)
    reloaded = await ctx.get(Node, root.id)
    assert reloaded is not None
    return reloaded


@pytest.mark.asyncio
async def test_default_walker_visit_order_unchanged(graph_context):
    root = await _seed_small_tree(graph_context)

    class GraphWalker(Walker):
        visited_nodes: list[str] = []

        @on_visit()
        async def visit_node(self, node):
            self.visited_nodes.append(node.id)
            for connected in await node.nodes(direction="out"):
                if (
                    connected.id not in self.visited_nodes
                    and connected not in self.queue._backing
                ):
                    await self.queue.append([connected])

    walker = GraphWalker()
    await walker.spawn(root)
    assert walker.visited_nodes[0] == "n.root"
    assert walker.visited_nodes[1] == "n.a"
    assert set(walker.visited_nodes[2:]) == {"n.b", "n.c"}


@pytest.mark.asyncio
async def test_neighborhood_bfs_fallback(graph_context):
    root = await _seed_small_tree(graph_context)
    hood = await root.neighborhood(2, direction="out")
    ids = sorted(n.id for n in hood)
    assert ids == ["n.a", "n.b", "n.c"]


@pytest.mark.asyncio
async def test_walker_prefetch_neighbors_smoke(graph_context):
    root = await _seed_small_tree(graph_context)

    class PrefetchWalker(Walker):
        def __init__(self):
            super().__init__(prefetch_neighbors=True, frontier_batch_size=2)
            self.visited_nodes: list[str] = []

        @on_visit()
        async def visit_node(self, node):
            self.visited_nodes.append(node.id)

    walker = PrefetchWalker()
    await walker.spawn(root)
    assert set(walker.visited_nodes) == {"n.root", "n.a", "n.b", "n.c"}


@pytest.mark.asyncio
async def test_observable_traverse_increments_counter():
    from unittest.mock import AsyncMock, MagicMock

    inner = MagicMock()
    inner.supports_transactions = False
    inner.traverse = AsyncMock(return_value=[{"node_id": "n.y", "depth": 1}])
    wrapped = ObservableDatabase(inner)
    tok = db_op_counter.set(0)
    try:
        await wrapped.traverse("edge", "n.x", max_depth=2)
        assert db_op_counter.get() == 1
        inner.traverse.assert_awaited_once()
    finally:
        db_op_counter.reset(tok)
