"""Tests for the auto-flush safety net on DeferredSaveMixin."""

import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Node
from jvspatial.core.mixins import DeferredSaveMixin
from jvspatial.db import create_database
from jvspatial.runtime.serverless import reset_serverless_mode_cache


class _AutoFlushNode(DeferredSaveMixin, Node):
    """Node with a tight auto-flush bound for testing."""

    name: str = ""
    counter: int = 0
    max_pending_saves = 5  # auto-flush after 5 deferred save() calls


@pytest.fixture
def temp_db_path():
    with tempfile.TemporaryDirectory() as d:
        yield Path(d) / "test.db"


@pytest.fixture
async def sqlite_context(temp_db_path):
    db = create_database("sqlite", db_path=str(temp_db_path))
    ctx = GraphContext(database=db)
    set_default_context(ctx)
    try:
        yield ctx
    finally:
        if hasattr(db, "close"):
            await db.close()


@pytest.fixture(autouse=True)
def _enable_deferred_env():
    with patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "false",
            "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true",
        },
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        yield
        reset_serverless_mode_cache()


class TestAutoFlushBound:
    async def test_auto_flush_triggers_at_threshold(self, sqlite_context, caplog):
        node = await _AutoFlushNode.create(name="x", counter=0)
        # First save (call 1 of 5). _pending_save_count is incremented
        # in __init__-from-create flow.
        # Issue another four; the 5th should trigger auto-flush.
        for i in range(1, 5):
            node.counter = i
            await node.save()

        with caplog.at_level(logging.WARNING):
            node.counter = 5
            await node.save()  # 5th deferred save -> auto-flush

        # The auto-flush WARNING was emitted.
        assert any(
            "max_pending_saves" in r.getMessage() and "auto-flushing" in r.getMessage()
            for r in caplog.records
        )

        # Auto-flush cleared dirty + pending counter.
        assert not node.is_dirty
        assert node._pending_save_count == 0

        # The current state was persisted.
        loaded = await _AutoFlushNode.get(node.id)
        assert loaded is not None
        assert loaded.counter == 5

    async def test_under_threshold_no_auto_flush(self, sqlite_context, caplog):
        node = await _AutoFlushNode.create(name="x", counter=0)
        # 3 deferred saves -> no flush (under cap of 5)
        for i in range(1, 4):
            node.counter = i
            await node.save()

        # No auto-flush warning.
        assert not any("auto-flushing" in r.getMessage() for r in caplog.records)
        assert node.is_dirty

    async def test_no_cap_means_no_auto_flush(self, sqlite_context, caplog):
        """The default class (max_pending_saves = None) never auto-flushes."""

        class _UnboundedNode(DeferredSaveMixin, Node):
            counter: int = 0
            # max_pending_saves intentionally unset -- inherits None.

        node = await _UnboundedNode.create(counter=0)
        for i in range(1, 50):
            node.counter = i
            await node.save()

        assert not any("auto-flushing" in r.getMessage() for r in caplog.records)
        assert node.is_dirty

    async def test_explicit_flush_resets_counter(self, sqlite_context, caplog):
        node = await _AutoFlushNode.create(name="x", counter=0)
        for i in range(1, 4):
            node.counter = i
            await node.save()
        await node.flush()
        assert node._pending_save_count == 0

        # Re-enable deferred mode and confirm the counter restart works.
        node.enable_deferred_saves()
        for i in range(4, 7):
            node.counter = i
            await node.save()
        # 3 deferred saves after the explicit flush -> still under cap.
        assert not any("auto-flushing" in r.getMessage() for r in caplog.records)
