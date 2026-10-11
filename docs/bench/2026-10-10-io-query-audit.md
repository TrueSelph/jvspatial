# I/O and query performance audit — 2026-10-10

**Conclusion:** jvspatial has strong adapter-level primitives, but several public paths bypass them or do work proportional to the collection instead of the requested result. Fix correctness in iteration, partial filtering, and cache writes first. Then connect entity APIs to bounded reads and native batch writes, repair SQLite ID pagination, and make file streaming incremental.

Audited checkout: `5e6e11a0ecb952ee4f571beb9b902c89a8f43ea1` (0.1.1). Existing release-workflow/documentation edits were left intact. No library implementation, version, SPEC, or changelog changes were made. This audit adds this report, a standalone diagnostic script, and raw results.

## Evidence and limits

- Source review: all five database adapters, query translators, entity/context/pager APIs, graph expansion, cache/observability wrappers, local/S3 file streaming, benchmark code and workflow.
- Executed: temporary SQLite and JSON stores; PostgreSQL 16.13 in a dedicated disposable Docker container; deterministic adapter/wrapper stubs for DynamoDB, S3, and cache edge cases.
- Environment: Python 3.12.9, SQLite 3.51.3, asyncpg 0.32.0, macOS 15.4.1 arm64. PostgreSQL used its default whole-document GIN setting. No application database was used.
- Query fixture: 20,000 raw Object records with a 256-character payload, numeric value, and group. Write comparison: 200 simple Object instances. Setup and warm-up are excluded from diagnostic timings; reads have seven samples, writes five. Native write comparisons use pre-exported records, whereas `GraphContext.save_batch` also performs export/cache work. Thus timings are path comparisons, not isolated driver speedups.
- Reported timings come from a final run without a concurrent audit test process. The host still runs other applications; sample ranges show substantial noise. Operation counts and query plans are stronger evidence than the absolute timings. No production p95/p99 or cross-backend ranking is claimed.
- Focused existing tests: **76 passed, 14 skipped**, four existing marker warnings. PostgreSQL was available for this run. The skipped cases include the explicitly disabled PostgreSQL iterator class, MongoDB without a test URI, and backend-inapplicable PostgreSQL checks. This is not the full test suite or CI qualification.
- Existing SQLite benchmark module: **6 passed**, three measured rounds per case. These are setup-inclusive timings and were not used as isolated query latency evidence.
- Live MongoDB, AWS DynamoDB/S3, serverless cold starts, network latency injection, and sustained concurrency/peak memory workloads were not measured.

Reproduction: [diagnostic script](io_query_audit_20261010.py), [raw results](2026-10-10-io-query-audit-results.json).

```bash
# JSON, SQLite, and deterministic stubs only; no external service needed.
PYTHONPATH=. .venv/bin/python docs/bench/io_query_audit_20261010.py

# Optional PostgreSQL: set AUDIT_POSTGRES_DSN to a DISPOSABLE database.
# The script creates/drops a random schema; asyncpg must be installed.
PYTHONPATH=. AUDIT_POSTGRES_DSN="$DISPOSABLE_POSTGRES_DSN" \
  .venv/bin/python docs/bench/io_query_audit_20261010.py

# Existing focused regression slice, using the same disposable PostgreSQL service:
JVSPATIAL_POSTGRES_TEST_DSN="$DISPOSABLE_POSTGRES_DSN" \
  .venv/bin/python -m pytest tests/db/test_sqlite.py \
  tests/db/test_cursor_pagination.py tests/core/test_pager_audit_fixes.py \
  tests/core/test_node_query_pushdown.py tests/db/test_query_operator_parity_audit.py \
  -o addopts='' -q
```

The script records current behavior, including defects; it is an audit probe, not a passing-regression-test specification. Runtime-only dependencies were installed outside the repository environment.

## Measured opportunities

These compare current public paths with existing lower-level alternatives, except the SQLite ID-column query, which is a diagnostic SQL prototype.

| Workload | Current path, median | Comparison, median | Structural evidence |
|---|---:|---:|---|
| SQLite first match, 20k matches | `find_one`: 100.430 ms | `find(limit=1)`: 0.298 ms | 20,000 documents fetched versus 1 |
| PostgreSQL first match, 20k matches | `find_one`: 354.378 ms | `find(limit=1)`: 1.760 ms | 20,000 documents fetched versus 1 |
| SQLite save 200 Objects | `save_batch`: 37.820 ms | `bulk_save`: 1.195 ms | 200 commits versus 1 |
| PostgreSQL save 200 Objects | `save_batch`: 492.841 ms | `bulk_save`: 15.629 ms | Serial saves versus COPY/temp-table merge |
| SQLite detailed save 200 records | `bulk_save_detailed`: 44.706 ms | `bulk_save`: 1.195 ms | Detailed API inherits serial implementation |
| SQLite ID cursor page, 50 rows | translated `find`: 14.854 ms | physical-ID SQL: 0.238 ms | Collection scan + temporary sort versus indexed ID range |

Additional deterministic observations:

- Page 200 at 50 rows/page fetches **9,950 discarded full records plus 50 returned records**, and separately counts matches, on both SQLite and PostgreSQL.
- JSON iteration of 500 records at batch size 50 performs **5,500 record-load attempts**: ten full scans plus the final empty-page scan.
- Both SQLite and PostgreSQL custom-sort iteration returned **1 of 3 records** in the reproduction.
- The S3 streaming probe completed **100 chunks plus an EOF read before yielding its first chunk**.

## Prioritized findings and recommendations

Priority 1 means fix before expanding production use of that path; Priority 2 is scaling and operability work. Effort estimates below are relative, not delivery commitments.

### F01 — P1: Iterators silently lose rows outside ascending ID order

**Evidence:** `jvspatial/db/database.py:366–462` and `jvspatial/db/postgres.py:1898–1985`. Both advance with `id > last_id` even when the caller supplies another sort or descending ID. PostgreSQL appends ID to ORDER BY but does not encode the primary sort value into its continuation predicate.

**Reproduction:** records `a:30, b:20, c:10`, ordered by rank ascending, batch size 1, should yield `c,b,a`; both adapters yield only `c`. Descending ID also yields only `c`. The inherited implementation affects JSON, SQLite, MongoDB and DynamoDB; live reproduction covered SQLite and PostgreSQL.

**Recommendation:** implement a shared composite cursor using every sort field plus unique ID, preserving directions and missing/null ordering. Until supported, reject unsupported sorts explicitly. Validate positive, bounded batch sizes. `GraphContext.find_page` and the keyset helpers are existing building blocks, but must be parity-tested before reuse.

**Also:** PostgreSQL holds a pool connection across every consumer `yield`. The live probe shows zero idle connections while a consumer pauses with the only opened connection checked out. Ordinary resumable pages should acquire/release per page; retain a deliberately scoped connection/transaction only for an explicit consistency contract. Add cancellation/early-close tests and pool-wait metrics. Merely enlarging the pool conceals this pressure.

**Acceptance:** complete, duplicate-free iteration for asc/desc, tied values, null/missing fields, resume, and wrappers; test paused consumers and cancellation. Effort: medium.

### F02 — P1: DynamoDB partial pushdown drops residual predicates

**Evidence:** `jvspatial/db/dynamodb.py:929–991`, `1233–1268`, `1322–1348`. `_build_filter_expression` skips unsupported predicates. When any filter expression exists, `find` skips the remaining Python match altogether.

**Reproduction:** a real adapter with a stub GSI response receives `category=alpha`, indexed `status=open`, and unindexed `score > 50`. It returns both score 1 and score 100. The stub represents valid server filtering of the indexed fields; no AWS service was contacted.

**Recommendation:** make translation return `(pushed_predicate, residual_predicate)` and always evaluate the residual. Only stop at the requested result count after all predicates pass. Apply the same invariant to scan and GSI paths, across pagination. This is a prerequisite for more aggressive query optimization.

For performance, add native `LastEvaluatedKey` iteration and key-aware access planning, rather than repeatedly rescanning through the generic ID pager. Distinguish key conditions from filter expressions: AWS documents that filters apply after reads and do not reduce read capacity. [AWS reference](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/Query.FilterExpression.html).

**Acceptance:** mixed indexed/unindexed/operator queries must match the in-memory oracle, including multi-page responses and limits. Measure consumed capacity and scanned/returned counts on live DynamoDB separately. Effort: small/medium for correctness, medium for native iteration.

### F03 — P1: Cache wrapper can publish failed writes and hide native iteration

**Evidence:** `jvspatial/db/_cache.py:262–291`, `356–358`; inherited `Database.find_iter`.

`bulk_save` caches every submitted record after receiving only a success count. JSON can return a partial count, so an unsuccessful write can be returned by a subsequent cached `get`. The diagnostic backend reports zero saved records and no persisted value; the wrapped `get` nevertheless returns the submitted record.

Separately, `CachingDatabase` has no `find_iter` override. Because the method exists on the base class, `__getattr__` never forwards it. A stub native iterator was called **zero times** through the public factory's cache wrapper. This prevents native cursor/iteration enhancements from reaching cached deployments.

**Recommendation:** invalidate all attempted IDs for count-only partial-success APIs, or consume accurate per-record outcomes before promoting cache entries. Explicitly forward native iterators with correct generator cleanup. Preserve transaction invalidation and current scope boundaries; do not enable wider caching to mask excess reads.

**Acceptance:** partial failures never become cache hits; native iterator delegation and cleanup work for cache-only, observe-only, and combined wrappers. Effort: small.

### F04 — P1: `find_one` is an unbounded read on every built-in adapter

**Evidence:** `jvspatial/db/database.py:464–477`; `Object.find_one` delegates at `jvspatial/core/entities/object.py:754–788`. Built-ins do not override the base method.

It calls `find(collection, query)` and takes the first item. Unique indexed matches avoid the worst case, but broad predicates fetch/decode every match. The 20k fixture demonstrated this on two live backends.

**Recommendation:** pass `limit=1` in the base implementation. Implement early-stop scanning where unsupported-query/JSON fallback paths still materialize everything despite a limit. Preserve ordering semantics; a no-sort first match has no guaranteed stable order.

**Acceptance:** one returned raw record on pushdown paths, bounded early exit on supported fallback paths, no change to no-match behavior. Effort: small for base fix, medium for scan execution.

### F05 — P1: Entity batch writes bypass native batch implementations

**Evidence:** `jvspatial/core/context.py:1749–1847`: Nodes always take serial `self.save`; other entities check the DynamoDB-specific `batch_write` method and otherwise perform serial `db.save`. The generic `bulk_save`/`bulk_save_detailed` capability is unused.

Additionally, only PostgreSQL overrides `bulk_save_detailed`; JSON, SQLite, MongoDB and DynamoDB inherit the serial base loop at `jvspatial/db/database.py:533–585`, despite having native `bulk_save` implementations. SQLite SQL tracing confirms 200 independent transactions for both context and detailed saves versus one for `bulk_save`.

**Recommendation:** unify adapter bulk execution and structured per-record outcomes, then route context batches through it by collection. Preserve validation, index preparation, entity-specific save behavior, migrations, cache invalidation, and honest partial-success semantics. Do not replace Node saves mechanically without deciding which lifecycle behavior must run per entity. Use bounded chunk sizes for memory and backend limits.

**Acceptance:** bounded native wire operations/transactions; full success, duplicate IDs, partial failure, cache updates, and entity hooks match the documented contract. Effort: medium.

### F06 — P1: SQLite ID pagination misses the existing primary-key index

**Evidence:** `jvspatial/db/_sqlite_translate.py:93–100`, `283+`; schema at `jvspatial/db/sqlite.py:197–220`; generic find at `660–751`.

The table already has `(collection, id)` as its primary key. The translator instead generates `json_extract(data, '$.id')`, including a null-sorting expression. The recorded plan uses the collection index and a temporary B-tree for sorting. A physical-column range query uses the primary-key index directly. This is avoidable even before adding application indexes.

**Recommendation:** map ID filter/sort expressions to the physical non-null ID column consistently, including joined aliases. Verify the adapter's raw-record ID coercion contract first so SQL and returned JSON cannot disagree. Avoid a redundant null discriminator for this guaranteed non-null field. Add plan assertions, not latency-only tests.

For annotated compound sorts, `create_index` also ignores requested key direction (`sqlite.py:431–435`), and generated null-discriminator ORDER BY terms need matching index expressions. Repair based on actual EXPLAIN plans and workload shapes; retain missing-last behavior. SQLite requires expression/query alignment for expression-index use. [SQLite reference](https://www.sqlite.org/expridx.html).

**Acceptance:** ID pages use the indexed range without a temporary sort; multi-key mixed-direction and nullable-field plans are checked separately. Effort: small/medium.

### F07 — P1 for large files: “Streaming” buffers the entire file

**Evidence:** both `jvspatial/storage/interfaces/local.py:631` and `s3.py:529` call `await asyncio.to_thread(list, _read_chunks())` before yielding.

This offloads blocking reads but retains all chunks in memory and delays the first byte until the entire object is read. The S3 stub confirms the full read and close before the first yield. Local storage has the same source pattern; no live S3 throughput claim is made.

**Recommendation:** use incremental worker reads or a bounded producer/consumer queue, preserving backpressure. Close file/body handles in `finally`, including cancellation and consumer abandonment. Benchmark chunk sizes; avoid assuming 8 KiB is optimal when each read crosses a thread boundary.

**Acceptance:** first chunk arrives before EOF; memory depends on chunk size/queue capacity rather than total file size; abort closes resources promptly. Effort: small/medium.

### F08 — P2: JSON has repeated full scans, unbounded scheduling, and synchronous metadata I/O

**Evidence:** `jvspatial/db/jsondb.py:316–350`, `353–384`, `424–473`. `find` and filtered `count` gather all records before matching. Count is described as streaming but holds the complete decoded list. The default iterator repeatedly invokes this full scan: 500 records produced 5,500 load attempts.

Read helpers also split existence checks and reads into two thread submissions per file (`210–233`). `_get_collection_dir`/`_get_record_path` perform mkdir/resolve and first-use sweep work synchronously when invoked by async read methods (`136–186`, `307–310`). A first-use initialization lock can block the loop while another thread performs the sweep. SQLite also performs synchronous directory creation during connection initialization (`sqlite.py:177–190`).

**Recommendation:** bounded batches/worker queues, one offloaded open/read/parse operation handling missing-file exceptions, incremental matching, and scan-once iteration. Decide explicitly whether a one-time ID list is acceptable or external sorting/indexing is needed; do not claim constant memory while retaining O(N) paths. Move all filesystem metadata work off the event loop without weakening path confinement, locks, or fsync durability.

**Acceptance:** O(N) record reads per full JSON iteration; bounded in-flight reads; loop-lag tests under slow metadata/read operations; unchanged crash-safety and path tests. Effort: medium.

### F09 — P2: Page-number navigation transfers discarded documents

**Evidence:** `jvspatial/core/pager.py:142–195`. Every numbered page counts all matches, then downloads either the entire prefix to establish an ID pivot or `offset + page_size` full documents for custom sort. The comment “minimal projection” is inaccurate: there is no projection argument in this call.

**Recommendation:** prefer `GraphContext.find_page` for forward navigation with a qualified composite cursor; make exact counts optional. Keep numbered paging for compatibility but document its cost. Add an explicit raw projection/ID-only API for pivot/export workloads without constructing partially hydrated entities. PostgreSQL/SQLite fallback counts should stream match counters instead of building result lists where native COUNT cannot apply.

**Acceptance:** forward page work is proportional to page size when indexed; deep numbered pages do not transfer full discarded payloads; count cost is exposed separately. Effort: medium.

### F10 — P2: Graph expansion bounds output more than database work

**Evidence:** `jvspatial/core/graph_expansion.py:275–301` loads every incident edge before sorting and applying `max_edges_per_node`. `_node_degrees` at `28–35` then issues one count per returned node using unbounded gather. `expand_node` also requests an exact incident count per page (`137–156`).

**Recommendation:** implement bounded incident-edge reads with explicit ordering semantics, frontier-batched node retrieval, and grouped degree queries. Preserve existing spine-priority behavior through an explicit generic policy; blindly adding LIMIT before the Python priority sort would change results. Make exact degree/total counts optional when a consumer only needs a page. Keep walker protection and graph reachability invariants intact.

`GraphContext.nodes_bulk` fallback also fetches all selected neighbor documents before applying node filtering and per-source caps (`context.py:1322–1414`). Push supported predicates earlier and use `find_many` for ID-only lookup.

**Acceptance:** hub work remains bounded as degree grows; count-query number does not scale one-for-one with returned nodes; same traversal/order semantics. Effort: medium/large.

### F11 — P2: Fallback execution and observability need explicit budgets

**Evidence:** PostgreSQL `find` (`postgres.py:964–978`) and SQLite (`sqlite.py:736–751`) materialize a whole collection for untranslatable predicates. Mixed supported/unsupported filters lose all pushdown. `ObservableDatabase` measures adapter calls, not physical wire calls or scanned rows (`_observable.py:109–149`, `420–460`). Its iterator duration includes consumer time across yields. `PerformanceMonitor` retains unbounded event lists (`core/context.py:63–73`), which matters for long-lived contexts.

**Recommendation:** safe partial pushdown for AND clauses plus residual evaluation, following F02's correctness rule; never push LIMIT ahead of residual filtering or an unsupported sort. Add an opt-in scan budget/fallback-refusal policy and explicit plan metadata. Report execution mode, rows/bytes examined and returned, pool wait, retries, actual statements, and iterator active time separately from consumer time. Use bounded samples/aggregate histograms for long-lived monitoring.

Keep regex timeouts and all authorization/transaction boundaries. Do not log raw sensitive query values in new metrics.

**Acceptance:** unsupported predicates are visible, bounded execution is enforceable when requested, metrics distinguish 1 logical bulk call from N wire operations, and long-lived monitoring has bounded storage. Effort: medium.

### F12 — P1 for measurement confidence: Existing benchmarks obscure query regressions

**Evidence:** `tests/benchmarks/test_sqlite_benchmarks.py:49–139` includes database setup and 2,000 individual seed writes inside each measured invocation. PostgreSQL benchmarks likewise include connection/setup/seeding (`test_postgres_benchmarks.py:31–72`). This makes them end-to-end setup benchmarks rather than isolated query measurements.

The benchmark workflow installs `.[dev,test]` (`.github/workflows/benchmarks.yml:68–70`), while asyncpg is in the separate `postgres` extra (`pyproject.toml:63–65`): the service container alone does not ensure PostgreSQL benchmarks execute. The PostgreSQL benchmark helper generates a schema name but never creates it; once asyncpg is available, a fresh schema can fail before benchmarking. It closes the adapter without dropping the schema. The separate hub recorder has different setup and should not be conflated with this helper.

The PostgreSQL iterator test class is unconditionally skipped (`tests/db/test_cursor_pagination.py:219–232`). The suite passing therefore does not establish F01's iterator correctness. CI comparison currently warns at >25% regression; it is not a performance gate (`.github/workflows/benchmarks.yml:193`).

**Recommendation:** persistent-loop fixtures seeded outside timing, separate cold/warm measurements, explicit backend extras, safe schema setup/teardown, and a required “expected backend cases executed” check. Restore iterator tests. Add deterministic statement-count and EXPLAIN gates alongside noisy wall-clock comparisons. Measure end-to-end entity APIs in addition to adapters.

**Acceptance:** query-only measurements react to query changes, no silently absent backend coverage, no leaked benchmark schemas, and correctness/scaling tests cover the defects above. Effort: medium.

## What is already worth preserving

- Native `find_many` implementations and context read batching reduce N+1 reads (`context.py:1849+`).
- PostgreSQL COPY-based bulk writes, entity-leading indexes, count/neighbor pushdown, and optional recursive traversal are valuable existing building blocks.
- PostgreSQL/MongoDB/SQLite neighbor joins avoid loading every edge for ordinary `Node.nodes` calls. Existing focused PostgreSQL pushdown tests ran in this audit.
- Edge-derived adjacency avoids rewriting large hub-node adjacency arrays. The historical [hub audit](2026-09-hub-node-baseline.md) is useful prior evidence, not a current-run benchmark.
- Atomic JSON/local writes, per-path locks, bounded regex execution, and context invalidation are correctness constraints for every optimization.

## Recommended sequence

| Order | Scope | Expected benefit | Completion criterion |
|---|---|---|---|
| 1 | F01–F03 correctness; restore relevant tests | Prevent silent omissions, excess matches, and phantom persisted records | Cross-backend and wrapper correctness cases pass |
| 2 | F04/F05 bounded first-match reads and true entity batching | Largest directly measured reductions in transferred data and transactions | Row/statement-count gates plus preserved lifecycle behavior |
| 3 | F06/F07 indexed SQLite paging and incremental file streams | Predictable page latency and memory under larger datasets/files | EXPLAIN and streaming/backpressure evidence |
| 4 | F08–F11 scan/graph budgets, projection, telemetry | Lower repeated work and visible degradation paths | Scaling tests and operational counters |
| In parallel with fixes | F12 benchmark repair | Trustworthy regression detection | Expected backend cases actually run |

Follow-on enhancement: migrate MongoDB's Motor implementation to PyMongo Async with cursor/transaction/reconnect parity tests. Motor's official documentation sets deprecation at May 14, 2026 and critical-fix support through May 14, 2027. As of this audit, that is a maintenance priority; any throughput improvement still requires measurement. [Motor lifecycle reference](https://motor.readthedocs.io/en/stable/).

Avoid speculative global cache increases, blanket GIN removal, weakened durability, or unbounded concurrent gathers. First remove unnecessary work; then tune pool sizes, batch sizes, and indexes using representative application shapes.

## Documentation discrepancies to track with fixes

These are issue-ready audit findings; no external issue was posted.

- `docs/md/cursor-pagination.md` promises composite-sort iteration and constant memory across backend implementations; F01/F08 contradict those claims.
- `Database.bulk_save_detailed` describes native adapter semantics not implemented by several adapters; F05.
- JSON filtered count and the benchmark guide describe streaming, but gather retains all records; F08.
- `ObjectPager` describes a minimal projection without requesting one; F09.
- Benchmark documentation implies PostgreSQL service coverage that the dependency/setup path does not establish; F12.
- SPEC/ROADMAP still contain older backend/transaction/migration descriptions. Reconcile only alongside corresponding implementation work, as required by AGENTS.md. This report does not change the technical contract.
