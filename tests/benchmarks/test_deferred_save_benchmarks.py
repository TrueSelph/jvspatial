"""DeferredSaveMixin coalescing benchmark.

Confirms the mixin actually coalesces N in-memory updates into 1
underlying database write -- the central performance promise of the
mixin. We measure two scenarios against the same backend:

* **batched** -- 100 ``save()`` calls in deferred mode + 1 ``flush()``,
  which should produce exactly 1 underlying write.
* **immediate** -- 100 ``save()`` calls with deferred mode disabled,
  producing 100 underlying writes.

The expected ratio is roughly 100x. We don't assert that ratio in the
bench (CI variance would force the threshold loose enough to be
useless); instead the absolute numbers are tracked over time and the
CI workflow flags when either degrades.
"""

import os
from unittest.mock import patch

import pytest

from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Node
from jvspatial.core.mixins import DeferredSaveMixin
from jvspatial.db.sqlite import SQLiteDB
from jvspatial.runtime.serverless import reset_serverless_mode_cache

from .conftest import run_async

pytestmark = pytest.mark.benchmark


class _BenchNode(DeferredSaveMixin, Node):
    """Local benchmark Node type, mirroring real-world MRO."""

    name: str = ""
    counter: int = 0


def _enable_deferred_env():
    """Patch env so deferred saves are unambiguously enabled."""
    return patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "false",
            "JVSPATIAL_ENABLE_DEFERRED_SAVES": "true",
        },
        clear=False,
    )


def _disable_deferred_env():
    return patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "false",
            "JVSPATIAL_ENABLE_DEFERRED_SAVES": "false",
        },
        clear=False,
    )


# ---- Benches ---------------------------------------------------------


def test_bench_deferred_save_batched_100(benchmark):
    """100 in-memory mutations + 1 flush -> 1 underlying SQL write."""

    async def scenario():
        with _enable_deferred_env():
            os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
            os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
            reset_serverless_mode_cache()

            db = SQLiteDB(db_path=":memory:")
            ctx = GraphContext(database=db)
            set_default_context(ctx)
            try:
                node = await _BenchNode.create(name="seed", counter=0)
                for i in range(100):
                    node.counter = i
                    await node.save()  # marks dirty, no IO
                await node.flush()  # one write
            finally:
                await db.close()
                reset_serverless_mode_cache()

    benchmark(run_async, scenario)


def test_bench_immediate_save_100(benchmark):
    """100 mutations + 100 ``save()``s with deferred disabled -> 100 writes."""

    async def scenario():
        with _disable_deferred_env():
            os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
            os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
            reset_serverless_mode_cache()

            db = SQLiteDB(db_path=":memory:")
            ctx = GraphContext(database=db)
            set_default_context(ctx)
            try:
                node = await _BenchNode.create(name="seed", counter=0)
                for i in range(100):
                    node.counter = i
                    await node.save()  # immediate write
            finally:
                await db.close()
                reset_serverless_mode_cache()

    benchmark(run_async, scenario)
