"""Deterministic work bounds, independent of machine timing."""

import asyncio
from unittest.mock import AsyncMock

from jvspatial.core import GraphContext, Object
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.sqlite import SQLiteDB


async def test_json_iteration_scans_each_record_once(tmp_path, monkeypatch):
    db = JsonDB(str(tmp_path))
    await db.bulk_save("object", [{"id": f"r{i:03}"} for i in range(123)])
    load = AsyncMock(wraps=db._async_load_record)
    monkeypatch.setattr(db, "_async_load_record", load)
    rows = [r async for r in db.find_iter("object", {}, batch_size=7)]
    assert len(rows) == 123
    assert load.await_count == 123


async def test_json_scan_bounds_inflight_reads(tmp_path, monkeypatch):
    db = JsonDB(str(tmp_path))
    await db.bulk_save("object", [{"id": f"r{i:03}"} for i in range(123)])
    active = peak = 0
    original = db._async_load_record

    async def load(path):
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0)
        try:
            return await original(path)
        finally:
            active -= 1

    monkeypatch.setattr(db, "_async_load_record", load)
    assert await db.count("object", {"id": {"$exists": True}}) == 123
    assert peak <= 32


async def test_sqlite_id_pages_use_primary_key(tmp_path):
    db = SQLiteDB(str(tmp_path / "db.sqlite"))
    try:
        await db.bulk_save("object", [{"id": f"r{i:03}"} for i in range(123)])
        conn = await db._get_connection()
        sqls = []
        await conn.set_trace_callback(sqls.append)
        await db.find("object", {"id": {"$gt": "r010"}}, sort=[("id", 1)], limit=7)
        await conn.set_trace_callback(None)
        query = next(s for s in sqls if s.startswith("SELECT"))
        cur = await conn.execute("EXPLAIN QUERY PLAN " + query)
        plan = " ".join(str(r[3]) for r in await cur.fetchall())
        await cur.close()
        assert "id>?" in plan
        assert "TEMP B-TREE" not in plan
    finally:
        await db.close()


async def test_entity_batch_uses_one_native_transaction(tmp_path):
    class BatchRecord(Object):
        value: int = 0

    db = SQLiteDB(str(tmp_path / "db.sqlite"))
    try:
        ctx = GraphContext(database=db, enable_performance_monitoring=False)
        conn = await db._get_connection()
        statements = []
        await conn.set_trace_callback(statements.append)
        entities = [BatchRecord(value=i) for i in range(30)]
        assert await ctx.save_batch(entities) == entities
        await conn.set_trace_callback(None)
        assert sum(s == "COMMIT" for s in statements) == 1
        assert await db.count("object") == 30
    finally:
        await db.close()
