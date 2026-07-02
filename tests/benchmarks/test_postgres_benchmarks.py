"""Postgres performance benchmarks (skipped when no live DSN)."""

from __future__ import annotations

import os

import pytest

from jvspatial.db.postgres import PostgresDB

from .conftest import run_async
from .graph_fixtures import seed_chain_graph

_DSN = os.getenv(
    "JVSPATIAL_POSTGRES_TEST_DSN",
    "postgresql://jvspatial:jvspatial@localhost:5432/jvspatial",
)


def _postgres_available() -> bool:
    try:
        import asyncpg  # noqa: F401
    except ImportError:
        return False
    return bool(_DSN)


pytestmark = [
    pytest.mark.benchmark,
    pytest.mark.skipif(
        not _postgres_available(), reason="Postgres/asyncpg unavailable"
    ),
]


async def _with_pg(coro):
    import uuid

    schema = f"bench_{uuid.uuid4().hex[:12]}"
    db = PostgresDB(dsn=_DSN, schema_name=schema)
    try:
        return await coro(db)
    finally:
        await db.close()


def test_bench_postgres_traverse_depth(benchmark):
    """Recursive CTE traversal over a seeded chain."""

    async def _run():
        async def work(db: PostgresDB):
            await seed_chain_graph(db, length=40)
            for _ in range(10):
                await db.traverse("edge", "n.0", direction="out", max_depth=5)

        await _with_pg(work)

    benchmark(run_async, _run)


def test_bench_postgres_find_many_bulk(benchmark):
    """Bulk fetch by id list."""

    async def _run():
        async def work(db: PostgresDB):
            await seed_chain_graph(db, length=100)
            ids = [f"n.{i}" for i in range(100)]

            async def _fetch():
                await db.find_many("node", ids)

            for _ in range(20):
                await _fetch()

        await _with_pg(work)

    benchmark(run_async, _run)
