"""Unit tests for PostgresTransaction.find_one_and_update without a live DB."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from jvspatial.db.postgres import PostgresTransaction


class _FakeRow(dict):
    def __getitem__(self, key: Any) -> Any:
        if key == "data":
            return dict(self)
        if key == "ctid":
            return "(0,1)"
        return super().__getitem__(key)


@pytest.mark.asyncio
async def test_transaction_exposes_find_one_and_update() -> None:
    """Public transaction handle must expose compare-and-set."""
    assert hasattr(PostgresTransaction, "find_one_and_update")
    assert callable(PostgresTransaction.find_one_and_update)


@pytest.mark.asyncio
async def test_transaction_find_one_and_update_uses_held_connection() -> None:
    """CAS must run on the held connection with FOR UPDATE, no nested txn."""
    db = MagicMock()
    db.schema_name = "public"
    db._bootstrap_collection = AsyncMock()
    db._split_payload = MagicMock(
        return_value=("o.WorkItem.1", "WorkItem", None, '{"id":"o.WorkItem.1"}')
    )
    db._record_from_row = MagicMock(
        side_effect=lambda row: {
            "id": "o.WorkItem.1",
            "entity": "WorkItem",
            "context": {"status": "queued", "lease_fence": 0},
        }
    )
    db._validate_insert_if_absent = MagicMock()

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(
        return_value=_FakeRow(
            id="o.WorkItem.1",
            entity="WorkItem",
            context={"status": "queued", "lease_fence": 0},
        )
    )
    conn.execute = AsyncMock()

    txn = PostgresTransaction(db, conn, transaction=MagicMock())
    updated = await txn.find_one_and_update(
        "o",
        {"id": "o.WorkItem.1", "context.status": "queued", "context.lease_fence": 0},
        {
            "$set": {
                "context.status": "running",
                "context.lease_fence": 1,
                "context.lease_token": "tok-a",
            }
        },
    )

    assert updated is not None
    assert updated["context"]["status"] == "running"
    assert updated["context"]["lease_fence"] == 1
    assert updated["context"]["lease_token"] == "tok-a"
    assert conn.fetchrow.await_count == 1
    sql = conn.fetchrow.await_args.args[0]
    assert "FOR UPDATE" in sql
    assert conn.execute.await_count == 1
    assert conn.transaction.await_count == 0
    assert conn.transaction.call_count == 0


@pytest.mark.asyncio
async def test_transaction_find_one_and_update_stale_match_returns_none() -> None:
    """Stale expected-state query must not write."""
    db = MagicMock()
    db.schema_name = "public"
    db._bootstrap_collection = AsyncMock()
    db._record_from_row = MagicMock()

    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=None)
    conn.execute = AsyncMock()

    txn = PostgresTransaction(db, conn, transaction=MagicMock())
    updated = await txn.find_one_and_update(
        "o",
        {"id": "o.WorkItem.1", "context.lease_fence": 1},
        {"$set": {"context.status": "succeeded"}},
    )

    assert updated is None
    conn.execute.assert_not_awaited()
