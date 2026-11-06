"""Compiler coverage is explicit and never certifies data types or access."""

from unittest.mock import AsyncMock

import pytest

from jvspatial.db.jsondb import JsonDB
from jvspatial.db.postgres import PostgresDB
from tests.db.test_postgres_integration import pg_db as pg_db


def test_default_backend_refuses_numeric_pushdown_coverage(tmp_path):
    database = JsonDB(str(tmp_path))
    assert not database.can_pushdown_numeric_sort({}, [("context.score", 1)])


def test_postgres_coverage_requires_the_whole_query_and_order():
    database = PostgresDB(dsn="postgresql://unused/unused")
    database._ensure_pool = AsyncMock(side_effect=AssertionError("No I/O permitted"))
    assert database.can_pushdown_numeric_sort(
        {"context.score": {"$type": "number"}}, [("context.score", 1), ("id", 1)]
    )
    assert not database.can_pushdown_numeric_sort({}, [("context.my-score", 1)])
    assert not database.can_pushdown_numeric_sort(
        {"context.score": {"$unsupported": 1}}, [("id", 1)]
    )
    assert not database.can_pushdown_numeric_sort({}, [])
    database._ensure_pool.assert_not_awaited()


def test_wrappers_forward_current_coverage_without_a_data_cache(tmp_path):
    from jvspatial.db._cache import CachingDatabase
    from jvspatial.db._observable import ObservableDatabase

    database = ObservableDatabase(
        CachingDatabase(PostgresDB(dsn="postgresql://unused/unused"))
    )
    assert database.can_pushdown_numeric_sort({}, [("context.score", -1), ("id", -1)])
    assert not database.can_pushdown_numeric_sort({}, [("context.my-score", 1)])
    database.inner.inner = JsonDB(str(tmp_path))
    assert not database.can_pushdown_numeric_sort({}, [("context.score", -1)])


@pytest.mark.asyncio
async def test_covered_projection_preserves_numeric_top_n_and_nulls(pg_db):
    for identifier, value in (("a", 10), ("b", 9), ("c", 2), ("d", None)):
        await pg_db.save(
            "node", {"id": identifier, "entity": "Item", "context": {"score": value}}
        )
    await pg_db.save("node", {"id": "e", "entity": "Item", "context": {}})
    for direction, expected in ((1, ["c", "b"]), (-1, ["a", "b"])):
        ordering = [("context.score", direction), ("id", direction)]
        assert pg_db.can_pushdown_numeric_sort({"entity": "Item"}, ordering)
        page = await pg_db.find_projected(
            "node",
            {"entity": "Item"},
            fields=["id", "context.score"],
            sort=ordering,
            limit=2,
        )
        assert [row["id"] for row in page] == expected
        all_rows = await pg_db.find_projected(
            "node", {"entity": "Item"}, fields=["id"], sort=ordering
        )
        assert set(row["id"] for row in all_rows[-2:]) == {"d", "e"}
