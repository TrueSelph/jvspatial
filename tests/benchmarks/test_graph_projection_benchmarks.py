"""Warm capture regression benchmarks on the realistic dummy graph."""

import asyncio

import pytest

from examples.core.graph_projection_example import (
    DEMO_SEMANTICS,
    PublicDemoAccess,
    demo_scope,
    seed_demo,
)
from jvspatial import GraphContext, ProjectionRequest
from jvspatial.db.sqlite import SQLiteDB


@pytest.mark.benchmark
@pytest.mark.parametrize("view", ["relationships", "hierarchy", "ontology"])
def test_warm_projection_capture(benchmark, view):
    loop = asyncio.new_event_loop()
    db = SQLiteDB(db_path=":memory:")
    ctx = GraphContext(db)
    try:
        objects, _ = loop.run_until_complete(seed_demo(ctx))
        request = ProjectionRequest(
            root_id=objects["harbor"].id,
            view=view,
            max_depth=4,
            edge_types=("DependsOn", "SuppliedBy", "LocatedIn", "AlternativeTo"),
            max_bytes=65536,
            execution_mode="native",
        )

        def capture():
            return loop.run_until_complete(
                ctx.project_graph(
                    request,
                    scope=demo_scope(),
                    access=PublicDemoAccess(),
                    semantics=DEMO_SEMANTICS,
                )
            )

        capture()  # warm initialization outside benchmark samples
        result = benchmark(capture)
        assert len(result.to_dict()["nodes"]) == 9
        assert len(result.to_dict()["edges"]) == 10
        assert result.to_dict()["meta"]["complete"]
    finally:
        loop.run_until_complete(db.close())
        loop.close()


@pytest.mark.benchmark
@pytest.mark.parametrize("view", ["relationships", "hierarchy", "ontology"])
def test_warm_rich_projection_capture(benchmark, view):
    from examples.core.rich_graph_context_example import (
        capture_demo,
    )
    from examples.core.rich_graph_context_example import seed_demo as seed_rich

    loop = asyncio.new_event_loop()
    db = SQLiteDB(db_path=":memory:")
    context = GraphContext(db)
    try:
        records = loop.run_until_complete(seed_rich(context))

        def capture():
            return loop.run_until_complete(
                capture_demo(context, records, view=view, execution_mode="native")
            )

        capture()
        result = benchmark(capture)
        assert len(result.to_dict()["nodes"]) == 6
        assert len(result.to_dict()["edges"]) == 7
        assert result.to_dict()["meta"]["complete"]
        assert result.to_dict()["format_version"] == 2
    finally:
        loop.run_until_complete(db.close())
        loop.close()
