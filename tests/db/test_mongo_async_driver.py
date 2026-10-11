"""Both Mongo drivers use the same async adapter contract."""

import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from jvspatial.db.mongodb import MongoDB


async def test_pymongo_close_is_awaited():
    db = MongoDB(driver="pymongo")
    client = MagicMock()
    client.close = AsyncMock()
    db._client = client
    await db.close()
    client.close.assert_awaited_once()
    assert db._client is None


@pytest.mark.parametrize("driver", ["motor", "pymongo"])
async def test_live_driver_queries_bulk_cursor_and_degrees(driver):
    uri = os.getenv("JVSPATIAL_MONGODB_TEST_URI")
    if not uri:
        pytest.skip("JVSPATIAL_MONGODB_TEST_URI is not configured")
    db = MongoDB(uri=uri, db_name=f"audit_{uuid.uuid4().hex}", driver=driver)
    try:
        records = [{"id": f"{i:03}", "context": {"rank": i}} for i in range(200)]
        records += [
            {"id": "null", "context": {"rank": None}},
            {"id": "missing", "context": {}},
        ]
        result = await db.bulk_save_detailed("object", records)
        assert result.all_saved
        rows = [
            r
            async for r in db.find_iter(
                "object", {}, sort=[("context.rank", -1)], batch_size=7
            )
        ]
        assert len(rows) == 202
        assert [r["id"] for r in rows[:3]] == ["199", "198", "197"]
        assert await db.find_ids(
            "object", {}, sort=[("context.rank", -1)], offset=100, limit=2
        ) == ["099", "098"]
        assert await db.find_one("object", {}) is not None
        await db.bulk_save(
            "edge",
            [
                {"id": "ab", "source": "a", "target": "b"},
                {"id": "aa", "source": "a", "target": "a"},
            ],
        )
        assert await db.count_incident_edges("edge", ["a", "b", "z"]) == {
            "a": 2,
            "b": 1,
            "z": 0,
        }
        iterator = db.find_iter("object", {})
        await anext(iterator)
        await iterator.aclose()
        assert not await db.is_transactional()  # This test service is standalone.
    finally:
        if db._client is not None:
            await db._client.drop_database(db.db_name)
        await db.close()
