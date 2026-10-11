"""Standalone audit probes; no application data or production services required.

Run from repository root with PYTHONPATH=. .venv/bin/python <this file>.
Optional: AUDIT_POSTGRES_DSN must point to a disposable database; this script
creates and drops its own randomly named schema. JSON/SQLite use temp storage.
Timings exclude seed/setup and are local observations, not service-level claims.
"""

import asyncio
import json
import os
import platform
import statistics
import tempfile
import time
import uuid
from collections import Counter
from types import SimpleNamespace
from typing import Any

from jvspatial.core import GraphContext, Object
from jvspatial.core.context import scoped_default_context
from jvspatial.core.pager import ObjectPager
from jvspatial.db import (
    create_database,
    register_database_type,
    unregister_database_type,
)
from jvspatial.db.database import Database
from jvspatial.db.dynamodb import DynamoDB
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.sqlite import SQLiteDB
from jvspatial.storage.interfaces.s3 import S3FileInterface


class AuditRecord(Object):
    """Declare a record used only by disposable audit workloads."""

    value: int = 0
    group: int = 0
    payload: str = ""


async def timed(fn, repeats=7):
    """Measure warmed operation durations over repeated samples."""
    await fn()  # warm-up
    samples = []
    for _ in range(repeats):
        start = time.perf_counter()
        await fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {
        "median_ms": round(statistics.median(samples), 3),
        "min_ms": round(min(samples), 3),
        "max_ms": round(max(samples), 3),
        "samples": len(samples),
    }


async def shared_probes(db, n=20000):
    """Measure common query and write workloads for one backend."""
    records = [
        {
            "id": f"audit-{i:08}",
            "entity": "AuditRecord",
            "context": {"value": i, "group": i % 10, "payload": "x" * 256},
        }
        for i in range(n)
    ]
    await db.bulk_save("object", records)
    q = {"entity": "AuditRecord"}
    result = {
        "records": n,
        "find_one": await timed(lambda: db.find_one("object", q)),
        "find_limit_1": await timed(lambda: db.find("object", q, limit=1)),
        "id_page_50": await timed(
            lambda: db.find(
                "object", {"id": {"$gt": "audit-00010000"}}, sort=[("id", 1)], limit=50
            )
        ),
    }
    calls = []
    original_find = db.find

    async def counted_find(*args: Any, **kwargs: Any):
        rows = await original_find(*args, **kwargs)
        calls.append({"limit": kwargs.get("limit"), "returned": len(rows)})
        return rows

    db.find = counted_find
    await db.find_one("object", q)
    result["find_one_calls"] = list(calls)
    calls.clear()
    ctx = GraphContext(database=db, enable_performance_monitoring=False)
    with scoped_default_context(ctx):
        page = await ObjectPager(AuditRecord, page_size=50).get_page(200)
    result["pager_200"] = {"returned": len(page), "find_calls": list(calls)}
    db.find = original_find

    entities = [AuditRecord(value=i) for i in range(200)]
    payloads = [await entity.export() for entity in entities]
    result["save_batch_200"] = await timed(lambda: ctx.save_batch(entities), 5)
    result["bulk_save_200"] = await timed(lambda: db.bulk_save("object", payloads), 5)
    result["bulk_save_detailed_200"] = await timed(
        lambda: db.bulk_save_detailed("object", payloads), 5
    )

    await db.bulk_save(
        "ordering",
        [
            {"id": "a", "context": {"rank": 30}},
            {"id": "b", "context": {"rank": 20}},
            {"id": "c", "context": {"rank": 10}},
        ],
    )
    result["custom_sort_iteration"] = [
        r["id"]
        async for r in db.find_iter(
            "ordering", {}, sort=[("context.rank", 1)], batch_size=1
        )
    ]
    result["expected_custom_sort_iteration"] = ["c", "b", "a"]
    result["descending_id_iteration"] = [
        r["id"]
        async for r in db.find_iter("ordering", {}, sort=[("id", -1)], batch_size=1)
    ]
    return result


async def sqlite_probes():
    """Inspect SQLite operation timings and native query plans."""
    db = SQLiteDB(db_path=":memory:")
    try:
        result = await shared_probes(db)
        conn = await db._get_connection()  # diagnostic SQL inspection only
        sqls = []
        await conn.set_trace_callback(sqls.append)
        await db.find(
            "object", {"id": {"$gt": "audit-00010000"}}, sort=[("id", 1)], limit=50
        )
        await conn.set_trace_callback(None)
        query = next(s for s in sqls if s.startswith("SELECT"))
        result["id_page_sql"] = query
        cur = await conn.execute("EXPLAIN QUERY PLAN " + query)
        result["id_page_plan"] = [tuple(r) for r in await cur.fetchall()]
        await cur.close()
        native_sql = (
            "SELECT data FROM records WHERE collection='object' "
            "AND id > 'audit-00010000' ORDER BY id LIMIT 50"
        )
        cur = await conn.execute("EXPLAIN QUERY PLAN " + native_sql)
        result["native_id_plan"] = [tuple(r) for r in await cur.fetchall()]
        await cur.close()

        async def native_page():
            cur = await conn.execute(native_sql)
            rows = await cur.fetchall()
            await cur.close()
            return [json.loads(r[0]) for r in rows]

        result["native_id_page_50"] = await timed(native_page)
        entities = [AuditRecord(value=i) for i in range(200)]
        payloads = [await e.export() for e in entities]
        ctx = GraphContext(database=db, enable_performance_monitoring=False)
        result["write_statements"] = {}
        for name, fn in [
            ("context_save_batch", lambda: ctx.save_batch(entities)),
            ("bulk_save", lambda: db.bulk_save("object", payloads)),
            ("bulk_save_detailed", lambda: db.bulk_save_detailed("object", payloads)),
        ]:
            sqls.clear()
            await conn.set_trace_callback(sqls.append)
            await fn()
            await conn.set_trace_callback(None)
            result["write_statements"][name] = dict(
                Counter(s.strip().split()[0].upper() for s in sqls)
            )
        return result
    finally:
        await db.close()


async def json_probes():
    """Count JSON record loads during ordered iteration."""
    with tempfile.TemporaryDirectory(prefix="jvspatial-io-audit-") as path:
        db = JsonDB(base_path=path)
        await db.bulk_save(
            "object", [{"id": f"r{i:05}", "value": i} for i in range(500)]
        )
        reads = 0
        original_load = db._async_load_record

        async def counted_load(path):
            nonlocal reads
            reads += 1
            return await original_load(path)

        db._async_load_record = counted_load
        start = time.perf_counter()
        seen = [r async for r in db.find_iter("object", {}, batch_size=50)]
        return {
            "records": len(seen),
            "file_load_attempts": reads,
            "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        }


async def s3_probe():
    """Check when an S3 body yields its first chunk."""

    class Body:
        def __init__(self):
            self.reads = 0
            self.closed = False

        def read(self, size):
            self.reads += 1
            return b"x" * size if self.reads <= 100 else b""

        def close(self):
            self.closed = True

    class LocalS3Probe(S3FileInterface):
        def __init__(self, body):
            self.bucket_name = "audit-stub"
            self.s3_client = SimpleNamespace(get_object=lambda **kw: {"Body": body})
            self._ClientError = RuntimeError

        def _sanitize_key(self, path):
            return path

    body = Body()
    stream = LocalS3Probe(body).stream_file("test", chunk_size=8192)
    first = await anext(stream)
    result = {
        "first_chunk_bytes": len(first),
        "body_reads_before_first_yield": body.reads,
        "body_closed_before_first_yield": body.closed,
        "total_content_chunks": 100,
    }
    await stream.aclose()
    return result


async def dynamo_probe():
    """Check residual predicate matching against a stub GSI."""
    """Exercise the real adapter with a deterministic wire stub; no AWS access."""
    wrong = {
        "id": "wrong",
        "context": {"category": "alpha", "status": "open", "score": 1},
    }
    good = {
        "id": "good",
        "context": {"category": "alpha", "status": "open", "score": 100},
    }

    class StubDynamo(DynamoDB):
        def __init__(self):
            self._indexed_fields = {
                "object": {
                    "context.category": {
                        "gsi_name": "category",
                        "attr_name": "category",
                    },
                    "context.status": {"gsi_name": "status", "attr_name": "status"},
                }
            }

        async def _ensure_table_exists(self, collection):
            return "audit-stub"

        async def _get_client(self):
            return self

        async def _run_with_throttle_retry(self, name, fn):
            return await fn()

        async def query(self, **kwargs):
            return {"Items": [{"data": {"S": json.dumps(r)}} for r in [wrong, good]]}

    db = StubDynamo()
    query = {
        "context.category": "alpha",
        "context.status": "open",
        "context.score": {"$gt": 50},
    }
    rows = await db.find("object", query)
    return {
        "returned_ids": [r["id"] for r in rows],
        "expected_ids": ["good"],
        "query": query,
        "evidence": "adapter execution against stub GSI response",
    }


async def wrapper_probe():
    """Check native iterator forwarding and failed-write cache state."""

    class StubDB(Database):
        def __init__(self):
            self.native_iterations = 0

        async def save(self, collection, data):
            return data

        async def get(self, collection, id):
            return None

        async def delete(self, collection, id):
            pass

        async def find(self, collection, query, **kw):
            return []

        async def find_iter(self, collection, query, **kw):
            self.native_iterations += 1
            yield {"id": "native"}

        async def bulk_save(self, collection, records):
            return 0  # valid partial-success count: no writes persisted

    inner = StubDB()
    register_database_type("io-audit-stub", lambda **kw: inner)
    try:
        db = create_database("io-audit-stub", cache_get_size=100)
        rows = [r async for r in db.find_iter("object", {})]
        await db.bulk_save("object", [{"id": "failed"}])
        cached = await db.get("object", "failed")
        return {
            "native_iterator_calls": inner.native_iterations,
            "iteration_results": rows,
            "cached_failed_write": cached,
            "underlying_failed_write": await inner.get("object", "failed"),
        }
    finally:
        unregister_database_type("io-audit-stub")


async def postgres_probes(dsn):
    """Measure PostgreSQL operations in a disposable schema."""
    import asyncpg

    from jvspatial.db.postgres import PostgresDB

    schema = "io_audit_" + uuid.uuid4().hex[:12]
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(f'CREATE SCHEMA "{schema}"')
    finally:
        await conn.close()
    db = PostgresDB(dsn=dsn, schema_name=schema, min_size=1, max_size=2)
    try:
        result = await shared_probes(db)
        iterator = db.find_iter("ordering", {}, batch_size=1)
        await iterator.__anext__()
        pool = await db._ensure_pool()
        result["pool_while_consumer_paused"] = {
            "size": pool.get_size(),
            "idle": pool.get_idle_size(),
        }
        await iterator.aclose()
        result["pool_after_iterator_closed"] = {
            "size": pool.get_size(),
            "idle": pool.get_idle_size(),
        }
        return result
    finally:
        await db.close()
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')
        finally:
            await conn.close()


async def main():
    """Run available local probes and emit their JSON results."""
    result = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "sqlite": await sqlite_probes(),
        "json": await json_probes(),
        "s3_stub": await s3_probe(),
        "dynamo_stub": await dynamo_probe(),
        "cache_wrapper_stub": await wrapper_probe(),
    }
    if os.getenv("AUDIT_POSTGRES_DSN"):
        result["postgres"] = await postgres_probes(os.environ["AUDIT_POSTGRES_DSN"])
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
