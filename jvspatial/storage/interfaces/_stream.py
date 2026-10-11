"""Incremental blocking-reader bridge with cancellation-safe ownership."""

import asyncio
from typing import Any, AsyncIterator, Callable


async def _await_worker(task: asyncio.Task) -> Any:
    """Drain a worker despite repeated cancellation before releasing ownership."""
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        if not task.cancelled():
            task.exception()  # Retrieve any worker failure; cancellation wins.
        raise


async def _io_call(fn: Callable[..., Any], *args: Any) -> Any:
    """Finish an in-flight worker call before allowing resource cleanup."""
    return await _await_worker(asyncio.create_task(asyncio.to_thread(fn, *args)))


async def stream_reader(
    opener: Callable[[], Any], chunk_size: int
) -> AsyncIterator[bytes]:
    """Own one reader, consuming at most one chunk per consumer advance."""
    if (
        isinstance(chunk_size, bool)
        or not isinstance(chunk_size, int)
        or chunk_size < 1
    ):
        raise ValueError("chunk_size must be a positive integer")
    opening = asyncio.create_task(asyncio.to_thread(opener))
    try:
        reader = await _await_worker(opening)
    except asyncio.CancelledError:
        if opening.cancelled() or opening.exception() is not None:
            raise
        reader = opening.result()
        await _io_call(reader.close)
        raise
    try:
        while True:
            chunk = await _io_call(reader.read, chunk_size)
            if not chunk:
                return
            yield chunk
    finally:
        await _io_call(reader.close)
