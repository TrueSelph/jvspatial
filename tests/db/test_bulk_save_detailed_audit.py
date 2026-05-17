"""BulkSaveResult / bulk_save_detailed semantics (audit §5.6 / §5.7).

The legacy ``bulk_save`` returned a single ``int`` so partial-failure
backends (JsonDB, DynamoDB) could silently drop records without callers
noticing. ``bulk_save_detailed`` returns a structured
:class:`BulkSaveResult` with ``attempted`` / ``saved`` / ``failed_ids``.
"""

import tempfile
import uuid

import pytest

from jvspatial.db import create_database
from jvspatial.db.database import BulkSaveResult


@pytest.fixture
async def jsondb():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = create_database("json", base_path=f"{tmpdir}/{uuid.uuid4().hex}")
        yield db


def test_bulk_save_result_dataclass_fields():
    r = BulkSaveResult(attempted=3, saved=3)
    assert r.attempted == 3
    assert r.saved == 3
    assert r.failed_ids == []
    assert r.all_saved is True

    partial = BulkSaveResult(attempted=3, saved=2, failed_ids=["x"])
    assert partial.all_saved is False


@pytest.mark.asyncio
async def test_bulk_save_detailed_returns_structured_result(jsondb):
    records = [{"id": f"r{i}", "n": i} for i in range(5)]
    result = await jsondb.bulk_save_detailed("widgets", records)
    assert isinstance(result, BulkSaveResult)
    assert result.attempted == 5
    assert result.saved == 5
    assert result.failed_ids == []
    assert result.all_saved


@pytest.mark.asyncio
async def test_bulk_save_int_still_returned_for_back_compat(jsondb):
    records = [{"id": f"r{i}", "n": i} for i in range(4)]
    saved_count = await jsondb.bulk_save("widgets", records)
    assert saved_count == 4


@pytest.mark.asyncio
async def test_bulk_save_missing_id_includes_index(jsondb):
    records = [
        {"id": "r0", "n": 0},
        {"n": 1},  # missing id at index 1
        {"id": "r2", "n": 2},
    ]
    with pytest.raises(ValueError, match="index 1"):
        await jsondb.bulk_save_detailed("widgets", records)
