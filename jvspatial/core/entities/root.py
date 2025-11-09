"""Root node class for jvspatial graph."""

import asyncio
from typing import ClassVar, Optional, Type

from typing_extensions import override

from .node import Node


class Root(Node):
    """Singleton root node for the graph.

    Attributes:
        id: Fixed ID for the root node (protected)
        is_root: Flag indicating this is the root node
    """

    id: str = "n:Root:root"
    is_root: bool = True
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @override
    @classmethod
    async def get(cls: Type["Root"], id: Optional[str] = None) -> "Root":  # type: ignore[override]
        """Retrieve the root node, creating it if it doesn't exist.

        Returns:
            Root instance
        """
        async with cls._lock:
            id = "n:Root:root"
            from ..context import get_default_context

            context = get_default_context()
            node_data = await context.database.get("node", id)
            if node_data:
                return cls(id=node_data["id"], **node_data["context"])
            node = cls(id=id, is_root=True, edge_ids=[], _visitor_ref=None)
            await node.save()
            existing = await context.database.get("node", id)
            if existing and existing["id"] != node.id:
                raise RuntimeError("Root node singleton violation detected")
            return node
