"""Tests for Database.insert_if_absent across adapters and wrappers.

Contract (v1): conflict on primary key ``id`` only; never update/replace an
existing row; return the stored winner plus ``created``.
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.db.database import Database, InsertIfAbsentResult
from jvspatial.db.jsondb import JsonDB

try:
    from jvspatial.db.sqlite import SQLiteDB

    HAS_SQLITE = True
except ImportError:  # pragma: no cover
    SQLiteDB = None  # type: ignore[misc]
    HAS_SQLITE = False


# ---------------------------------------------------------------------------
# ABC / validation
# ---------------------------------------------------------------------------


class _StubDB(Database):
    """Minimal concrete Database for ABC default-path tests."""

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        return data

    async def get(self, collection: str, id: str):
        return None

    async def delete(self, collection: str, id: str) -> None:
        return None

    async def find(self, collection: str, query: Dict[str, Any], **kwargs):
        return []


@pytest.mark.asyncio
async def test_abc_default_raises_not_implemented():
    db = _StubDB()
    with pytest.raises(NotImplementedError, match="insert_if_absent"):
        await db.insert_if_absent("object", {"id": "x", "v": 1})


@pytest.mark.asyncio
async def test_abc_rejects_non_id_conflict_target():
    db = _StubDB()
    with pytest.raises(ValueError, match="conflict_target"):
        await db.insert_if_absent("object", {"id": "x"}, conflict_target="email")


@pytest.mark.asyncio
async def test_abc_rejects_missing_id():
    db = _StubDB()
    with pytest.raises(ValueError, match="id"):
        await db.insert_if_absent("object", {"v": 1})


@pytest.mark.asyncio
async def test_abc_rejects_empty_id():
    db = _StubDB()
    with pytest.raises(ValueError, match="id"):
        await db.insert_if_absent("object", {"id": ""})


def test_insert_if_absent_result_frozen():
    r = InsertIfAbsentResult(record={"id": "a"}, created=True)
    assert r.created is True
    assert r.record["id"] == "a"
    with pytest.raises(Exception):
        r.created = False  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SQLite
# ---------------------------------------------------------------------------


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir) / "iia.db"


@pytest.fixture
async def sqlite_db(temp_db_path):
    if not HAS_SQLITE:
        pytest.skip("aiosqlite required")
    from jvspatial.db import create_database

    db = create_database("sqlite", db_path=str(temp_db_path))
    try:
        yield db
    finally:
        if hasattr(db, "close"):
            await db.close()


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite required")
async def test_sqlite_insert_absent_then_conflict_preserves_winner(sqlite_db):
    first = {"id": "rec.1", "entity": "X", "context": {"v": 1}}
    r1 = await sqlite_db.insert_if_absent("object", first)
    assert isinstance(r1, InsertIfAbsentResult)
    assert r1.created is True
    assert r1.record["context"]["v"] == 1

    loser = {"id": "rec.1", "entity": "X", "context": {"v": 999}}
    r2 = await sqlite_db.insert_if_absent("object", loser)
    assert r2.created is False
    assert r2.record["context"]["v"] == 1  # winner unchanged

    loaded = await sqlite_db.get("object", "rec.1")
    assert loaded is not None
    assert loaded["context"]["v"] == 1


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite required")
async def test_sqlite_save_still_upserts(sqlite_db):
    """Regression: save() remains INSERT OR REPLACE upsert."""
    await sqlite_db.save("object", {"id": "u.1", "context": {"v": 1}})
    await sqlite_db.save("object", {"id": "u.1", "context": {"v": 2}})
    loaded = await sqlite_db.get("object", "u.1")
    assert loaded is not None
    assert loaded["context"]["v"] == 2


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite required")
async def test_sqlite_concurrent_same_id_one_created(sqlite_db):
    rec_id = "conc.same"
    payloads = [{"id": rec_id, "entity": "X", "context": {"n": i}} for i in range(16)]

    results = await asyncio.gather(
        *[sqlite_db.insert_if_absent("object", p) for p in payloads]
    )
    created_flags = [r.created for r in results]
    assert sum(1 for c in created_flags if c) == 1
    winner = next(r.record for r in results if r.created)
    for r in results:
        assert r.record == winner
    loaded = await sqlite_db.get("object", rec_id)
    assert loaded == winner


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite required")
async def test_sqlite_secondary_unique_conflict_does_not_delete_peer(sqlite_db):
    """INSERT OR IGNORE must not wipe a peer row the way OR REPLACE does."""
    conn = await sqlite_db._get_connection()
    await conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_object_ctx_k
        ON records (collection, json_extract(data, '$.context.k'))
        """
    )
    await conn.commit()

    peer = {"id": "peer.1", "entity": "A", "context": {"k": "shared"}}
    await sqlite_db.save("object", peer)

    challenger = {"id": "chal.1", "entity": "B", "context": {"k": "shared"}}
    # May raise or return created=False; peer must survive either way.
    try:
        await sqlite_db.insert_if_absent("object", challenger)
    except Exception:
        pass

    still = await sqlite_db.get("object", "peer.1")
    assert still is not None
    assert still["context"]["k"] == "shared"
    # Challenger must not have replaced peer via OR REPLACE.
    assert still["id"] == "peer.1"


@pytest.mark.asyncio
@pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite required")
async def test_sqlite_rejects_bad_conflict_target(sqlite_db):
    with pytest.raises(ValueError, match="conflict_target"):
        await sqlite_db.insert_if_absent("object", {"id": "x"}, conflict_target="other")


# ---------------------------------------------------------------------------
# JsonDB
# ---------------------------------------------------------------------------


@pytest.fixture
async def jsondb():
    with tempfile.TemporaryDirectory() as tmp:
        db = JsonDB(base_path=tmp)
        yield db


@pytest.mark.asyncio
async def test_jsondb_insert_if_absent_roundtrip(jsondb):
    r1 = await jsondb.insert_if_absent("object", {"id": "j.1", "context": {"v": 1}})
    assert r1.created is True
    r2 = await jsondb.insert_if_absent("object", {"id": "j.1", "context": {"v": 99}})
    assert r2.created is False
    assert r2.record["context"]["v"] == 1


@pytest.mark.asyncio
async def test_jsondb_concurrent_same_id(jsondb):
    results = await asyncio.gather(
        *[
            jsondb.insert_if_absent("object", {"id": "j.conc", "context": {"n": i}})
            for i in range(12)
        ]
    )
    assert sum(1 for r in results if r.created) == 1
    winner = next(r.record for r in results if r.created)
    for r in results:
        assert r.record == winner


# ---------------------------------------------------------------------------
# Wrappers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_observable_forwards_insert_if_absent():
    from jvspatial.db._observable import ObservableDatabase
    from jvspatial.observability import db_op_counter

    inner = MagicMock()
    inner.supports_transactions = False
    expected = InsertIfAbsentResult(record={"id": "w.1", "v": 1}, created=True)
    inner.insert_if_absent = AsyncMock(return_value=expected)
    inner.save = AsyncMock(side_effect=AssertionError("save must not be used"))

    token = db_op_counter.set(0)
    try:
        wrapped = ObservableDatabase(inner)
        result = await wrapped.insert_if_absent("object", {"id": "w.1", "v": 1})
        assert db_op_counter.get() == 1
    finally:
        db_op_counter.reset(token)

    assert result is expected
    inner.insert_if_absent.assert_awaited_once_with(
        "object", {"id": "w.1", "v": 1}, conflict_target="id"
    )


@pytest.mark.asyncio
async def test_caching_forwards_insert_if_absent_and_caches(monkeypatch):
    from jvspatial.db._cache import CachingDatabase

    monkeypatch.setenv("SERVERLESS_MODE", "false")
    inner = MagicMock()
    inner.supports_transactions = False
    record = {"id": "c.1", "v": 1}
    inner.insert_if_absent = AsyncMock(
        return_value=InsertIfAbsentResult(record=record, created=True)
    )
    inner.get = AsyncMock(side_effect=AssertionError("should be cache hit"))
    inner.save = AsyncMock(side_effect=AssertionError("save must not be used"))

    cached = CachingDatabase(inner)
    result = await cached.insert_if_absent("object", {"id": "c.1", "v": 1})
    assert result.created is True
    assert await cached.get("object", "c.1") == record
    inner.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_caching_insert_if_absent_existing_still_caches(monkeypatch):
    from jvspatial.db._cache import CachingDatabase

    monkeypatch.setenv("SERVERLESS_MODE", "false")
    inner = MagicMock()
    inner.supports_transactions = False
    stored = {"id": "c.2", "v": 7}
    inner.insert_if_absent = AsyncMock(
        return_value=InsertIfAbsentResult(record=stored, created=False)
    )
    inner.get = AsyncMock(side_effect=AssertionError("should be cache hit"))

    cached = CachingDatabase(inner)
    result = await cached.insert_if_absent("object", {"id": "c.2", "v": 999})
    assert result.created is False
    assert await cached.get("object", "c.2") == stored


# ---------------------------------------------------------------------------
# MongoDB (unit, mocked)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mongodb_insert_one_then_duplicate_finds_existing():
    pytest.importorskip("motor")
    from pymongo.errors import DuplicateKeyError

    from jvspatial.db.mongodb import MongoDB

    db = MongoDB.__new__(MongoDB)
    db._db = MagicMock()
    coll = MagicMock()
    db._db.__getitem__ = MagicMock(return_value=coll)
    db._ensure_connected = AsyncMock()

    async def _run(_name, factory):
        return await factory()

    db._run_with_reconnect = _run

    coll.insert_one = AsyncMock(return_value=None)
    data = {"_id": "m.1", "id": "m.1", "v": 1}
    r1 = await MongoDB.insert_if_absent(db, "object", dict(data))
    assert r1.created is True
    coll.insert_one.assert_awaited()

    coll.insert_one = AsyncMock(side_effect=DuplicateKeyError("dup"))
    coll.find_one = AsyncMock(return_value={"_id": "m.1", "id": "m.1", "v": 1})
    r2 = await MongoDB.insert_if_absent(
        db, "object", {"_id": "m.1", "id": "m.1", "v": 99}
    )
    assert r2.created is False
    assert r2.record["v"] == 1
    coll.find_one.assert_awaited()


# ---------------------------------------------------------------------------
# DynamoDB (unit, mocked) — only if module importable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dynamodb_put_conditional_then_get_on_conflict():
    try:
        from botocore.exceptions import ClientError

        from jvspatial.db.dynamodb import DynamoDB
    except ImportError:
        pytest.skip("dynamodb extras not installed")

    db = DynamoDB.__new__(DynamoDB)
    db._ensure_table_exists = AsyncMock(return_value="tbl")
    db._extract_indexed_fields = MagicMock(return_value={})
    client = MagicMock()
    db._get_client = AsyncMock(return_value=client)

    async def _run(_name, factory):
        return await factory()

    db._run_with_throttle_retry = _run

    client.put_item = AsyncMock(return_value={})
    r1 = await DynamoDB.insert_if_absent(db, "object", {"id": "d.1", "v": 1})
    assert r1.created is True
    put_kwargs = client.put_item.await_args.kwargs
    assert "attribute_not_exists" in put_kwargs.get("ConditionExpression", "")

    err = ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "x"}},
        "PutItem",
    )
    client.put_item = AsyncMock(side_effect=err)
    client.get_item = AsyncMock(
        return_value={
            "Item": {
                "collection": {"S": "object"},
                "id": {"S": "d.1"},
                "data": {"S": '{"id":"d.1","v":1}'},
            }
        }
    )
    r2 = await DynamoDB.insert_if_absent(db, "object", {"id": "d.1", "v": 99})
    assert r2.created is False
    assert r2.record["v"] == 1
