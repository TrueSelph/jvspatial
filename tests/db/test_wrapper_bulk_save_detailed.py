"""Wrapping adapters must forward ``bulk_save_detailed`` to the backend.

``ObservableDatabase`` and ``CachingDatabase`` subclass ``Database``, whose
default ``bulk_save_detailed`` is a serial ``save`` loop. Without an explicit
override that default shadows ``__getattr__`` forwarding, so a wrapped
Postgres ``COPY`` silently became one round trip per record.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from jvspatial.db._cache import CachingDatabase
from jvspatial.db._observable import ObservableDatabase
from jvspatial.db.database import BulkSaveResult
from jvspatial.observability import db_op_counter

RECORDS = [{"id": f"r{i}", "entity": "E", "context": {}} for i in range(3)]


def _inner() -> MagicMock:
    inner = MagicMock()
    inner.supports_transactions = False
    inner.bulk_save_detailed = AsyncMock(
        return_value=BulkSaveResult(attempted=3, saved=2, failed_ids=["r2"])
    )
    inner.save = AsyncMock(side_effect=AssertionError("per-record save used"))
    return inner


@pytest.mark.asyncio
async def test_observable_forwards_bulk_save_detailed_as_one_op():
    inner = _inner()
    token = db_op_counter.set(0)
    try:
        result = await ObservableDatabase(inner).bulk_save_detailed("node", RECORDS)
        assert db_op_counter.get() == 1
    finally:
        db_op_counter.reset(token)
    assert result.saved == 2
    inner.bulk_save_detailed.assert_awaited_once_with("node", RECORDS)


@pytest.mark.asyncio
async def test_caching_forwards_bulk_save_detailed_and_skips_failed_ids(monkeypatch):
    monkeypatch.setenv("SERVERLESS_MODE", "false")
    inner = _inner()
    inner.get = AsyncMock(return_value=None)
    cached = CachingDatabase(inner)
    result = await cached.bulk_save_detailed("node", RECORDS)
    inner.bulk_save_detailed.assert_awaited_once_with("node", RECORDS)
    assert result.failed_ids == ["r2"]
    assert await cached.get("node", "r0") == RECORDS[0]  # served from cache
    assert await cached.get("node", "r2") is None  # failed id not cached
    inner.get.assert_awaited_once_with("node", "r2")
