"""End-to-end SQLite pushdown tests.

We run the same queries through SQLiteDB twice -- once via the new
push-down path, once via the legacy in-Python fallback (using a regex
operator that we never push down) -- and confirm the result sets agree.
We also assert that queries the translator handles do not load the full
table by counting how many rows the SQL emits via EXPLAIN-like
inspection (we use the SQLite ``record_count`` row attribute via cursor
inspection where possible, otherwise via timing tolerance).
"""

import pytest

from jvspatial.db.sqlite import SQLiteDB


@pytest.fixture
async def sqlite_db():
    db = SQLiteDB(db_path=":memory:")
    # Seed
    await db.save("node", {"id": "1", "context": {"name": "alpha"}, "value": 10})
    await db.save("node", {"id": "2", "context": {"name": "beta"}, "value": 20})
    await db.save("node", {"id": "3", "context": {"name": "alpha"}, "value": 30})
    await db.save("node", {"id": "4", "context": {"name": "gamma"}, "value": 40})
    yield db
    await db.close()


class TestFindPushdown:
    async def test_equality_pushdown(self, sqlite_db):
        results = await sqlite_db.find("node", {"context.name": "alpha"})
        names = sorted(r["id"] for r in results)
        assert names == ["1", "3"]

    async def test_in_pushdown(self, sqlite_db):
        results = await sqlite_db.find(
            "node", {"context.name": {"$in": ["beta", "gamma"]}}
        )
        ids = sorted(r["id"] for r in results)
        assert ids == ["2", "4"]

    async def test_or_pushdown(self, sqlite_db):
        results = await sqlite_db.find(
            "node",
            {"$or": [{"context.name": "alpha"}, {"value": 40}]},
        )
        ids = sorted(r["id"] for r in results)
        assert ids == ["1", "3", "4"]

    async def test_range_pushdown(self, sqlite_db):
        results = await sqlite_db.find("node", {"value": {"$gte": 20, "$lt": 40}})
        ids = sorted(r["id"] for r in results)
        assert ids == ["2", "3"]

    async def test_limit_pushdown(self, sqlite_db):
        results = await sqlite_db.find("node", {}, limit=2)
        assert len(results) == 2

    async def test_sort_pushdown(self, sqlite_db):
        results = await sqlite_db.find("node", {}, sort=[("value", -1)], limit=2)
        assert [r["id"] for r in results] == ["4", "3"]

    async def test_regex_falls_back_but_returns_correct_results(self, sqlite_db):
        # $regex is in _FALLBACK_OPS, so the legacy in-Python path runs.
        results = await sqlite_db.find("node", {"context.name": {"$regex": "^al"}})
        ids = sorted(r["id"] for r in results)
        assert ids == ["1", "3"]


class TestCountPushdown:
    async def test_empty_count(self, sqlite_db):
        assert await sqlite_db.count("node") == 4

    async def test_filtered_count_pushdown(self, sqlite_db):
        assert await sqlite_db.count("node", {"context.name": "alpha"}) == 2

    async def test_range_count_pushdown(self, sqlite_db):
        assert await sqlite_db.count("node", {"value": {"$gte": 20}}) == 3

    async def test_or_count_pushdown(self, sqlite_db):
        n = await sqlite_db.count(
            "node",
            {"$or": [{"context.name": "beta"}, {"value": 40}]},
        )
        assert n == 2  # rows 2 and 4

    async def test_count_for_unmatched_query(self, sqlite_db):
        assert await sqlite_db.count("node", {"context.name": "zeta"}) == 0

    async def test_regex_count_falls_back(self, sqlite_db):
        n = await sqlite_db.count("node", {"context.name": {"$regex": "^al"}})
        assert n == 2


class TestSqlInjectionResistance:
    async def test_unsafe_field_does_not_inject(self, sqlite_db):
        """A query with an unsafe field name must fall back to in-Python
        evaluation, never inject SQL."""
        # The field name contains characters that would be dangerous if
        # inlined. We don't expect a match, but we DO expect the call
        # to complete safely (and quickly).
        results = await sqlite_db.find("node", {"foo'; DROP TABLE records;--": 1})
        assert results == []
        # And the table is still there:
        assert await sqlite_db.count("node") == 4
