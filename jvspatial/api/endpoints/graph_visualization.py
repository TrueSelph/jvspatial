"""Progressive JSON graph API handlers (bounded expand + BFS subgraph)."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any, Callable, Dict, Optional

from fastapi import HTTPException, Query
from fastapi.responses import JSONResponse

from jvspatial.core.context import GraphContext, get_default_context

logger = logging.getLogger(__name__)


def weak_etag_for_payload(payload: Dict[str, Any]) -> str:
    """Return a short hex digest for ETag headers from a stable JSON serialization."""
    body = json.dumps(payload, sort_keys=True, default=str).encode()
    return hashlib.sha256(body).hexdigest()[:16]


def make_graph_expand_handler(
    graph_context: Optional[GraphContext],
) -> Callable[..., Any]:
    """Build GET /graph/expand handler with bound ``graph_context`` (or default at runtime)."""

    async def graph_expand(
        node_id: str = Query(  # noqa: B008
            ...,
            description="Node id to expand (e.g. n.Root.root)",
        ),
        direction: str = Query(  # noqa: B008
            default="both",
            description="Edge direction filter: both, out, or in (non-bidirectional edges only)",
            pattern="^(both|out|in|all)$",
        ),
        limit: int = Query(  # noqa: B008
            default=50,
            ge=0,
            le=500,
            description="Max edges in this page",
        ),
        cursor: int = Query(  # noqa: B008
            default=0,
            ge=0,
            description="Offset into the node's edge-id list",
        ),
        detail_level: str = Query(  # noqa: B008
            default="full",
            description="full (default): id + entity + label + trimmed context on every node/edge; summary: omit context for smaller payloads",
            pattern="^(summary|full)$",
        ),
    ) -> JSONResponse:
        ctx = graph_context if graph_context is not None else get_default_context()
        try:
            payload = await ctx.expand_node(
                node_id,
                direction=direction,
                limit=limit,
                cursor=cursor,
                detail_level=detail_level,
            )
        except Exception as e:
            logger.exception("graph expand failed")
            raise HTTPException(
                status_code=500, detail=f"Graph expand failed: {e}"
            ) from e
        tag = weak_etag_for_payload(payload)
        return JSONResponse(
            content=payload,
            headers={"ETag": f'W/"{tag}"'},
        )

    return graph_expand


def make_graph_subgraph_handler(
    graph_context: Optional[GraphContext],
) -> Callable[..., Any]:
    """Build GET /graph/subgraph handler with bound ``graph_context``."""

    async def graph_subgraph(
        root: str = Query(  # noqa: B008
            ...,
            description="BFS root node id (e.g. n.Root.root)",
        ),
        max_depth: int = Query(2, ge=0, le=50),  # noqa: B008
        max_nodes: int = Query(100, ge=1, le=10_000),  # noqa: B008
        max_edges_per_node: int = Query(200, ge=1, le=2000),  # noqa: B008
        detail_level: str = Query(  # noqa: B008
            default="full",
            description="full (default): trimmed context on all nodes/edges; summary: omit context",
            pattern="^(summary|full)$",
        ),
    ) -> JSONResponse:
        ctx = graph_context if graph_context is not None else get_default_context()
        try:
            payload = await ctx.subgraph_bfs(
                root,
                max_depth=max_depth,
                max_nodes=max_nodes,
                max_edges_per_node=max_edges_per_node,
                detail_level=detail_level,
            )
        except Exception as e:
            logger.exception("graph subgraph failed")
            raise HTTPException(
                status_code=500, detail=f"Graph subgraph failed: {e}"
            ) from e
        tag = weak_etag_for_payload(payload)
        return JSONResponse(
            content=payload,
            headers={"ETag": f'W/"{tag}"'},
        )

    return graph_subgraph
