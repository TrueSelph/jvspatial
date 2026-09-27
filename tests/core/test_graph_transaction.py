"""graph_transaction binds Node writes to the backend transaction handle."""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from jvspatial.core.context import (
    TransactionUnavailable,
    get_default_context,
    graph_transaction,
)
from jvspatial.core.entities import Edge, Node


class _FakeTxn:
    def __init__(self) -> None:
        self.saved: List[Dict[str, Any]] = []

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        self.saved.append({"collection": collection, **data})
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        return next((row for row in self.saved if row.get("id") == id), None)

    async def find(self, collection: str, query: Dict[str, Any], **_kwargs) -> list:
        return []

    async def delete(self, collection: str, id: str) -> bool:
        return False


class _FakeDB:
    def __init__(self) -> None:
        self.txn = _FakeTxn()
        self.committed = False
        self.rolled_back = False

    async def begin_transaction(self) -> _FakeTxn:
        return self.txn

    async def commit_transaction(self, transaction: _FakeTxn) -> None:
        assert transaction is self.txn
        self.committed = True

    async def rollback_transaction(self, transaction: _FakeTxn) -> None:
        assert transaction is self.txn
        self.rolled_back = True


class Folder(Node):
    name: str = ""


class Note(Node):
    title: str = ""


class Contains(Edge):
    pass


@pytest.mark.asyncio
async def test_graph_transaction_writes_through_the_handle_and_commits() -> None:
    db = _FakeDB()
    async with graph_transaction(db) as ctx:
        assert ctx.database is db.txn
        assert get_default_context().database is db.txn
        await Folder.create(name="inbox")
    assert db.committed is True
    assert db.rolled_back is False
    assert any(row.get("collection") == "node" for row in db.txn.saved)


@pytest.mark.asyncio
async def test_graph_transaction_rolls_back_on_error() -> None:
    db = _FakeDB()
    with pytest.raises(RuntimeError, match="boom"):
        async with graph_transaction(db):
            await Folder.create(name="inbox")
            raise RuntimeError("boom")
    assert db.committed is False
    assert db.rolled_back is True


@pytest.mark.asyncio
async def test_graph_transaction_refuses_a_store_without_begin() -> None:
    with pytest.raises(TransactionUnavailable):
        async with graph_transaction(object()):
            pass
