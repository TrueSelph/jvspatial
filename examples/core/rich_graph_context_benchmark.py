"""Reproducible rich-versus-equivalent-field capture measurements, no model calls."""

import asyncio
import json
import statistics
import tempfile
import time
from pathlib import Path

from jvspatial import (
    GraphContext,
    ProjectionContextConfig,
    ProjectionEvidence,
    ProjectionField,
    ProjectionRelation,
    ProjectionRequest,
    ProjectionScope,
    ProjectionSemantics,
)
from jvspatial.db.sqlite import SQLiteDB


async def measure(db, topology, budget, rounds=15):
    """Seed rooted fixtures outside timing; alternate paired warm captures."""
    await db.bulk_save(
        "node",
        [
            {"id": "n.Root.root", "entity": "Root", "context": {}},
            {"id": "n.App.demo", "entity": "App", "context": {}},
            *(
                {
                    "id": f"n.Record.{i:04}",
                    "entity": "Record",
                    "context": {
                        "name": "Recorded item",
                        "state": "unverified",
                        "source": "synthetic-source",
                        "observed": "2026-10-11",
                    },
                }
                for i in range(budget)
            ),
        ],
    )
    await db.bulk_save(
        "edge",
        [
            {
                "id": "e.Link.root",
                "entity": "Link",
                "source": "n.Root.root",
                "target": "n.App.demo",
                "bidirectional": False,
                "context": {},
            },
            {
                "id": "e.Link.app",
                "entity": "Link",
                "source": "n.App.demo",
                "target": "n.Record.0000",
                "bidirectional": False,
                "context": {},
            },
            *(
                {
                    "id": f"e.Relation.{i:04}",
                    "entity": "Relation",
                    "source": (
                        "n.Record.0000"
                        if topology == "hub"
                        else f"n.Record.{(i-1)//3:04}"
                    ),
                    "target": f"n.Record.{i:04}",
                    "bidirectional": False,
                    "context": {"role": "requires", "schema": "example-v1"},
                }
                for i in range(1, budget)
            ),
        ],
    )
    context = GraphContext(db)
    scope = ProjectionScope.all(
        node_fields=("name", "state", "source", "observed"),
        edge_fields=("role", "schema"),
    )
    request = ProjectionRequest(
        root_id="n.Record.0000",
        max_depth=10,
        max_candidates=budget,
        max_nodes=1000,
        max_edges=1000,
        max_frontier=1000,
        max_edges_per_node=1000,
        max_bytes=2000000,
        execution_mode="native",
    )
    profile = ProjectionContextConfig(
        profile_id="recorded-facts",
        revision="1",
        node_fields={
            "Record": (
                ProjectionField(path="name"),
                ProjectionField(
                    path="state",
                    evidence=ProjectionEvidence(
                        source_path="source", observed_at_path="observed"
                    ),
                ),
                ProjectionField(path="source"),
                ProjectionField(path="observed"),
            )
        },
        edge_fields={
            "Relation": (ProjectionField(path="role"), ProjectionField(path="schema"))
        },
    )
    semantics = ProjectionSemantics(
        relation_rules=(
            ProjectionRelation(
                id="prerequisite",
                edge_type="Relation",
                description="A recorded dependency",
                direction="requires",
                inverse="required by",
                edge_filter={
                    "context.role": "requires",
                    "context.schema": "example-v1",
                },
            ),
        )
    )

    async def capture(rich):
        return await context.project_graph(
            request,
            scope=scope,
            context_config=profile if rich else None,
            semantics=semantics if rich else None,
        )

    await capture(False)
    await capture(True)
    timings = {False: [], True: []}
    results = {}
    for round_number in range(rounds):
        for rich in (False, True) if round_number % 2 else (True, False):
            start = time.perf_counter()
            results[rich] = await capture(rich)
            timings[rich].append((time.perf_counter() - start) * 1000)
    rows = {}
    for rich in (False, True):
        result = results[rich]
        render = []
        for _ in range(rounds):
            start = time.perf_counter()
            text = result.render_text()
            render.append((time.perf_counter() - start) * 1000)
        data = result.to_dict()
        rows["rich" if rich else "equivalent_fields"] = {
            "median_ms": statistics.median(timings[rich]),
            "p95_ms": sorted(timings[rich])[int(0.95 * (rounds - 1))],
            "render_median_ms": statistics.median(render),
            "rendered_bytes": len(text.encode()),
            "canonical_bytes": result.statistics["payload_bytes"],
            "database_operations": result.statistics["database_operations"],
            "candidate_records": result.statistics["candidate_records"],
            "nodes": len(data["nodes"]),
            "edges": len(data["edges"]),
            "clipped_fields": sum(
                len(r["truncated_fields"]) for r in data["nodes"] + data["edges"]
            ),
        }
    assert (
        rows["rich"]["database_operations"]
        == rows["equivalent_fields"]["database_operations"]
    )
    for key in ("nodes", "edges", "candidate_records"):
        assert rows["rich"][key] == rows["equivalent_fields"][key]
    assert rows["rich"]["canonical_bytes"] <= request.max_bytes
    rows["median_overhead_pct"] = (
        rows["rich"]["median_ms"] / rows["equivalent_fields"]["median_ms"] - 1
    ) * 100
    return {"topology": topology, "candidate_budget": budget, **rows}


async def main():
    """Emit JSON diagnostics for both candidate budgets and graph shapes."""
    rows = []
    with tempfile.TemporaryDirectory() as directory:
        for topology in ("sparse", "hub"):
            for budget in (100, 1000):
                db = SQLiteDB(str(Path(directory) / f"{topology}-{budget}.db"))
                try:
                    rows.append(await measure(db, topology, budget))
                finally:
                    await db.close()
    print(
        json.dumps(
            {
                "methodology": "paired-warm-capture-v1",
                "backend": "sqlite",
                "rounds": 15,
                "physical_scans": "not_measured",
                "model_tokens": "not_measured",
                "measurements": rows,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
