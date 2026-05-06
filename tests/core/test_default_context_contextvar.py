"""Regression tests for the per-task default-context (ContextVar) API.

Verifies the rewrite of ``_default_context`` from a module-global mutable
to a ``contextvars.ContextVar``-backed slot:

- ``set_default_context`` returns a Token usable with ``reset_default_context``
- ``clear_default_context`` resets the per-task slot to None
- ``scoped_default_context`` / ``scoped_default_context_async`` set + auto-restore
- Concurrent asyncio tasks no longer stomp on each other's defaults
"""

import asyncio

import pytest

from jvspatial.core.context import (
    GraphContext,
    _default_context_var,
    clear_default_context,
    get_default_context,
    reset_default_context,
    scoped_default_context,
    scoped_default_context_async,
    set_default_context,
)


@pytest.fixture(autouse=True)
def _isolate_default_context():
    """Snapshot/restore the per-task ContextVar around each test.

    Tests in this module exercise the raw setter with throwaway
    ``GraphContext()`` instances (no database). Restoring the slot keeps
    those throwaways from leaking into neighbouring test modules.
    """
    saved_cv = _default_context_var.get()
    try:
        yield
    finally:
        if saved_cv is None:
            clear_default_context()
        else:
            _default_context_var.set(saved_cv)


def test_set_default_context_returns_token_for_reset():
    """set_default_context returns a Token that reset_default_context honours."""
    ctx_a = GraphContext()
    ctx_b = GraphContext()

    set_default_context(ctx_a)
    token_b = set_default_context(ctx_b)
    assert _default_context_var.get() is ctx_b

    reset_default_context(token_b)
    assert _default_context_var.get() is ctx_a


def test_clear_default_context_sets_slot_to_none():
    set_default_context(GraphContext())
    assert _default_context_var.get() is not None
    clear_default_context()
    assert _default_context_var.get() is None


def test_scoped_default_context_restores_on_exit():
    outer = GraphContext()
    inner = GraphContext()
    set_default_context(outer)

    with scoped_default_context(inner):
        assert _default_context_var.get() is inner

    assert _default_context_var.get() is outer


def test_scoped_default_context_restores_on_exception():
    outer = GraphContext()
    inner = GraphContext()
    set_default_context(outer)

    with pytest.raises(RuntimeError, match="boom"):
        with scoped_default_context(inner):
            assert _default_context_var.get() is inner
            raise RuntimeError("boom")

    assert _default_context_var.get() is outer


def test_concurrent_tasks_have_isolated_defaults():
    """Two coroutines running concurrently must each see their own swap.

    Regression: with the old module-global, the second task overwrite would
    leak into the first task's view, producing data-on-wrong-DB bugs under
    realistic FastAPI/uvicorn load.
    """
    ctx_a = GraphContext()
    ctx_b = GraphContext()
    seen: dict = {}

    async def task_a():
        set_default_context(ctx_a)
        await asyncio.sleep(0.01)
        seen["a"] = _default_context_var.get()

    async def task_b():
        set_default_context(ctx_b)
        await asyncio.sleep(0.01)
        seen["b"] = _default_context_var.get()

    async def runner():
        await asyncio.gather(task_a(), task_b())

    asyncio.run(runner())
    assert seen["a"] is ctx_a
    assert seen["b"] is ctx_b


def test_async_scoped_default_context_restores_on_exit():
    outer = GraphContext()
    inner = GraphContext()
    set_default_context(outer)

    async def runner():
        async with scoped_default_context_async(inner):
            assert _default_context_var.get() is inner

    asyncio.run(runner())
    assert _default_context_var.get() is outer


def test_get_default_context_returns_set_value():
    ctx = GraphContext()
    set_default_context(ctx)
    assert get_default_context() is ctx
