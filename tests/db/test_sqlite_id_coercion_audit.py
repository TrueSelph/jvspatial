"""SQLite ``save()`` id coercion to ``str`` (audit §5.20)."""

import tempfile

import pytest

from jvspatial.db.sqlite import SQLiteDB


@pytest.mark.asyncio
async def test_int_id_roundtrips_through_save_and_get():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = SQLiteDB(db_path=f"{tmpdir}/x.db")
        await db.save("widgets", {"id": 42, "name": "alpha"})
        # The persisted id is stringified — get() by the str form works.
        got = await db.get("widgets", "42")
        assert got is not None
        assert got["name"] == "alpha"
        await db.close()
