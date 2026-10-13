"""Tests for the ObservableDatabase wrapper.

Covers:
* successful calls, including slow calls, stay silent while failures are logged,
* slow-query metrics still increment at the configured threshold,
* metrics recorder gets called with the right labels,
* error path emits the log/metric with success=False before re-raising,
* factory wires observe=True/slow_query_ms/metrics correctly,
* observability composes correctly with the cache wrapper.
"""

import logging
import tempfile
from typing import Iterator, List

import pytest

from jvspatial.db._cache import CachingDatabase
from jvspatial.db._observable import ObservableDatabase
from jvspatial.db.factory import create_database
from jvspatial.db.jsondb import JsonDB
from jvspatial.observability import db_op_counter


class _CapturingRecorder:
    def __init__(self) -> None:
        self.durations: List = []
        self.counters: List = []
        self.values: List = []

    def record_duration(self, name, seconds, /, **labels):
        self.durations.append((name, seconds, dict(labels)))

    def increment_counter(self, name, /, *, amount=1, **labels):
        self.counters.append((name, amount, dict(labels)))

    def record_value(self, name, value, /, **labels):
        self.values.append((name, value, dict(labels)))


@pytest.fixture
def jsondb() -> Iterator[JsonDB]:
    with tempfile.TemporaryDirectory() as tmp:
        yield JsonDB(base_path=tmp)


# ---------------------- routine log suppression ----------------------


class TestRoutineOperationsSilent:
    async def test_fast_operations_record_metrics_without_logs(self, jsondb, caplog):
        recorder = _CapturingRecorder()
        wrapped = ObservableDatabase(jsondb, metrics=recorder)
        await jsondb.save("node", {"id": "x", "v": 1})
        with caplog.at_level(logging.DEBUG, logger="jvspatial.db.observable"):
            await wrapped.find("node", {})

        assert not [
            record
            for record in caplog.records
            if record.name == "jvspatial.db.observable"
        ]
        assert recorder.durations
        assert recorder.counters


# ---------------------- slow query silence --------------------------


class TestSlowQuery:
    async def test_slow_query_stays_silent(self, jsondb, caplog):
        # Slow-call telemetry belongs in metrics, not application logs.
        wrapped = ObservableDatabase(jsondb, slow_query_ms=0.0)
        await jsondb.save("node", {"id": "x", "v": 1})
        with caplog.at_level(logging.DEBUG, logger="jvspatial.db.observable"):
            await wrapped.get("node", "x")
        records = [r for r in caplog.records if r.name == "jvspatial.db.observable"]
        assert records == []

    async def test_fast_query_stays_silent(self, jsondb, caplog):
        # Threshold high enough that nothing in this test triggers it.
        wrapped = ObservableDatabase(jsondb, slow_query_ms=10_000.0)
        await jsondb.save("node", {"id": "x", "v": 1})
        with caplog.at_level(logging.INFO, logger="jvspatial.db.observable"):
            await wrapped.get("node", "x")
        warns = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and r.name == "jvspatial.db.observable"
        ]
        assert warns == []


# ---------------------- metrics ---------------------------------------


class TestMetrics:
    async def test_records_duration_and_counter_per_op(self, jsondb):
        rec = _CapturingRecorder()
        wrapped = ObservableDatabase(jsondb, metrics=rec)
        await wrapped.save("node", {"id": "x", "v": 1})
        await wrapped.get("node", "x")

        durations = {d[0]: d for d in rec.durations}
        counters = {c[0]: c for c in rec.counters}
        assert "jvspatial.db.op.duration_seconds" in durations
        assert "jvspatial.db.op.count" in counters

        # Labels carry the standard dimensions.
        d_name, d_secs, d_labels = rec.durations[0]
        assert d_labels["backend"] == "JsonDB"
        assert d_labels["collection"] == "node"
        assert d_labels["op"] in ("save", "get")
        assert d_labels["success"] is True
        assert d_secs >= 0

    async def test_metrics_failure_does_not_break_op(self, jsondb):
        class _Boom:
            def record_duration(self, *a, **k):
                raise RuntimeError("metrics broken")

            def increment_counter(self, *a, **k):
                raise RuntimeError("metrics broken")

            def record_value(self, *a, **k):
                raise RuntimeError("metrics broken")

        wrapped = ObservableDatabase(jsondb, metrics=_Boom())
        await jsondb.save("node", {"id": "x", "v": 1})
        # The op must complete normally despite the metrics backend
        # raising on every emission.
        result = await wrapped.get("node", "x")
        assert result == {"id": "x", "v": 1}

    async def test_slow_op_increments_slow_count_metric(self, jsondb):
        rec = _CapturingRecorder()
        wrapped = ObservableDatabase(jsondb, metrics=rec, slow_query_ms=0.0)
        await jsondb.save("node", {"id": "x", "v": 1})
        await wrapped.get("node", "x")
        slow_counters = [
            c for c in rec.counters if c[0] == "jvspatial.db.op.slow_count"
        ]
        assert slow_counters, "slow op should emit slow_count counter"

    async def test_db_op_counter_increments_per_operation(self, jsondb):
        wrapped = ObservableDatabase(jsondb)
        tok = db_op_counter.set(0)
        try:
            await wrapped.save("node", {"id": "x", "v": 1})
            await wrapped.get("node", "x")
            await wrapped.find("node", {})
            assert db_op_counter.get() == 3
        finally:
            db_op_counter.reset(tok)


# ---------------------- error path ------------------------------------


class TestErrorPath:
    async def test_exception_logged_with_success_false(self, jsondb, caplog):
        rec = _CapturingRecorder()
        wrapped = ObservableDatabase(jsondb, metrics=rec)

        class _Bomb(Exception):
            pass

        async def _exploding_save(collection, data):
            raise _Bomb("kaboom")

        # Monkey-patch the inner backend's save to raise.
        jsondb.save = _exploding_save  # type: ignore[assignment]

        with caplog.at_level(logging.INFO, logger="jvspatial.db.observable"):
            with pytest.raises(_Bomb):
                await wrapped.save("node", {"id": "x"})

        # The log record must capture success=False.
        save_recs = [r for r in caplog.records if getattr(r, "op", None) == "save"]
        assert save_recs
        assert getattr(save_recs[-1], "success", None) is False
        assert save_recs[-1].levelno == logging.ERROR

        # Metrics also tagged success=False.
        assert any(d[2].get("success") is False for d in rec.durations)


# ---------------------- factory wiring --------------------------------


class TestFactoryWiring:
    async def test_observe_true_wraps(self, tmp_path):
        rec = _CapturingRecorder()
        db = create_database(
            "json",
            base_path=str(tmp_path),
            observe=True,
            metrics=rec,
        )
        assert isinstance(db, ObservableDatabase)
        await db.save("node", {"id": "x", "v": 1})
        assert rec.counters, "metrics should fire after a save"

    async def test_observe_false_no_wrap(self, tmp_path):
        db = create_database("json", base_path=str(tmp_path))
        assert not isinstance(db, ObservableDatabase)

    async def test_compose_cache_then_observe(self, tmp_path):
        """Factory applies cache first, observability outside.

        Metrics should include user-visible latency across the cache wrapper.
        Routine successful reads must remain silent."""
        db = create_database(
            "json",
            base_path=str(tmp_path),
            cache_get_size=8,
            observe=True,
        )
        # Outermost wrapper is ObservableDatabase, next layer is
        # CachingDatabase, innermost is JsonDB.
        assert isinstance(db, ObservableDatabase)
        assert isinstance(db.inner, CachingDatabase)
        assert isinstance(db.inner.inner, JsonDB)
        # Backend label correctly unwraps.
        assert db._backend == "JsonDB"
