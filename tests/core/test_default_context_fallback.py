"""Regression tests for the process-wide GraphContext fallback.

Background: ``set_default_context`` writes to a per-task ``ContextVar``.
That value only propagates to tasks that were created from a Context
which already had it set. Several legitimate launchers (Server built
inside ``asyncio.run``, request loop running on a different thread,
custom ASGI adapters that spawn a fresh event loop per invocation) leave
request handlers with an empty per-task slot — historically the
lazy-init branch raised ``RuntimeError`` even though the database was
fully configured.

These tests cover the fallback that ``set_default_context`` now
records, and ``get_default_context`` consults when the ContextVar is
empty.
"""

import asyncio
import threading

import pytest

from jvspatial.core.context import (
    GraphContext,
    _default_context_var,
    clear_default_context_global,
    get_default_context,
    scoped_default_context,
    set_default_context,
)


@pytest.fixture(autouse=True)
def _isolate_fallback():
    """Reset both per-task slot and process-wide fallback around each test."""
    saved_cv = _default_context_var.get()
    try:
        yield
    finally:
        clear_default_context_global()
        if saved_cv is not None:
            _default_context_var.set(saved_cv)


def test_fallback_recovers_when_contextvar_empty():
    """A fresh task with no inherited ContextVar still resolves the configured context."""
    configured = GraphContext()
    set_default_context(configured)

    seen = {}

    async def runner():
        # asyncio.run starts a fresh top-level Context that copies the
        # current Context; the ContextVar value set above is inherited
        # into this task. Simulate a non-inheriting launcher by clearing
        # the per-task slot before the read.
        _default_context_var.set(None)
        seen["ctx"] = get_default_context()

    asyncio.run(runner())
    assert seen["ctx"] is configured


def test_fallback_recovers_in_separate_thread():
    """Threads do not inherit ContextVar values; fallback must still resolve."""
    configured = GraphContext()
    set_default_context(configured)

    seen = {}

    def worker():
        # Fresh thread → fresh Context, ContextVar is at its default (None).
        seen["pre"] = _default_context_var.get()
        seen["ctx"] = get_default_context()

    t = threading.Thread(target=worker)
    t.start()
    t.join()

    assert seen["pre"] is None
    assert seen["ctx"] is configured


def test_per_task_value_takes_precedence_over_fallback():
    """ContextVar set on the current task always wins over the fallback."""
    fallback_ctx = GraphContext()
    task_ctx = GraphContext()

    set_default_context(fallback_ctx)
    with scoped_default_context(task_ctx):
        assert get_default_context() is task_ctx

    # After scope exit, fallback resolves again because the per-task slot
    # was restored to its prior value (which may itself be the fallback
    # bound after first lookup).
    assert get_default_context() is fallback_ctx


def test_clear_default_context_does_not_drop_fallback():
    """``clear_default_context`` only nulls the per-task slot."""
    configured = GraphContext()
    set_default_context(configured)

    from jvspatial.core.context import clear_default_context

    clear_default_context()
    # Per-task slot is None but fallback is still recorded → resolves.
    assert get_default_context() is configured


def test_clear_default_context_global_drops_fallback():
    """``clear_default_context_global`` resets both."""
    configured = GraphContext()
    set_default_context(configured)

    clear_default_context_global()
    # Both per-task slot and fallback are None now. ``get_default_context``
    # lazy-inits a throwaway context (manager flag is_auto_created behavior
    # depends on prior tests; we only assert the call does not return the
    # cleared instance).
    resolved = get_default_context()
    assert resolved is not configured


def test_set_default_context_none_does_not_clobber_fallback():
    """Passing ``None`` clears the per-task slot but keeps the fallback intact."""
    configured = GraphContext()
    set_default_context(configured)
    set_default_context(None)

    # Fallback still resolves.
    assert get_default_context() is configured


def test_set_prime_database_clears_auto_created_flag():
    """Once a real prime DB is bound, the manager is no longer 'auto-created'."""
    from jvspatial.db.factory import create_database
    from jvspatial.db.manager import DatabaseManager

    # Force an auto-created instance.
    DatabaseManager._instance = None
    auto = DatabaseManager.get_instance()
    assert auto._auto_created is True

    auto.set_prime_database(create_database("json", base_path="./_test_prime_clear"))
    assert auto._auto_created is False

    # Reset for downstream tests.
    DatabaseManager._instance = None
