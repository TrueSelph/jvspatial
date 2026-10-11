"""Tests for cursor pagination (``Database.find_iter``).

Covers:

* ``encode_cursor`` / ``decode_cursor`` round trip + invalid-cursor handling.
* Base-class default ``find_iter`` (using JsonDB) — yields all records,
  honors batch_size, applies query filter, accepts a cursor to resume.
* Object-level ``find_iter`` surface hydrates Pydantic instances.
* PG native ``find_iter`` (against live container) — same semantics in
  one SQL round trip per page; preserves order; honors filters; resumes.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import uuid
from typing import AsyncIterator, Iterator

import pytest
import pytest_asyncio

from jvspatial.db.database import decode_cursor, encode_cursor
from jvspatial.db.jsondb import JsonDB

# ---- cursor encoding ------------------------------------------------------


class TestCursorEncoding:
    def test_round_trip(self) -> None:
        payload = {"id": "n.X.42", "extra": "value"}
        cursor = encode_cursor(payload)
        assert isinstance(cursor, bytes)
        decoded = decode_cursor(cursor)
        assert decoded == payload

    def test_decode_empty_is_none(self) -> None:
        assert decode_cursor(None) is None
        assert decode_cursor(b"") is None

    def test_decode_invalid_raises(self) -> None:
        with pytest.raises(ValueError, match="invalid cursor"):
            decode_cursor(b"not-valid-base64-or-json!!!")

    def test_cursor_is_opaque_bytes(self) -> None:
        # Callers should not try to introspect; the bytes are
        # intentionally opaque. We assert the type only.
        cursor = encode_cursor({"id": "x"})
        assert isinstance(cursor, bytes)


# ---- default impl (JsonDB) -------------------------------------------------


@pytest.fixture
async def jsondb_with_50() -> AsyncIterator[JsonDB]:
    with tempfile.TemporaryDirectory() as tmp:
        db = JsonDB(base_path=tmp)
        for i in range(50):
            await db.save(
                "node",
                {
                    "id": f"n.J.{i:04d}",
                    "entity": "T",
                    "context": {"k": i, "even": i % 2 == 0},
                },
            )
        yield db


class TestDefaultFindIter:
    async def test_yields_all_records(self, jsondb_with_50: JsonDB) -> None:
        ids = [r["id"] async for r in jsondb_with_50.find_iter("node", {})]
        assert len(ids) == 50

    async def test_order_is_id_ascending(self, jsondb_with_50: JsonDB) -> None:
        ids = [r["id"] async for r in jsondb_with_50.find_iter("node", {})]
        assert ids == sorted(ids)

    async def test_unique_ids(self, jsondb_with_50: JsonDB) -> None:
        ids = [r["id"] async for r in jsondb_with_50.find_iter("node", {})]
        assert len(set(ids)) == len(ids)

    async def test_batch_size_independent_of_total_count(
        self, jsondb_with_50: JsonDB
    ) -> None:
        for batch in (1, 7, 13, 50, 200):
            ids = [
                r["id"]
                async for r in jsondb_with_50.find_iter("node", {}, batch_size=batch)
            ]
            assert len(ids) == 50, f"batch_size={batch} produced {len(ids)}"

    async def test_filter_applied(self, jsondb_with_50: JsonDB) -> None:
        ids = [
            r["id"]
            async for r in jsondb_with_50.find_iter("node", {"context.k": {"$gte": 40}})
        ]
        assert len(ids) == 10
        assert all(r >= "n.J.0040" for r in ids)

    async def test_resume_via_cursor(self, jsondb_with_50: JsonDB) -> None:
        # Page 1: first 20 records.
        page1 = []
        last_id = None
        async for rec in jsondb_with_50.find_iter("node", {}, batch_size=20):
            page1.append(rec["id"])
            last_id = rec["id"]
            if len(page1) >= 20:
                break
        assert len(page1) == 20

        # Resume from page1's last id; expect the remaining 30.
        cursor = encode_cursor({"id": last_id})
        page2 = [
            r["id"]
            async for r in jsondb_with_50.find_iter(
                "node", {}, batch_size=20, cursor=cursor
            )
        ]
        assert len(page2) == 30
        assert set(page1).isdisjoint(set(page2))
        assert page1 + page2 == sorted(page1 + page2)

    async def test_empty_collection_yields_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = JsonDB(base_path=tmp)
            ids = [r["id"] async for r in db.find_iter("node", {})]
            assert ids == []


# ---- Object surface --------------------------------------------------------


class TestObjectFindIter:
    async def test_hydrates_typed_instances(self) -> None:
        from jvspatial.core.context import GraphContext, set_default_context
        from jvspatial.core.entities.node import Node

        class _Widget(Node):
            label: str = ""
            qty: int = 0

        with tempfile.TemporaryDirectory() as tmp:
            ctx = GraphContext(database=JsonDB(base_path=tmp))
            set_default_context(ctx)
            for i in range(15):
                await _Widget.create(label=f"w{i:02d}", qty=i)

            seen = []
            async for widget in _Widget.find_iter(batch_size=4):
                assert isinstance(widget, _Widget)
                seen.append(widget.qty)
            assert sorted(seen) == list(range(15))


# ---- PG native ------------------------------------------------------------


_PG_DSN = os.getenv(
    "JVSPATIAL_POSTGRES_TEST_DSN",
    "postgresql://jvspatial:jvspatial@localhost:5432/jvspatial",
)


@pytest_asyncio.fixture(loop_scope="function")
async def pg_db_paged() -> AsyncIterator:
    """Per-test PostgresDB seeded with 200 records in a throwaway schema."""
    try:
        import asyncpg
    except ImportError:
        pytest.skip("asyncpg not installed")

    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn=_PG_DSN), timeout=2.0)
    except Exception:
        pytest.skip("Postgres not reachable")

    from jvspatial.db.postgres import PostgresDB

    schema = f"jvs_pgtest_{uuid.uuid4().hex[:12]}"
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
    finally:
        await conn.close()

    db = PostgresDB(dsn=_PG_DSN, schema_name=schema)
    try:
        records = [
            {
                "id": f"n.PG.{i:04d}",
                "entity": "pg",
                "context": {"k": i, "bucket": i % 7},
            }
            for i in range(200)
        ]
        await db.bulk_save_detailed("node", records)
        yield db
    finally:
        try:
            await db.close()
        except RuntimeError:
            pass
        try:
            cleanup = await asyncpg.connect(dsn=_PG_DSN)
            try:
                await cleanup.execute(f'DROP SCHEMA "{schema}" CASCADE')
            finally:
                await cleanup.close()
        except Exception:
            pass


class TestPostgresFindIter:
    @pytest.mark.parametrize(
        "sort",
        [[("id", -1)], [("context.k", -1)], [("context.bucket", 1), ("context.k", -1)]],
    )
    async def test_composite_sort_and_released_connection(self, pg_db_paged, sort):
        from jvspatial.db.database import finalize_find_results

        fields = (
            sort if any(k == "id" for k, _ in sort) else [*sort, ("id", sort[0][1])]
        )
        expected = finalize_find_results(
            await pg_db_paged.find("node", {}), sort=fields
        )
        iterator = pg_db_paged.find_iter("node", {}, sort=sort, batch_size=7)
        first = await anext(iterator)
        pool = await pg_db_paged._ensure_pool()
        assert pool.get_idle_size() == pool.get_size()
        rows = [first, *[r async for r in iterator]]
        assert [r["id"] for r in rows] == [r["id"] for r in expected]

    async def test_pages_all_records(self, pg_db_paged) -> None:
        ids = [r["id"] async for r in pg_db_paged.find_iter("node", {}, batch_size=37)]
        assert len(ids) == 200
        assert ids == sorted(ids)

    async def test_filter_pushes_down(self, pg_db_paged) -> None:
        ids = [
            r["id"]
            async for r in pg_db_paged.find_iter(
                "node", {"context.bucket": 3}, batch_size=20
            )
        ]
        # 200 // 7 + (1 if 200 % 7 > 3 else 0) = 28 + ...
        # i=3,10,17,...,199 — 200/7 = 28.57 → 29 values where i % 7 == 3.
        assert len(ids) == 29
        assert ids == sorted(ids)

    async def test_resume_via_cursor(self, pg_db_paged) -> None:
        page1 = []
        last_id = None
        async for rec in pg_db_paged.find_iter("node", {}, batch_size=50):
            page1.append(rec["id"])
            last_id = rec["id"]
            if len(page1) >= 50:
                break

        cursor = encode_cursor({"id": last_id})
        page2 = [
            r["id"]
            async for r in pg_db_paged.find_iter(
                "node", {}, batch_size=50, cursor=cursor
            )
        ]
        assert len(page2) == 150
        assert page1 + page2 == sorted(page1 + page2)
        assert set(page1).isdisjoint(set(page2))


@pytest.mark.parametrize("direction", [1, -1])
async def test_postgres_null_numeric_keyset_complete(pg_db_paged, direction):
    from jvspatial.db.database import (
        _keyset_payload,
        _keyset_sort_fields,
        finalize_find_results,
    )

    records = [
        {"id": "numeric2", "context": {"rank": 2}},
        {"id": "numeric100", "context": {"rank": 100}},
        {"id": "null", "context": {"rank": None}},
        {"id": "missing", "context": {}},
    ]
    await pg_db_paged.bulk_save("nullable", records)
    fields = _keyset_sort_fields([("context.rank", direction)])
    expected = finalize_find_results(records, sort=fields)
    iterator = pg_db_paged.find_iter("nullable", {}, sort=fields, batch_size=1)
    first = await anext(iterator)
    await iterator.aclose()
    cursor = encode_cursor(_keyset_payload(first, fields))
    resumed = [
        r
        async for r in pg_db_paged.find_iter(
            "nullable", {}, sort=fields, batch_size=1, cursor=cursor
        )
    ]
    assert [r["id"] for r in [first, *resumed]] == [r["id"] for r in expected]


async def test_postgres_residual_scan_budget_and_early_release(
    pg_db_paged, monkeypatch
):
    import jvspatial.db.postgres as module
    from jvspatial.db.database import DatabaseError, _query_execution

    native = module.translate_query

    def translate(query):
        return None if "$regex" in repr(query) else native(query)

    monkeypatch.setattr(module, "translate_query", translate)
    await pg_db_paged.bulk_save(
        "residual",
        [
            {
                "id": f"{i:03}",
                "context": {"group": i % 2, "label": "match" if i % 5 == 0 else "miss"},
            }
            for i in range(100)
        ],
    )
    query = {"context.group": 1, "context.label": {"$regex": "^match$"}}
    assert [
        r["id"]
        for r in await pg_db_paged.find("residual", query, sort=[("id", 1)], limit=1)
    ] == ["005"]
    assert _query_execution.get()["scanned_rows"] == 3
    pool = await pg_db_paged._ensure_pool()
    assert pool.get_idle_size() == pool.get_size()
    assert await pg_db_paged.count("residual", query) == 10
    pg_db_paged.fallback_scan_limit = 2
    with pytest.raises(DatabaseError, match="fallback_scan_limit"):
        await pg_db_paged.find("residual", query)
    assert pool.get_idle_size() == pool.get_size()


async def test_postgres_bulk_preserves_physical_vectors(pg_db_paged):
    await pg_db_paged.enable_vector_column("vectors", "embedding", dim=2)
    result = await pg_db_paged.bulk_save_detailed(
        "vectors",
        [
            {"id": "near", "embedding": [1, 0]},
            {"id": "far", "embedding": [0, 1]},
            {"id": "near", "embedding": [1, 0]},
        ],
    )
    assert result.all_saved
    ranked = await pg_db_paged.find(
        "vectors", {"embedding": {"$near": [1, 0], "$limit": 2}}
    )
    assert [row["id"] for row in ranked] == ["near", "far"]
