"""Shared fixtures and helpers for the benchmark suite.

The benchmarks live in their own directory (``tests/benchmarks``) and
are excluded from the default ``pytest`` invocation by the
``--ignore=tests/benchmarks`` flag in ``pyproject.toml``. To run them:

    pytest tests/benchmarks --benchmark-only

Or via the CI workflow at ``.github/workflows/benchmarks.yml``.

Why we run async benches synchronously
--------------------------------------
``pytest-benchmark`` measures the inner timing region only, and its
``benchmark(callable)`` wrapper expects a sync callable. We therefore
run the inner async work via ``asyncio.run(coro())`` inside the bench
target, which gives a fair apples-to-apples timing across runs and
between branches. The event-loop startup cost is paid inside the
measured region but is identical across compared runs, so it doesn't
affect *regression detection* (the only thing we use these for).
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
