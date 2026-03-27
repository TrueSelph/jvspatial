"""Tests for progressive graph payload and bounded expansion."""

import tempfile

import pytest

from jvspatial.core.context import GraphContext
from jvspatial.core.graph_expansion import expand_node, subgraph_bfs
from jvspatial.db.jsondb import JsonDB


def _node(nid: str, edges: list, entity: str = "Node", **ctx) -> dict:
    return {
        "id": nid,
        "entity": entity,
        "edges": edges,
        "context": dict(ctx),
    }


def _edge(eid: str, src: str, tgt: str, bidirectional: bool = True) -> dict:
    return {
        "id": eid,
        "entity": "Edge",
        "source": src,
        "target": tgt,
        "bidirectional": bidirectional,
        "context": {},
    }


@pytest.fixture
async def graph_ctx():
    tmp = tempfile.mkdtemp()
    db = JsonDB(base_path=tmp)
    ctx = GraphContext(database=db)
    return ctx


@pytest.mark.asyncio
async def test_expand_node_returns_neighbors_and_pagination(graph_ctx: GraphContext):
    db = graph_ctx.database
    await db.save("node", _node("n.Root.root", ["e.1", "e.2"], Root=True, name="root"))
    await db.save("node", _node("n.A.a1", [], name="a"))
    await db.save("node", _node("n.B.b1", [], name="b"))
    await db.save("edge", _edge("e.1", "n.Root.root", "n.A.a1"))
    await db.save("edge", _edge("e.2", "n.Root.root", "n.B.b1"))

    out = await expand_node(graph_ctx, "n.Root.root", limit=10, cursor=0)
    assert out["found"] is True
    assert out["pagination"]["total_edge_count"] == 2
    assert out["pagination"]["has_more"] is False
    ids = {n["id"] for n in out["nodes"]}
    assert ids == {"n.Root.root", "n.A.a1", "n.B.b1"}
    assert len(out["edges"]) == 2


@pytest.mark.asyncio
async def test_expand_node_pagination_cursor(graph_ctx: GraphContext):
    db = graph_ctx.database
    edges = [f"e.{i}" for i in range(5)]
    await db.save("node", _node("n.Hub.h", edges))
    for i in range(5):
        await db.save(
            "node",
            _node(f"n.T.{i}", [], entity="T"),
        )
        await db.save(
            "edge",
            _edge(f"e.{i}", "n.Hub.h", f"n.T.{i}"),
        )

    p1 = await expand_node(graph_ctx, "n.Hub.h", limit=2, cursor=0)
    assert p1["pagination"]["has_more"] is True
    assert p1["pagination"]["next_cursor"] == 2
    assert p1["pagination"]["returned_edges"] == 2

    p2 = await expand_node(graph_ctx, "n.Hub.h", limit=2, cursor=2)
    assert p2["pagination"]["next_cursor"] == 4
    assert len(p2["edges"]) == 2

    p3 = await expand_node(graph_ctx, "n.Hub.h", limit=10, cursor=4)
    assert p3["pagination"]["has_more"] is False
    assert len(p3["edges"]) == 1


@pytest.mark.asyncio
async def test_expand_node_direction_out(graph_ctx: GraphContext):
    db = graph_ctx.database
    await db.save("node", _node("n.S.s", ["e.out", "e.in"]))
    await db.save("node", _node("n.T.t", []))
    await db.save(
        "edge",
        _edge("e.out", "n.S.s", "n.T.t", bidirectional=False),
    )
    await db.save(
        "edge",
        _edge("e.in", "n.T.t", "n.S.s", bidirectional=False),
    )

    out_both = await expand_node(graph_ctx, "n.S.s", direction="both")
    assert len(out_both["edges"]) == 2

    out_out = await expand_node(graph_ctx, "n.S.s", direction="out")
    assert len(out_out["edges"]) == 1
    assert out_out["edges"][0]["id"] == "e.out"


@pytest.mark.asyncio
async def test_expand_missing_node(graph_ctx: GraphContext):
    out = await expand_node(graph_ctx, "n.Missing.x", limit=10, cursor=0)
    assert out["found"] is False
    assert out["nodes"] == []


@pytest.mark.asyncio
async def test_subgraph_bfs_depth_and_max_nodes(graph_ctx: GraphContext):
    db = graph_ctx.database
    await db.save("node", _node("n.R.r", ["e1"]))
    await db.save("node", _node("n.A.a", ["e2"]))
    await db.save("node", _node("n.B.b", []))
    await db.save("edge", _edge("e1", "n.R.r", "n.A.a"))
    await db.save("edge", _edge("e2", "n.A.a", "n.B.b"))

    sub = await subgraph_bfs(
        graph_ctx, "n.R.r", max_depth=1, max_nodes=50, max_edges_per_node=50
    )
    ids = {n["id"] for n in sub["nodes"]}
    assert ids == {"n.R.r", "n.A.a"}
    assert len(sub["edges"]) == 1

    sub2 = await subgraph_bfs(
        graph_ctx, "n.R.r", max_depth=2, max_nodes=50, max_edges_per_node=50
    )
    ids2 = {n["id"] for n in sub2["nodes"]}
    assert ids2 == {"n.R.r", "n.A.a", "n.B.b"}
    assert sub2["meta"]["truncated"] is False


@pytest.mark.asyncio
async def test_subgraph_bfs_max_nodes_truncated(graph_ctx: GraphContext):
    db = graph_ctx.database
    await db.save("node", _node("n.R.r", ["e1", "e2"]))
    await db.save("node", _node("n.A.a", []))
    await db.save("node", _node("n.B.b", []))
    await db.save("edge", _edge("e1", "n.R.r", "n.A.a"))
    await db.save("edge", _edge("e2", "n.R.r", "n.B.b"))

    sub = await subgraph_bfs(
        graph_ctx, "n.R.r", max_depth=2, max_nodes=2, max_edges_per_node=50
    )
    assert sub["meta"]["node_count"] <= 2
    assert sub["meta"]["truncated"] is True


@pytest.mark.asyncio
async def test_node_label_is_entity_class_name(graph_ctx: GraphContext):
    db = graph_ctx.database
    await db.save(
        "node",
        _node("n.Custom.c1", [], entity="MyEntity", title="should not appear in label"),
    )
    out = await expand_node(graph_ctx, "n.Custom.c1", limit=5, cursor=0)
    assert out["found"] is True
    n0 = out["nodes"][0]
    assert n0["entity"] == "MyEntity"
    assert n0["label"] == "MyEntity"
    assert "context" in n0
    assert n0["context"].get("title") == "should not appear in label"


@pytest.mark.asyncio
async def test_expand_edge_entity_label_direction(graph_ctx: GraphContext):
    db = graph_ctx.database
    await db.save("node", _node("n.C.c", ["e.bi", "e.out", "e.in"]))
    await db.save("node", _node("n.X.x", []))
    await db.save("node", _node("n.Y.y", []))
    await db.save(
        "edge",
        {
            "id": "e.bi",
            "entity": "RelatesTo",
            "source": "n.C.c",
            "target": "n.X.x",
            "bidirectional": True,
            "context": {"k": "v"},
        },
    )
    await db.save(
        "edge",
        _edge("e.out", "n.C.c", "n.X.x", bidirectional=False),
    )
    await db.save(
        "edge",
        _edge("e.in", "n.Y.y", "n.C.c", bidirectional=False),
    )

    out = await expand_node(
        graph_ctx, "n.C.c", limit=10, cursor=0, detail_level="summary"
    )
    by_id = {e["id"]: e for e in out["edges"]}
    assert by_id["e.bi"]["entity"] == "RelatesTo"
    assert by_id["e.bi"]["label"] == "RelatesTo"
    assert by_id["e.bi"]["direction"] == "undirected"
    assert "context" not in by_id["e.bi"]

    assert by_id["e.out"]["entity"] == "Edge"
    assert by_id["e.out"]["direction"] == "outgoing"
    assert by_id["e.in"]["direction"] == "incoming"


@pytest.mark.asyncio
async def test_subgraph_edges_have_no_direction(graph_ctx: GraphContext):
    db = graph_ctx.database
    await db.save("node", _node("n.R.r", ["e1"]))
    await db.save("node", _node("n.A.a", []))
    await db.save("edge", _edge("e1", "n.R.r", "n.A.a"))

    sub = await subgraph_bfs(graph_ctx, "n.R.r", max_depth=2, max_nodes=50)
    e0 = sub["edges"][0]
    assert "direction" not in e0
    assert e0["entity"] == "Edge"
    assert e0["label"] == "Edge"


@pytest.mark.asyncio
async def test_summary_omits_context_on_nodes_and_edges(graph_ctx: GraphContext):
    db = graph_ctx.database
    await db.save("node", _node("n.A.a", ["e1"], entity="A", foo="bar"))
    await db.save("node", _node("n.B.b", []))
    await db.save(
        "edge",
        {
            "id": "e1",
            "entity": "Link",
            "source": "n.A.a",
            "target": "n.B.b",
            "bidirectional": True,
            "context": {"x": 1},
        },
    )
    out = await expand_node(graph_ctx, "n.A.a", detail_level="summary")
    for n in out["nodes"]:
        assert "context" not in n
    for e in out["edges"]:
        assert "context" not in e
        assert e["direction"] in ("undirected", "outgoing", "incoming", "loop")
