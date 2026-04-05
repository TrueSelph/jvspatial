"""Tests for Database default find_one_and_update / find_one_and_delete (JsonDB, SQLite)."""

import tempfile

import pytest

from jvspatial.db.jsondb import JsonDB

try:
    import aiosqlite  # noqa: F401

    from jvspatial.db import create_database

    HAS_SQLITE = True
except ImportError:  # pragma: no cover
    create_database = None  # type: ignore[misc]
    HAS_SQLITE = False


@pytest.fixture
def jsondb():
    with tempfile.TemporaryDirectory() as tmp:
        yield JsonDB(base_path=tmp)


@pytest.mark.asyncio
async def test_jsondb_inherits_find_one_and_update_upsert(jsondb: JsonDB):
    out = await jsondb.find_one_and_update(
        "coll",
        {"_id": "s1"},
        {"$set": {"updated_at": 1.0}, "$setOnInsert": {"agent_id": "a"}},
        upsert=True,
    )
    assert out is not None
    assert out["_id"] == "s1"
    assert out["agent_id"] == "a"
    assert out["updated_at"] == 1.0


@pytest.mark.asyncio
async def test_jsondb_find_one_and_delete_compound_query(jsondb: JsonDB):
    await jsondb.save(
        "batches",
        {
            "_id": "sender1",
            "id": "sender1",
            "data": 1,
            "_jv_claim": "tok123",
        },
    )
    deleted = await jsondb.find_one_and_delete(
        "batches",
        {"_id": "sender1", "_jv_claim": "tok123"},
    )
    assert deleted is not None
    assert deleted["_jv_claim"] == "tok123"
    assert await jsondb.get("batches", "sender1") is None


@pytest.mark.asyncio
async def test_jsondb_find_one_and_delete_no_match_wrong_token(jsondb: JsonDB):
    await jsondb.save(
        "batches",
        {"_id": "sender1", "id": "sender1", "_jv_claim": "tok123"},
    )
    deleted = await jsondb.find_one_and_delete(
        "batches",
        {"_id": "sender1", "_jv_claim": "wrong"},
    )
    assert deleted is None
    still = await jsondb.get("batches", "sender1")
    assert still is not None


@pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite required")
@pytest.mark.asyncio
async def test_sqlite_find_one_and_update_and_delete_compound():
    with tempfile.TemporaryDirectory() as tmp:
        import os

        path = os.path.join(tmp, "t.db")
        db = create_database("sqlite", db_path=path)
        try:
            await db.save(
                "batches",
                {
                    "_id": "sender1",
                    "id": "sender1",
                    "x": 1,
                    "_jv_claim": "abc",
                },
            )
            upd = await db.find_one_and_update(
                "batches",
                {"_id": "sender1"},
                {"$set": {"x": 2}},
            )
            assert upd is not None
            assert upd["x"] == 2

            gone = await db.find_one_and_delete(
                "batches",
                {"_id": "sender1", "_jv_claim": "abc"},
            )
            assert gone is not None
            assert await db.get("batches", "sender1") is None
        finally:
            if hasattr(db, "close"):
                await db.close()
