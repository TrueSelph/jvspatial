"""Projected reads preserve filtering, ordering, missing/null and backend parity."""

import pytest

from jvspatial.db import create_database
from tests.db.test_postgres_integration import pg_db as pg_db

pytestmark = pytest.mark.asyncio


async def check_projection(db):
    for row in (
        {
            "id": "one",
            "entity": "Record",
            "context": {
                "name": "Beta",
                "score": 7,
                "nullable": None,
                "tags": ["a", "b"],
                "weird-key": "safe",
                "body": "x" * 64000,
            },
        },
        {"id": "two", "entity": "Record", "context": {"name": "Alpha", "score": 2}},
        {"id": "three", "entity": "Record", "context": {"name": "Other", "score": 0}},
    ):
        await db.save("object", row)
    rows = await db.find_projected(
        "object",
        {"context.score": {"$gte": 2}},
        fields=["id", "context.name", "context.nullable"],
        sort=[("context.score", -1)],
        limit=2,
    )
    assert rows == [
        {"id": "one", "context.name": "Beta", "context.nullable": None},
        {"id": "two", "context.name": "Alpha"},
    ]
    assert await db.find_projected(
        "object", {"id": "one"}, fields=["context.tags.1"]
    ) == [{"context.tags.1": "b"}]
    assert await db.find_projected(
        "object", {"id": "one"}, fields=["context.weird-key"]
    ) == [{"context.weird-key": "safe"}]
    assert await db.find_projected("object", {}, fields=["id"], limit=0) == []
    for fields in ([], ["context..name"], "id"):
        with pytest.raises(ValueError):
            await db.find_projected("object", {}, fields=fields)


async def test_portable_projection(tmp_path):
    db = create_database("json", base_path=str(tmp_path))
    await check_projection(db)


async def test_postgres_projection(pg_db):
    await check_projection(pg_db)


async def test_postgres_residual_filters_run_before_projection_and_limit(
    pg_db, monkeypatch
):
    from jvspatial.db import postgres

    await pg_db.save("object", {"id": "a", "context": {"score": 1}})
    await pg_db.save("object", {"id": "b", "context": {"score": 3}})
    monkeypatch.setattr(postgres, "translate_query", lambda _query: None)
    rows = await pg_db.find_projected(
        "object",
        {"context.score": {"$gte": 2}},
        fields=["id"],
        limit=1,
        sort=[("context.score", -1)],
    )
    assert rows == [{"id": "b"}]


async def test_projection_retains_transaction_visibility_and_rollback(pg_db):
    from jvspatial.core.context import graph_transaction

    with pytest.raises(RuntimeError, match="abort"):
        async with graph_transaction(pg_db) as context:
            await context.database.save(
                "object", {"id": "uncommitted", "context": {"value": 42}}
            )
            assert await context.database.find_projected(
                "object", {}, fields=["id", "context.value"]
            ) == [{"id": "uncommitted", "context.value": 42}]
            raise RuntimeError("abort")
    assert await pg_db.find_projected("object", {}, fields=["id"]) == []


async def test_wrappers_do_not_cache_projection_as_full_record(tmp_path):
    from jvspatial.db._cache import CachingDatabase
    from jvspatial.db._observable import ObservableDatabase

    base = create_database("json", base_path=str(tmp_path))
    wrapped = ObservableDatabase(CachingDatabase(base))
    await wrapped.save(
        "object", {"id": "whole", "context": {"value": "kept", "body": "complete"}}
    )
    assert await wrapped.find_projected("object", {}, fields=["id"]) == [
        {"id": "whole"}
    ]
    assert (await wrapped.get("object", "whole"))["context"]["body"] == "complete"


async def test_observable_projection_supports_legacy_duck_adapter():
    from jvspatial.db._observable import ObservableDatabase

    class Legacy:
        async def find(self, collection, query, *, limit=None, sort=None):
            return [{"id": "legacy", "context": {"value": None}}]

    wrapped = ObservableDatabase(Legacy())
    assert await wrapped.find_projected(
        "object", {}, fields=["id", "context.value", "missing"]
    ) == [{"id": "legacy", "context.value": None}]


async def test_portable_projection_does_not_alias_input_containers():
    from jvspatial.db.database import project_record_fields

    original = {"context": {"values": [1, {"nested": 2}]}}
    projected = project_record_fields(original, ["context.values"])
    projected["context.values"][1]["nested"] = 3
    assert original["context"]["values"][1]["nested"] == 2
