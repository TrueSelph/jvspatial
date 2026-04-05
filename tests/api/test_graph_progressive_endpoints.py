"""HTTP tests for /api/graph/expand and /api/graph/subgraph."""

import asyncio
import tempfile

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.config import ServerConfig
from jvspatial.api.server import Server


@pytest.fixture
def server_with_graph():
    db_path = tempfile.mkdtemp()
    srv = Server(
        config=ServerConfig(
            database=dict(db_type="json", db_path=db_path),
            graph_endpoint_enabled=True,
        )
    )
    db = srv._graph_context.database

    async def seed():
        await db.save(
            "node",
            {
                "id": "n.Root.root",
                "entity": "Root",
                "edges": ["e.1"],
                "context": {"name": "root"},
            },
        )
        await db.save(
            "node",
            {
                "id": "n.Child.c1",
                "entity": "Node",
                "edges": ["e.1"],
                "context": {"title": "child"},
            },
        )
        await db.save(
            "edge",
            {
                "id": "e.1",
                "entity": "Edge",
                "source": "n.Root.root",
                "target": "n.Child.c1",
                "bidirectional": True,
                "context": {},
            },
        )

    asyncio.run(seed())
    srv.app = srv._create_app_instance()
    return srv


def test_graph_expand_endpoint(server_with_graph):
    client = TestClient(server_with_graph.app)
    r = client.get(
        "/api/graph/expand",
        params={"node_id": "n.Root.root", "limit": 10, "cursor": 0},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["found"] is True
    assert "ETag" in r.headers or r.headers.get("etag")
    ids = {n["id"] for n in data["nodes"]}
    assert "n.Root.root" in ids and "n.Child.c1" in ids
    root = next(n for n in data["nodes"] if n["id"] == "n.Root.root")
    assert root["label"] == root["entity"] == "Root"
    assert root["context"].get("name") == "root"
    assert len(data["edges"]) == 1
    e0 = data["edges"][0]
    assert e0["entity"] == e0["label"] == "Edge"
    assert e0["direction"] == "undirected"
    assert e0["context"] == {}


@pytest.fixture
def server_graph_endpoint_disabled():
    db_path = tempfile.mkdtemp()
    srv = Server(
        config=ServerConfig(
            database=dict(db_type="json", db_path=db_path),
            graph_endpoint_enabled=False,
        )
    )
    srv.app = srv._create_app_instance()
    return srv


def test_progressive_routes_absent_when_graph_disabled(server_graph_endpoint_disabled):
    client = TestClient(server_graph_endpoint_disabled.app)
    r = client.get(
        "/api/graph/expand",
        params={"node_id": "n.Root.root", "limit": 10, "cursor": 0},
    )
    assert r.status_code == 404
    root = client.get("/").json()
    assert "graph" not in root
    assert "graph_progressive" not in root


def test_graph_subgraph_endpoint(server_with_graph):
    client = TestClient(server_with_graph.app)
    r = client.get(
        "/api/graph/subgraph",
        params={"root": "n.Root.root", "max_depth": 2, "max_nodes": 20},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["root_id"] == "n.Root.root"
    assert len(data["nodes"]) >= 2
    assert all("context" in n for n in data["nodes"])
    for e in data["edges"]:
        assert "direction" not in e
        assert e["entity"] == e["label"] == "Edge"
