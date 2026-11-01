"""Shallow node deletion must not explore the rest of a rooted graph."""

import os

import pytest

from jvspatial.core import Edge, Node, Root
from jvspatial.core.context import (
    GraphContext,
    graph_transaction,
    scoped_default_context_async,
)
from jvspatial.db.factory import create_database


class ShallowDeletionNode(Node):
    label: str = ""


class ShallowDeletionEdge(Edge):
    role: str = ""


@pytest.mark.parametrize(
    "backend", ["json", "sqlite", "postgres", "postgres_transaction"]
)
@pytest.mark.parametrize("other_records", [1, 40])
async def test_shallow_delete_reads_only_incident_edges(
    tmp_path, monkeypatch, backend, other_records
):
    """A shared author cycle must not turn a record delete into a graph scan."""
    if backend.startswith("postgres"):
        dsn = os.environ.get("JVSPATIAL_SHALLOW_DELETE_TEST_DSN")
        if not dsn:
            pytest.skip("Set JVSPATIAL_SHALLOW_DELETE_TEST_DSN for PostgreSQL")
        database = create_database("postgres", dsn=dsn)
    elif backend == "sqlite":
        database = create_database("sqlite", db_path=str(tmp_path / "graph.db"))
    else:
        database = create_database("json", base_path=str(tmp_path / "graph"))
    try:
        scope = (
            graph_transaction(database)
            if backend == "postgres_transaction"
            else scoped_default_context_async(GraphContext(database=database))
        )
        async with scope as ctx:
            root = await Root.get()
            app = await ShallowDeletionNode.create(label="Application")
            await root.connect(app, edge=ShallowDeletionEdge, role="application")
            record = await ShallowDeletionNode.create(label="Disposable record")
            incoming = await app.connect(
                record, edge=ShallowDeletionEdge, role="contains"
            )
            author = await ShallowDeletionNode.create(label="Shared author")
            await app.connect(author, edge=ShallowDeletionEdge, role="member")
            outgoing = await record.connect(
                author, edge=ShallowDeletionEdge, role="authored_by"
            )
            retained = await author.connect(app, edge=ShallowDeletionEdge, role="owns")
            children = []
            for index in range(other_records):
                child = await ShallowDeletionNode.create(label=f"Other record {index}")
                await app.connect(child, edge=ShallowDeletionEdge, role="contains")
                children.append(child)
            visited_sources = []
            original = ctx.find_edges_between

            async def incident_only(source_id=None, target_id=None, **kwargs):
                visited_sources.append(source_id)
                assert source_id == record.id, "Shallow deletion explored a neighbour"
                return await original(
                    source_id=source_id, target_id=target_id, **kwargs
                )

            monkeypatch.setattr(ctx, "find_edges_between", incident_only)
            await record.delete(cascade=False)
            assert visited_sources == [record.id]
            assert await ctx.database.get("node", record.id) is None
            assert await ctx.database.get("edge", incoming.id) is None
            assert await ctx.database.get("edge", outgoing.id) is None
            stored = await ctx.database.get("edge", retained.id)
            assert stored["context"]["role"] == "owns"
            for node in (app, author, *children):
                assert await ctx.database.get("node", node.id) is not None
        async with scoped_default_context_async(GraphContext(database=database)):
            assert await ShallowDeletionNode.get(record.id) is None
    finally:
        close = getattr(database, "close", None)
        if close is not None:
            await close()
