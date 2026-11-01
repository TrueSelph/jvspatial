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
        topology = await db._client.admin.command("hello")
        expected = bool(topology.get("setName")) or topology.get("msg") == "isdbgrid"
        assert await db.is_transactional() is expected
    finally:
        if db._client is not None:
            await db._client.drop_database(db.db_name)
        await db.close()


@pytest.mark.parametrize("driver", ["motor", "pymongo"])
async def test_live_transaction_read_contract_commit_and_rollback(driver):
    """Qualify shared reads on real sessions when a replica set is configured."""
    from jvspatial.db.transaction import transaction_context

    uri = os.getenv("JVSPATIAL_MONGODB_TEST_URI")
    if not uri:
        pytest.skip("JVSPATIAL_MONGODB_TEST_URI is not configured")
    db = MongoDB(
        uri=uri, db_name=f"transaction_audit_{uuid.uuid4().hex}", driver=driver
    )
    try:
        if not await db.is_transactional():
            pytest.skip("MongoDB transactions require a replica set or sharded cluster")
        await db.save("object", {"id": "existing", "rank": 1})
        async with transaction_context(db) as tx:
            assert tx is not None
            await tx.save("object", {"id": "committed", "rank": 2})
            assert await tx.count("object") == 2
            assert await tx.find_ids("object", {}, sort=[("rank", 1)]) == [
                "existing",
                "committed",
            ]
            assert set(await tx.find_many("object", ["existing", "committed"])) == {
                "existing",
                "committed",
            }
            rows = [r async for r in tx.find_iter("object", {}, batch_size=1)]
            assert {r["id"] for r in rows} == {"existing", "committed"}
            assert await db.get("object", "committed") is None
        assert await db.get("object", "committed") is not None
        with pytest.raises(RuntimeError, match="abort"):
            async with transaction_context(db) as tx:
                assert tx is not None
                await tx.save("object", {"id": "rolled_back", "rank": 3})
                assert await tx.find_one("object", {"id": "rolled_back"}) is not None
                raise RuntimeError("abort")
        assert await db.get("object", "rolled_back") is None
    finally:
        if db._client is not None:
            await db._client.drop_database(db.db_name)
        await db.close()
