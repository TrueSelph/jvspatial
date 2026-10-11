"""Warm SQLite operation benchmarks; setup/seeding are outside timing."""

import pytest

from jvspatial.db.sqlite import SQLiteDB

from .conftest import benchmark_async

pytestmark = pytest.mark.benchmark
SEED_SIZE = 2000


async def _setup():
    db = SQLiteDB(db_path=":memory:")
    await db.bulk_save(
        "node",
        [
            {
                "id": f"n{i:06d}",
                "context": {
                    "name": f"name-{i}",
                    "active": i % 7 == 0,
                    "category": "even" if i % 2 == 0 else "odd",
                },
                "value": i,
                "tags": ["tag1", "tag2"] if i % 3 == 0 else [],
            }
            for i in range(SEED_SIZE)
        ],
    )
    return db


async def _close(db):
    await db.close()


def test_bench_sqlite_count_empty(benchmark):
    benchmark_async(benchmark, _setup, lambda db: db.count("node"), _close)


def test_bench_sqlite_count_pushdown(benchmark):
    benchmark_async(
        benchmark, _setup, lambda db: db.count("node", {"context.active": True}), _close
    )


def test_bench_sqlite_count_fallback_via_regex(benchmark):
    benchmark_async(
        benchmark,
        _setup,
        lambda db: db.count("node", {"context.name": {"$regex": "name-1"}}),
        _close,
    )


def test_bench_sqlite_find_pushdown(benchmark):
    async def find(db):
        rows = await db.find("node", {"context.category": "even"}, limit=50)
        assert len(rows) == 50

    benchmark_async(benchmark, _setup, find, _close)


def test_bench_sqlite_sort_limit_pushdown(benchmark):
    async def find(db):
        rows = await db.find("node", {}, sort=[("value", -1)], limit=10)
        assert len(rows) == 10
        assert rows[0]["value"] == SEED_SIZE - 1

    benchmark_async(benchmark, _setup, find, _close)


def test_bench_sqlite_find_fallback_via_regex(benchmark):
    async def find(db):
        rows = await db.find("node", {"context.name": {"$regex": "^name-1[0-9]$"}})
        assert len(rows) == 10

    benchmark_async(benchmark, _setup, find, _close)
