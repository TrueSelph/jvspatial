"""Shared fixtures and helpers for the benchmark suite.

The benchmarks live in their own directory (``tests/benchmarks``) and
are excluded from the default ``pytest`` invocation by the
``--ignore=tests/benchmarks`` flag in ``pyproject.toml``. To run them:

    pytest tests/benchmarks --benchmark-only

Or via the CI workflow at ``.github/workflows/benchmarks.yml``.

Warm operations use ``benchmark_async``: seed once outside timing, reuse
one loop and connection, then tear down in that loop. The measured region
includes run_until_complete dispatch, not loop creation or fixture seeding.
``run_async`` remains for explicitly setup-inclusive write/lifecycle scenarios;
those timings must not be compared with warm-operation benchmarks.
"""

import asyncio
import tempfile
from typing import Iterator

import pytest


@pytest.fixture
def temp_dir() -> Iterator[str]:
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


def run_async(coro_func, *args, **kwargs):
    """Run an async callable to completion in a fresh event loop.

    Returns the coroutine result. Suitable for use as the inner
    callable handed to pytest-benchmark.
    """
    return asyncio.run(coro_func(*args, **kwargs))


def benchmark_async(benchmark, setup, operation, teardown=None):
    """Seed outside timing and keep a single event loop/connection lifecycle."""
    loop = asyncio.new_event_loop()
    resource = None
    try:
        resource = loop.run_until_complete(setup())

        def measured():
            return loop.run_until_complete(operation(resource))

        return benchmark(measured)
    finally:
        try:
            if resource is not None and teardown is not None:
                loop.run_until_complete(teardown(resource))
        finally:
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
                loop.run_until_complete(loop.shutdown_default_executor())
            finally:
                loop.close()
