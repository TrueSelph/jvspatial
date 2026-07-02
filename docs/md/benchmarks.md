# Performance benchmarks

jvspatial ships a regression-detection benchmark suite using
[`pytest-benchmark`][pytest-benchmark]. The point is **not** absolute
speed numbers (those depend wildly on hardware) but to catch
regressions: if a change makes one of the IO hot paths 25% slower
than it used to be, we want to know on the PR.

## Running benchmarks locally

```bash
pip install -e '.[dev,test]'

# Run the whole bench suite
pytest tests/benchmarks --benchmark-only

# Run one bench module
pytest tests/benchmarks/test_sqlite_benchmarks.py --benchmark-only

# Run one specific benchmark
pytest tests/benchmarks/test_sqlite_benchmarks.py::test_bench_sqlite_count_pushdown \
       --benchmark-only

# Compare against a saved baseline
pytest tests/benchmarks --benchmark-only \
       --benchmark-autosave \
       --benchmark-compare=0001 \
       --benchmark-compare-fail=mean:25%
```

The default `pytest` invocation does **not** run benchmarks (the
`--ignore=tests/benchmarks` flag in `pyproject.toml` skips them) so
the regular dev loop stays fast.

## What's in the suite

The current benches guard the IO hot paths landed in Phases A1 and A2:

* **JsonDB** (`tests/benchmarks/test_jsondb_benchmarks.py`)
  * `test_bench_jsondb_save_throughput` -- single atomic write.
  * `test_bench_jsondb_batched_saves_500` -- 500-write throughput.
  * `test_bench_jsondb_count_empty_query` -- dirent fast path.
  * `test_bench_jsondb_count_filtered` -- streaming match.
  * `test_bench_jsondb_find_filtered` -- parallel-read + filter.
* **SQLite** (`tests/benchmarks/test_sqlite_benchmarks.py`)
  * `test_bench_sqlite_count_empty` -- `SELECT COUNT(*)`.
  * `test_bench_sqlite_count_pushdown` -- translated WHERE +
    `COUNT(*)`.
  * `test_bench_sqlite_count_fallback_via_regex` -- fallback floor.
  * `test_bench_sqlite_find_pushdown` -- WHERE + LIMIT.
  * `test_bench_sqlite_sort_limit_pushdown` -- ORDER BY + LIMIT.
  * `test_bench_sqlite_find_fallback_via_regex` -- legacy fallback.
* **DeferredSaveMixin** (`tests/benchmarks/test_deferred_save_benchmarks.py`)
  * `test_bench_deferred_save_batched_100` -- 100 dirty marks + 1 flush.
  * `test_bench_immediate_save_100` -- comparison case, 100 writes.
* **Postgres** (`tests/benchmarks/test_postgres_benchmarks.py`) — skipped when
  `asyncpg` is unavailable or `JVSPATIAL_POSTGRES_TEST_DSN` is unreachable.
  * `test_bench_postgres_traverse_depth` -- recursive CTE traversal on a
    seeded chain graph.
  * `test_bench_postgres_find_many_bulk` -- bulk fetch by id list.

The `_fallback_*` benches deliberately exercise the *slow* path so
that future contributors who refactor the translator can see whether
the legacy in-Python filter path got faster or slower.

## How CI uses these

`.github/workflows/benchmarks.yml` runs the suite on every PR that
touches `jvspatial/`, `tests/benchmarks/`, or `pyproject.toml`. A
**Postgres service container** (`pgvector/pgvector:pg16`) is started for
the job so Postgres benches run in CI when `asyncpg` is installed.
`JVSPATIAL_POSTGRES_TEST_DSN` defaults to
`postgresql://jvspatial:jvspatial@localhost:5432/jvspatial`.

The workflow:

1. Captures the PR's benchmark results.
2. Downloads the most recent `bench-baseline` artifact (produced by
   the same workflow's last run on `main`).
3. Computes per-benchmark percent change.
4. Posts a markdown comparison table as a PR comment.

A regression > 25% emits a workflow warning but does **not** fail the
build. Hard-gating performance on shared GitHub runners produces too
many false positives to be useful. Treat the comment as a signal to
investigate.

## Writing new benchmarks

Drop a new file in `tests/benchmarks/`. Conventions:

* Module-level `pytestmark = pytest.mark.benchmark`.
* Bench functions take `benchmark` as the first arg (provided by
  `pytest-benchmark`) and call `benchmark(callable, *args)`.
* For async code use the `run_async` helper from
  `tests/benchmarks/conftest.py` -- it runs the coroutine to
  completion in a fresh event loop, which keeps timing apples-to-
  apples between branches.
* Aim for individual measurements between 1 ms and 100 ms. Shorter
  benches are dominated by `pytest-benchmark` overhead; longer ones
  blow out CI time.
* If you change a hot path on purpose -- e.g. you intentionally
  added work for correctness -- rebase main, re-run the workflow on
  main to update the baseline, and note the new floor in
  `CHANGELOG.md`.

## Interpreting results

The most important number per benchmark is **mean** time. The
distribution (`min`/`max`/`stddev`) tells you whether the bench
itself is stable enough to act on. A bench with `stddev` larger
than ~10% of `mean` is too noisy for hard regression detection;
either the workload is too short (increase the inner loop) or it's
inherently variable (consider whether it should be in the suite).

When in doubt, run a bench locally three times in a row. If the
numbers move > 5% between runs on the same code, the noise floor is
too high for tight thresholds.

[pytest-benchmark]: https://pytest-benchmark.readthedocs.io/
