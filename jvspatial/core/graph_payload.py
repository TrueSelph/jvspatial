"""Compact JSON payloads for progressive graph visualization.

``summary`` omits ``context`` for smaller payloads; ``full`` includes trimmed
``context`` on every node and edge for inspection and custom viewers.

Node and edge ``label`` fields are the entity/class name only (from the stored
``entity`` field, with id-based fallbacks when missing).
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

DetailLevel = Literal["summary", "full"]

_MAX_LABEL = 120
# Raised limits for ``full`` inspection payloads (still bounded for safety).
_MAX_CONTEXT_KEYS = 64
_MAX_CONTEXT_STRING = 2000


def truncate_entity_label(entity: str) -> str:
    """Clamp entity/class string used for node and edge ``label`` fields."""
    if len(entity) <= _MAX_LABEL:
        return entity
    return entity[: _MAX_LABEL - 3] + "..."


def entity_type_from_node_id(node_id: str) -> str:
    """Infer node entity segment from ``n.Type.local`` ids; default ``Unknown``."""
    parts = node_id.split(".")
    if len(parts) >= 2:
        return parts[1]
    return "Unknown"


def entity_type_from_edge_id(edge_id: str) -> str:
    """Infer edge entity segment from ``e.Type.local`` ids; default ``Edge``."""
    parts = edge_id.split(".")
    if len(parts) >= 2:
        return parts[1]
    return "Edge"


def expand_edge_direction(center_id: str, edge_doc: Dict[str, Any]) -> str:
    """Direction of an edge relative to the expand center (expand API only).

    Returns:
        ``undirected`` if the edge is bidirectional; ``loop`` if both endpoints
        are the center; ``outgoing`` if center is source only; ``incoming`` if
        center is target only; ``undirected`` as fallback if center is not an endpoint.
    """
    src = edge_doc.get("source")
    tgt = edge_doc.get("target")
    if bool(edge_doc.get("bidirectional", True)):
        return "undirected"
    if src == center_id and tgt == center_id:
        return "loop"
    if src == center_id and tgt != center_id:
        return "outgoing"
    if tgt == center_id and src != center_id:
        return "incoming"
    return "undirected"


def trim_context(context: Optional[Dict[str, Any]], *, full: bool) -> Dict[str, Any]:
    """Trim or omit ``context`` for payloads; only non-empty when ``full`` is true."""
    if not context:
        return {}
    if not full:
        return {}
    out: Dict[str, Any] = {}
    for i, (key, value) in enumerate(context.items()):
        if key.startswith("_"):
            continue
        if i >= _MAX_CONTEXT_KEYS:
            break
        if isinstance(value, str) and len(value) > _MAX_CONTEXT_STRING:
            out[key] = value[: _MAX_CONTEXT_STRING - 3] + "..."
        elif isinstance(value, dict):
            out[key] = trim_context(value, full=True)
        else:
            out[key] = value
    return out


def node_record_to_payload(
    record: Dict[str, Any],
    *,
    detail_level: DetailLevel = "summary",
    degree: Optional[int] = None,
    missing: bool = False,
) -> Dict[str, Any]:
    """Build a JSON-serializable node dict for graph APIs (summary or full detail)."""
    node_id = str(record.get("id", ""))
    entity = str(record.get("entity") or entity_type_from_node_id(node_id))
    edges = record.get("edges") or []
    if not isinstance(edges, list):
        edges = []
    resolved_degree = degree if degree is not None else len(edges)
    ctx = record.get("context") if isinstance(record.get("context"), dict) else {}
    label = truncate_entity_label(entity)
    payload: Dict[str, Any] = {
        "id": node_id,
        "entity": entity,
        "degree": resolved_degree,
        "label": label,
    }
    if missing:
        payload["missing"] = True
    if detail_level == "full":
        payload["context"] = trim_context(ctx, full=True)
    return payload


def edge_record_to_payload(
    record: Dict[str, Any],
    *,
    detail_level: DetailLevel = "summary",
    expand_center_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a JSON-serializable edge dict; optional ``direction`` vs expand center."""
    edge_id = str(record.get("id", ""))
    entity = str(record.get("entity") or entity_type_from_edge_id(edge_id))
    elabel = truncate_entity_label(entity)
    payload: Dict[str, Any] = {
        "id": edge_id,
        "source": str(record.get("source", "")),
        "target": str(record.get("target", "")),
        "bidirectional": bool(record.get("bidirectional", True)),
        "entity": entity,
        "label": elabel,
    }
    if expand_center_id is not None:
        payload["direction"] = expand_edge_direction(expand_center_id, record)
    if detail_level == "full":
        ctx = record.get("context") if isinstance(record.get("context"), dict) else {}
        payload["context"] = trim_context(ctx, full=True)
    return payload


def merge_unique_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate nodes by ``id``, last occurrence wins."""
    by_id: Dict[str, Dict[str, Any]] = {}
    for n in nodes:
        nid = n.get("id")
        if nid:
            by_id[str(nid)] = n
    return list(by_id.values())


def merge_unique_edges(edges: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Deduplicate edges by ``id``, last occurrence wins."""
    by_id: Dict[str, Dict[str, Any]] = {}
    for e in edges:
        eid = e.get("id")
        if eid:
            by_id[str(eid)] = e
    return list(by_id.values())


__all__ = [
    "DetailLevel",
    "edge_record_to_payload",
    "entity_type_from_edge_id",
    "entity_type_from_node_id",
    "expand_edge_direction",
    "merge_unique_edges",
    "merge_unique_nodes",
    "node_record_to_payload",
    "truncate_entity_label",
    "trim_context",
]
