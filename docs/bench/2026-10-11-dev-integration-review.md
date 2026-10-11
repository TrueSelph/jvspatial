# Dev integration review — 2026-10-11

This integrates the three open pull requests into `dev` for testing. It does
not promote changes to `main`, publish a package, or change version `0.1.1`.
Release notes remain under `Unreleased`.

## Reviewed inputs

| PR | Head commit | Assessment |
|---|---|---|
| [#53](https://github.com/TrueSelph/jvspatial/pull/53) | `2a51d6778d81b038e71e99edb29ec76de2242fbe` | Artifact action v25 → v27. Upstream comparison changes workflow-run discovery/logging; runtime and input contracts are unchanged. Existing benchmark inputs remain supported. |
| [#54](https://github.com/TrueSelph/jvspatial/pull/54) | `33666d6afeb3e2fac8da9abc9ddb3cc9f2141d6d` | Read-only graph projections retain explicit scope/access, evidence paths, completeness markers, budgets, and fresh reads. Inference remains downstream. |
| [#55](https://github.com/TrueSelph/jvspatial/pull/55) | `6e0195363d4d8d5c095e4ddc842a308199e50573` | Composite cursors, residual predicates, confirmed bulk outcomes, native wrapper forwarding, and bounded transfer/streaming are covered by regression tests. Repeated cancellation required the additional fix below. |

All checks on these exact PR heads passed before integration. Combined checks
are separate evidence; a green individual PR does not establish merge fitness.

## Reconciliation and review findings

- Main baseline: `f645f20ea64bd72bc02254dbffc06b6c3cbaecc7`.
  Previous dev: `2209937aa8d9115411319c25daba3e9e34de3965`.
  The old dev tree is identical to historical main release `9b3fac2`
  (tree `f4283bed48bb78ed6068e97ce636ed29fdff8d46`). Its content is already in
  main through that squash release. The merge preserves dev history and takes
  current main content before integrating the PRs.
- Cache/observability conflicts retain both projection methods and the I/O
  methods. They mirror native graph paging capability, bypass stale projection
  node caches, and preserve native iteration, ID paging, degree counts, and
  uncertain-write invalidation.
- PostgreSQL benchmarks use explicit disposable schemas, seed outside timed
  operations, and close/drop resources. Both live PostgreSQL cases executed.
- Changelog conflicts retain both feature sets under `Unreleased`. The merged
  pytest configuration retains source-tree imports; PyMongo's minimum stays
  `4.13.0`. SPEC citations for overlapping code are updated.
- A reproduced stream race allowed a second cancellation to cancel the task
  awaiting a blocking worker, closing its reader during an active read.
  The integration fix repeatedly shields/drains the worker before cleanup and
  preserves cancellation. Regression tests cover opening, reading, and closing.
- New combined tests run the rooted supply-chain example through native batch
  writes, wrapped ID queries and degree counts, then fresh ontology captures.
  Earlier captures remain immutable; restricted suppliers and private fields
  stay excluded. Cache-only, observation-only, and combined wrappers execute.
- `save_batch` uses normal context-save preparation and returns confirmed
  successes in input order. Storage exceptions propagate after invalidation;
  writes across collections remain best-effort. It does not invoke entity
  `save()` overrides, consistent with individual context saves.

## Combined local validation

Python 3.12.9; fresh editable installation with `dev,test,postgres,pgvector,lambda`.
Disposable PostgreSQL/pgvector 16 and MongoDB 8.0 services were used. MongoDB
tests exercised both Motor and PyMongo Async; projection tests exercised JSON,
SQLite, PostgreSQL, and MongoDB.

| Check | Result |
|---|---|
| `pytest tests/ -q --tb=short --cov=jvspatial --cov-report=term --cov-fail-under=60` | 2,578 passed, 22 skipped; 69.95% coverage; 179.87 seconds |
| Graph projection module within that full run | All 62 cases passed, including live backend variants |
| `pytest tests/benchmarks --benchmark-only --benchmark-min-rounds=5` | 18 passed, 4 non-benchmark cases skipped; both PostgreSQL cases executed |
| `pre-commit run --all-files` | All hooks passed |
| `pip check` | No dependency conflicts |
| Clean wheel build/import | `0.1.1`; imports from installed wheel; async projection and batch APIs present |

To reproduce live coverage, set `JVSPATIAL_POSTGRES_TEST_DSN` and
`JVSPATIAL_PROJECTION_TEST_DSN` to a disposable PostgreSQL database, and
`JVSPATIAL_MONGODB_TEST_URI` and `JVSPATIAL_PROJECTION_MONGO_URI` to a disposable
standalone MongoDB service before running the commands above. Fixtures use
isolated schemas/databases and clean them up.

Dev pushes now trigger tests, lint, the dependency audit, and benchmarks. The
test matrix provisions live PostgreSQL and MongoDB on Python 3.10–3.12.
Benchmark baseline publication remains restricted to main; PyPI publication
triggers are unchanged. Remote workflow results must be checked for the pushed
dev commit separately from these local results.

## Qualification limits

These checks do not establish production throughput, concurrency, cold-start
latency, live AWS capacity/throttling, or MongoDB replica-set transaction
behavior. DynamoDB/S3 coverage uses local doubles. Projection output/candidate
budgets do not prove bounded physical scans or raw-record memory; captures are
best-effort multi-read evidence rather than atomic historical snapshots.
