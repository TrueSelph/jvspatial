"""Default ``find_one_and_update`` / ``find_one_and_delete`` must honor
both ``_id`` and ``id`` query keys.

Audit §5.3 / SPEC §4.1: non-Mongo backends (JsonDB, SQLite, DynamoDB)
persist records keyed by ``id`` only. Callers that follow the
Mongo-style convention of querying by ``_id`` were silently missed by
the default compound-op implementation, which fed the query into
``QueryEngine.match`` against records that have no ``_id`` field.

The default impls now normalize ``_id`` → ``id`` before matching.
"""

import tempfile
import uuid

import pytest

from jvspatial.db import create_database


@pytest.fixture
async def jsondb():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = create_database("json", base_path=f"{tmpdir}/{uuid.uuid4().hex}")
        yield db


@pytest.mark.asyncio
async def test_find_one_and_update_matches_by_underscored_id(jsondb):
    await jsondb.save("widgets", {"id": "w1", "qty": 1})
    out = await jsondb.find_one_and_update(
        "widgets", {"_id": "w1"}, {"$set": {"qty": 2}}
    )
    assert out is not None
    assert out["qty"] == 2
    # Side-effect on disk reflects the update.
    fresh = await jsondb.get("widgets", "w1")
    assert fresh["qty"] == 2


@pytest.mark.asyncio
async def test_find_one_and_update_matches_by_id_unchanged(jsondb):
    await jsondb.save("widgets", {"id": "w2", "qty": 5})
    out = await jsondb.find_one_and_update(
        "widgets", {"id": "w2"}, {"$set": {"qty": 7}}
    )
    assert out is not None
    assert out["qty"] == 7


@pytest.mark.asyncio
async def test_find_one_and_delete_matches_by_underscored_id(jsondb):
    await jsondb.save("widgets", {"id": "w3", "qty": 9})
    deleted = await jsondb.find_one_and_delete("widgets", {"_id": "w3"})
    assert deleted is not None
    assert deleted["id"] == "w3"
    assert await jsondb.get("widgets", "w3") is None


@pytest.mark.asyncio
async def test_find_one_and_update_upsert_with_underscored_id(jsondb):
    out = await jsondb.find_one_and_update(
        "widgets",
        {"_id": "w_new"},
        {"$set": {"qty": 42}},
        upsert=True,
    )
    assert out is not None
    assert out["id"] == "w_new"
    assert out["qty"] == 42
    persisted = await jsondb.get("widgets", "w_new")
    assert persisted is not None
