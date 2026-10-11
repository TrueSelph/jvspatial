"""Behavioral regressions from the I/O and query audit."""

import json

import pytest

from jvspatial.db import (
    create_database,
    register_database_type,
    unregister_database_type,
)
from jvspatial.db.database import Database, encode_cursor, finalize_find_results
from jvspatial.db.dynamodb import DynamoDB
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.sqlite import SQLiteDB
from jvspatial.runtime.serverless import reset_serverless_mode_cache


@pytest.fixture(params=["json", "sqlite"])
async def store(request, tmp_path):
    db = JsonDB(str(tmp_path)) if request.param == "json" else SQLiteDB(":memory:")
    yield db
    if request.param == "sqlite":
        await db.close()


@pytest.mark.parametrize(
    "sort",
    [
        [("id", -1)],
        [("context.rank", 1)],
        [("context.rank", -1)],
        [("context.rank", 1), ("context.group", -1), ("id", 1)],
    ],
)
async def test_iteration_preserves_complete_order(store, sort):
    rows = [
        {"id": "a", "context": {"rank": 30, "group": 1}},
        {"id": "b", "context": {"rank": 20, "group": 1}},
        {"id": "c", "context": {"rank": 10, "group": 1}},
        {"id": "d", "context": {"rank": 10, "group": 2}},
        {"id": "e", "context": {"rank": None, "group": 1}},
        {"id": "f", "context": {"group": 1}},
    ]
    await store.bulk_save("object", rows)
    effective_sort = (
        sort if any(k == "id" for k, _ in sort) else [*sort, ("id", sort[0][1])]
    )
    expected = finalize_find_results(rows, sort=effective_sort)
    actual = [r async for r in store.find_iter("object", {}, sort=sort, batch_size=1)]
    assert [r["id"] for r in actual] == [r["id"] for r in expected]


async def test_iteration_keeps_user_id_constraint(store):
    await store.bulk_save("object", [{"id": c} for c in "abcdef"])
    rows = [
        r async for r in store.find_iter("object", {"id": {"$lt": "e"}}, batch_size=1)
    ]
    assert [r["id"] for r in rows] == list("abcd")
    resumed = [
        r
        async for r in store.find_iter(
            "object",
            {"id": {"$lt": "e"}},
            batch_size=1,
            cursor=encode_cursor({"id": "b"}),
        )
    ]
    assert [r["id"] for r in resumed] == list("cd")


@pytest.mark.parametrize("size", [0, -1])
async def test_iteration_rejects_invalid_batch_size(store, size):
    with pytest.raises(ValueError, match="batch_size"):
        _ = [r async for r in store.find_iter("object", {}, batch_size=size)]


class StubDB(Database):
    def __init__(self):
        self.native_calls = 0
        self.find_limits = []

    async def save(self, collection, data):
        return data

    async def get(self, collection, id):
        return None

    async def delete(self, collection, id):
        pass

    async def find(self, collection, query, **kwargs):
        self.find_limits.append(kwargs.get("limit"))
        return [{"id": "first"}]

    async def find_iter(self, collection, query, **kwargs):
        self.native_calls += 1
        yield {"id": "native"}

    async def bulk_save(self, collection, records):
        return 0


async def test_first_match_is_bounded():
    db = StubDB()
    assert await db.find_one("object", {}) == {"id": "first"}
    assert db.find_limits == [1]


@pytest.mark.parametrize("observe", [False, True])
async def test_cache_delegates_iteration_and_never_publishes_failed_write(
    monkeypatch, observe
):
    monkeypatch.setenv("SERVERLESS_MODE", "false")
    reset_serverless_mode_cache()
    inner = StubDB()
    register_database_type("audit-test", lambda **kwargs: inner)
    try:
        db = create_database("audit-test", cache_get_size=10, observe=observe)
        assert [r async for r in db.find_iter("object", {})] == [{"id": "native"}]
        assert inner.native_calls == 1
        assert await db.bulk_save("object", [{"id": "failed"}]) == 0
        assert await db.get("object", "failed") is None
    finally:
        unregister_database_type("audit-test")
        reset_serverless_mode_cache()


class StubDynamo(DynamoDB):
    def __init__(self, use_gsi):
        self.use_gsi = use_gsi
        self._indexed_fields = {
            "object": {
                "context.category": {"gsi_name": "category", "attr_name": "category"},
                "context.status": {"gsi_name": "status", "attr_name": "status"},
            }
        }

    def _find_matching_gsi(self, collection, query):
        return super()._find_matching_gsi(collection, query) if self.use_gsi else None

    async def _ensure_table_exists(self, collection):
        return "audit"

    async def _get_client(self):
        return self

    async def _run_with_throttle_retry(self, name, fn):
        return await fn()

    async def query(self, **kwargs):
        if "ExclusiveStartKey" not in kwargs:
            rows = [
                {
                    "id": "wrong",
                    "context": {"category": "alpha", "status": "open", "score": 1},
                }
            ]
            extra = {"LastEvaluatedKey": {"id": {"S": "wrong"}}}
        else:
            rows = [
                {
                    "id": "good",
                    "context": {"category": "alpha", "status": "open", "score": 100},
                }
            ]
            extra = {}
        return {"Items": [{"data": {"S": json.dumps(r)}} for r in rows], **extra}

    scan = query


@pytest.mark.parametrize("use_gsi", [False, True])
async def test_dynamo_partial_pushdown_keeps_residual_across_pages(use_gsi):
    db = StubDynamo(use_gsi)
    rows = await db.find(
        "object",
        {
            "context.category": "alpha",
            "context.status": "open",
            "context.score": {"$gt": 50},
        },
        limit=1,
    )
    assert [r["id"] for r in rows] == ["good"]


async def test_mongo_native_detailed_bulk_reports_failed_record(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from pymongo.errors import BulkWriteError

    from jvspatial.db.mongodb import MongoDB

    db = MongoDB(uri="mongodb://unused", db_name="audit")
    db._db = {
        "object": SimpleNamespace(
            bulk_write=AsyncMock(
                side_effect=BulkWriteError(
                    {
                        "writeErrors": [
                            {"index": 1, "code": 11000, "errmsg": "duplicate"}
                        ],
                        "writeConcernErrors": [],
                        "nMatched": 1,
                        "nUpserted": 0,
                    }
                )
            )
        )
    }
    monkeypatch.setattr(db, "_ensure_connected", AsyncMock())
    result = await db.bulk_save_detailed("object", [{"id": "a"}, {"id": "b"}])
    assert result.saved == 1
    assert result.failed_ids == ["b"]
    assert db._db["object"].bulk_write.await_count == 1


async def test_dynamo_native_detailed_bulk_reports_unprocessed_ids(monkeypatch):
    from unittest.mock import AsyncMock

    db = StubDynamo(True)

    async def write(**kwargs):
        return {
            "UnprocessedItems": {
                "audit": [
                    r
                    for r in kwargs["RequestItems"]["audit"]
                    if r["PutRequest"]["Item"]["id"]["S"] == "b"
                ]
            }
        }

    monkeypatch.setattr(db, "batch_write_item", write, raising=False)
    monkeypatch.setattr("jvspatial.db.dynamodb.asyncio.sleep", AsyncMock())
    result = await db.bulk_save_detailed("object", [{"id": "a"}, {"id": "b"}])
    assert result.saved == 1
    assert result.failed_ids == ["b"]


async def test_dynamo_scan_page_residual_and_native_resume(monkeypatch):
    from unittest.mock import AsyncMock

    db = StubDynamo(False)
    key = {"collection": {"S": "object"}, "id": {"S": "low"}}
    scan = AsyncMock(
        side_effect=[
            {
                "Items": [{"data": {"S": '{"id":"low","context":{"score":1}}'}}],
                "LastEvaluatedKey": key,
                "ScannedCount": 1,
            },
            {
                "Items": [{"data": {"S": '{"id":"high","context":{"score":100}}'}}],
                "ScannedCount": 1,
            },
        ]
    )
    monkeypatch.setattr(db, "scan", scan, raising=False)
    query = {"context.score": {"$gt": 50}}
    rows, cursor = await db.scan_page("object", query, page_size=1)
    assert rows == [] and cursor
    rows, end = await db.scan_page("object", query, page_size=1, cursor=cursor)
    assert [r["id"] for r in rows] == ["high"] and end is None
    assert scan.call_args.kwargs["ExclusiveStartKey"] == key
    with pytest.raises(ValueError, match="match"):
        await db.scan_page("other", query, cursor=cursor)
