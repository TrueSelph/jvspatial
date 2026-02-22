"""Root node class for jvspatial graph."""

import asyncio
from typing import Any, ClassVar, Optional, Type

from typing_extensions import override

from .node import Node


class Root(Node):
    """Singleton root node for the graph.

    Attributes:
        id: Fixed ID for the root node (protected)
    """

    id: str = "n.Root.root"
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    def __init__(self, **kwargs: Any) -> None:
        """Initialize Root with fixed ID.

        Args:
            **kwargs: Node attributes (id will be overridden)
        """
        # Always use the fixed ID for Root, ignore any passed ID
        kwargs["id"] = "n.Root.root"
        super().__init__(**kwargs)

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

    @override
    @classmethod
    async def create(cls: Type["Root"], **kwargs: Any) -> "Root":
        """Create root node - delegates to get() to ensure singleton.

        This method ensures Root nodes always use the fixed ID 'n.Root.root'
        and prevents duplicate root nodes from being created.

        Args:
            **kwargs: Ignored - Root always uses fixed ID

        Returns:
            Root instance (singleton)
        """
        # Ignore any ID passed in kwargs - Root must always use fixed ID
        kwargs.pop("id", None)
        return await cls.get()

    @override
    async def save(self: "Root") -> "Root":
        """Save root node, ensuring ID is never changed.

        Returns:
            Saved Root instance
        """
        # Ensure ID is always the fixed value
        if self.id != "n.Root.root":
            object.__setattr__(self, "id", "n.Root.root")
        return await super().save()
