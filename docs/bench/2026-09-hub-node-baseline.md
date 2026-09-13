# Hub-node scale baseline (Postgres object-spatial layer)

**Date:** 2026-09-11
**Purpose:** fix the "before" numbers for the hub-node scale remediation, then
append an "after" table per phase. Every phase cites this file.

## How the numbers are produced

Harness: [`tests/benchmarks/test_hub_node_bench.py`](../../tests/benchmarks/test_hub_node_bench.py)
(recorder, not a pytest-benchmark bench). Render tables with
[`tests/benchmarks/hub_bench_report.py`](../../tests/benchmarks/hub_bench_report.py).

```bash
docker run -d --name jvspatial-bench-pg -p 55432:5432 \
  -e POSTGRES_USER=jvspatial -e POSTGRES_PASSWORD=jvspatial -e POSTGRES_DB=jvspatial \
  pgvector/pgvector:pg16 -c shared_buffers=512MB -c max_connections=200

JVSPATIAL_POSTGRES_TEST_DSN=postgresql://jvspatial:jvspatial@localhost:55432/jvspatial \
JVSPATIAL_BENCH_RESULTS=docs/bench/<run>.jsonl \
  pytest tests/benchmarks/test_hub_node_bench.py -m "bench or bench_slow" -s -p no:randomly
python tests/benchmarks/hub_bench_report.py docs/bench/<run>.jsonl
```

Per tier (degree ∈ {1k, 10k, 100k}), on a fresh schema with the default
`Node` / `Edge` / bench-class indexes ensured:

- **Seed** (COPY via `bulk_save_detailed`): one hub with `degree` outgoing
  `BenchContains` edges to `BenchLeaf` nodes, one sink with `degree` incoming
  `BenchContains` edges from the same leaves, plus 82 unconnected spare leaves.
  Records mirror the active adjacency mode — with persisted edge ids the hub
  and sink rows each carry `degree` ids in `edges`.
- **Pool** — `min_size = max_size = 40`, and connections are re-opened right
  before the concurrency burst (asyncpg closes connections idle > 300 s, which
  the 100k read phase exceeds), so samples measure queries and locking, not
  connection establishment.
- **Reads** — 20 samples (5 at 100k), context cache cleared before each so
  every sample is cold; round trips counted with `db_op_counter` through
  `create_database(..., observe=True)`.
- **`save()`** — 50 samples of `hub.counter = i; await hub.save()`.
- **`connect()`** — 50 sequential `hub.connect(spare_leaf, edge=BenchContains)`.
- **Concurrency** — 32 `hub.connect()` calls to distinct spare leaves under
  `asyncio.gather`.
- **Sizes** — `pg_column_size` of the hub row, `node_data_gin`, and total
  relation sizes, after seeding and again after the 82 hub writes.

Raw records: `2026-09-hub-node-phase<N>.jsonl` (one JSON object per tier).
Each phase's code is benchmarked from a clean worktree with the same harness.

**Machine.** Apple M1 Pro (10 cores, 32 GB), macOS 15.4. Postgres 16.14
(`pgvector/pgvector:pg16` in Docker Desktop, `shared_buffers=512MB`). Python
3.11.10, asyncpg 0.31.0. Client and server share the host (loopback), so a
round trip costs ~0.1 ms here. Over a real network every extra round trip
multiplies, so the round-trip counts matter as much as the latencies.

## Before — jvspatial 0.0.17 (`8fc5138`, `edge_ids_mode=persist`)

| operation | 1k p50 / p95 ms (trips) | 10k p50 / p95 ms (trips) | 100k p50 / p95 ms (trips) |
|---|---|---|---|
| `ctx.get(Hub)` (hydrate hub) | 1.0 / 1.5 | 3.9 / 5.1 | 32.4 / 47.7 |
| `hub.connect(leaf, edge=E)` | 6.6 / 7.9 (5) | 23.2 / 52.3 (5) | 160.2 / 581.5 (5) |
| `hub.save()` after scalar change | 11.5 / 13.6 | 110.9 / 137.2 | 1160.6 / 1661.6 |
| `hub.nodes(edge=[E], node=['Leaf'], limit=20)` | 40.7 / 64.5 (3) | 439.6 / 485.6 (21) | 4936.1 / 5184.8 (201) |
| `hub.nodes(edge=E, limit=20)` | 1.1 / 2.0 (1) | 1.1 / 1.7 (1) | 1.3 / 3.0 (1) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in', limit=20)` | 45.6 / 72.1 (3) | 474.4 / 511.8 (21) | 5317.0 / 5338.7 (201) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in')` | 39.3 / 70.5 (3) | 470.0 / 523.0 (21) | 5218.3 / 5379.3 (201) |
| `len(await hub.nodes(edge=[E]))` | 43.3 / 69.0 (3) | 472.2 / 511.0 (21) | 4807.5 / 4881.5 (201) |
| 32× concurrent `connect()` (ms) | 134 wall / 133 max | 813 wall / 813 max | 10276 wall / 10244 max |

| size (after seed → after 82 hub writes) | 1k | 10k | 100k |
|---|---|---|---|
| hub row `pg_column_size(data)` | 26.0 KB → 27.8 KB | 257.5 KB → 251.0 KB | 2.5 MB → 2.4 MB |
| `node_data_gin` size | 192.0 KB → 3.3 MB | 1.6 MB → 8.5 MB | 25.5 MB → 47.3 MB |
| `node` table total | 784.0 KB → 7.6 MB | 6.4 MB → 47.0 MB | 72.8 MB → 346.4 MB |
| `edge` table total | 1.8 MB → 1.9 MB | 16.3 MB → 18.6 MB | 163.9 MB → 164.0 MB |

(`sink.nodes(..., direction='in')` stands in for the brief's
`hub.nodes(..., direction="in")`: the hub has no incoming edges, so the sink
carries the same fan-out inbound. The first recorded run used a cold
`min_size=1` pool, which folded asyncpg connection setup into the samples;
it was superseded by this warm-pool run of the same code.)

### Interpretation

The expected shape holds. Every cost that should scale with the request
instead scales with the hub's degree.

- **Writes.** `connect()` stays at 5 round trips but gets about 24× slower
  from 1k to 100k (p50). `save()` gets about 100× slower (11.5 ms → 1.16 s).
  - Each `connect()` makes two `atomic_add_edge_id` calls. Each call takes
    `SELECT … FOR UPDATE` on the node row, decodes the whole `edges` array,
    applies `$addToSet` in Python, and rewrites the row.
  - `save()` unions the array in SQL (`save_with_edge_merge`) and rewrites a
    2.5 MB row.
- **Row-lock serialisation.** 32 concurrent `connect()`s to one hub queue
  behind each other on the row lock. The slowest call waits for the other 31
  (133 ms at 1k, 10.2 s at 100k), so wall time equals the worst single call.
- **List-form reads.** `nodes(edge=[E], node=[…], limit=20)` skips the join
  fast path. It loads every outgoing edge, hydrates every neighbour in
  500-id `find_many` chunks, then filters and slices in Python.
  - Round trips are `1 + ⌈degree/500⌉ + 1`: 201 at 100k, which is ~5 s to
    return 20 rows.
  - The class form (`edge=E`) takes the join fast path and stays at 1 round
    trip and about 1–2 ms at every tier.
  - The `len(nodes())` count anti-pattern costs the same as a full listing.
- **Index / heap bloat.** Only 82 rewrites of the hub row grow `node_data_gin`
  17× at 1k (192 KB → 3.3 MB) and nearly double it at 100k. The `node` table
  grows from 73 MB to 346 MB, all dead TOASTed copies of the hub row. The
  whole-document `jsonb_path_ops` GIN re-indexes every array element on every
  rewrite.

## After Phase 1 — adjacency derived from the edge table (`edge_ids_mode=derive`)

Code: `23af4c0` + the Phase 1 change set (worktree).

| operation | 1k p50 / p95 ms (trips) | 10k p50 / p95 ms (trips) | 100k p50 / p95 ms (trips) |
|---|---|---|---|
| `ctx.get(Hub)` (hydrate hub) | 0.5 / 0.8 | 0.8 / 1.0 | 0.6 / 3.7 |
| `hub.connect(leaf, edge=E)` | 1.8 / 2.5 (3) | 1.7 / 2.6 (3) | 1.9 / 3.0 (3) |
| `hub.save()` after scalar change | 0.8 / 1.4 | 0.8 / 3.5 | 0.7 / 1.1 |
| `hub.nodes(edge=[E], node=['Leaf'], limit=20)` | 42.1 / 64.5 (3) | 459.2 / 505.0 (21) | 4850.6 / 5425.8 (201) |
| `hub.nodes(edge=E, limit=20)` | 1.3 / 2.7 (1) | 1.2 / 1.7 (1) | 1.4 / 3.7 (1) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in', limit=20)` | 42.5 / 75.5 (3) | 474.4 / 525.2 (21) | 5038.7 / 5254.3 (201) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in')` | 45.4 / 77.5 (3) | 479.2 / 515.2 (21) | 5047.6 / 5195.6 (201) |
| `len(await hub.nodes(edge=[E]))` | 43.6 / 73.2 (3) | 466.9 / 501.1 (21) | 4642.9 / 4915.5 (201) |
| 32× concurrent `connect()` (ms) | 18 wall / 18 max | 29 wall / 29 max | 19 wall / 18 max |

| size (after seed → after 82 hub writes) | 1k | 10k | 100k |
|---|---|---|---|
| hub row `pg_column_size(data)` | 134 B → 136 B | 134 B → 136 B | 134 B → 136 B |
| `node_data_gin` size | 104.0 KB → 112.0 KB | 1.0 MB → 1.6 MB | 13.4 MB → 13.4 MB |
| `node` table total | 504.0 KB → 512.0 KB | 4.2 MB → 4.8 MB | 44.6 MB → 44.6 MB |
| `edge` table total | 1.8 MB → 1.9 MB | 16.5 MB → 16.6 MB | 162.0 MB → 162.1 MB |

**Gate: passed.**

- `connect()` and `save()` are flat across 1k / 10k / 100k.
  - `connect()` p95 is 2.5 / 2.6 / 3.0 ms, and the 100k tier costs 1.1× the
    1k tier (A1 asks for ≤ 1.5×). Before, it was 7.9 / 52 / 582 ms.
  - `save()` p50 is 0.7–0.8 ms at every degree. Before, it was 11.5 ms →
    1.16 s.
  - `connect()` drops from 5 round trips to 3: the two node-row
    read-modify-writes are gone.
- The hub row is 136 B at every degree. After the 82 writes the node GIN and
  table sizes no longer grow at 1k and 100k; before, they multiplied.
- 32-way concurrent `connect()` takes 18–29 ms wall at every degree (≈ 10–16×
  a single call). That cost is event-loop CPU, not locking. Before, it was
  133 ms → 10.2 s, and grew with degree.
- List-form reads are unchanged, as expected. They are Phase 2's target.

## After Phase 2 — neighbour filters, limits and counts pushed into SQL

Code: `dc2a6cc` + the Phase 2 change set.

| operation | 1k p50 / p95 ms (trips) | 10k p50 / p95 ms (trips) | 100k p50 / p95 ms (trips) |
|---|---|---|---|
| `ctx.get(Hub)` (hydrate hub) | 0.5 / 4.0 | 0.8 / 1.4 | 0.6 / 6.4 |
| `hub.connect(leaf, edge=E)` | 1.8 / 2.3 (3) | 1.5 / 1.9 (3) | 1.6 / 2.8 (3) |
| `hub.save()` after scalar change | 0.7 / 1.0 | 0.7 / 3.2 | 0.9 / 2.2 |
| `hub.nodes(edge=[E], node=['Leaf'], limit=20)` | 2.1 / 9.7 (1) | 1.2 / 1.8 (1) | 1.2 / 3.1 (1) |
| `hub.nodes(edge=E, limit=20)` | 1.1 / 2.4 (1) | 1.1 / 1.5 (1) | 1.2 / 6.1 (1) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in', limit=20)` | 1.0 / 1.3 (1) | 1.0 / 1.3 (1) | 1.4 / 2.4 (1) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in')` | 18.7 / 44.7 (1) | 230.9 / 256.1 (1) | 2128.5 / 2187.0 (1) |
| `len(await hub.nodes(edge=[E]))` | 21.7 / 45.4 (1) | 226.0 / 246.9 (1) | 2112.8 / 2182.1 (1) |
| `hub.count_nodes(edge=[E])` | 3.0 / 3.3 (1) | 33.3 / 37.0 (1) | 82.8 / 100.0 (1) |
| 32× concurrent `connect()` (ms) | 16 wall / 15 max | 16 wall / 15 max | 16 wall / 16 max |

| size (after seed → after 82 hub writes) | 1k | 10k | 100k |
|---|---|---|---|
| hub row `pg_column_size(data)` | 134 B → 136 B | 134 B → 136 B | 134 B → 136 B |
| `node_data_gin` size | 104.0 KB → 112.0 KB | 808.0 KB → 816.0 KB | 13.0 MB → 13.0 MB |
| `node` table total | 504.0 KB → 512.0 KB | 3.9 MB → 3.9 MB | 44.2 MB → 44.2 MB |
| `edge` table total | 1.7 MB → 1.9 MB | 16.6 MB → 16.7 MB | 162.2 MB → 162.3 MB |

**Gate: passed.**

- The list form `nodes(edge=[E], node=["Leaf"], limit=20)` is 1 round trip in
  both directions at every tier. Its p50 is 1.0–2.1 ms and flat across tiers.
  - Before, it cost 201 round trips and ~5 s at 100k.
  - The outlier is the 1k out-direction p95 of 9.7 ms. That tier's other
    samples sit at 1–2 ms, so it looks like noise.
- `count_nodes(edge=[E])` replaces `len(await nodes(...))` and is 1 round trip.
  - It takes 83 ms at 100k, against 2.1 s for the `len()` pattern here and
    4.8 s on 0.0.17.
  - It still grows with degree. `COUNT` over the `edge ⋈ node` join has to
    visit every matching row.
- Unbounded listings are now 1 round trip too (2.1 s at 100k, down from ~5 s
  and 201 trips). What remains is hydrating 100k `Node` objects in Python.
  Page instead: `nodes_page(...)`.
- The Phase 1 numbers (connect, save, concurrency, sizes) are unchanged.

## After Phase 3 — entity-leading indexes, optional GIN, `$text`

Code: `905d122` + the Phase 3 change set.

**Typed-find gate.** `test_typed_find_is_index_bound` runs
`find({"entity": "BenchEntry", "context.track_id": t}, sort=[("context.created_at", -1)], limit=20)`
50 times on a shared `node` table of 1M rows. The rows are spread over ten
entities, and `BenchEntry` holds 100k of them: 1000 tracks × 100. The class
declares `@compound_index([("track_id", 1), ("created_at", -1)])`.

| typed find (sorted, limit 20) | rows | p50 / p95 ms | index walked | sort node | node_data_gin |
|---|---|---|---|---|---|
| 0.0.17 `8fc5138` | 1,000,000 | 4.44 / 9.24 | node_context_track_id_context_created_at_idx, node_entity_idx | yes | present |
| Phase 3 `905d122` | 1,000,000 | 0.72 / 2.96 | node_entity_context_track_id_context_created_at_idx | no | off |

**Gate: passed.** p95 is 2.96 ms, well under the 10 ms bar, and the plan is
index-bound with the whole-document GIN off. One scan of
`(entity, track_id, created_at DESC NULLS LAST)` returns the first 20 rows
with no Sort node. On 0.0.17 the same class index skipped `entity` and
ordered descending keys `NULLS FIRST`. Postgres therefore had to AND it with
the entity index and sort every matching row. At this track size that still
stays under 10 ms locally, but the cost grows with the rows per track.

Hub-node numbers on the same code:

| operation | 1k p50 / p95 ms (trips) | 10k p50 / p95 ms (trips) | 100k p50 / p95 ms (trips) |
|---|---|---|---|
| `ctx.get(Hub)` (hydrate hub) | 0.6 / 2.1 | 0.8 / 2.3 | 0.8 / 2.9 |
| `hub.connect(leaf, edge=E)` | 1.7 / 3.0 (3) | 2.0 / 4.0 (3) | 2.7 / 4.2 (3) |
| `hub.save()` after scalar change | 0.8 / 2.1 | 0.7 / 1.3 | 1.2 / 2.4 |
| `hub.nodes(edge=[E], node=['Leaf'], limit=20)` | 1.1 / 2.4 (1) | 1.2 / 2.7 (1) | 1.5 / 3.8 (1) |
| `hub.nodes(edge=E, limit=20)` | 1.0 / 2.4 (1) | 1.3 / 2.5 (1) | 3.6 / 6.0 (1) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in', limit=20)` | 1.1 / 1.4 (1) | 1.3 / 3.7 (1) | 2.1 / 6.8 (1) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in')` | 19.2 / 47.8 (1) | 237.7 / 248.8 (1) | 2118.2 / 2203.4 (1) |
| `len(await hub.nodes(edge=[E]))` | 20.5 / 48.5 (1) | 239.0 / 254.5 (1) | 2086.3 / 2092.6 (1) |
| `hub.count_nodes(edge=[E])` | 3.5 / 4.4 (1) | 35.7 / 37.8 (1) | 89.2 / 141.5 (1) |
| 32× concurrent `connect()` (ms) | 16 wall / 16 max | 16 wall / 15 max | 15 wall / 14 max |

The Phase 1 and 2 results hold. The Edge `(source, target, entity)` unique
index is now built on the real `entity` column. Its definition changed, but
traversal latencies stay within run-to-run noise.

Seeding note: the Phase 3 hub tier seeds through `create_database(observe=True)`,
which now forwards `bulk_save_detailed` to COPY (fixed in `905d122`). Earlier
tiers seeded per record; that only affected setup time, not the measured
operations.

## Final pre-release — `51186f1` (Phase 5 + wrappers/tenant fixes)

Raw: [`2026-09-hub-node-final.jsonl`](2026-09-hub-node-final.jsonl). Same machine and
Postgres image as the Phase 0–3 runs. Confirms the full stack still holds the
gates before cutting 0.0.18.

| operation | 1k p50 / p95 ms (trips) | 10k p50 / p95 ms (trips) | 100k p50 / p95 ms (trips) |
|---|---|---|---|
| `ctx.get(Hub)` (hydrate hub) | 0.7 / 1.0 | 0.6 / 1.2 | 0.9 / 1.9 |
| `hub.connect(leaf, edge=E)` | 2.1 / 3.3 (3) | 1.9 / 2.8 (3) | 2.1 / 3.4 (3) |
| `hub.save()` after scalar change | 0.8 / 1.3 | 0.8 / 4.2 | 0.8 / 1.4 |
| `hub.nodes(edge=[E], node=['Leaf'], limit=20)` | 1.2 / 1.5 (1) | 1.2 / 1.8 (1) | 1.7 / 2.6 (1) |
| `hub.nodes(edge=E, limit=20)` | 1.4 / 2.0 (1) | 1.4 / 1.8 (1) | 2.0 / 2.0 (1) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in', limit=20)` | 1.3 / 2.2 (1) | 1.3 / 1.9 (1) | 1.6 / 2.0 (1) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in')` | 23.1 / 48.7 (1) | 274.7 / 281.4 (1) | 2493.6 / 2600.1 (1) |
| `len(await hub.nodes(edge=[E]))` | 23.0 / 50.7 (1) | 276.8 / 344.6 (1) | 2367.4 / 2500.3 (1) |
| `hub.count_nodes(edge=[E])` | 3.8 / 4.2 (1) | 43.0 / 47.9 (1) | 103.3 / 110.7 (1) |
| 32× concurrent `connect()` (ms) | 18 wall / 18 max | 19 wall / 19 max | 17 wall / 16 max |

| size (after seed → after 82 hub writes) | 1k | 10k | 100k |
|---|---|---|---|
| hub row `pg_column_size(data)` | 134 B → 136 B | 134 B → 136 B | 134 B → 136 B |
| `node_data_gin` size | 104.0 KB → 280.0 KB | 808.0 KB → 816.0 KB | 10.5 MB → 10.5 MB |
| `node` table total | 504.0 KB → 704.0 KB | 4.0 MB → 4.0 MB | 41.8 MB → 41.8 MB |
| `edge` table total | 1.8 MB → 2.1 MB | 16.5 MB → 16.5 MB | 161.7 MB → 161.8 MB |

| typed find (sorted, limit 20) | rows | p50 / p95 ms | index walked | sort node | node_data_gin |
|---|---|---|---|---|---|
| `51186f1` | 1,000,000 | 1.03 / 1.81 | node_entity_context_track_id_context_created_at_idx | no | off |

**Gates: still passed.**

- A1: `connect()` 100k p95 is 3.4 ms vs 3.3 ms at 1k (≈ 1.0×; bar ≤ 1.5×).
  `save()` p50 stays ~0.8 ms at every tier.
- A3: list-form `nodes(..., limit=20)` is 1 round trip and flat (~1–3 ms).
- A6: typed find p95 1.81 ms, index-bound, GIN off.
- Concurrent `connect()` wall ≈ 17–19 ms at every degree (no row-lock serialisation).
- Numbers sit within run-to-run noise of the Phase 3 table.
