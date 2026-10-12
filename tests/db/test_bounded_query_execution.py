"""Verify query work with counters and plans, rather than timing assertions."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from jvspatial.core.context import GraphContext, PerformanceMonitor
from jvspatial.db._sqlite_translate import translate_query, translate_sort
from jvspatial.db.database import DatabaseError, _pushdown_conjuncts, _query_execution
from jvspatial.db.factory import create_database
from jvspatial.db.sqlite import SQLiteDB


async def seed(db):
    await db.bulk_save(
        "object",
        [
            {
                "id": f"{i:04}",
                "context": {
                    "group": i % 2,
                    "label": "match" if i % 5 == 0 else "miss",
                    "rank": i,
                },
            }
            for i in range(200)
        ],
    )


async def test_partial_pushdown_and_early_exit(tmp_path):
    db = SQLiteDB(tmp_path / "bounded.db")
    try:
        await seed(db)
        query = {"context.group": 1, "context.label": {"$regex": "^match$"}}
        result = await db.find("object", query, limit=1, sort=[("id", 1)])
        assert [row["id"] for row in result] == ["0005"]
        assert _query_execution.get()["partial_pushdown"] is True
        assert _query_execution.get()["scanned_rows"] == 3
        assert await db.count("object", query) == 20
        assert _query_execution.get()["scanned_rows"] == 100
    finally:
        await db.close()


async def test_scan_budget_does_not_truncate_silently(tmp_path):
    db = create_database(
        "sqlite", db_path=tmp_path / "budget.db", fallback_scan_limit=2, observe=True
    )
    try:
        await seed(db)
        with pytest.raises(DatabaseError, match="fallback_scan_limit"):
            await db.find("object", {"context.label": {"$regex": "match"}})
        with pytest.raises(DatabaseError, match="fallback_scan_limit"):
            await db.count("object", {"context.label": {"$regex": "match"}})
        assert len(await db.find("object", {"id": "0000"})) == 1
    finally:
        await db.close()


def test_partial_pushdown_never_splits_or_and_regex_options():
    query = {"$or": [{"id": "1"}, {"context.label": {"$regex": "match"}}]}
    assert _pushdown_conjuncts(query, translate_query) == {}
    assert _pushdown_conjuncts({"$and": [{"id": "1"}, query]}, translate_query) == {
        "$and": [{"id": "1"}]
    }


async def test_compound_sort_index_matches_nulls_and_direction(tmp_path):
    db = SQLiteDB(tmp_path / "index.db")
    try:
        await seed(db)
        fields = [("context.group", 1), ("context.rank", -1)]
        await db.create_index("object", fields)
        conn = await db._get_connection()
        cursor = await conn.execute(
            f"EXPLAIN QUERY PLAN SELECT data FROM records WHERE collection=? ORDER BY {translate_sort([*fields, ('id', 1)])} LIMIT 5",
            ("object",),
        )
        plan = " ".join(row[3] for row in await cursor.fetchall())
        await cursor.close()
        assert "__sort" in plan
        assert "TEMP B-TREE" not in plan
        assert [r["id"] for r in await db.find("object", {}, sort=fields, limit=2)] == [
            "0198",
            "0196",
        ]
    finally:
        await db.close()


@pytest.mark.parametrize("backend", ["json", "sqlite"])
async def test_grouped_degrees_and_bounded_hub(backend, tmp_path):
    db = create_database(
        backend,
        **(
            {"db_path": tmp_path / "graph.db"}
            if backend == "sqlite"
            else {"base_path": tmp_path / "json"}
        ),
    )
    context = GraphContext(database=db)
    try:
        await db.bulk_save(
            "node",
            [
                {"id": "center", "entity": "Node"},
                *[{"id": f"neighbor{i}", "entity": "Node"} for i in range(200)],
            ],
        )
        await db.bulk_save(
            "edge",
            [
                {"id": f"{i:04}", "source": "center", "target": f"neighbor{i}"}
                for i in range(200)
            ]
            + [{"id": "self", "source": "center", "target": "center"}],
        )
        assert await db.count_incident_edges(
            "edge", ["center", "neighbor0", "absent"]
        ) == {"center": 201, "neighbor0": 1, "absent": 0}
        original = db.find
        db.find = AsyncMock(wraps=original)
        db.count = AsyncMock(side_effect=AssertionError("individual counts forbidden"))
        payload = await context.subgraph_bfs(
            "center",
            max_depth=1,
            max_edges_per_node=5,
            priority_node_prefixes=[],
            include_counts=False,
        )
        assert payload["meta"]["truncated"]
        assert payload["meta"]["edge_count"] == 5
        calls = [c for c in db.find.call_args_list if c.args[0] == "edge"]
        assert calls and all(c.kwargs["limit"] <= 6 for c in calls)
    finally:
        if hasattr(db, "close"):
            await db.close()


async def test_monitor_samples_are_bounded():
    monitor = PerformanceMonitor(sample_limit=3)
    for i in range(10):
        await monitor.record_db_operation("object", "find", i, 0)
        await monitor.record_io_operation("read", i)
    assert len(monitor.db_operations) == len(monitor.io_operations) == 3
    assert monitor.db_operations[0]["duration"] == 7
    stats = await monitor.get_stats()
    assert stats["total_bytes_read"] == 0
    assert stats["db_operations"] == 10
    assert stats["avg_db_duration"] == 4.5


async def test_iterator_active_time_and_wrapper_cleanup(monkeypatch):
    from jvspatial.db._observable import ObservableDatabase
    from jvspatial.db.jsondb import JsonDB

    db = JsonDB.__new__(JsonDB)
    closed = False

    async def stream(*args, **kw):
        nonlocal closed
        try:
            yield {"id": "1"}
            yield {"id": "2"}
        finally:
            closed = True

    db.find_iter = stream
    wrapper = ObservableDatabase(db)
    emissions = []
    monkeypatch.setattr(wrapper, "_emit", lambda **kw: emissions.append(kw))
    iterator = wrapper.find_iter("object", {})
    await anext(iterator)
    await asyncio.sleep(0.03)
    await iterator.aclose()
    assert closed
    assert emissions[0]["duration_s"] >= 0.025
    assert emissions[0]["active_duration_s"] < 0.02


def test_partial_regex_retains_flags():
    from jvspatial.db._postgres_translate import translate_query as pg_translate

    query = {"context.label": {"$regex": "alpha", "$options": "i", "$unknown": True}}
    pushed = _pushdown_conjuncts(query, pg_translate)
    assert pushed == {"$and": [{"context.label": {"$regex": "alpha", "$options": "i"}}]}


async def test_observed_fallback_reports_context_local_work(tmp_path, caplog):
    import logging

    db = create_database("sqlite", db_path=tmp_path / "observe.db", observe=True)
    try:
        await seed(db)
        with caplog.at_level(logging.DEBUG, logger="jvspatial.db.observable"):
            await db.find(
                "object",
                {"context.group": 1, "context.label": {"$regex": "^match$"}},
                limit=1,
                sort=[("id", 1)],
            )
        record = next(r for r in caplog.records if getattr(r, "op", None) == "find")
        assert record.execution_mode == "residual_scan"
        assert record.scanned_rows == 3
        assert record.decoded_bytes > 0
        assert (
            _query_execution.get() is None
            or _query_execution.get() is not record.__dict__
        )
    finally:
        await db.close()


async def test_numbered_sqlite_page_only_hydrates_selected_ids(tmp_path):
    from unittest.mock import patch

    from jvspatial.core import Object
    from jvspatial.core.pager import ObjectPager

    db = SQLiteDB(tmp_path / "pages.db")
    try:
        context = GraphContext(database=db)
        await db.bulk_save(
            "object",
            [{"id": f"{i:04}", "entity": "Object", "context": {}} for i in range(200)],
        )
        calls = []
        native = db.find_many

        async def hydrate(collection, ids):
            calls.append(ids)
            return await native(collection, ids)

        db.find_many = hydrate
        with patch("jvspatial.core.context.get_default_context", return_value=context):
            page = await ObjectPager(Object, page_size=5).get_page(20)
        assert [r.id for r in page] == [f"{i:04}" for i in range(95, 100)]
        assert calls == [[f"{i:04}" for i in range(95, 100)]]
    finally:
        await db.close()


async def test_retry_attempt_metrics_are_explicit(monkeypatch):
    from pymongo.errors import ConnectionFailure

    from jvspatial.db.database import _io_metrics
    from jvspatial.db.dynamodb import DynamoDB
    from jvspatial.db.mongodb import MongoDB

    metrics = {}
    token = _io_metrics.set(metrics)
    try:
        mongo = MongoDB()
        operation = AsyncMock(side_effect=[ConnectionFailure("lost"), "ok"])
        assert await mongo._run_with_reconnect("read", operation) == "ok"
        assert metrics == {"driver_attempts": 2, "retry_count": 1}
        metrics.clear()
        db = DynamoDB.__new__(DynamoDB)
        monkeypatch.setattr(
            "jvspatial.db.dynamodb._is_dynamodb_throttle_error",
            lambda exc: isinstance(exc, RuntimeError),
        )
        monkeypatch.setattr("jvspatial.db.dynamodb.asyncio.sleep", AsyncMock())
        operation = AsyncMock(side_effect=[RuntimeError("throttle"), "ok"])
        assert await db._run_with_throttle_retry("read", operation) == "ok"
        assert metrics == {"driver_attempts": 2, "retry_count": 1}
    finally:
        _io_metrics.reset(token)


@pytest.mark.parametrize("backend", ["json", "sqlite"])
async def test_priority_matches_other_endpoint_even_when_center_shares_prefix(
    backend, tmp_path
):
    from jvspatial.core.graph_expansion import _bounded_incident_edges

    db = create_database(
        backend,
        **(
            {"db_path": tmp_path / "priorities.db"}
            if backend == "sqlite"
            else {"base_path": tmp_path / "priorities"}
        ),
    )
    try:
        await db.bulk_save(
            "edge",
            [
                *[
                    {
                        "id": f"a{i}",
                        "source": "n.Custom.center",
                        "target": f"n.Other.{i}",
                    }
                    for i in range(20)
                ],
                {
                    "id": "z-priority",
                    "source": "n.Custom.center",
                    "target": "n.Custom.other",
                },
            ],
        )
        rows, truncated = await _bounded_incident_edges(
            db, "n.Custom.center", 2, ["n.Custom."]
        )
        assert [eid for eid, _ in rows] == ["z-priority", "a0"]
        assert truncated
    finally:
        if hasattr(db, "close"):
            await db.close()


async def test_sqlite_repeated_index_setup_preserves_distinct_sort_directions(tmp_path):
    db = SQLiteDB(tmp_path / "directions.db")
    try:
        await seed(db)
        for direction in (1, -1):
            await db.create_index("object", [("context.rank", direction)])
        connection = await db._get_connection()
        for direction in (1, -1):
            cursor = await connection.execute(
                f"EXPLAIN QUERY PLAN SELECT data FROM records WHERE collection=? ORDER BY {translate_sort([('context.rank', direction), ('id', direction)])} LIMIT 5",
                ("object",),
            )
            plan = " ".join(r[3] for r in await cursor.fetchall())
            await cursor.close()
            assert "__sort" in plan and "TEMP B-TREE" not in plan
    finally:
        await db.close()
