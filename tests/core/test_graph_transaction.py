"""graph_transaction binds Node writes to the backend transaction handle."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List, Optional, cast
from unittest.mock import AsyncMock

import pytest

from jvspatial.core.annotations import attribute
from jvspatial.core.context import (
    GraphContext,
    TransactionUnavailable,
    begin_request_identity_map,
    end_request_identity_map,
    get_default_context,
    graph_transaction,
    scoped_default_context_async,
)
from jvspatial.core.entities import Edge, Node
from jvspatial.core.entities.object import Object
from jvspatial.db.database import Database


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


class _StoreTxn:
    def __init__(self, rows: Dict[str, Dict[str, Any]]) -> None:
        self.rows = deepcopy(rows)

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        self.rows[data["id"]] = deepcopy(data)
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        return deepcopy(self.rows.get(id))

    async def delete(self, collection: str, id: str) -> bool:
        return self.rows.pop(id, None) is not None


class _StoreDB(_StoreTxn):
    def __init__(self) -> None:
        super().__init__({})

    async def begin_transaction(self) -> _StoreTxn:
        return _StoreTxn(self.rows)

    async def commit_transaction(self, transaction: _StoreTxn) -> None:
        self.rows = transaction.rows

    async def rollback_transaction(self, transaction: _StoreTxn) -> None:
        pass


class Folder(Node):
    name: str = ""


class Note(Node):
    title: str = ""


class Contains(Edge):
    pass


class IndexedRecord(Object):
    lookup: str = attribute(default="", indexed=True)


class _IndexDB:
    def __init__(self) -> None:
        self.created = 0

    async def create_index(self, *_args: Any, **_kwargs: Any) -> None:
        self.created += 1


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


@pytest.mark.asyncio
async def test_graph_transaction_invalidates_parent_cache_after_commit() -> None:
    db = _StoreDB()
    parent = GraphContext(cast(Database, db))
    async with scoped_default_context_async(parent):
        identity_token = begin_request_identity_map()
        try:
            folder = await Folder.create(name="before")
            assert (await Folder.get(folder.id)).name == "before"
            async with graph_transaction(db):
                inside = await Folder.get(folder.id)
                inside.name = "after"
                await inside.save()
            assert (await Folder.get(folder.id)).name == "after"
        finally:
            end_request_identity_map(identity_token)


@pytest.mark.asyncio
async def test_graph_transaction_rollback_does_not_leak_cached_mutation() -> None:
    db = _StoreDB()
    parent = GraphContext(cast(Database, db))
    async with scoped_default_context_async(parent):
        identity_token = begin_request_identity_map()
        try:
            folder = await Folder.create(name="before")
            assert (await Folder.get(folder.id)).name == "before"
            with pytest.raises(RuntimeError, match="abort"):
                async with graph_transaction(db):
                    inside = await Folder.get(folder.id)
                    inside.name = "rolled back"
                    await inside.save()
                    raise RuntimeError("abort")
            assert (await Folder.get(folder.id)).name == "before"
        finally:
            end_request_identity_map(identity_token)


@pytest.mark.asyncio
async def test_index_setup_is_scoped_to_database_instance(monkeypatch) -> None:
    monkeypatch.setenv("JVSPATIAL_AUTO_CREATE_INDEXES", "true")
    first, second = _IndexDB(), _IndexDB()
    for database in (first, first, second):
        await GraphContext(cast(Database, database)).ensure_indexes(IndexedRecord)
    assert first.created > 0
    assert second.created == first.created
