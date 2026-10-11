# Stalled-worktree integration — 2026-10-11

Integrated onto dev from `fcd89ef`, keeping release assignment separate for 0.2.0.
The original Claude worktrees remain untouched and recoverable.

## Disposition

| Worktree | Incorporated | Deliberately excluded |
|---|---|---|
| sleepy-bartik-0b17d8 (`c94b498`) | Descending annotation pass-through, cross-adapter single-field regression tests, PostgreSQL ordering migration. Adapted to current nullable JSONB sort companions and database-instance index caching. | Blanket normalization of direct MongoDB index requests; their explicit name/direction contract is retained. |
| competent-cori-49a9d7 | Default-context installation and restoration in GraphContext tests. | The obsolete storage payload repair, already superseded on dev. |
| goofy-raman-c1089d | Complete PNG/unknown binary fixtures, content-detection boundary tests, python-magic test dependency and active libmagic CI lane. | Trusting extensions/upload hints after libmagic reports unknown binary content; edits to retired CLAUDE.md. |
| angry-bartik-43791b | Regression principle for node `$exists` filtering. Fixed the local helper to match the existing null-as-absent contract. | Changing the shared query/SQL contract so explicit null counts as present. MongoDB's native field-presence behavior remains as documented. |
| laughing-snyder-9fda8a | Verified numeric/null sort fixes and companion indexes already exist on dev. | Replacing newer adapter code with the older implementation. |

## Additional failure-mode review

A live two-worker PostgreSQL probe reproduced a duplicate catalog-name failure
while both workers created the same sort companion. Index creation and repair
now acquire a transaction-scoped advisory lock per schema/canonical index name.
Transactional DDL also restores the original index if repair fails after dropping
its canonical name. Live tests cover concurrent direction migration, duplicate
rejection after migration, injected failure before rename, and exact index
restoration after rollback. Existing descending-plan checks verify use of the
nullable JSONB sort companion without an explicit Sort node.

MongoDB annotation-created single-field indexes retain their legacy ascending
shape because a single-key B-tree serves either direction. Direct adapter index
calls retain the explicitly requested shape/name. Wrapped and unwrapped database
regressions exercise the distinction. DynamoDB single-field list declarations
retain the scalar form's GSI name and ID range key; this is mocked API evidence,
not live AWS qualification.

## Validation

- Local full suite with native PostgreSQL, standalone MongoDB and libmagic:
  **2,782 passed, 22 skipped, 70.62% coverage**. After the final MongoDB compatibility
  refinement and added rollback regression, the complete focused index/node-query
  set passed **55 tests**, including live PostgreSQL migration and rollback.
- GraphContext module: **48 tests** passed in each of two shuffled orders
  (seeds 42 and 77), in separate fresh processes.
- All pre-commit hooks passed. Benchmarks: **21 passed, 4 intentionally skipped**,
  including both live PostgreSQL benchmark cases. JSON results were saved as
  `/tmp/jvspatial-stalled-benchmarks.json`; fresh PR CI reruns the suite and its
  compatible baseline comparison.
- Native services match CI's PostgreSQL pgvector/pg16 and standalone MongoDB 8.
  The first MongoDB run used an existing replica set and failed the test's explicit
  standalone-topology assertion; the isolated standalone rerun passed.

Reproduce using the repository's `pytest --cov=jvspatial --cov-fail-under=60`,
`pytest tests/benchmarks --benchmark-only`, and `pre-commit run --all-files` gates.
Set `JVSPATIAL_POSTGRES_TEST_DSN` and `JVSPATIAL_PROJECTION_TEST_DSN` to an isolated
PostgreSQL test service, and `JVSPATIAL_MONGODB_TEST_URI` and
`JVSPATIAL_PROJECTION_MONGO_URI` to a standalone MongoDB test service. Install the
`test` extra and system libmagic. Benchmarks use disposable PostgreSQL schemas;
local timings are regression observations, not production throughput guarantees.
