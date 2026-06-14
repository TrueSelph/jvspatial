"""Tests for the graph invariant validator.

Builds tiny graphs against a JsonDB context and asserts that
:func:`validate_graph` correctly reports orphans, dangling edges, and
root cycles.
"""

from __future__ import annotations

import tempfile
from typing import Any, AsyncIterator

import pytest

from jvspatial.core.context import GraphContext
from jvspatial.core.validate import ValidationReport, validate_graph
from jvspatial.db.jsondb import JsonDB

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def ctx() -> AsyncIterator[GraphContext]:
    with tempfile.TemporaryDirectory() as tmp:
        yield GraphContext(database=JsonDB(base_path=tmp))


async def _node(ctx: GraphContext, nid: str, entity: str = "AppNode") -> None:
    await ctx.database.save(
        "node",
        {"id": nid, "entity": entity, "context": {}},
    )


async def _edge(
    ctx: GraphContext,
    eid: str,
    source: str,
    target: str,
    *,
    bidirectional: bool = False,
) -> None:
    await ctx.database.save(
        "edge",
        {
            "id": eid,
            "entity": "Edge",
            "source": source,
            "target": target,
            "bidirectional": bidirectional,
            "context": {},
        },
    )


class TestValidateGraph:
    async def test_empty_graph_is_ok(self, ctx: GraphContext) -> None:
        report = await validate_graph(context=ctx)
        assert report.ok
        assert report.nodes_visited == 0

    async def test_well_formed_graph_passes(self, ctx: GraphContext) -> None:
        # Root → AppRoot → User
        await _node(ctx, "n.Root.1", entity="Root")
        await _node(ctx, "n.App.1", entity="App")
        await _node(ctx, "n.User.1")
        await _edge(ctx, "e.1", "n.Root.1", "n.App.1")
        await _edge(ctx, "e.2", "n.App.1", "n.User.1")

        report = await validate_graph(context=ctx)
        assert report.ok, report.summary()
        assert report.nodes_visited == 3
        assert report.edges_visited == 2

    async def test_detects_orphan_node(self, ctx: GraphContext) -> None:
        await _node(ctx, "n.Root.1", entity="Root")
        await _node(ctx, "n.Reachable")
        await _node(ctx, "n.Orphan")  # never connected
        await _edge(ctx, "e.1", "n.Root.1", "n.Reachable")

        report = await validate_graph(context=ctx)
        assert not report.ok
        assert report.orphan_node_ids == ["n.Orphan"]

    async def test_bidirectional_edge_counts_as_reachable(
        self, ctx: GraphContext
    ) -> None:
        # Edge goes Child → Root with bidirectional=True. Validator
        # must still consider Child reachable.
        await _node(ctx, "n.Root.1", entity="Root")
        await _node(ctx, "n.Child")
        await _edge(ctx, "e.1", "n.Child", "n.Root.1", bidirectional=True)

        report = await validate_graph(context=ctx)
        assert report.ok, report.summary()

    async def test_detects_dangling_edge_missing_target(
        self, ctx: GraphContext
    ) -> None:
        await _node(ctx, "n.Root.1", entity="Root")
        await _node(ctx, "n.A")
        await _edge(ctx, "e.bad", "n.A", "n.nonexistent")

        report = await validate_graph(context=ctx)
        assert "e.bad" in report.dangling_edge_ids
        assert not report.ok

    async def test_detects_dangling_edge_missing_source(
        self, ctx: GraphContext
    ) -> None:
        await _node(ctx, "n.Root.1", entity="Root")
        await _node(ctx, "n.A")
        await _edge(ctx, "e.bad", "n.does-not-exist", "n.A")

        report = await validate_graph(context=ctx)
        assert "e.bad" in report.dangling_edge_ids

    async def test_dangling_edge_check_can_be_disabled(self, ctx: GraphContext) -> None:
        await _node(ctx, "n.Root.1", entity="Root")
        await _node(ctx, "n.A")
        await _edge(ctx, "e.bad", "n.A", "n.nonexistent")

        report = await validate_graph(context=ctx, check_dangling_edges=False)
        assert report.dangling_edge_ids == []

    async def test_detects_cycle_through_root(self, ctx: GraphContext) -> None:
        # Root → A → B → Root creates a cycle. A and B both end up in
        # the cycle list (they each have a path back through Root).
        await _node(ctx, "n.Root.1", entity="Root")
        await _node(ctx, "n.A")
        await _node(ctx, "n.B")
        await _edge(ctx, "e.1", "n.Root.1", "n.A")
        await _edge(ctx, "e.2", "n.A", "n.B")
        await _edge(ctx, "e.3", "n.B", "n.Root.1")

        report = await validate_graph(context=ctx)
        assert "n.A" in report.root_cycle_node_ids
        assert not report.ok

    async def test_summary_renders(self, ctx: GraphContext) -> None:
        await _node(ctx, "n.Root.1", entity="Root")
        await _node(ctx, "n.lost")  # orphan
        report = await validate_graph(context=ctx)
        assert "1 orphan" in report.summary()

    async def test_ok_report_summary(self, ctx: GraphContext) -> None:
        await _node(ctx, "n.Root.1", entity="Root")
        report = await validate_graph(context=ctx)
        assert "graph OK" in report.summary()
