"""Tenant isolation (row-level security) across the Postgres graph paths.

RLS policies apply per table, so a join sees only the edges *and* the nodes
the active tenant may read. Two tenants share one hub id: ``acme`` owns the
hub and two leaves; ``beta`` owns an edge from that hub id to its own leaf.
Every read and write path must honour ``PostgresDB.tenant(...)`` — including
the ones that manage their own connection or transaction.

Runs as an unprivileged role (superusers bypass RLS) when
``JVSPATIAL_POSTGRES_TEST_DSN`` is reachable.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import Any, AsyncIterator, Dict
from urllib.parse import urlparse, urlunparse

import pytest

pytestmark = pytest.mark.asyncio(loop_scope="module")

_DSN = os.getenv(
    "JVSPATIAL_POSTGRES_TEST_DSN",
    "postgresql://jvspatial:jvspatial@localhost:5432/jvspatial",
)

HUB = "n.Hub.h"


@pytest.fixture
async def rls_db() -> AsyncIterator[Any]:
    """PostgresDB as a NOSUPERUSER NOBYPASSRLS role, RLS on node and edge."""
    try:
        import asyncpg

        from jvspatial.db.postgres import PostgresDB
    except ImportError:
        pytest.skip("asyncpg not installed")
    try:
        admin = await asyncio.wait_for(asyncpg.connect(dsn=_DSN), timeout=2.0)
    except Exception:
        pytest.skip(f"Postgres unreachable at {_DSN}")
    schema = f"jvs_tgraph_{uuid.uuid4().hex[:10]}"
    role = f"jvs_tgraph_{uuid.uuid4().hex[:8]}"
    await admin.execute(f'CREATE SCHEMA "{schema}"')
    await admin.execute(
        f"CREATE ROLE \"{role}\" WITH LOGIN PASSWORD 'tgraph-pw' "
        "NOSUPERUSER NOBYPASSRLS"
    )
    await admin.execute(f'GRANT USAGE, CREATE ON SCHEMA "{schema}" TO "{role}"')
    parsed = urlparse(_DSN)
    dsn = urlunparse(
        parsed._replace(
            netloc=f"{role}:tgraph-pw@{parsed.hostname}:{parsed.port or 5432}"
        )
    )
    db = PostgresDB(dsn=dsn, schema_name=schema, min_size=1, max_size=4)
    try:
        await db.enable_rls("node")
        await db.enable_rls("edge")
        await _seed(db)
        yield db
    finally:
        await db.close()
        await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
        await admin.execute(f'DROP ROLE IF EXISTS "{role}"')
        await admin.close()


def _node(nid: str, tenant: str, **ctx: Any) -> Dict[str, Any]:
    return {"id": nid, "entity": nid.split(".")[1], "tenant_id": tenant, "context": ctx}


def _edge(eid: str, src: str, tgt: str, tenant: str) -> Dict[str, Any]:
    return {
        "id": eid,
        "entity": "Link",
        "tenant_id": tenant,
        "context": {},
        "source": src,
        "target": tgt,
        "bidirectional": False,
    }


async def _seed(db: Any) -> None:
    async with db.tenant("acme"):
        for rec in (
            _node(HUB, "acme"),
            _node("n.Leaf.a1", "acme"),
            _node("n.Leaf.a2", "acme"),
        ):
            await db.save("node", rec)
        for rec in (
            _edge("e.Link.a1", HUB, "n.Leaf.a1", "acme"),
            _edge("e.Link.a2", HUB, "n.Leaf.a2", "acme"),
        ):
            await db.save("edge", rec)
    async with db.tenant("beta"):
        await db.save("node", _node("n.Leaf.b1", "beta"))
        await db.save("edge", _edge("e.Link.b1", HUB, "n.Leaf.b1", "beta"))


async def _ids(rows: Any) -> set:
    return {r["id"] for r in rows}


async def test_neighbour_joins_see_only_the_tenant(rls_db):
    for tenant, expected in (
        ("acme", {"n.Leaf.a1", "n.Leaf.a2"}),
        ("beta", {"n.Leaf.b1"}),
    ):
        async with rls_db.tenant(tenant):
            for kwargs in ({}, {"edge_entities": ["Link"]}, {"direction": "both"}):
                rows = await rls_db.find_connected_nodes("node", "edge", HUB, **kwargs)
                assert await _ids(rows) == expected, (tenant, kwargs)
                assert await rls_db.count_connected_nodes(
                    "node", "edge", HUB, **kwargs
                ) == len(expected)
            bulk = await rls_db.find_connected_nodes_bulk("node", "edge", [HUB])
            assert await _ids(bulk[HUB]) == expected
    assert await rls_db.find_connected_nodes("node", "edge", HUB) == []


async def test_traverse_sees_only_the_tenant(rls_db):
    async with rls_db.tenant("acme"):
        hops = await rls_db.traverse("edge", HUB, max_depth=2)
        assert {h["node_id"] for h in hops} == {"n.Leaf.a1", "n.Leaf.a2"}
    async with rls_db.tenant("beta"):
        hops = await rls_db.traverse("edge", HUB, max_depth=2)
        assert {h["node_id"] for h in hops} == {"n.Leaf.b1"}


async def test_atomic_ops_respect_the_tenant(rls_db):
    async with rls_db.tenant("acme"):
        doc = await rls_db.find_one_and_update(
            "node", {"_id": "n.Leaf.a1"}, {"$set": {"context.seen": True}}
        )
        assert doc is not None and doc["context"]["seen"] is True
    async with rls_db.tenant("beta"):
        assert (
            await rls_db.find_one_and_update(
                "node", {"_id": "n.Leaf.a1"}, {"$set": {"context.seen": False}}
            )
            is None
        )
        assert await rls_db.find_one_and_delete("node", {"_id": "n.Leaf.a2"}) is None
    async with rls_db.tenant("acme"):
        assert (await rls_db.get("node", "n.Leaf.a1"))["context"]["seen"] is True
        deleted = await rls_db.find_one_and_delete("node", {"_id": "n.Leaf.a2"})
        assert deleted is not None and deleted["id"] == "n.Leaf.a2"


async def test_bulk_save_writes_within_the_tenant(rls_db):
    async with rls_db.tenant("acme"):
        result = await rls_db.bulk_save_detailed(
            "node", [_node(f"n.Leaf.bulk{i}", "acme") for i in range(3)]
        )
        assert result.all_saved
        assert {"n.Leaf.bulk0", "n.Leaf.bulk2"} <= await _ids(
            await rls_db.find("node", {})
        )
    async with rls_db.tenant("beta"):
        assert await rls_db.get("node", "n.Leaf.bulk0") is None
