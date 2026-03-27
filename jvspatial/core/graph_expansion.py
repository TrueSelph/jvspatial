"""Bounded graph expansion for progressive visualization (no full-graph scan)."""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set

from jvspatial.core.graph_payload import (
    DetailLevel,
    edge_record_to_payload,
    entity_type_from_node_id,
    merge_unique_edges,
    merge_unique_nodes,
    node_record_to_payload,
    truncate_entity_label,
)

if TYPE_CHECKING:
    from jvspatial.core.context import GraphContext


def _coerce_edge_id_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value]
    return []


def _edge_matches_direction(
    edge_doc: Dict[str, Any], node_id: str, direction: str
) -> bool:
    src = edge_doc.get("source")
    tgt = edge_doc.get("target")
    if node_id not in (src, tgt):
        return False
    if bool(edge_doc.get("bidirectional", True)):
        return True
    d = (direction or "both").lower()
    if d in ("", "both", "all"):
        return True
    if d == "out":
        return src == node_id
    if d == "in":
        return tgt == node_id
    return True


def _other_endpoint(edge_doc: Dict[str, Any], node_id: str) -> Optional[str]:
    src = edge_doc.get("source")
    tgt = edge_doc.get("target")
    if src == node_id:
        return str(tgt) if tgt else None
    if tgt == node_id:
        return str(src) if src else None
    return None


async def expand_node(
    context: GraphContext,
    node_id: str,
    *,
    direction: str = "both",
    limit: int = 50,
    cursor: int = 0,
    detail_level: DetailLevel = "full",
) -> Dict[str, Any]:
    """Load the center node and a page of incident edges plus neighbor summaries.

    Uses the node's persisted ``edges`` list and batch ``get`` calls — O(limit),
    not O(|E|).

    Args:
        context: Active graph context
        node_id: Node to expand around
        direction: ``both`` (default), ``out``, or ``in`` (for non-bidirectional edges)
        limit: Max edges in this page (capped at 500)
        cursor: Offset into the sorted edge-id list
        detail_level: ``summary`` (no context) or ``full`` (trimmed context on all nodes/edges)

    Returns:
        Dict with ``center_id``, ``nodes``, ``edges``, ``pagination``
    """
    limit = max(0, min(int(limit), 500))
    cursor = max(0, int(cursor))
    db = context.database
    center_raw = await db.get("node", node_id)
    if not center_raw:
        return {
            "center_id": node_id,
            "nodes": [],
            "edges": [],
            "pagination": {
                "cursor": cursor,
                "next_cursor": None,
                "has_more": False,
                "total_edge_count": 0,
                "returned_edges": 0,
            },
            "found": False,
        }

    all_edge_ids = sorted(_coerce_edge_id_list(center_raw.get("edges")))
    total = len(all_edge_ids)
    page_ids = all_edge_ids[cursor : cursor + limit]

    edge_docs: List[Dict[str, Any]] = []
    for eid in page_ids:
        doc = await db.get("edge", eid)
        if doc and _edge_matches_direction(doc, node_id, direction):
            edge_docs.append(doc)

    neighbor_ids: List[str] = []
    for doc in edge_docs:
        other = _other_endpoint(doc, node_id)
        if other and other != node_id:
            neighbor_ids.append(other)

    neighbor_ids_unique = sorted(set(neighbor_ids))
    neighbor_records: Dict[str, Dict[str, Any]] = {}
    for nid in neighbor_ids_unique:
        nraw = await db.get("node", nid)
        if nraw:
            neighbor_records[nid] = nraw

    nodes_out: List[Dict[str, Any]] = [
        node_record_to_payload(
            center_raw,
            detail_level=detail_level,
            degree=total,
        )
    ]
    for nid in neighbor_ids_unique:
        if nid in neighbor_records:
            nedges = neighbor_records[nid].get("edges") or []
            deg = len(nedges) if isinstance(nedges, list) else 0
            nodes_out.append(
                node_record_to_payload(
                    neighbor_records[nid],
                    detail_level=detail_level,
                    degree=deg,
                )
            )
        else:
            ent = entity_type_from_node_id(nid)
            miss_payload: Dict[str, Any] = {
                "id": nid,
                "entity": ent,
                "degree": 0,
                "label": truncate_entity_label(ent),
                "missing": True,
            }
            if detail_level == "full":
                miss_payload["context"] = {}
            nodes_out.append(miss_payload)

    edges_out = [
        edge_record_to_payload(
            doc,
            detail_level=detail_level,
            expand_center_id=node_id,
        )
        for doc in edge_docs
    ]
    next_cursor = cursor + len(page_ids) if cursor + len(page_ids) < total else None
    has_more = next_cursor is not None

    return {
        "center_id": node_id,
        "nodes": merge_unique_nodes(nodes_out),
        "edges": merge_unique_edges(edges_out),
        "pagination": {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "has_more": has_more,
            "total_edge_count": total,
            "returned_edges": len(edges_out),
        },
        "found": True,
    }


async def subgraph_bfs(
    context: GraphContext,
    root_id: str,
    *,
    max_depth: int = 2,
    max_nodes: int = 100,
    max_edges_per_node: int = 200,
    detail_level: DetailLevel = "full",
) -> Dict[str, Any]:
    """Breadth-first load of a bounded subgraph from ``root_id``.

    Stops when ``max_depth`` or ``max_nodes`` would be exceeded. Each node
    follows at most ``max_edges_per_node`` incident edges (sorted by edge id).

    Args:
        context: Active graph context
        root_id: BFS root (e.g. ``n.Root.root``)
        max_depth: Number of hops from root (root is depth 0)
        max_nodes: Maximum distinct nodes in the result
        max_edges_per_node: Cap on edges followed per node when expanding
        detail_level: ``summary`` or ``full``

    Returns:
        Dict with ``root_id``, ``nodes``, ``edges``, ``meta``
    """
    max_depth = max(0, min(int(max_depth), 50))
    max_nodes = max(1, min(int(max_nodes), 10_000))
    max_edges_per_node = max(1, min(int(max_edges_per_node), 2000))

    db = context.database
    seen: Set[str] = set()
    edges_by_id: Dict[str, Dict[str, Any]] = {}
    nodes_by_id: Dict[str, Dict[str, Any]] = {}
    truncated = False

    q: deque[tuple[str, int]] = deque([(root_id, 0)])

    while q:
        if len(seen) >= max_nodes:
            truncated = True
            break
        vid, d = q.popleft()
        if vid in seen:
            continue
        seen.add(vid)

        raw = await db.get("node", vid)
        if raw:
            nodes_by_id[vid] = raw

        if d >= max_depth:
            continue

        all_eids = _coerce_edge_id_list((raw or {}).get("edges"))
        eids = sorted(all_eids)[:max_edges_per_node]
        if len(all_eids) > len(eids):
            truncated = True

        for eid in eids:
            edoc = await db.get("edge", eid)
            if not edoc:
                continue
            edges_by_id[eid] = edoc
            other = _other_endpoint(edoc, vid)
            if not other:
                continue
            if other not in seen:
                q.append((other, d + 1))

    node_payloads: List[Dict[str, Any]] = []
    for nid in sorted(seen):
        rec = nodes_by_id.get(nid)
        if rec:
            ecount = len(_coerce_edge_id_list(rec.get("edges")))
            node_payloads.append(
                node_record_to_payload(rec, detail_level=detail_level, degree=ecount)
            )
        else:
            ent = entity_type_from_node_id(nid)
            miss: Dict[str, Any] = {
                "id": nid,
                "entity": ent,
                "degree": 0,
                "label": truncate_entity_label(ent),
                "missing": True,
            }
            if detail_level == "full":
                miss["context"] = {}
            node_payloads.append(miss)

    edge_payloads = [
        edge_record_to_payload(doc, detail_level=detail_level)
        for doc in edges_by_id.values()
    ]

    return {
        "root_id": root_id,
        "nodes": merge_unique_nodes(node_payloads),
        "edges": merge_unique_edges(edge_payloads),
        "meta": {
            "max_depth": max_depth,
            "max_nodes": max_nodes,
            "max_edges_per_node": max_edges_per_node,
            "truncated": truncated,
            "node_count": len(seen),
            "edge_count": len(edges_by_id),
        },
    }
