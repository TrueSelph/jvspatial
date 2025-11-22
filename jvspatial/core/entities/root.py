"""Root node class for jvspatial graph."""

import asyncio
from typing import ClassVar, Optional, Type

from typing_extensions import override

from .node import Node


class Root(Node):
    """Singleton root node for the graph.

    Attributes:
        id: Fixed ID for the root node (protected)
    """

    id: str = "n.Root.root"
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @override
    @classmethod
    async def get(cls: Type["Root"], id: Optional[str] = None) -> "Root":  # type: ignore[override]
        """Retrieve the root node, creating it if it doesn't exist.

        Returns:
            Root instance
        """
        async with cls._lock:
            id = "n.Root.root"
            from ..context import get_default_context

            context = get_default_context()
            node_data = await context.database.get("node", id)
            if node_data:
                context_data = node_data.get("context", {})
                if not isinstance(context_data, dict):
                    context_data = {}

                # Handle edge_ids from database format (stored as "edges" at top level)
                edge_ids = node_data.get("edges", [])
                if not isinstance(edge_ids, list):
                    edge_ids = []

                # Ensure we have a valid ID
                node_id = node_data.get("id", id)
                if node_id != "n.Root.root":
                    node_id = "n.Root.root"

                root = cls(id=node_id, edge_ids=edge_ids, **context_data)
                root._graph_context = context
                return root

            # Create new Root node if not found
            node = cls(id=id, edge_ids=[], _visitor_ref=None)
            node._graph_context = context
            await node.save()
            existing = await context.database.get("node", id)
            if existing and existing.get("id") != node.id:
                raise RuntimeError("Root node singleton violation detected")
            return node
