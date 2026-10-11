# I/O and query performance implementation — 2026-10-10

The twelve findings in the [audit](2026-10-10-io-query-audit.md) now have implementation changes and regression coverage. The validation below was completed before pull-request preparation; no release or deployment was performed. Existing release-workflow edits were kept separate.

## Changes by finding

| Finding | Implementation | Verification |
|---|---|---|
| F01: lost rows / held PostgreSQL connections | Composite cursors include every key, direction and ID; validate batch sizes; typed PostgreSQL numeric/null sorts; per-page pool release; native Mongo cursor cleanup. Existing ID cursors remain usable for ID order. | Ascending/descending, ties, multiple keys, missing/null, resume, numeric values beyond 9, paused consumers; live PostgreSQL and both Mongo drivers. |
| F02: Dynamo residual filters | Re-evaluate residual predicates on every GSI/scan page before limiting. Add unordered `scan_page` with native LastEvaluatedKey, predicate-bound cursor and evaluated-item cap. | Deterministic multi-page GSI/scan stubs, mixed operators, empty matched page with continuation, mismatched cursor rejection. |
| F03: failed writes cached / native iteration masked | Invalidate attempted IDs on errors or uncertain counts; promote only confirmed outcomes; explicit wrapper iterator delegation and cleanup. | Cache-only and combined wrappers, partial bulk failures and native iteration, transaction/cache regressions. |
| F04: unbounded first match | Base `find_one` uses limit=1; JSON/SQL residual matching can stop once the requested match count is reached. | One raw result instead of 20,000; residual early-stop counters. |
| F05: serial entity/detailed writes | Context preparation is shared with individual context saves; chunks of 500 by collection use native detailed writes and preserve success/input ordering. Native JSON/SQLite/Mongo/Dynamo detailed APIs report honest outcomes. PostgreSQL duplicate IDs take the final input, and configured physical vector columns are populated within the batch transaction. | One SQLite commit for 200 entities, duplicate IDs and partial outcomes, mixed collections, transaction-handle routing, pgvector ranking. |
| F06: SQLite IDs / sort indexes | ID translation uses the physical primary key. Retain equality/unique indexes and add companions matching nullable sort expressions, directions and ID tiebreaker. Distinct direction signatures have distinct names; PostgreSQL typed sort companions retain identifier-length bounds. | EXPLAIN uses ID ranges without temporary sorting; mixed-direction, nullable and repeated-direction index setup; live PostgreSQL entity-leading index plan. |
| F07: whole-file buffering | Local/S3 streams bridge one worker read per consumer advance, close in finally and wait for in-flight work before cancellation cleanup. | First read yields a chunk before EOF; backpressure, early close, blocked-read cancellation and invalid chunk sizes. S3 uses a deterministic body stub. |
| F08: repeated JSON scans / scheduling | Single-pass ID iteration, bounded read/save groups (32), streamed count/match, one open/read/parse operation, async-path metadata offloading. SQLite directory creation is deferred to async connection initialization. | 500 files cause 500 loads instead of 5,500; in-flight read cap; existing atomic, confinement and loop-rebind coverage. |
| F09: discarded page payloads / count overhead | Native SQL/Mongo `find_ids` projection with offset; hydrate only chosen IDs. `ObjectPager(count_total=False)` uses lookahead and None totals; keysets remain the forward-navigation API. | Deep-page selected-ID hydration, ordering/null boundaries, filter constraints, count-free navigation. |
| F10: hub loads / per-node counts | Bounded queries for each explicit generic priority tier and ordinary incidents; frontier-batched nodes; grouped SQL/Mongo degrees; optional exact counts. Priority predicates match the opposite endpoint, including when the center shares its prefix. Scheduled nodes stay within max_nodes. Filtered `nodes_bulk` reads push predicates into the node query; plain ID retrieval uses find_many. | Hub transfer cap, priority compatibility and opposite-endpoint regression, grouped self-loop degree parity, count-free expansion and graph traversal tests. |
| F11: fallback budgets / monitoring | Safe conjunction pushdown plus full residual matching; candidate streaming/counting; optional SQL fallback_scan_limit raises rather than truncating. Context-local execution metadata, decoded bytes, PostgreSQL pool wait and retry-driver attempt counts. Iterator active duration is separate from total duration. Diagnostic samples are bounded; counts, means and byte/cache totals remain lifetime aggregates. | Partial AND versus OR/NOT behavior, regex flags retained, early exit / budget rejection / released pool, metadata isolation, retry counts and monitoring retention. |
| F12: benchmark setup / silent service skips | Warm query measurements reuse one loop/store with setup and cleanup outside timing. CI installs the PostgreSQL extra and rejects skipped PostgreSQL cases. Methodology stamp prevents comparison with the old setup-inclusive baseline. | All timed benchmark cases execute; both PostgreSQL cases present and unskipped; workflow YAML / embedded Python validation. |

The follow-on driver enhancement is available as `create_database("mongodb", ..., driver="pymongo")`. Motor remains the compatibility default. Live tests pass on PyMongo 4.18.2 and the declared minimum 4.13.2. [MongoDB documents the driver differences](https://www.mongodb.com/docs/languages/python/pymongo-driver/current/reference/migration/); no general throughput advantage is claimed from changing drivers alone.

## Repeated diagnostic results

The original [baseline JSON](2026-10-10-io-query-audit-results.json) is preserved. The same [probe script](io_query_audit_20261010.py) produced separate [implementation results](2026-10-10-io-query-implementation-results.json).

| Local workload | Audit median (ms) | Implementation median (ms) |
|---|---:|---:|
| SQLite find_one, 20k matches | 100.430 | 0.118 |
| PostgreSQL find_one, 20k matches | 354.378 | 1.617 |
| SQLite context save_batch, 200 Objects | 37.820 | 5.320 |
| PostgreSQL context save_batch, 200 Objects | 492.841 | 15.694 |
| SQLite detailed bulk save, 200 records | 44.706 | 1.011 |
| SQLite ID page, 50 rows | 14.854 | 0.675 |

Stronger structural evidence:

- Both first-match probes request and return **one** raw row, rather than 20,000.
- All three SQLite write paths (context, ordinary bulk, detailed bulk) now use **one commit** for 200 records. The count of INSERT statements remains 200.
- SQLite ID pagination uses its primary-key range and no temporary sort.
- JSON iteration performs **500 loads for 500 records**, versus 5,500 before.
- The S3 probe reads **one chunk** before yielding, versus 100 chunks plus EOF before.
- Composite/descending probes return all three rows; the Dynamo probe rejects its low-score false match; failed bulk data stays absent from the cache.
- A paused PostgreSQL iterator leaves its pool connection idle.
- Numbered pager probes use the new projection/hydration methods. Their empty `find_calls` list means no calls to the old full-document find path, **not zero database operations**. Native SQL/Mongo still perform projection and hydration, plus an exact count unless disabled.

These timings are local diagnostics on a busy macOS host, not production p95/p99 or cross-backend rankings. Setup/warm-up are excluded, reads have seven samples and writes five. Export/cache preparation remains included in context save_batch. PostgreSQL qualification used disposable PostgreSQL 16.14 with pgvector; the original audit used PostgreSQL 16.13. Python 3.12.9 and SQLite 3.51.3 were used. Live MongoDB qualification used a disposable standalone 8.0.32 server.

## Validation

- Full implementation suite: **2,416 passed, 108 skipped**, with live PostgreSQL/pgvector and MongoDB, including the final priority/direction regressions. Statement coverage: **68.22%** (15,543 of 22,782 statements). The run completed in 301.12 seconds with 109 warnings.
- Focused checks include 149 passing adapter/context/storage tests; another 50 pass with PyMongo 4.13.2, including both live drivers. Final plan/priority checks are also passing.
- Benchmarks: **15 passed, 4 skipped**. Both PostgreSQL benchmark cases executed. The four skips are the separate, untimed hub scale recorder, which pytest-benchmark excludes in benchmark-only mode.
- All configured pre-commit hooks pass on a clean staged-tree snapshot using `pre-commit run --all-files`, including Flake8 plugins, default mypy settings and secret scanning. Workflow YAML and embedded Python compile; git diff whitespace checks pass.
- Commit preparation replaced iterator instrumentation's Python 3.10-only `anext` call with `__anext__`, bound the DynamoDB retry closure explicitly, and completed formatting/docstrings. Follow-up regression runs passed **61 tests (12 service-dependent skips)** and **57 tests** for adapters, bounded queries, observation and streaming. The isolated pre-commit environment avoids the installed pytest syntax issue encountered during earlier manual mypy checks.
- No GitHub Actions, release artifacts or deployment qualification was performed.

Reproduce against disposable services:

```bash
PYTHONPATH=. \
  JVSPATIAL_POSTGRES_TEST_DSN="$DISPOSABLE_POSTGRES_DSN" \
  JVSPATIAL_MONGODB_TEST_URI="$DISPOSABLE_MONGODB_URI" \
  pytest -q -o addopts='' --ignore=tests/benchmarks --cov=jvspatial

JVSPATIAL_POSTGRES_TEST_DSN="$DISPOSABLE_POSTGRES_DSN" \
  pytest tests/benchmarks --benchmark-only

AUDIT_POSTGRES_DSN="$DISPOSABLE_POSTGRES_DSN" \
  python docs/bench/io_query_audit_20261010.py > new-results.json
```

## Adoption notes and remaining qualification

- `save_batch` now propagates backend exceptions after invalidating attempted identities. It is not atomic across collections. Use graph_transaction where supported, or handle structured partial outcomes/reconciliation. Context saves do not invoke overridden entity.save hooks; applications needing those hooks should call them explicitly.
- Companion indexes consume extra space and add write maintenance. Index creation is idempotent and uses separate names for sort directions; existing equality and unique indexes remain in place.
- JSON keeps O(N) file paths, and custom sorted JSON/unsupported SQL ordering retains matching records. The scan budget is opt-in and counts evaluated residual candidates; it does not constrain a native SQL plan, driver prefetch or DynamoDB scan capacity.
- Native DynamoDB scan_page is unordered. Continue past empty match pages until the cursor is None. Sorted DynamoDB find_iter retains its compatible generic keyset path; use native scan pages where ordering is unnecessary.
- Exact graph counts remain the default and may scan many edges. include_counts=False removes that work and returns unknown values as None. Transfer caps do not imply constant database work without suitable indexes.
- Paging remains live. Mutable sort keys can skip/revisit rows; separate projection/hydration may observe deletes. Use supported transactions or an immutable snapshot for stronger consistency.
- Monitoring's driver attempts, decoded bytes and evaluated candidates are not physical protocol round trips, packet bytes or server EXPLAIN rows. Full transport tracing and sustained production pool/latency histograms need deployment instrumentation.
- Live AWS DynamoDB/S3 capacity, throttling, large-object transfer, long-running concurrency/peak RSS and serverless cold starts remain workload qualification. DynamoDB and S3 correctness tests here use deterministic adapters/bodies. The standalone Mongo tests do not qualify replica-set transactions; topology gating and transaction mocks are covered separately. A default-driver cutover needs downstream qualification and a compatibility cycle.
