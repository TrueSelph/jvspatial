"""Shared transaction APIs retain reads on adapter transaction handles."""

from typing import Any

import pytest

from jvspatial.db.transaction import MongoDBTransaction


class _Cursor:
    def __init__(self, rows, projection):
        self.rows = list(rows)
        self.projection = projection

    def sort(self, spec):
        for field, direction in reversed(spec or []):
            self.rows.sort(
                key=lambda row, field=field: row.get(field), reverse=direction < 0
            )
        return self

    def skip(self, count):
        self.rows = self.rows[count:]
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    async def to_list(self, length=None):
        rows = self.rows if length is None else self.rows[:length]
        if not self.projection:
            return rows
        return [
            {key: row.get(key) for key in self.projection} | {"_id": row["_id"]}
            for row in rows
        ]


class _Collection:
    def __init__(self):
        self.rows = {
            "one": {"_id": "one", "id": "one", "rank": 1, "label": "first"},
            "two": {"_id": "two", "id": "two", "rank": 2, "label": "second"},
        }
        self.calls = []

    def _match(self, query):
        rows = list(self.rows.values())
        for key, value in query.items():
            if key.startswith("$"):
                continue
            if isinstance(value, dict) and "$in" in value:
                rows = [row for row in rows if row.get(key) in value["$in"]]
            else:
                rows = [row for row in rows if row.get(key) == value]
        return rows

    def find(self, query, projection=None, *, session):
        self.calls.append(("find", query, projection, session))
        return _Cursor(self._match(query), projection)

    async def find_one(self, query, *, session):
        self.calls.append(("find_one", query, session))
        rows = self._match(query)
        return rows[0] if rows else None

    async def count_documents(self, query, *, session):
        self.calls.append(("count_documents", query, session))
        return len(self._match(query))


class _DB:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, _name):
        return self.collection


@pytest.mark.asyncio
async def test_mongo_transaction_inherits_consistent_read_contract():
    """Session reads, including projections, stay on the Mongo transaction."""
    session: Any = object()
    collection = _Collection()
    tx = MongoDBTransaction("txn", session, _DB(collection))

    assert await tx.find_one("node", {"id": "one"}) == collection.rows["one"]
    assert await tx.count("node") == 2
    before = len(collection.calls)
    assert await tx.find_ids("node", {}, limit=0) == []
    assert len(collection.calls) == before
    assert await tx.find_ids("node", {}, limit=1, sort=[("rank", 1)]) == ["one"]
    assert await tx.find_many("node", ["two", "one", "two"]) == {
        "two": collection.rows["two"],
        "one": collection.rows["one"],
    }
    assert await tx.find_projected("node", {"id": "one"}, fields=["label"]) == [
        {"label": "first"}
    ]
    assert collection.calls
    assert all(call[-1] is session for call in collection.calls)
    assert any(call[0] == "count_documents" for call in collection.calls)
    assert any(
        call[0] == "find" and call[1].get("_id", {}).get("$in") == ["two", "one"]
        for call in collection.calls
    )


@pytest.mark.asyncio
async def test_transaction_context_rolls_back_on_cancellation():
    """Cancellation aborts the native handle rather than leaving it open."""
    import asyncio
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from jvspatial.db.transaction import transaction_context

    tx = object()
    db = SimpleNamespace(
        begin_transaction=AsyncMock(return_value=tx),
        commit_transaction=AsyncMock(),
        rollback_transaction=AsyncMock(),
    )
    with pytest.raises(asyncio.CancelledError):
        async with transaction_context(db) as opened:
            assert opened is tx
            raise asyncio.CancelledError
    db.commit_transaction.assert_not_awaited()
    db.rollback_transaction.assert_awaited_once_with(tx)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["commit", "rollback"])
@pytest.mark.parametrize("async_end", [True, False])
async def test_mongo_transaction_ends_session_for_both_driver_shapes(action, async_end):
    """Both Motor and PyMongo asynchronous sessions actually finish cleanup."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock, Mock

    from jvspatial.db.mongodb import MongoDB

    end = AsyncMock() if async_end else Mock()
    tx = SimpleNamespace(
        commit=AsyncMock(),
        rollback=AsyncMock(),
        session=SimpleNamespace(end_session=end),
    )
    db = object.__new__(MongoDB)
    await getattr(db, f"{action}_transaction")(tx)
    getattr(tx, action).assert_awaited_once()
    if async_end:
        end.assert_awaited_once()
    else:
        end.assert_called_once()
