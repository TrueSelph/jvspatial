"""SQLite cross-loop detection (audit §5.10 / SPEC §4.3).

``aiosqlite`` binds its connection to the event loop that opened it.
Reusing a ``SQLiteDB`` instance across loops previously produced an
opaque "Future attached to a different loop" error from inside
``aiosqlite``; the wrapper now detects the binding change and
transparently rebinds to the current loop instead.
"""

import asyncio
import tempfile

import pytest

from jvspatial.db import create_database


@pytest.mark.asyncio
async def test_same_loop_reuse_works():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = create_database("sqlite", db_path=f"{tmpdir}/x.db")
        await db.save("widgets", {"id": "w1", "qty": 1})
        got = await db.get("widgets", "w1")
        assert got is not None
        await db.save("widgets", {"id": "w2", "qty": 2})
        await db.close()


def test_cross_loop_reuse_auto_rebinds():
    """Across loops the connection is silently rebuilt on the active loop."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = create_database("sqlite", db_path=f"{tmpdir}/x.db")

        async def first() -> None:
            await db.save("widgets", {"id": "w1", "qty": 1})

        asyncio.run(first())

        async def second() -> None:
            # Auto-rebind on a new loop — no error.
            await db.save("widgets", {"id": "w2", "qty": 2})
            got = await db.get("widgets", "w2")
            assert got is not None
            await db.close()

        asyncio.run(second())


def test_owning_loop_tracked():
    """After save the SQLiteDB tracks the loop that owns the connection."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = create_database("sqlite", db_path=f"{tmpdir}/x.db")

        async def go() -> None:
            await db.save("widgets", {"id": "w1", "qty": 1})
            # ``_owning_loop`` is private but the contract is part of
            # the cross-loop fix; assert it was populated.
            assert db._owning_loop is asyncio.get_running_loop()
            await db.close()
            assert db._owning_loop is None

        asyncio.run(go())
