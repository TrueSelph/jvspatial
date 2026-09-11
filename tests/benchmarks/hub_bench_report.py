"""Render hub-node bench JSONL (``$JVSPATIAL_BENCH_RESULTS``) as markdown tables.

Usage::

    python tests/benchmarks/hub_bench_report.py docs/bench/2026-09-hub-node-phase0.jsonl

Prints one latency table (p50 / p95 ms, round trips) and one size table,
columns ordered by degree. Paste the output into the bench document.
"""

from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

_LATENCY_ROWS = [
    ("hub_get", "`ctx.get(Hub)` (hydrate hub)"),
    ("hub_connect", "`hub.connect(leaf, edge=E)`"),
    ("hub_save", "`hub.save()` after scalar change"),
    ("nodes_list_out_limit20", "`hub.nodes(edge=[E], node=['Leaf'], limit=20)`"),
    ("nodes_class_out_limit20", "`hub.nodes(edge=E, limit=20)`"),
    (
        "nodes_list_in_limit20",
        "`sink.nodes(edge=[E], node=['Leaf'], direction='in', limit=20)`",
    ),
    (
        "nodes_list_in_unlimited",
        "`sink.nodes(edge=[E], node=['Leaf'], direction='in')`",
    ),
    ("count_via_len_nodes", "`len(await hub.nodes(edge=[E]))`"),
    ("count_nodes", "`hub.count_nodes(edge=[E])`"),
]

_SIZE_ROWS = [
    ("hub_row_bytes", "hub row `pg_column_size(data)`"),
    ("node_gin_bytes", "`node_data_gin` size"),
    ("node_total_bytes", "`node` table total"),
    ("edge_total_bytes", "`edge` table total"),
]


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return str(n)


def _label(degree: int) -> str:
    return f"{degree // 1000}k" if degree % 1000 == 0 else str(degree)


def render(records: List[Dict[str, Any]]) -> str:
    records = sorted(records, key=lambda r: r["degree"])
    heads = [_label(r["degree"]) for r in records]
    out: List[str] = []
    meta = records[0]
    out.append(
        f"jvspatial {meta['jvspatial']} @ `{meta['git_sha']}`, "
        f"edge_ids_mode=`{meta['edge_ids_mode']}`, Postgres {meta['postgres']}"
    )
    out.append("")
    out.append(
        "| operation | " + " | ".join(f"{h} p50 / p95 ms (trips)" for h in heads) + " |"
    )
    out.append("|---|" + "---|" * len(heads))
    for key, label in _LATENCY_ROWS:
        if not any(key in r for r in records):
            continue
        cells = []
        for r in records:
            m = r.get(key)
            if not m:
                cells.append("—")
                continue
            trips = f" ({m['round_trips']})" if "round_trips" in m else ""
            cells.append(f"{m['p50_ms']:.1f} / {m['p95_ms']:.1f}{trips}")
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    cells = []
    for r in records:
        c = r["concurrent_connect_32"]
        cells.append(f"{c['wall_ms']:.0f} wall / {c['max_call_ms']:.0f} max")
    out.append("| 32× concurrent `connect()` (ms) | " + " | ".join(cells) + " |")
    out.append("")
    out.append(
        "| size (after seed → after 82 hub writes) | " + " | ".join(heads) + " |"
    )
    out.append("|---|" + "---|" * len(heads))
    for key, label in _SIZE_ROWS:
        cells = [
            f"{_fmt_bytes(r['sizes_after_seed'][key])} → "
            f"{_fmt_bytes(r['sizes_after_writes'][key])}"
            for r in records
        ]
        out.append(f"| {label} | " + " | ".join(cells) + " |")
    return "\n".join(out)


def main(argv: List[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    with open(argv[1], encoding="utf-8") as fh:
        records = [json.loads(line) for line in fh if line.strip()]
    print(render(records))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
