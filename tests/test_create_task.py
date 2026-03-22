"""Tests for jvspatial.create_task (Shape A and Shape B)."""

import asyncio
import inspect
from unittest.mock import patch

import pytest

from jvspatial.async_utils import create_task
from jvspatial.runtime.serverless import reset_serverless_mode_cache
from jvspatial.serverless.deferred_invoke import (
    clear_deferred_invoke_handlers,
    register_deferred_invoke_handler,
)


@pytest.fixture(autouse=True)
def _non_serverless(monkeypatch):
    monkeypatch.setenv("SERVERLESS_MODE", "false")
    monkeypatch.delenv("AWS_LAMBDA_FUNCTION_NAME", raising=False)
    monkeypatch.delenv("AWS_LAMBDA_RUNTIME_API", raising=False)
    reset_serverless_mode_cache()
    yield
    reset_serverless_mode_cache()
    clear_deferred_invoke_handlers()


# ---------- Shape B (coroutine) ----------


@pytest.mark.asyncio
async def test_shape_b_returns_task_and_runs():
    results = []

    async def work():
        results.append("done")

    task = await create_task(work(), name="b-test")
    assert isinstance(task, asyncio.Task)
    await task
    assert results == ["done"]


@pytest.mark.asyncio
async def test_shape_b_serverless_awaits_inline_returns_none(monkeypatch):
    monkeypatch.setenv("SERVERLESS_MODE", "true")
    reset_serverless_mode_cache()
    ran: list[str] = []

    async def work():
        ran.append("done")

    result = await create_task(work(), name="inline")
    assert result is None
    assert ran == ["done"]


@pytest.mark.asyncio
async def test_shape_b_non_serverless_schedules_background():
    ran: list[str] = []

    async def work():
        ran.append("done")

    task = await create_task(work(), name="bg")
    assert isinstance(task, asyncio.Task)
    await asyncio.sleep(0.05)
    assert ran == ["done"]


@pytest.mark.asyncio
async def test_shape_b_serverless_no_warning(monkeypatch, caplog):
    monkeypatch.setenv("SERVERLESS_MODE", "true")
    reset_serverless_mode_cache()
    caplog.set_level("WARNING")

    async def work():
        pass

    await create_task(work(), name="no-warn")
    assert not any(
        "create_task(coroutine) called in serverless mode" in r.message
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_shape_b_concurrent_returns_task_on_serverless(monkeypatch):
    monkeypatch.setenv("SERVERLESS_MODE", "true")
    reset_serverless_mode_cache()

    async def work():
        pass  # pragma: no cover

    task = await create_task(work(), name="conc", concurrent=True)
    assert isinstance(task, asyncio.Task)
    await task


# ---------- Shape A (handler) ----------


@pytest.mark.asyncio
async def test_shape_a_non_serverless_calls_handler():
    received = {}

    async def handler(event):
        received.update(event)
        return {"ok": True}

    register_deferred_invoke_handler("test.shape_a", handler)

    task = await create_task("test.shape_a", {"key": "val"}, name="a-test")
    assert isinstance(task, asyncio.Task)
    await task
    assert received["key"] == "val"
    assert received["task_type"] == "test.shape_a"


@pytest.mark.asyncio
async def test_shape_a_non_serverless_delay():
    received = {}

    async def handler(event):
        received.update(event)
        return {}

    register_deferred_invoke_handler("test.delay", handler)
    task = await create_task("test.delay", {"x": 1}, delay_seconds=0.05, name="delay")
    assert isinstance(task, asyncio.Task)
    await asyncio.sleep(0.01)
    assert not received  # not yet
    await task
    assert received["x"] == 1


@pytest.mark.asyncio
async def test_shape_a_serverless_dispatches(monkeypatch):
    monkeypatch.setenv("SERVERLESS_MODE", "true")
    reset_serverless_mode_cache()

    with patch("jvspatial.serverless.factory.dispatch_deferred_task") as mock_dispatch:
        result = await create_task("test.srv", {"a": 1}, name="srv")
        assert result is None
        mock_dispatch.assert_called_once()
        args, kwargs = mock_dispatch.call_args
        assert args[0] == "test.srv"
        assert args[1] == {"a": 1}


# ---------- Invalid first argument ----------


@pytest.mark.asyncio
async def test_invalid_first_arg_raises():
    with pytest.raises(TypeError, match="task_type string or a coroutine"):
        await create_task(42)


# ---------- Top-level import ----------


def test_top_level_import():
    from jvspatial import create_task as ct

    assert inspect.iscoroutinefunction(ct)
