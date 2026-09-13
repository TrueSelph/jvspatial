"""Hub-node scale benchmark for the Postgres object-spatial layer.

Records the cost of the operations whose price grows with the *fan-out* of a
node rather than with the size of the request: ``connect()`` / ``save()`` on a
hub, neighbour listings with and without type filters, the
``len(await n.nodes())`` count anti-pattern, the on-disk size of the hub row,
and 32-way concurrent ``connect()`` against one hub (row-lock serialisation).

This is a *recorder*, not a pytest-benchmark regression bench: each tier
prints p50/p95 latencies, DB round trips (``db_op_counter``) and sizes, and
optionally appends a JSON record to ``$JVSPATIAL_BENCH_RESULTS``. The numbers
feed ``docs/bench/2026-09-hub-node-baseline.md``.

Run (Postgres reachable at ``JVSPATIAL_POSTGRES_TEST_DSN``)::

    pytest tests/benchmarks/test_hub_node_bench.py -m bench -s
    # include the 100k-degree tier
    pytest tests/benchmarks/test_hub_node_bench.py -m "bench or bench_slow" -s

Skips cleanly when asyncpg is missing or the DSN is unreachable. Each tier
runs in a throwaway schema that is dropped afterwards.
"""

from __future__ import annotations

import asyncio
import contextlib
import functools
import json
import math
import os
import subprocess
import time
import uuid
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, List, Tuple

import pytest

try:
    import asyncpg
except ImportError:  # pragma: no cover - optional dependency
    asyncpg = None  # type: ignore[assignment]

import jvspatial
from jvspatial.core import context as context_module
from jvspatial.core.annotations import compound_index
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.core.entities import Edge, Node
from jvspatial.core.utils import generate_id
from jvspatial.db import create_database
from jvspatial.observability import db_op_counter

_DSN = os.getenv(
    "JVSPATIAL_POSTGRES_TEST_DSN",
    "postgresql://jvspatial:jvspatial@localhost:5432/jvspatial",
)
_RESULTS_PATH = os.getenv("JVSPATIAL_BENCH_RESULTS")

pytestmark = [pytest.mark.bench]

# Latency samples per measured operation.
_WRITE_ITERATIONS = 50
_CONCURRENT_CONNECTS = 32
_SEED_CHUNK = 25_000


class BenchHub(Node):
    """Hub (and sink) node — the high fan-out endpoint."""

    label: str = ""
    counter: int = 0


class BenchLeaf(Node):
    """Leaf node hanging off the hub."""

    idx: int = 0
    title: str = ""


class BenchContains(Edge):
    """Typed containment edge (hub -> leaf, leaf -> sink)."""


@compound_index([("group_id", 1), ("created_at", -1)], name="bench_group_recent")
class BenchEntry(Node):
    """Record-style node for the typed-find gate (sorted, limited per group)."""

    group_id: str = ""
    created_at: str = ""


# ---- helpers ----------------------------------------------------------------


def _pct(samples: List[float], p: float) -> float:
    ordered = sorted(samples)
    k = max(0, math.ceil(p / 100.0 * len(ordered)) - 1)
    return ordered[k]


def _summary(samples_ms: List[float]) -> Dict[str, float]:
    return {
        "p50_ms": round(_pct(samples_ms, 50), 3),
        "p95_ms": round(_pct(samples_ms, 95), 3),
        "max_ms": round(max(samples_ms), 3),
        "n": len(samples_ms),
    }


async def _timed(fn: Callable[[], Awaitable[Any]]) -> Tuple[float, int, Any]:
    """Run ``fn`` once; return (elapsed_ms, db round trips, result)."""
    token = db_op_counter.set(0)
    try:
        t0 = time.perf_counter()
        result = await fn()
        elapsed = (time.perf_counter() - t0) * 1000.0
        return elapsed, db_op_counter.get(), result
    finally:
        db_op_counter.reset(token)


async def _dsn_reachable() -> bool:
    if asyncpg is None:
        return False
    try:
        conn = await asyncio.wait_for(asyncpg.connect(dsn=_DSN), timeout=2.0)
    except Exception:
        return False
    await conn.close()
    return True


def _git_sha() -> str:
    try:
        return (
            subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL
            )
            .decode()
            .strip()
        )
    except Exception:
        return "unknown"


@contextlib.asynccontextmanager
async def _bench_graph() -> AsyncIterator[Tuple[GraphContext, Any, str]]:
    """Yield ``(context, observable_db, schema)`` on a fresh schema."""
    schema = f"bench_hub_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(dsn=_DSN)
    await admin.execute(f"CREATE SCHEMA {schema}")
    db = create_database(
        "postgres",
        dsn=_DSN,
        schema_name=schema,
        # Warm pool: open every connection up front so samples (and the
        # 32-way burst) measure queries, not connection establishment.
        min_size=_CONCURRENT_CONNECTS + 8,
        max_size=_CONCURRENT_CONNECTS + 8,
        observe=True,
        slow_query_ms=1e9,
    )
    ctx = GraphContext(database=db)
    set_default_context(ctx)
    # ``ensure_indexes`` memoises per collection:entity in a module global;
    # every tier runs on a fresh schema, so the memo must not leak across.
    context_module._ensured_indexes.clear()
    try:
        for cls in (Node, Edge, BenchHub, BenchLeaf, BenchContains):
            await ctx.ensure_indexes(cls)
        yield ctx, db, schema
    finally:
        set_default_context(None)
        context_module._ensured_indexes.clear()
        with contextlib.suppress(Exception):
            await db.close()  # type: ignore[attr-defined]
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


def _persists_edge_ids(ctx: GraphContext) -> bool:
    probe = getattr(ctx, "persists_edge_ids", None)
    return bool(probe()) if callable(probe) else True


async def _seed(ctx: GraphContext, db: Any, degree: int, spare: int) -> Dict[str, Any]:
    """Seed hub -> ``degree`` leaves and ``degree`` leaves -> sink via COPY.

    Also seeds ``spare`` unconnected leaves for the write measurements.
    Records mirror the persisted format of the active adjacency mode:
    with persisted edge ids the hub row carries ``degree`` ids in ``edges``.
    """
    persist = _persists_edge_ids(ctx)
    hub_id = generate_id("n", "BenchHub")
    sink_id = generate_id("n", "BenchHub")
    leaf_ids = [generate_id("n", "BenchLeaf") for _ in range(degree)]
    spare_ids = [generate_id("n", "BenchLeaf") for _ in range(spare)]
    out_eids = [generate_id("e", "BenchContains") for _ in range(degree)]
    in_eids = [generate_id("e", "BenchContains") for _ in range(degree)]

    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for i, (lid, oe, ie) in enumerate(zip(leaf_ids, out_eids, in_eids)):
        rec: Dict[str, Any] = {
            "id": lid,
            "entity": "BenchLeaf",
            "context": {"idx": i, "title": f"leaf {i}"},
        }
        if persist:
            rec["edges"] = [oe, ie]
        nodes.append(rec)
        edges.append(
            {
                "id": oe,
                "entity": "BenchContains",
                "context": {},
                "source": hub_id,
                "target": lid,
                "bidirectional": False,
            }
        )
        edges.append(
            {
                "id": ie,
                "entity": "BenchContains",
                "context": {},
                "source": lid,
                "target": sink_id,
                "bidirectional": False,
            }
        )
    for j, sid in enumerate(spare_ids):
        rec = {
            "id": sid,
            "entity": "BenchLeaf",
            "context": {"idx": degree + j, "title": f"spare {j}"},
        }
        if persist:
            rec["edges"] = []
        nodes.append(rec)
    for hid, label, eids in ((hub_id, "hub", out_eids), (sink_id, "sink", in_eids)):
        rec = {
            "id": hid,
            "entity": "BenchHub",
            "context": {"label": label, "counter": 0},
        }
        if persist:
            rec["edges"] = list(eids)
        nodes.append(rec)

    for coll, recs in (("node", nodes), ("edge", edges)):
        for off in range(0, len(recs), _SEED_CHUNK):
            result = await db.bulk_save_detailed(coll, recs[off : off + _SEED_CHUNK])
            assert result.all_saved, f"seed {coll} lost rows: {result.failed_ids[:5]}"

    return {
        "hub_id": hub_id,
        "sink_id": sink_id,
        "spare_ids": spare_ids,
        "persist": persist,
    }


async def _sizes(admin: Any, schema: str, hub_id: str) -> Dict[str, int]:
    row = await admin.fetchrow(
        f"SELECT pg_column_size(data) AS hub_bytes FROM {schema}.node WHERE id = $1",
        hub_id,
    )
    rel = await admin.fetchrow(
        f"""
        SELECT pg_relation_size('{schema}.node_data_gin') AS node_gin_bytes,
               pg_total_relation_size('{schema}.node') AS node_total_bytes,
               pg_total_relation_size('{schema}.edge') AS edge_total_bytes
        """
    )
    return {
        "hub_row_bytes": int(row["hub_bytes"]),
        "node_gin_bytes": int(rel["node_gin_bytes"]),
        "node_total_bytes": int(rel["node_total_bytes"]),
        "edge_total_bytes": int(rel["edge_total_bytes"]),
    }


# ---- the benchmark ----------------------------------------------------------


@pytest.mark.parametrize(
    "degree",
    [
        pytest.param(1_000, id="1k"),
        pytest.param(10_000, id="10k"),
        pytest.param(100_000, id="100k", marks=pytest.mark.bench_slow),
    ],
)
async def test_hub_node_scale(degree: int, request: pytest.FixtureRequest) -> None:
    markexpr = request.config.getoption("markexpr") or ""
    if degree >= 100_000 and "bench_slow" not in markexpr:
        pytest.skip("100k tier is opt-in: -m 'bench or bench_slow'")
    if not await _dsn_reachable():
        pytest.skip(f"Postgres unreachable at {_DSN}; set JVSPATIAL_POSTGRES_TEST_DSN")

    read_iters = 20 if degree < 100_000 else 5
    spare = _WRITE_ITERATIONS + _CONCURRENT_CONNECTS
    results: Dict[str, Any] = {}

    async with _bench_graph() as (ctx, db, schema):
        admin = await asyncpg.connect(dsn=_DSN)
        try:
            t0 = time.perf_counter()
            seeded = await _seed(ctx, db, degree, spare)
            seed_s = time.perf_counter() - t0
            await admin.execute(f"ANALYZE {schema}.node")
            await admin.execute(f"ANALYZE {schema}.edge")
            results["sizes_after_seed"] = await _sizes(admin, schema, seeded["hub_id"])

            # -- hub hydration (the persisted edge list rides along) --
            samples: List[float] = []
            for _ in range(read_iters):
                await ctx.clear_cache()
                ms, _, hub = await _timed(lambda: ctx.get(BenchHub, seeded["hub_id"]))
                samples.append(ms)
            results["hub_get"] = _summary(samples)
            assert hub is not None
            sink = await ctx.get(BenchHub, seeded["sink_id"])
            assert sink is not None

            # -- neighbour reads --
            read_cases: Dict[str, Tuple[Callable[[], Awaitable[Any]], int]] = {
                "nodes_list_out_limit20": (
                    lambda: hub.nodes(
                        edge=[BenchContains], node=["BenchLeaf"], limit=20
                    ),
                    20,
                ),
                "nodes_class_out_limit20": (
                    lambda: hub.nodes(edge=BenchContains, limit=20),
                    20,
                ),
                "nodes_list_in_limit20": (
                    lambda: sink.nodes(
                        edge=[BenchContains],
                        node=["BenchLeaf"],
                        direction="in",
                        limit=20,
                    ),
                    20,
                ),
                "nodes_list_in_unlimited": (
                    lambda: sink.nodes(
                        edge=[BenchContains], node=["BenchLeaf"], direction="in"
                    ),
                    degree,
                ),
                "count_via_len_nodes": (
                    lambda: hub.nodes(edge=[BenchContains]),
                    degree,
                ),
            }
            if hasattr(hub, "count_nodes"):  # 0.0.18+: the replacement for len()
                read_cases["count_nodes"] = (
                    lambda: hub.count_nodes(edge=[BenchContains]),
                    degree,
                )
            for name, (fn, expected) in read_cases.items():
                samples = []
                trips = 0
                for _ in range(read_iters):
                    await ctx.clear_cache()
                    ms, trips, out = await _timed(fn)
                    samples.append(ms)
                    got = out if isinstance(out, int) else len(out)
                    assert got == expected, f"{name}: {got} != {expected}"
                results[name] = {**_summary(samples), "round_trips": trips}

            # -- save() after a scalar change --
            samples = []
            for i in range(_WRITE_ITERATIONS):
                hub.counter = i + 1

                async def _save() -> Any:
                    return await hub.save()

                ms, _, _ = await _timed(_save)
                samples.append(ms)
            results["hub_save"] = _summary(samples)

            # -- sequential connect() of fresh leaves --
            spare_ids = seeded["spare_ids"]
            seq_leaves = [
                await ctx.get(BenchLeaf, sid) for sid in spare_ids[:_WRITE_ITERATIONS]
            ]
            samples = []
            trips = 0
            for leaf in seq_leaves:
                ms, trips, _ = await _timed(
                    functools.partial(hub.connect, leaf, edge=BenchContains)
                )
                samples.append(ms)
            results["hub_connect"] = {**_summary(samples), "round_trips": trips}

            # -- 32-way concurrent connect() to the same hub --
            conc_leaves = [
                await ctx.get(BenchLeaf, sid) for sid in spare_ids[_WRITE_ITERATIONS:]
            ]

            async def _one(leaf: BenchLeaf) -> float:
                t = time.perf_counter()
                await hub.connect(leaf, edge=BenchContains)
                return (time.perf_counter() - t) * 1000.0

            # asyncpg closes connections idle > 300 s, which the long 100k
            # read phase exceeds; re-open them so the burst measures locking,
            # not reconnects.
            await asyncio.gather(
                *(db.get("node", seeded["hub_id"]) for _ in range(len(conc_leaves)))
            )
            t0 = time.perf_counter()
            per_call = await asyncio.gather(*(_one(leaf) for leaf in conc_leaves))
            wall_ms = (time.perf_counter() - t0) * 1000.0
            results["concurrent_connect_32"] = {
                "wall_ms": round(wall_ms, 3),
                "max_call_ms": round(max(per_call), 3),
                "p50_call_ms": round(_pct(list(per_call), 50), 3),
            }

            final_degree = await db.count("edge", {"source": seeded["hub_id"]})
            assert final_degree == degree + spare
            results["sizes_after_writes"] = await _sizes(
                admin, schema, seeded["hub_id"]
            )

            pg_version = await admin.fetchval("SHOW server_version")
        finally:
            await admin.close()

    record = {
        "degree": degree,
        "jvspatial": jvspatial.__version__,
        "git_sha": _git_sha(),
        "edge_ids_mode": "persist" if seeded["persist"] else "derive",
        "postgres": pg_version,
        "seed_seconds": round(seed_s, 2),
        "read_iterations": read_iters,
        **results,
    }
    print(f"\n[hub-bench] degree={degree}\n" + json.dumps(record, indent=2))
    if _RESULTS_PATH:
        with open(_RESULTS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")


@pytest.mark.bench_slow
async def test_typed_find_is_index_bound(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sorted, limited typed ``find`` on a shared ``node`` table of N rows.

    ``N`` defaults to 1M (``JVSPATIAL_BENCH_TYPED_ROWS``) spread over ten
    entities; ``BenchEntry`` holds a tenth, 1000 groups of ~100 rows each.
    Measures ``find({"entity": "BenchEntry", "context.group_id": t},
    sort=created_at desc, limit=20)`` with the whole-document GIN off and
    records whether the plan walks an index without a Sort node.
    """
    if "bench_slow" not in (request.config.getoption("markexpr") or ""):
        pytest.skip("typed-find gate is opt-in: -m 'bench or bench_slow'")
    if not await _dsn_reachable():
        pytest.skip(f"Postgres unreachable at {_DSN}; set JVSPATIAL_POSTGRES_TEST_DSN")
    monkeypatch.setenv("JVSPATIAL_PG_GIN_INDEX", "off")
    rows = int(os.getenv("JVSPATIAL_BENCH_TYPED_ROWS", "1000000"))
    entities = ["BenchEntry"] + [f"BenchOther{i}" for i in range(9)]

    async with _bench_graph() as (ctx, db, schema):
        admin = await asyncpg.connect(dsn=_DSN)
        try:
            await ctx.ensure_indexes(BenchEntry)
            # Seed through the adapter itself: before 0.0.18 the observable
            # wrapper degraded bulk_save_detailed to per-record saves.
            seed_db = getattr(db, "inner", db)
            t0 = time.perf_counter()
            batch: List[Dict[str, Any]] = []
            for i in range(rows):
                entity = entities[i % len(entities)]
                batch.append(
                    {
                        "id": generate_id("n", entity),
                        "entity": entity,
                        "context": {
                            "group_id": f"t{(i // len(entities)) % 1000}",
                            "created_at": f"2026-09-{i:08d}",
                        },
                    }
                )
                if len(batch) == _SEED_CHUNK:
                    await seed_db.bulk_save_detailed("node", batch)
                    batch = []
            if batch:
                await seed_db.bulk_save_detailed("node", batch)
            seed_s = time.perf_counter() - t0
            await admin.execute(f"ANALYZE {schema}.node")

            per_group = min(20, rows // len(entities) // 1000)
            samples: List[float] = []
            for k in range(50):
                query = {
                    "entity": "BenchEntry",
                    "context.group_id": f"t{(k * 37) % 1000}",
                }
                ms, _, out = await _timed(
                    functools.partial(
                        db.find,
                        "node",
                        query,
                        sort=[("context.created_at", -1)],
                        limit=20,
                    )
                )
                samples.append(ms)
                assert len(out) == per_group

            from jvspatial.db._postgres_translate import translate_query, translate_sort

            where, params = translate_query(
                {"entity": "BenchEntry", "context.group_id": "t7"}
            )
            order = translate_sort([("context.created_at", -1)])
            raw = await admin.fetchval(
                f"EXPLAIN (FORMAT JSON) SELECT data FROM {schema}.node "
                f"WHERE {where} ORDER BY {order} LIMIT 20",
                *params,
            )
            plan = json.loads(raw) if isinstance(raw, str) else raw

            def _walk(node: Dict[str, Any]) -> List[Dict[str, Any]]:
                return [node] + [n for c in node.get("Plans", []) for n in _walk(c)]

            steps = _walk(plan[0]["Plan"])
            index_names = sorted({s["Index Name"] for s in steps if "Index Name" in s})
            has_sort = any(s["Node Type"] == "Sort" for s in steps)
            gin = await admin.fetchval(
                "SELECT count(*) FROM pg_indexes WHERE schemaname = $1 "
                "AND indexname = 'node_data_gin'",
                schema,
            )
        finally:
            await admin.close()

    record = {
        "kind": "typed_find",
        "rows": rows,
        "jvspatial": jvspatial.__version__,
        "git_sha": _git_sha(),
        "seed_seconds": round(seed_s, 2),
        "node_data_gin": bool(gin),
        "typed_find_sorted_limit20": _summary(samples),
        "plan_indexes": index_names,
        "plan_sorts": has_sort,
    }
    print("\n[typed-find]\n" + json.dumps(record, indent=2))
    if _RESULTS_PATH:
        with open(_RESULTS_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
