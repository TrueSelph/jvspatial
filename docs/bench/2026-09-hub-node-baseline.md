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
- **Reads** — 20 samples (5 at 100k), context cache cleared before each so
  every sample is cold; round trips counted with `db_op_counter` through
  `create_database(..., observe=True)`.
- **`save()`** — 50 samples of `hub.counter = i; await hub.save()`.
- **`connect()`** — 50 sequential `hub.connect(spare_leaf, edge=BenchContains)`.
- **Concurrency** — 32 `hub.connect()` calls to distinct spare leaves under
  `asyncio.gather` (pool `max_size=40`, so the pool is not the bottleneck).
- **Sizes** — `pg_column_size` of the hub row, `node_data_gin`, and total
  relation sizes, after seeding and again after the 82 hub writes.

Raw records: `2026-09-hub-node-phase0.jsonl` (one JSON object per tier).

**Machine.** Apple M1 Pro (10 cores, 32 GB), macOS 15.4. Postgres 16.14
(`pgvector/pgvector:pg16` in Docker Desktop, `shared_buffers=512MB`). Python
3.11.10, asyncpg 0.31.0. Client and server share the host (loopback), so a
round trip costs ~0.1 ms here. Over a real network every extra round trip
multiplies, so the round-trip counts matter as much as the latencies.

## Before — jvspatial 0.0.17 (`8fc5138`, `edge_ids_mode=persist`)

| operation | 1k p50 / p95 ms (trips) | 10k p50 / p95 ms (trips) | 100k p50 / p95 ms (trips) |
|---|---|---|---|
| `ctx.get(Hub)` (hydrate hub) | 1.0 / 3.6 | 4.2 / 9.2 | 34.1 / 43.6 |
| `hub.connect(leaf, edge=E)` | 7.7 / 11.7 (5) | 21.5 / 48.5 (5) | 162.3 / 558.5 (5) |
| `hub.save()` after scalar change | 11.3 / 13.7 | 107.0 / 123.6 | 1151.3 / 1535.1 |
| `hub.nodes(edge=[E], node=['Leaf'], limit=20)` | 39.5 / 64.3 (3) | 448.2 / 488.6 (21) | 4821.4 / 4835.3 (201) |
| `hub.nodes(edge=E, limit=20)` | 1.3 / 3.7 (1) | 1.1 / 4.0 (1) | 2.0 / 3.9 (1) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in', limit=20)` | 46.7 / 70.8 (3) | 469.9 / 513.6 (21) | 5050.2 / 5104.4 (201) |
| `sink.nodes(edge=[E], node=['Leaf'], direction='in')` | 39.2 / 72.3 (3) | 485.2 / 513.4 (21) | 4972.2 / 5101.1 (201) |
| `len(await hub.nodes(edge=[E]))` | 42.8 / 70.8 (3) | 467.8 / 508.6 (21) | 4682.5 / 4927.7 (201) |
| 32× concurrent `connect()` (ms) | 573 wall / 568 max | 1131 wall / 1121 max | 11665 wall / 11657 max |

| size (after seed → after 82 hub writes) | 1k | 10k | 100k |
|---|---|---|---|
| hub row `pg_column_size(data)` | 25.9 KB → 27.9 KB | 257.2 KB → 251.0 KB | 2.5 MB → 2.4 MB |
| `node_data_gin` size | 192.0 KB → 3.3 MB | 1.6 MB → 8.6 MB | 23.4 MB → 47.3 MB |
| `node` table total | 784.0 KB → 7.6 MB | 6.4 MB → 47.1 MB | 71.0 MB → 337.3 MB |
| `edge` table total | 1.7 MB → 1.8 MB | 16.3 MB → 18.6 MB | 163.8 MB → 163.9 MB |

(`sink.nodes(..., direction='in')` stands in for the brief's
`hub.nodes(..., direction="in")`: the hub has no incoming edges, so the sink
carries the same fan-out inbound.)

### Interpretation

The expected shape holds. Every cost that should scale with the request
instead scales with the hub's degree.

- **Writes.** `connect()` stays at 5 round trips but gets about 21× slower
  from 1k to 100k. `save()` gets about 100× slower (11 ms → 1.15 s).
  - Each `connect()` makes two `atomic_add_edge_id` calls. Each call takes
    `SELECT … FOR UPDATE` on the node row, decodes the whole `edges` array,
    applies `$addToSet` in Python, and rewrites the row.
  - `save()` unions the array in SQL (`save_with_edge_merge`) and rewrites a
    2.5 MB row.
- **Row-lock serialisation.** 32 concurrent `connect()`s to one hub queue
  behind each other on the row lock. The slowest call waits for the other 31
  (568 ms at 1k, 11.7 s at 100k), so wall time equals the worst single call.
- **List-form reads.** `nodes(edge=[E], node=[…], limit=20)` skips the join
  fast path. It loads every outgoing edge, hydrates every neighbour in
  500-id `find_many` chunks, then filters and slices in Python.
  - Round trips are `1 + ⌈degree/500⌉ + 1`: 201 at 100k, which is 4.8 s to
    return 20 rows.
  - The class form (`edge=E`) takes the join fast path and stays at 1 round
    trip and about 1–2 ms at every tier.
  - The `len(nodes())` count anti-pattern costs the same as a full listing.
- **Index / heap bloat.** Only 82 rewrites of the hub row grow `node_data_gin`
  17× at 1k (192 KB → 3.3 MB) and double it at 100k. The `node` table grows
  from 71 MB to 337 MB, all dead TOASTed copies of the hub row. The
  whole-document `jsonb_path_ops` GIN re-indexes every array element on every
  rewrite.

## After Phase 1

_Pending._

## After Phase 2

_Pending._

## After Phase 3

_Pending._
