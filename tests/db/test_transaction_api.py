"""Shared transaction APIs retain reads on adapter transaction handles."""

from typing import Any

import pytest

from jvspatial.db.transaction import MongoDBTransaction


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    def sort(self, _sort):
        return self

    def limit(self, limit):
        self.rows = self.rows[:limit]
        return self

    async def to_list(self, length=None):
        return self.rows if length is None else self.rows[:length]


class _Collection:
    def __init__(self):
        self.rows = {
            "one": {"_id": "one", "id": "one", "rank": 1},
            "two": {"_id": "two", "id": "two", "rank": 2},
        }
        self.calls = []

    def find(self, query, *, session):
        self.calls.append(("find", query, session))
        rows = list(self.rows.values())
        for key, value in query.items():
            if key.startswith("$"):
                continue
            if isinstance(value, dict) and "$in" in value:
                rows = [row for row in rows if row.get(key) in value["$in"]]
            else:
                rows = [row for row in rows if row.get(key) == value]
        return _Cursor(rows)

    async def find_one(self, query, *, session):
        self.calls.append(("find_one", query, session))
        return self.rows.get(query.get("_id"))


class _DB:
    def __init__(self, collection):
        self.collection = collection

    def __getitem__(self, _name):
        return self.collection


@pytest.mark.asyncio
async def test_mongo_transaction_inherits_consistent_read_contract():
    session: Any = object()
    collection = _Collection()
    tx = MongoDBTransaction("txn", session, _DB(collection))

    assert await tx.find_one("node", {"id": "one"}) == collection.rows["one"]
    assert await tx.count("node") == 2
    assert await tx.find_ids("node", {}, limit=1, sort=[("rank", 1)]) == ["one"]
    assert await tx.find_many("node", ["two", "one", "two"]) == {
        "two": collection.rows["two"],
        "one": collection.rows["one"],
    }
    assert collection.calls
    assert all(call[-1] is session for call in collection.calls)
