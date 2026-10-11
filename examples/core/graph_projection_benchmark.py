"""Record local projection scaling without asserting machine-specific latency.

Example: python -m examples.core.graph_projection_benchmark --output result.json
The fixtures connect every synthetic node through an application root. JSON
physical file reads are measured; SQL physical scan work remains unknown.
"""

import argparse
import asyncio
import json
import math
import os
import platform
import statistics
import tempfile
import time
import uuid
from pathlib import Path

from jvspatial import Edge, GraphContext, ProjectionRequest, ProjectionScope
from jvspatial.core.utils import generate_id
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.sqlite import SQLiteDB


class MeasuredJsonDB(JsonDB):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.file_reads = 0

    async def _async_load_record(self, path):
        self.file_reads += 1
        return await super()._async_load_record(path)


def summary(samples):
    values = sorted(samples)
    return {
        "samples": len(values),
        "p50_ms": round(statistics.median(values), 3),
        "p95_ms": round(values[max(0, math.ceil(0.95 * len(values)) - 1)], 3),
    }


async def measure(backend, directory, degree, unrelated, samples):
    admin = None
    schema = "projection_bench_" + uuid.uuid4().hex[:12]
    if backend == "json":
        db = MeasuredJsonDB(base_path=directory)
    elif backend == "sqlite":
        db = SQLiteDB(db_path=str(Path(directory) / "benchmark.db"))
    else:
        import asyncpg

        from jvspatial.db.postgres import PostgresDB

        dsn = os.environ["JVSPATIAL_PROJECTION_TEST_DSN"]
        admin = await asyncpg.connect(dsn)
        await admin.execute(f'CREATE SCHEMA "{schema}"')
        db = PostgresDB(dsn=dsn, schema_name=schema)
    ctx = GraphContext(db)
    try:
        root = "n.Root.root"
        app, standpoint, other = [generate_id("n", "Node") for _ in range(3)]
        nodes = [
            {"id": nid, "entity": "Node", "context": {}}
            for nid in (root, app, standpoint, other)
        ]
        edges = []

        def link(source, target, entity):
            return {
                "id": generate_id("e", entity),
                "entity": entity,
                "source": source,
                "target": target,
                "bidirectional": False,
                "context": {},
            }

        edges.extend(
            [
                link(root, app, "Contains"),
                link(app, standpoint, "Contains"),
                link(app, other, "Contains"),
            ]
        )
        for source, count in [(standpoint, degree), (other, unrelated)]:
            for _ in range(count):
                nid = generate_id("n", "Node")
                nodes.append({"id": nid, "entity": "Node", "context": {}})
                edges.append(link(source, nid, "Link"))
        await db.bulk_save("node", nodes)
        await db.bulk_save("edge", edges)
        await ctx.ensure_indexes(Edge)
        request = ProjectionRequest(
            root_id=standpoint,
            max_depth=1,
            edge_types=("Link",),
            max_nodes=degree + 1,
            max_edges=degree,
            max_candidates=degree * 3 + 10,
            max_edges_per_node=degree + 2,
            max_bytes=4000000,
            max_frontier=degree + 1,
            execution_mode="compatibility" if backend == "json" else "native",
        )
        # Warm initialization and query paths outside measured samples.
        await ctx.project_graph(request, scope=ProjectionScope.all())
        timings, reads = [], []
        result = None
        for _ in range(samples):
            if backend == "json":
                db.file_reads = 0
            start = time.perf_counter()
            result = await ctx.project_graph(request, scope=ProjectionScope.all())
            timings.append((time.perf_counter() - start) * 1000)
            if backend == "json":
                reads.append(db.file_reads)
        data = result.to_dict()
        assert len(data["nodes"]) == degree + 1
        assert len(data["edges"]) == degree
        assert data["meta"]["complete"]
        renderings = {}
        for name, renderer in [
            ("text", result.render_text),
            ("mermaid", result.render_mermaid),
        ]:
            render_times = []
            for _ in range(samples):
                start = time.perf_counter()
                content = renderer()
                render_times.append((time.perf_counter() - start) * 1000)
            renderings[name] = {**summary(render_times), "bytes": len(content.encode())}
        crud = {}
        for name in ("get", "save"):
            values = []
            for _ in range(samples * 10):
                start = time.perf_counter()
                if name == "get":
                    await db.get("node", standpoint)
                else:
                    await db.save("node", nodes[2])
                values.append((time.perf_counter() - start) * 1000)
            crud[name] = summary(values)
        return {
            "backend": backend,
            "local_degree": degree,
            "unrelated_edges": unrelated,
            "capture": summary(timings),
            "work": result.statistics,
            "json_file_reads_per_capture": reads[0] if reads else None,
            "returned_nodes": len(data["nodes"]),
            "returned_edges": len(data["edges"]),
            "renderers": renderings,
            "ordinary_crud": crud,
        }
    finally:
        if hasattr(db, "close"):
            await db.close()
        if admin:
            await admin.execute(f'DROP SCHEMA "{schema}" CASCADE')
            await admin.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--samples", type=int, default=7)
    args = parser.parse_args()
    if args.samples < 1 or args.samples > 100:
        parser.error("samples must be between 1 and 100")
    rows = []
    backends = ["json", "sqlite"]
    if os.getenv("JVSPATIAL_PROJECTION_TEST_DSN"):
        backends.append("postgres")
    for backend in backends:
        for degree, unrelated in [(20, 0), (20, 1000), (200, 1000)]:
            with tempfile.TemporaryDirectory() as directory:
                rows.append(
                    await measure(backend, directory, degree, unrelated, args.samples)
                )
    report = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "notes": "Warm local measurements; physical SQL scan rows unknown; no model inference performed.",
        "results": rows,
    }
    encoded = json.dumps(report, indent=2)
    if args.output:
        await asyncio.to_thread(Path(args.output).write_text, encoded + "\n")
    print(encoded)


if __name__ == "__main__":
    asyncio.run(main())
