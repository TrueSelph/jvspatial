"""Tests for jvspatial.db.work_claim helpers."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from jvspatial.db.work_claim import (
    _CLAIM_FIELD,
    _CLAIM_UNTIL_FIELD,
    claim_record,
    delete_claimed_record,
    release_claim,
)


def _make_db(doc=None):
    """Build a mock Database that returns *doc* from find_one_and_update/find_one_and_delete."""
    db = AsyncMock()
    db.find_one_and_update.return_value = doc
    db.find_one_and_delete.return_value = doc
    return db


@pytest.mark.asyncio
async def test_claim_record_returns_stripped_doc_and_token():
    now = time.time()
    raw = {
        "_id": "rec-1",
        "payload": "hello",
        "_jv_claim": "old-token",
        "_jv_claim_until": now - 100,
    }
    db = _make_db(raw)
    doc, token = await claim_record(db, "my_col", "rec-1")
    assert doc == {"_id": "rec-1", "payload": "hello"}
    assert token and len(token) == 32  # hex token
    db.find_one_and_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_claim_record_returns_none_when_not_found():
    db = _make_db(None)
    doc, token = await claim_record(db, "my_col", "rec-1")
    assert doc is None
    assert token is None


@pytest.mark.asyncio
async def test_claim_record_returns_none_on_exception():
    db = AsyncMock()
    db.find_one_and_update.side_effect = RuntimeError("boom")
    doc, token = await claim_record(db, "col", "id")
    assert doc is None and token is None


@pytest.mark.asyncio
async def test_release_claim_calls_unset():
    db = AsyncMock()
    db.find_one_and_update.return_value = {"_id": "x"}
    await release_claim(db, "col", "id", "tok")
    args = db.find_one_and_update.call_args
    assert args[0][0] == "col"
    update = args[0][2]
    assert "$unset" in update
    assert _CLAIM_FIELD in update["$unset"]
    assert _CLAIM_UNTIL_FIELD in update["$unset"]


@pytest.mark.asyncio
async def test_release_claim_does_not_raise_on_failure():
    db = AsyncMock()
    db.find_one_and_update.side_effect = RuntimeError("nope")
    await release_claim(db, "col", "id", "tok")  # should not raise


@pytest.mark.asyncio
async def test_delete_claimed_record_success():
    db = _make_db({"_id": "x"})
    assert await delete_claimed_record(db, "col", "x", "tok") is True
    db.find_one_and_delete.assert_awaited_once()
    query = db.find_one_and_delete.call_args[0][1]
    assert query["_id"] == "x"
    assert query[_CLAIM_FIELD] == "tok"


@pytest.mark.asyncio
async def test_delete_claimed_record_not_found():
    db = _make_db(None)
    assert await delete_claimed_record(db, "col", "x", "tok") is False


@pytest.mark.asyncio
async def test_delete_claimed_record_exception():
    db = AsyncMock()
    db.find_one_and_delete.side_effect = RuntimeError("err")
    assert await delete_claimed_record(db, "col", "x", "tok") is False


@pytest.mark.asyncio
async def test_custom_stale_seconds(monkeypatch):
    from jvspatial.env import clear_load_env_cache

    monkeypatch.setenv("JVSPATIAL_WORK_CLAIM_STALE_SECONDS", "42")
    clear_load_env_cache()
    now = time.time()
    raw = {"_id": "r", "data": 1}
    db = _make_db(raw)
    doc, token = await claim_record(db, "col", "r")
    update = db.find_one_and_update.call_args[0][2]
    until = update["$set"][_CLAIM_UNTIL_FIELD]
    assert until >= now + 40
    assert until <= now + 45


def test_top_level_exports():
    from jvspatial import claim_record, delete_claimed_record, release_claim

    assert callable(claim_record)
    assert callable(release_claim)
    assert callable(delete_claimed_record)
