"""JsonDB performance benchmarks.

These guard the IO wins from Phase A1+A2:
* atomic writes (must stay close to the pre-A1 throughput despite the
  added fsync work; the fsync cost is the price we pay for durability),
* native ``count()`` empty path (dirent count, no JSON parse),
* native ``count()`` filtered path (parse + match without result-list
  materialization).

Each bench seeds N records into a fresh JsonDB instance and times one
representative operation. We intentionally use modest N (a few hundred
to a few thousand) so each individual measurement runs in single-digit
to low-double-digit milliseconds -- ``pytest-benchmark`` then runs many
iterations and reports the distribution.
"""

import pytest

from jvspatial.db.jsondb import JsonDB

from .conftest import run_async

pytestmark = pytest.mark.benchmark


# ---- Seed helpers ----------------------------------------------------


async def _seed(db: JsonDB, n: int) -> None:
    for i in range(n):
        await db.save(
            "node",
            {
                "id": f"n{i:06d}",
                "category": "even" if i % 2 == 0 else "odd",
                "value": i,
                "context": {"name": f"name-{i}", "active": (i % 7 == 0)},
            },
        )


# ---- Writes ----------------------------------------------------------


def test_bench_jsondb_save_throughput(benchmark, temp_dir):
    """Single record save() through atomic-write + per-path lock path.

    This is the hot path for streaming writes. The post-A1 number
    should be a small multiple slower than naive write (we trade
    speed for durability).
    """

    async def one_save():
        db = JsonDB(base_path=temp_dir)
        await db.save("node", {"id": "x", "value": 1})

    benchmark(run_async, one_save)


def test_bench_jsondb_batched_saves_500(benchmark, temp_dir):
    """500 saves to the same fresh instance.

    Useful as a coarse "ops/sec" indicator. Per-path lock + atomic
    write should serialize same-id writes but parallelize different-id.
    """

    async def many_saves():
        db = JsonDB(base_path=temp_dir)
        for i in range(500):
            await db.save("node", {"id": f"r{i}", "value": i})

    benchmark(run_async, many_saves)


# ---- Counts ----------------------------------------------------------


def test_bench_jsondb_count_empty_query(benchmark, temp_dir):
    """Empty count() should not parse any JSON files (A2 pushdown).

    Times a fresh count() against a pre-populated 1000-record
    collection. Regression guard: if someone removes the dirent
    fast path, this will jump by ~10x.
    """

    async def setup_then_count():
        db = JsonDB(base_path=temp_dir)
        await _seed(db, 1000)
        for _ in range(5):  # several counts to amortize setup
            await db.count("node")

    benchmark(run_async, setup_then_count)


def test_bench_jsondb_count_filtered(benchmark, temp_dir):
    """Filtered count() walks every file but skips result-list build.

    Regression guard for the streaming-match path.
    """

    async def setup_then_count():
        db = JsonDB(base_path=temp_dir)
        await _seed(db, 500)
        for _ in range(5):
            await db.count("node", {"category": "even"})

    benchmark(run_async, setup_then_count)


# ---- Find ------------------------------------------------------------


def test_bench_jsondb_find_filtered(benchmark, temp_dir):
    """find() with a simple equality filter on a 500-node collection.

    Exercises the parallel-read codepath plus QueryEngine.match.
    """

    async def setup_then_find():
        db = JsonDB(base_path=temp_dir)
        await _seed(db, 500)
        for _ in range(3):
            results = await db.find("node", {"category": "odd"})
            assert len(results) == 250

    benchmark(run_async, setup_then_find)
