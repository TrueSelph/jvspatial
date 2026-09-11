"""Bounded graph expansion for progressive visualization (no full-graph scan)."""

from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple

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


def _incident_query(node_id: str) -> Dict[str, Any]:
    """Edge-collection query for every edge touching ``node_id``."""
    return {"$or": [{"source": node_id}, {"target": node_id}]}


async def _node_degrees(
    context: GraphContext, records: Dict[str, Dict[str, Any]]
) -> Dict[str, int]:
    """Degree per node record.

    Persist mode reads the stored ``edges`` array; derive mode counts the
    edge collection (the array, if a legacy row still has one, is stale).
    """
    if context.persists_edge_ids():
        return {
            nid: len(_coerce_edge_id_list(rec.get("edges")))
            for nid, rec in records.items()
        }
    ids = list(records)
    db = context.database
    counts = await asyncio.gather(*(db.count("edge", _incident_query(n)) for n in ids))
    return dict(zip(ids, counts))


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


def _bfs_spine_edge_sort_key(
    eid: str, edge_doc: Optional[Dict[str, Any]], current_id: str
) -> tuple:
    """So Root→App→Agents stays in the BFS when ``max_edges_per_node`` caps lists.

    Edge lists are often sorted by id; without this, a hub can exhaust the cap
    before the canonical ``n.App`` / ``n.Agents`` link is seen.
    """
    other = _other_endpoint(edge_doc, current_id) if edge_doc else None
    if not other:
        return (9, eid)
    if other.startswith("n.App."):
        return (0, eid)
    if other.startswith("n.Agents."):
        return (1, eid)
    if other == "n.Root.root" or other.startswith("n.Root."):
        return (2, eid)
    return (3, eid)


async def expand_node(
    context: GraphContext,
    node_id: str,
    *,
    direction: str = "both",
    limit: int = 50,
    cursor: int = 0,
    after: Optional[str] = None,
    detail_level: DetailLevel = "full",
) -> Dict[str, Any]:
    """Load the center node and a page of incident edges plus neighbor summaries.

    Pages come from the edge collection sorted by edge id (index-backed on
    SQL backends), so a page costs O(limit) rows regardless of the node's
    degree when paging by keyset.

    Args:
        context: Active graph context
        node_id: Node to expand around
        direction: ``both`` (default), ``out``, or ``in`` (for non-bidirectional edges)
        limit: Max edges in this page (capped at 500)
        cursor: Offset into the id-sorted incident edges (costs O(cursor + limit))
        after: Keyset cursor — an edge id from a previous page's
            ``pagination.next_after``; takes precedence over ``cursor``
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
                "next_after": None,
                "has_more": False,
                "total_edge_count": 0,
                "returned_edges": 0,
            },
            "found": False,
        }

    incident = _incident_query(node_id)
    total = await db.count("edge", incident)
    page: List[Dict[str, Any]] = []
    if limit:
        if after:
            rows = await db.find(
                "edge",
                {"$and": [incident, {"id": {"$gt": after}}]},
                sort=[("id", 1)],
                limit=limit + 1,
            )
            has_more = len(rows) > limit
            page = rows[:limit]
        else:
            rows = await db.find(
                "edge", incident, sort=[("id", 1)], limit=cursor + limit
            )
            page = rows[cursor:]
            has_more = cursor + len(page) < total
    else:
        has_more = cursor < total

    edge_docs = [d for d in page if _edge_matches_direction(d, node_id, direction)]

    neighbor_ids_unique = sorted(
        {
            other
            for doc in edge_docs
            if (other := _other_endpoint(doc, node_id)) and other != node_id
        }
    )
    neighbor_records = (
        await db.find_many("node", neighbor_ids_unique) if neighbor_ids_unique else {}
    )
    degrees = await _node_degrees(context, neighbor_records)

    nodes_out: List[Dict[str, Any]] = [
        node_record_to_payload(
            center_raw,
            detail_level=detail_level,
            degree=total,
        )
    ]
    for nid in neighbor_ids_unique:
        if nid in neighbor_records:
            nodes_out.append(
                node_record_to_payload(
                    neighbor_records[nid],
                    detail_level=detail_level,
                    degree=degrees.get(nid, 0),
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
    next_cursor = cursor + len(page) if has_more and not after else None
    next_after = str(page[-1].get("id")) if has_more and page else None

    return {
        "center_id": node_id,
        "nodes": merge_unique_nodes(nodes_out),
        "edges": merge_unique_edges(edges_out),
        "pagination": {
            "cursor": cursor,
            "next_cursor": next_cursor,
            "next_after": next_after,
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
    Incident edges come from one edge-collection query per expanded node.

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

        eid_docs: List[Tuple[str, Optional[Dict[str, Any]]]] = [
            (str(doc.get("id")), doc)
            for doc in await db.find("edge", _incident_query(vid))
        ]
        eid_docs.sort(key=lambda t: _bfs_spine_edge_sort_key(t[0], t[1], vid))
        selected = eid_docs[:max_edges_per_node]
        if len(eid_docs) > len(selected):
            truncated = True

        for eid, edoc in selected:
            if not edoc:
                continue
            edges_by_id[eid] = edoc
            other = _other_endpoint(edoc, vid)
            if not other:
                continue
            if other not in seen:
                q.append((other, d + 1))

    degrees = await _node_degrees(context, nodes_by_id)
    node_payloads: List[Dict[str, Any]] = []
    for nid in sorted(seen):
        rec = nodes_by_id.get(nid)
        if rec:
            node_payloads.append(
                node_record_to_payload(
                    rec, detail_level=detail_level, degree=degrees.get(nid, 0)
                )
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
