# Graph projection qualification — 0.2.0

Date: 2026-10-10. Baseline: main `f645f20`. Python 3.12.9 on macOS 15.4.1 ARM64.

This report qualifies the extraction and rendering contract. It does not measure
language-model inference quality, production throughput, or remote-database latency.

## Realistic evidence case

The supply-chain demo roots all application nodes under one application root.
Its public Harbor ontology contains exactly nine nodes and ten relationships:
project dependencies, a shared component, a firmware cycle, two suppliers, regions,
and an alternative explicitly marked unverified. A private supplier and its region
are excluded. Expected IDs, paths, direction, permitted attributes, hierarchy
references, and declared ontology meanings are asserted on JSON, SQLite, PostgreSQL,
and MongoDB. The containment view separately returns 17 nodes and 16 edges.

The graph supports a potential exposure inference through a supplier to a region
with a flood warning. It does not establish causality or alternative suitability.
Tests verify this supporting evidence, not a model-generated answer.

## Correctness and configuration

The dedicated suite includes 59 passing cases with all four live/local adapters.
An independent seeded 30-node, 150-edge traversal oracle verifies out/in/both
directions, cycles, bidirectional relationships, denied intermediates, and paging.
Additional cases cover field/type/predicate selection, scope boundaries, malformed
grants, policy/backend errors, stale-cache bypass, revocation before new captures,
missing roots, deleted endpoints, cooperative timeout, and caller cancellation.

Every resource cap has a targeted test: depth, nodes, edges, candidates, per-node
incident work, frontier, canonical bytes, and nested detail. A 500-edge hub returns
a bounded partial result without exact counts. Ontology overhead pruning is tested
for closed endpoints and valid paths. Rendering performs no database reads and
escapes stored labels. Immutable results and input-copy isolation are verified.

## Local scaling measurements

Each case warms initialization before seven capture samples. Seeding is excluded.
The fixed-neighborhood experiment adds 1,000 unrelated edges under another branch.
Numbers are descriptive local samples under a shared development-machine load;
seven samples cannot support a production percentile/SLA claim.

| Backend | Local edges | Unrelated edges | Capture p50 ms | Capture sample p95 ms | Candidates | Adapter operations |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| json | 20 | 0 | 11.559 | 12.397 | 42 | 3 |
| json | 20 | 1000 | 211.858 | 228.282 | 42 | 3 |
| json | 200 | 1000 | 1063.38 | 1148.997 | 402 | 11 |
| sqlite | 20 | 0 | 0.931 | 1.304 | 42 | 3 |
| sqlite | 20 | 1000 | 2.072 | 2.714 | 42 | 3 |
| sqlite | 200 | 1000 | 13.097 | 33.341 | 402 | 11 |
| postgres | 20 | 0 | 6.856 | 9.318 | 42 | 3 |
| postgres | 20 | 1000 | 5.105 | 6.887 | 42 | 3 |
| postgres | 200 | 1000 | 38.886 | 134.61 | 402 | 11 |

The 20-edge result always returns 21 nodes and 20 edges; the 200-edge result
returns 201 nodes and 200 edges. Candidate work stays at 42 or 402 respectively.
JSON physical file reads grow from 44 to 1,044 for the same local neighborhood,
and reach 6,216 for the 200-edge case. Thus output/candidate caps do not make
JSON scans independent of graph size. Native SQLite/PostgreSQL paging limits
transferred records, while SQL physical scan rows remain unknown. MongoDB
correctness is qualified; MongoDB and DynamoDB latency are not measured here.

At 200 local edges, canonical JSON is about 111 KB and text about 113 KB.
Text rendering p50 spans 1.6–2.4 ms and Mermaid 0.69–0.75 ms in these samples.
Canonical `max_bytes` does not cap the separately rendered text/diagram.

Reproduce with `python -m examples.core.graph_projection_benchmark --output result.json`.
Set `JVSPATIAL_PROJECTION_TEST_DSN` for disposable PostgreSQL schemas.
The [raw measurements](2026-10-graph-projection-performance.json) include rendering,
bytes, ordinary CRUD, and environment details.

## Ordinary persistence overhead

A separate comparison used the same SQLite environment and dependencies for
baseline and feature sources, four alternating-order runs, and 500 operations
per sample. The table gives the median of each run’s median in milliseconds.

| Existing operation | Baseline | Feature |
| --- | ---: | ---: |
| db_get | 0.121177 | 0.125927 |
| db_save | 0.119458 | 0.127323 |
| cached_entity_get | 0.001625 | 0.001667 |

The hot paths have no new projection calls or writes. These tiny, noisy samples
do not establish statistical equivalence or a speed improvement. Existing traversal
and persistence regressions are checked by the full repository suite and benchmark
lane. See the [raw comparison](2026-10-graph-projection-crud.json).

## Release checks

- Full suite with whole-package coverage: **2,399 passed, 127 skipped**, zero
  failures. Total coverage 66.68%; projection module coverage **92%** (423
  statements, 32 uncovered). Optional/infrastructure skips remain disclosed.
- Dedicated feature suite: **59 passed** with JSON, SQLite, disposable PostgreSQL
  schemas, and disposable MongoDB databases.
- Benchmark lane: 16 existing/new benchmarks passed and four non-benchmark hub
  recorders skipped under `--benchmark-only`. Two older PostgreSQL benchmarks
  initially failed because their fixture never created its schema. The fixture
  now creates/drops that schema; both targeted reruns passed. All 18 benchmark
  cases were therefore exercised successfully across those runs.
- `pre-commit run --all-files`: all hooks passed, including new staged files.
- Wheel and source distribution for **0.2.0** built; `twine check` passed both.
- A clean temporary environment installed the wheel, passed `pip check`, verified
  imports from site-packages and public exports, and captured the nine-node,
  ten-edge dummy case in all three views on native SQLite.

Commands used: `pytest --cov=jvspatial --cov-report=term-missing`,
`pytest tests/core/test_graph_projection.py --cov=jvspatial`, and
`pytest tests/benchmarks --benchmark-only --benchmark-min-rounds=2 --benchmark-max-time=0.1`.
The whole-package coverage target also avoids a local asyncpg/coverage native
crash encountered with a narrowly selected coverage source. No dependency pins
were changed to work around it.

## Practical limits

- Best-effort multi-read capture can observe concurrent edits; it is not an atomic
  or retained historical snapshot. Current permissions are applied to every new capture.
- Policy/backend failures fail closed. The extraction deadline is cooperative;
  serialization and adapter cancellation/raw-record size have separate costs.
- Completeness applies to permitted filtered traversal within the requested radius,
  not every edge between boundary nodes or a global ontology inventory.
- Native paging is a transfer guarantee, not a constant-time query guarantee.
- No live-provider inference evaluation, distributed load test, DynamoDB live test,
  or production deployment is claimed.
