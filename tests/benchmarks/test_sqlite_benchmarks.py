"""SQLite performance benchmarks.

Specifically guards the Phase A2 wins:
* native ``count()`` for empty queries (``SELECT COUNT(*)``),
* native ``count()`` for filtered queries via the
  :mod:`jvspatial.db._sqlite_translate` pushdown,
* ``find()`` with WHERE + LIMIT pushdown,
* ``find()`` with ORDER BY + LIMIT pushdown,
* graceful fallback path performance (legacy in-Python filter via
  ``$regex``) -- this is the *worst case*; if it gets dramatically
  slower we want to know.

Each bench uses an in-memory SQLite database seeded fresh per run.
"""

import pytest

from jvspatial.db.sqlite import SQLiteDB

from .conftest import run_async

pytestmark = pytest.mark.benchmark


SEED_SIZE = 2000


async def _seed(db: SQLiteDB, n: int) -> None:
    for i in range(n):
        await db.save(
            "node",
            {
                "id": f"n{i:06d}",
                "context": {
                    "name": f"name-{i}",
                    "active": (i % 7 == 0),
                    "category": "even" if i % 2 == 0 else "odd",
                },
                "value": i,
                "tags": ["tag1", "tag2"] if i % 3 == 0 else [],
            },
        )


# ---- Counts ----------------------------------------------------------


def test_bench_sqlite_count_empty(benchmark):
    """``SELECT COUNT(*)`` -- O(1) server-side, regardless of N."""

    async def setup_then_count():
        db = SQLiteDB(db_path=":memory:")
        try:
            await _seed(db, SEED_SIZE)
            for _ in range(20):
                await db.count("node")
        finally:
            await db.close()

    benchmark(run_async, setup_then_count)


def test_bench_sqlite_count_pushdown(benchmark):
    """Filtered count via translated WHERE clause."""

    async def setup_then_count():
        db = SQLiteDB(db_path=":memory:")
        try:
            await _seed(db, SEED_SIZE)
            for _ in range(20):
                await db.count("node", {"context.active": True})
        finally:
            await db.close()

    benchmark(run_async, setup_then_count)


def test_bench_sqlite_count_fallback_via_regex(benchmark):
    """Filtered count for an untranslatable query (``$regex``).

    The fallback path materializes the full result list. This bench
    is a *floor*: any change that makes the fallback slower
    needs to be intentional.
    """

    async def setup_then_count():
        db = SQLiteDB(db_path=":memory:")
        try:
            await _seed(db, SEED_SIZE)
            for _ in range(5):
                await db.count("node", {"context.name": {"$regex": "name-1"}})
        finally:
            await db.close()

    benchmark(run_async, setup_then_count)


# ---- Find ------------------------------------------------------------


def test_bench_sqlite_find_pushdown(benchmark):
    """Filtered find with LIMIT pushdown."""

    async def setup_then_find():
        db = SQLiteDB(db_path=":memory:")
        try:
            await _seed(db, SEED_SIZE)
            for _ in range(20):
                results = await db.find("node", {"context.category": "even"}, limit=50)
                assert len(results) == 50
        finally:
            await db.close()

    benchmark(run_async, setup_then_find)


def test_bench_sqlite_sort_limit_pushdown(benchmark):
    """ORDER BY + LIMIT pushed into SQL."""

    async def setup_then_sorted_find():
        db = SQLiteDB(db_path=":memory:")
        try:
            await _seed(db, SEED_SIZE)
            for _ in range(20):
                results = await db.find("node", {}, sort=[("value", -1)], limit=10)
                assert len(results) == 10
                assert results[0]["value"] == SEED_SIZE - 1
        finally:
            await db.close()

    benchmark(run_async, setup_then_sorted_find)


def test_bench_sqlite_find_fallback_via_regex(benchmark):
    """find() with $regex -- legacy in-Python full-table filter.

    Worst-case bench. Exists as a floor and to detect when somebody
    accidentally turns the pushdown path into a fallback.
    """

    async def setup_then_find():
        db = SQLiteDB(db_path=":memory:")
        try:
            await _seed(db, SEED_SIZE)
            for _ in range(5):
                results = await db.find(
                    "node", {"context.name": {"$regex": "^name-1[0-9]$"}}
                )
                assert len(results) == 10
        finally:
            await db.close()

    benchmark(run_async, setup_then_find)
