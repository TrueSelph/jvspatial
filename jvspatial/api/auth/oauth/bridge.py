"""Async/sync bridge for Authlib's synchronous OAuth core.

Drives Authlib's sync grant handlers from async route handlers while their
hooks reach jvspatial's async ``Object`` storage.

Pattern: the route handler calls ``await run_sync_with_async_bridge(fn)`` which
runs ``fn`` (which internally calls Authlib's sync ``create_*_response``) in a
worker thread via ``anyio.to_thread.run_sync``. Inside that thread, Authlib's
sync grant hooks call ``call_async(coro_fn, *args)`` to execute async storage
coroutines back on the host event loop (blocking the worker until they resolve).
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, TypeVar

import anyio
import anyio.from_thread
import anyio.to_thread

T = TypeVar("T")


async def run_sync_with_async_bridge(fn: Callable[..., T], *args: Any) -> T:
    """Run a blocking ``fn`` in a worker thread that may call ``call_async``."""
    return await anyio.to_thread.run_sync(fn, *args)


def call_async(coro_fn: Callable[..., Awaitable[T]], *args: Any) -> T:
    """Run an async coroutine on the host event loop from a worker thread.

    Must be called from inside a function executed via
    ``run_sync_with_async_bridge`` (anyio installs the blocking portal there).
    """
    return anyio.from_thread.run(coro_fn, *args)
