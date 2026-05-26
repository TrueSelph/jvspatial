"""Integration tests for the Postgres backend.

Requires a live PostgreSQL 14+ instance with the ``vector`` extension
available (PG 15+ recommended). The tests connect via
``JVSPATIAL_POSTGRES_TEST_DSN`` if set; otherwise default to a localhost
container that matches the dev setup
(``postgresql://jvspatial:jvspatial@localhost:5432/jvspatial``).

Each test class isolates itself in a fresh ``tests_<uuid>`` schema so
parallel runs don't collide and a single dropped schema cleans up
everything.

CI usage::

    docker run --rm -d --name pgvector-test -p 5432:5432 \\
        -e POSTGRES_PASSWORD=jvspatial \\
        -e POSTGRES_USER=jvspatial \\
        -e POSTGRES_DB=jvspatial \\
        pgvector/pgvector:pg16
    JVSPATIAL_POSTGRES_TEST_DSN=postgresql://... pytest tests/db/test_postgres_integration.py

Skip when no DSN is reachable so the suite remains runnable on developer
machines without Docker.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, Optional

import pytest

try:
    import asyncpg
except ImportError:  # pragma: no cover - dependency gated below
    asyncpg = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from jvspatial.db.postgres import PostgresDB


pytestmark = pytest.mark.asyncio


# ---- DSN resolution --------------------------------------------------------


def _resolve_dsn() -> Optional[str]:
    """Pick the DSN: env override, otherwise the local dev container."""
    dsn = os.getenv("JVSPATIAL_POSTGRES_TEST_DSN")
    if dsn:
        return dsn
    return "postgresql://jvspatial:jvspatial@localhost:5432/jvspatial"


_DSN = _resolve_dsn()


# ---- isolated schema fixture ----------------------------------------------


@pytest.fixture
async def pg_db() -> AsyncIterator["PostgresDB"]:
    """Per-test PostgresDB scoped to a throwaway schema.

    Probes the DSN on every test (skips on failure) rather than relying
    on a session-scoped probe — pytest-asyncio's per-loop semantics make
    session-scoped async probes fragile.
    """
    if asyncpg is None or _DSN is None:
        pytest.skip("asyncpg not installed or no DSN")
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn=_DSN), timeout=2.0)
    except Exception:
        pytest.skip(
            "Postgres not reachable. Start the dev container or set "
            "JVSPATIAL_POSTGRES_TEST_DSN."
        )

    from jvspatial.db.postgres import PostgresDB

    schema = f"jvs_test_{uuid.uuid4().hex[:12]}"
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
    finally:
        await conn.close()

    db = PostgresDB(dsn=_DSN, schema_name=schema)
    try:
        yield db
    finally:
        try:
            await db.close()
        except RuntimeError:
            # Event loop already closing — best effort.
            pass
        try:
            cleanup = await asyncpg.connect(dsn=_DSN)
            try:
                await cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')
            finally:
                await cleanup.close()
        except Exception:
            # Cleanup is best-effort; the schema is namespaced by uuid
            # so a leak just leaves a junk schema behind.
            pass


# ---- CRUD ------------------------------------------------------------------


class TestPostgresCRUD:
    async def test_save_then_get(self, pg_db: "PostgresDB") -> None:
        rec = {"id": "n.x.1", "entity": "x", "context": {"name": "alpha"}}
        await pg_db.save("node", rec)
        loaded = await pg_db.get("node", "n.x.1")
        assert loaded is not None
        assert loaded["context"]["name"] == "alpha"

    async def test_save_is_upsert(self, pg_db: "PostgresDB") -> None:
        rec: Dict[str, Any] = {"id": "n.x.upsert", "entity": "x", "context": {"v": 1}}
        await pg_db.save("node", rec)
        rec["context"]["v"] = 2
        await pg_db.save("node", rec)
        loaded = await pg_db.get("node", "n.x.upsert")
        assert loaded["context"]["v"] == 2

    async def test_delete_removes(self, pg_db: "PostgresDB") -> None:
        await pg_db.save("node", {"id": "n.x.del", "entity": "x", "context": {}})
        await pg_db.delete("node", "n.x.del")
        assert await pg_db.get("node", "n.x.del") is None

    async def test_save_requires_id(self, pg_db: "PostgresDB") -> None:
        with pytest.raises(ValueError):
            await pg_db.save("node", {"entity": "x"})

    async def test_find_returns_matching(self, pg_db: "PostgresDB") -> None:
        for i in range(5):
            await pg_db.save(
                "node",
                {
                    "id": f"n.x.{i}",
                    "entity": "x",
                    "context": {"tag": "even" if i % 2 == 0 else "odd"},
                },
            )
        out = await pg_db.find("node", {"context.tag": "even"})
        ids = sorted(r["id"] for r in out)
        assert ids == ["n.x.0", "n.x.2", "n.x.4"]

    async def test_count_with_filter(self, pg_db: "PostgresDB") -> None:
        for i in range(10):
            await pg_db.save(
                "node",
                {"id": f"n.x.{i}", "entity": "x", "context": {"k": i}},
            )
        assert await pg_db.count("node") == 10
        assert await pg_db.count("node", {"context.k": {"$gte": 5}}) == 5

    async def test_find_many_bulk(self, pg_db: "PostgresDB") -> None:
        for i in range(3):
            await pg_db.save("node", {"id": f"n.x.{i}", "entity": "x", "context": {}})
        out = await pg_db.find_many("node", ["n.x.0", "n.x.2", "n.x.99"])
        assert set(out.keys()) == {"n.x.0", "n.x.2"}

    async def test_bulk_save_fast_path(self, pg_db: "PostgresDB") -> None:
        records = [
            {"id": f"n.b.{i}", "entity": "b", "context": {"i": i}} for i in range(50)
        ]
        result = await pg_db.bulk_save_detailed("node", records)
        assert result.attempted == 50
        assert result.saved == 50
        assert result.failed_ids == []
        assert await pg_db.count("node") == 50


# ---- Operator pushdown -----------------------------------------------------


class TestPostgresOperators:
    async def test_regex_native(self, pg_db: "PostgresDB") -> None:
        for n in ("alice", "bob", "carol", "alex"):
            await pg_db.save(
                "node",
                {"id": f"n.{n}", "entity": "u", "context": {"name": n}},
            )
        out = await pg_db.find("node", {"context.name": {"$regex": "^al"}})
        names = sorted(r["context"]["name"] for r in out)
        assert names == ["alex", "alice"]

    async def test_elem_match_native(self, pg_db: "PostgresDB") -> None:
        await pg_db.save(
            "node",
            {
                "id": "n.match",
                "entity": "n",
                "context": {
                    "entries": [
                        {"status": "open", "count": 3},
                        {"status": "open", "count": 12},
                        {"status": "closed", "count": 7},
                    ]
                },
            },
        )
        await pg_db.save(
            "node",
            {
                "id": "n.nomatch",
                "entity": "n",
                "context": {"entries": [{"status": "closed", "count": 99}]},
            },
        )
        out = await pg_db.find(
            "node",
            {
                "context.entries": {
                    "$elemMatch": {"status": "open", "count": {"$gt": 10}}
                }
            },
        )
        assert [r["id"] for r in out] == ["n.match"]

    async def test_size_native(self, pg_db: "PostgresDB") -> None:
        await pg_db.save(
            "node", {"id": "n.a", "entity": "n", "context": {"tags": ["x", "y"]}}
        )
        await pg_db.save(
            "node",
            {"id": "n.b", "entity": "n", "context": {"tags": ["x", "y", "z"]}},
        )
        out = await pg_db.find("node", {"context.tags": {"$size": 3}})
        assert [r["id"] for r in out] == ["n.b"]

    async def test_sort_pushdown(self, pg_db: "PostgresDB") -> None:
        for score in (5, 2, 8, 1, 7):
            await pg_db.save(
                "node",
                {"id": f"n.{score}", "entity": "n", "context": {"score": score}},
            )
        out = await pg_db.find("node", {}, sort=[("context.score", 1)])
        assert [r["id"] for r in out] == ["n.1", "n.2", "n.5", "n.7", "n.8"]


# ---- Atomic find_one_and_update --------------------------------------------


class TestPostgresAtomicOps:
    async def test_find_one_and_update_inc(self, pg_db: "PostgresDB") -> None:
        await pg_db.save(
            "node",
            {"id": "n.counter", "entity": "c", "context": {"hits": 0}},
        )
        result = await pg_db.find_one_and_update(
            "node",
            {"_id": "n.counter"},
            {"$inc": {"context.hits": 1}},
        )
        assert result is not None
        assert result["context"]["hits"] == 1
        loaded = await pg_db.get("node", "n.counter")
        assert loaded["context"]["hits"] == 1

    async def test_find_one_and_delete_returns_doc(self, pg_db: "PostgresDB") -> None:
        await pg_db.save("node", {"id": "n.gone", "entity": "x", "context": {"v": 42}})
        out = await pg_db.find_one_and_delete("node", {"_id": "n.gone"})
        assert out is not None
        assert out["context"]["v"] == 42
        assert await pg_db.get("node", "n.gone") is None

    async def test_find_one_and_update_upsert(self, pg_db: "PostgresDB") -> None:
        await pg_db.find_one_and_update(
            "node",
            {"_id": "n.upsert"},
            {"$set": {"context.created": True}},
            upsert=True,
        )
        loaded = await pg_db.get("node", "n.upsert")
        assert loaded is not None
        assert loaded["context"]["created"] is True


# ---- Walker traversal via recursive CTE ------------------------------------


async def _seed_graph(pg_db: "PostgresDB") -> None:
    """Build a small test graph: A → B → C, A → D, D → E."""
    nodes = ["A", "B", "C", "D", "E"]
    for n in nodes:
        await pg_db.save("node", {"id": f"n.{n}", "entity": "n", "context": {}})
    edges = [
        ("ab", "n.A", "n.B"),
        ("bc", "n.B", "n.C"),
        ("ad", "n.A", "n.D"),
        ("de", "n.D", "n.E"),
    ]
    for eid, source, target in edges:
        await pg_db.save(
            "edge",
            {
                "id": f"e.{eid}",
                "entity": "e",
                "context": {},
                "source": source,
                "target": target,
            },
        )


class TestPostgresTraverse:
    async def test_traverse_one_hop_out(self, pg_db: "PostgresDB") -> None:
        await _seed_graph(pg_db)
        out = await pg_db.traverse("edge", "n.A", direction="out", max_depth=1)
        ids = sorted(row["node_id"] for row in out)
        assert ids == ["n.B", "n.D"]

    async def test_traverse_two_hops_out(self, pg_db: "PostgresDB") -> None:
        await _seed_graph(pg_db)
        out = await pg_db.traverse("edge", "n.A", direction="out", max_depth=2)
        ids = sorted(row["node_id"] for row in out)
        # B, C, D, E — all reachable within 2 hops.
        assert ids == ["n.B", "n.C", "n.D", "n.E"]

    async def test_traverse_in_direction(self, pg_db: "PostgresDB") -> None:
        await _seed_graph(pg_db)
        # C has only B as inbound; E has only D as inbound.
        out = await pg_db.traverse("edge", "n.E", direction="in", max_depth=2)
        ids = sorted(row["node_id"] for row in out)
        assert ids == ["n.A", "n.D"]

    async def test_traverse_depth_metadata(self, pg_db: "PostgresDB") -> None:
        await _seed_graph(pg_db)
        out = await pg_db.traverse("edge", "n.A", direction="out", max_depth=3)
        depths = {row["node_id"]: row["depth"] for row in out}
        assert depths["n.B"] == 1
        assert depths["n.D"] == 1
        assert depths["n.C"] == 2
        assert depths["n.E"] == 2


# ---- Multi-tenant RLS ------------------------------------------------------


@pytest.fixture
async def pg_db_rls() -> AsyncIterator["PostgresDB"]:
    """PostgresDB connected as a NON-superuser role.

    RLS is bypassed by superusers and roles with ``BYPASSRLS`` — the
    default test container connects as ``jvspatial`` which is a
    superuser. For RLS tests we create a dedicated unprivileged role,
    grant it access to the test schema, and connect the adapter as
    that role.

    Production deployments MUST follow the same pattern: do not run
    the jvspatial app as a Postgres superuser if you rely on RLS for
    tenant isolation. Document this in postgres-guide.md (C9).
    """
    if asyncpg is None or _DSN is None:
        pytest.skip("asyncpg not installed or no DSN")
    try:
        admin = await asyncio.wait_for(asyncpg.connect(dsn=_DSN), timeout=2.0)
    except Exception:
        pytest.skip("Postgres not reachable")

    from urllib.parse import urlparse, urlunparse

    from jvspatial.db.postgres import PostgresDB

    schema = f"jvs_rls_{uuid.uuid4().hex[:12]}"
    role = f"jvs_rls_role_{uuid.uuid4().hex[:8]}"
    role_pw = "test-rls-pw"
    try:
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        await admin.execute(
            f"CREATE ROLE \"{role}\" WITH LOGIN PASSWORD '{role_pw}' "
            f"NOSUPERUSER NOBYPASSRLS"
        )
        await admin.execute(f'GRANT USAGE, CREATE ON SCHEMA "{schema}" TO "{role}"')
        await admin.execute(f'GRANT ALL ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"')
        await admin.execute(
            f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" '
            f'GRANT ALL ON TABLES TO "{role}"'
        )
    finally:
        await admin.close()

    # Rewrite the DSN to authenticate as the new role.
    parsed = urlparse(_DSN)
    rls_dsn = urlunparse(
        parsed._replace(
            netloc=f"{role}:{role_pw}@{parsed.hostname}:{parsed.port or 5432}"
        )
    )

    db = PostgresDB(dsn=rls_dsn, schema_name=schema)
    try:
        yield db
    finally:
        try:
            await db.close()
        except RuntimeError:
            pass
        try:
            admin = await asyncpg.connect(dsn=_DSN)
            try:
                await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
                await admin.execute(f'DROP ROLE IF EXISTS "{role}"')
            finally:
                await admin.close()
        except Exception:
            pass


class TestPostgresRLS:
    async def test_rls_isolates_tenants(self, pg_db_rls: "PostgresDB") -> None:
        await pg_db_rls.enable_rls("node")

        async with pg_db_rls.tenant("acme"):
            await pg_db_rls.save(
                "node",
                {
                    "id": "n.acme.1",
                    "entity": "n",
                    "tenant_id": "acme",
                    "context": {"name": "acme-row"},
                },
            )

        async with pg_db_rls.tenant("beta"):
            await pg_db_rls.save(
                "node",
                {
                    "id": "n.beta.1",
                    "entity": "n",
                    "tenant_id": "beta",
                    "context": {"name": "beta-row"},
                },
            )

        async with pg_db_rls.tenant("acme"):
            rows = await pg_db_rls.find("node", {})
            ids = [r["id"] for r in rows]
            assert ids == ["n.acme.1"]
            assert await pg_db_rls.get("node", "n.beta.1") is None

        async with pg_db_rls.tenant("beta"):
            rows = await pg_db_rls.find("node", {})
            ids = [r["id"] for r in rows]
            assert ids == ["n.beta.1"]
            assert await pg_db_rls.get("node", "n.acme.1") is None

    async def test_no_tenant_scope_sees_nothing_when_required(
        self, pg_db_rls: "PostgresDB"
    ) -> None:
        await pg_db_rls.enable_rls("node")
        async with pg_db_rls.tenant("acme"):
            await pg_db_rls.save(
                "node",
                {
                    "id": "n.x",
                    "entity": "n",
                    "tenant_id": "acme",
                    "context": {},
                },
            )
        # Without ``tenant(...)`` the GUC is empty; required-mode rejects all.
        assert await pg_db_rls.find("node", {}) == []


# ---- pgvector + hybrid queries --------------------------------------------


class TestPostgresPgvector:
    async def test_enable_vector_column_idempotent(self, pg_db: "PostgresDB") -> None:
        await pg_db.enable_vector_column("doc", "embedding", dim=4)
        # Re-enabling must not raise.
        await pg_db.enable_vector_column("doc", "embedding", dim=4)

    async def test_vector_round_trip(self, pg_db: "PostgresDB") -> None:
        await pg_db.enable_vector_column("doc", "embedding", dim=4)
        await pg_db.save(
            "doc",
            {
                "id": "d.1",
                "entity": "doc",
                "context": {"title": "alpha"},
                "embedding": [1.0, 0.0, 0.0, 0.0],
            },
        )
        # JSONB ``data`` blob preserves the embedding for record_from_row.
        loaded = await pg_db.get("doc", "d.1")
        assert loaded["embedding"] == [1.0, 0.0, 0.0, 0.0]

    async def test_near_ranks_by_cosine_distance(self, pg_db: "PostgresDB") -> None:
        await pg_db.enable_vector_column("doc", "embedding", dim=4)
        await pg_db.save(
            "doc",
            {
                "id": "d.a",
                "entity": "doc",
                "context": {"label": "near"},
                "embedding": [1.0, 0.0, 0.0, 0.0],
            },
        )
        await pg_db.save(
            "doc",
            {
                "id": "d.b",
                "entity": "doc",
                "context": {"label": "mid"},
                "embedding": [0.7, 0.7, 0.0, 0.0],
            },
        )
        await pg_db.save(
            "doc",
            {
                "id": "d.c",
                "entity": "doc",
                "context": {"label": "far"},
                "embedding": [0.0, 0.0, 1.0, 0.0],
            },
        )
        out = await pg_db.find(
            "doc",
            {"embedding": {"$near": [1.0, 0.0, 0.0, 0.0], "$limit": 3}},
        )
        # Cosine distance: d.a closest, then d.b, then d.c.
        assert [r["id"] for r in out] == ["d.a", "d.b", "d.c"]

    async def test_hybrid_jsonb_plus_near(self, pg_db: "PostgresDB") -> None:
        await pg_db.enable_vector_column("doc", "embedding", dim=4)
        for label, eid, vec in [
            ("open", "d.x", [1.0, 0.0, 0.0, 0.0]),
            ("open", "d.y", [0.0, 1.0, 0.0, 0.0]),
            ("closed", "d.z", [1.0, 0.0, 0.0, 0.0]),
        ]:
            await pg_db.save(
                "doc",
                {
                    "id": eid,
                    "entity": "doc",
                    "context": {"status": label},
                    "embedding": vec,
                },
            )
        # Only "open" docs sorted by similarity to [1,0,0,0]. Should
        # return d.x first, then d.y; d.z filtered out by metadata.
        out = await pg_db.find(
            "doc",
            {
                "context.status": "open",
                "embedding": {"$near": [1.0, 0.0, 0.0, 0.0], "$limit": 5},
            },
        )
        assert [r["id"] for r in out] == ["d.x", "d.y"]
