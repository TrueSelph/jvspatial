"""Warm PostgreSQL operations on an explicitly created disposable schema."""

import asyncio
import os
import uuid

import pytest

from jvspatial.db.postgres import PostgresDB

from .conftest import benchmark_async
from .graph_fixtures import seed_chain_graph

pytestmark = pytest.mark.benchmark
_DSN = os.getenv(
    "JVSPATIAL_POSTGRES_TEST_DSN",
    "postgresql://jvspatial:jvspatial@localhost:5432/jvspatial",
)


async def _setup():
    try:
        import asyncpg
    except ImportError:
        pytest.skip("asyncpg not installed")
    try:
        conn = await asyncio.wait_for(asyncpg.connect(_DSN), timeout=2)
    except Exception:
        pytest.skip("PostgreSQL benchmark service unavailable")
    schema = f"bench_{uuid.uuid4().hex[:12]}"
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
    finally:
        await conn.close()
    db = PostgresDB(dsn=_DSN, schema_name=schema)
    try:
        await seed_chain_graph(db, length=100)
        return db
    except BaseException:
        await _close(db)
        raise


async def _close(db):
    import asyncpg

    await db.close()
    conn = await asyncpg.connect(_DSN)
    try:
        await conn.execute(f'DROP SCHEMA IF EXISTS "{db.schema_name}" CASCADE')
    finally:
        await conn.close()


def test_bench_postgres_traverse_depth(benchmark):
    benchmark_async(
        benchmark,
        _setup,
        lambda db: db.traverse("edge", "n.0", direction="out", max_depth=5),
        _close,
    )


def test_bench_postgres_find_many_bulk(benchmark):
    benchmark_async(
        benchmark,
        _setup,
        lambda db: db.find_many("node", [f"n.{i}" for i in range(100)]),
        _close,
    )
