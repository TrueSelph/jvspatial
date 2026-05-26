"""Graph-structure validators.

CLAUDE.md spells out the modeling convention every jvspatial application
should follow:

1. Every ``Node`` is reachable from ``Root``.
2. Apps declare an app-root node and connect it (and only it) to ``Root``.
3. All app nodes hang off the app-root.
4. ``Object`` (not ``Node``) is the right base for record-style data
   that never participates in graph traversal.

The library doesn't enforce these at write-time (that would force
applications to over-fit). But it's useful to have an explicit checker
that audit / startup hooks can run.

:func:`validate_graph` walks every node and edge in the prime database
(or a caller-supplied :class:`GraphContext`) and reports violations:

* Orphans: nodes with no path to ``Root`` via outbound or bidirectional
  edges.
* Root cycles: any non-Root node with a path back to itself that
  passes through ``Root``.
* Dangling edges: edges whose ``source`` or ``target`` references a
  node id that doesn't exist.

The validator is read-only and emits a :class:`ValidationReport` —
callers decide whether to log, fail startup, or open a triage ticket.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ValidationReport:
    """Result of :func:`validate_graph`. Immutable."""

    orphan_node_ids: List[str] = field(default_factory=list)
    root_cycle_node_ids: List[str] = field(default_factory=list)
    dangling_edge_ids: List[str] = field(default_factory=list)
    nodes_visited: int = 0
    edges_visited: int = 0

    @property
    def ok(self) -> bool:
        """``True`` iff no violations were detected."""
        return not (
            self.orphan_node_ids or self.root_cycle_node_ids or self.dangling_edge_ids
        )

    def summary(self) -> str:
        """Render a human-readable one-line summary."""
        if self.ok:
            return (
                f"graph OK ({self.nodes_visited} nodes / "
                f"{self.edges_visited} edges)"
            )
        return (
            f"graph violations: {len(self.orphan_node_ids)} orphan(s), "
            f"{len(self.root_cycle_node_ids)} root-cycle node(s), "
            f"{len(self.dangling_edge_ids)} dangling edge(s) "
            f"(scanned {self.nodes_visited} nodes / "
            f"{self.edges_visited} edges)"
        )


async def validate_graph(
    *,
    context: Optional[Any] = None,
    check_orphans: bool = True,
    check_root_cycles: bool = True,
    check_dangling_edges: bool = True,
    node_collection: str = "node",
    edge_collection: str = "edge",
) -> ValidationReport:
    """Audit the graph against the modeling convention.

    Reads every node + edge from the supplied (or default) context and
    builds the adjacency map in memory. For large graphs this is O(N+E)
    on memory; consider running it as a scheduled job rather than on
    every request.

    Args:
        context: :class:`GraphContext` to read from. Defaults to the
            current default context.
        check_orphans: Detect nodes with no path to Root. Default True.
        check_root_cycles: Detect non-Root nodes that participate in a
            cycle containing Root. Default True.
        check_dangling_edges: Detect edges whose source or target
            references a missing node. Default True.
        node_collection: Collection name holding node records. Default
            ``"node"``.
        edge_collection: Collection name holding edge records. Default
            ``"edge"``.

    Returns:
        :class:`ValidationReport` describing what was found.
    """
    if context is None:
        from .context import get_default_context

        context = get_default_context()

    db = context.database
    node_rows: List[Dict[str, Any]] = await db.find(node_collection, {})
    edge_rows: List[Dict[str, Any]] = await db.find(edge_collection, {})

    node_ids: Set[str] = {
        str(n.get("id")) for n in node_rows if n.get("id") is not None
    }

    # Detect Root by entity discriminator. Root is the singleton
    # library-owned node — by convention exactly one exists. Multiple
    # Roots are themselves a violation but out of scope here; we just
    # treat any node with entity == "Root" as a valid origin.
    root_ids: Set[str] = {
        str(n["id"]) for n in node_rows if str(n.get("entity", "")).lower() == "root"
    }

    # Build two adjacencies:
    #
    # - ``reach_out`` / ``reach_in`` include bidirectional edges in both
    #   directions; used for orphan detection (convention allows
    #   bidirectional edges, so "reachable via either endpoint" is fine).
    # - ``directed_out`` / ``directed_in`` only count strictly-directed
    #   edges; used for cycle detection so a single bidirectional edge
    #   isn't a false positive.
    reach_out: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    reach_in: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    directed_out: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    directed_in: Dict[str, List[str]] = {nid: [] for nid in node_ids}
    dangling: List[str] = []

    def _payload(row: Dict[str, Any]) -> Dict[str, Any]:
        # Edges may store source/target either at the top level
        # (modern) or under ``context`` (older records). Honor both.
        if "source" in row or "target" in row:
            return row
        return row.get("context") or {}

    for edge in edge_rows:
        eid = str(edge.get("id", ""))
        payload = _payload(edge)
        src = payload.get("source")
        tgt = payload.get("target")
        bidirectional = payload.get("bidirectional", False)
        if src is None or tgt is None:
            dangling.append(eid)
            continue
        if check_dangling_edges and (
            str(src) not in node_ids or str(tgt) not in node_ids
        ):
            dangling.append(eid)
            continue
        src_s, tgt_s = str(src), str(tgt)
        reach_out.setdefault(src_s, []).append(tgt_s)
        reach_in.setdefault(tgt_s, []).append(src_s)
        if bidirectional:
            # Reachability traverses bidirectional edges in both
            # directions; cycle detection ignores them entirely.
            reach_out.setdefault(tgt_s, []).append(src_s)
            reach_in.setdefault(src_s, []).append(tgt_s)
        else:
            directed_out.setdefault(src_s, []).append(tgt_s)
            directed_in.setdefault(tgt_s, []).append(src_s)

    orphans: List[str] = []
    if check_orphans and root_ids:
        # BFS from any Root, following edges in either direction —
        # convention permits parent → child OR child → parent edges
        # as long as the node is connected.
        reachable: Set[str] = set()
        queue: deque[str] = deque(root_ids)
        while queue:
            current = queue.popleft()
            if current in reachable:
                continue
            reachable.add(current)
            for nxt in reach_out.get(current, ()):
                if nxt not in reachable:
                    queue.append(nxt)
            for prev in reach_in.get(current, ()):
                if prev not in reachable:
                    queue.append(prev)
        orphans = sorted(node_ids - reachable - root_ids)

    cycle_nodes: List[str] = []
    if check_root_cycles and root_ids:
        # A "root cycle" violation = a non-Root node that has a
        # strictly-directed cycle passing through Root. We walk only
        # the directed adjacency so a single bidirectional edge between
        # a node and Root isn't flagged.
        for root in root_ids:
            for child in directed_out.get(root, ()):
                if _path_exists(directed_out, child, root):
                    cycle_nodes.append(child)
            for parent in directed_in.get(root, ()):
                if _path_exists(directed_in, parent, root):
                    cycle_nodes.append(parent)
        cycle_nodes = sorted(set(cycle_nodes))

    return ValidationReport(
        orphan_node_ids=orphans,
        root_cycle_node_ids=cycle_nodes,
        dangling_edge_ids=sorted(set(dangling)),
        nodes_visited=len(node_ids),
        edges_visited=len(edge_rows),
    )


def _path_exists(
    adj: Dict[str, List[str]], start: str, target: str, *, max_steps: int = 10000
) -> bool:
    """Return True iff ``adj`` has a path from ``start`` to ``target``."""
    if start == target:
        return True
    seen: Set[str] = set()
    queue: deque[str] = deque([start])
    steps = 0
    while queue:
        steps += 1
        if steps > max_steps:
            # Defensive bound — refuses to loop forever on pathological
            # graphs. Real walks should never hit this.
            logger.warning(
                "validate_graph: path search aborted after %d steps", max_steps
            )
            return False
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        for nxt in adj.get(current, ()):
            if nxt == target:
                return True
            if nxt not in seen:
                queue.append(nxt)
    return False


__all__ = ["ValidationReport", "validate_graph"]
