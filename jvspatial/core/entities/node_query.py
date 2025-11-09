"""NodeQuery class for filtering connected nodes."""

import inspect
from typing import Any, List, Optional, Type, Union

from .edge import Edge
from .node import Node


class NodeQuery:
    """Query object for filtering connected nodes with database-level optimization.

    Attributes:
        nodes: List of nodes to query
        source: Source node for the query
        _cached: Whether results are cached
    """

    def __init__(self, nodes: List["Node"], source: Optional["Node"] = None) -> None:
        """Initialize a NodeQuery.

        Args:
            nodes: List of nodes to query
            source: Source node for the query
        """
        self.source = source
        self.nodes = nodes
        self._cached = True  # Nodes are already loaded

    async def filter(
        self: "NodeQuery",
        *,
        node: Optional[Union[str, List[str]]] = None,
        edge: Optional[Union[str, Type["Edge"], List[Union[str, Type["Edge"]]]]] = None,
        direction: str = "both",
        **kwargs: Any,
    ) -> List["Node"]:
        """Filter nodes by type, edge type, direction, or edge properties.

        Args:
            node: Node type(s) to filter by
            edge: Edge type(s) to filter by
            direction: Connection direction to filter by
            **kwargs: Edge properties to filter by

        Returns:
            Filtered list of nodes
        """
        if self.source is None:
            return []

        filtered_nodes = self.nodes.copy()
        if node:
            node_types = [node] if isinstance(node, str) else node
            filtered_nodes = [
                n for n in filtered_nodes if n.__class__.__name__ in node_types
            ]
        if edge or direction != "both" or kwargs:
            edge_types = []
            if edge:
                edge_types = [
                    e.__name__ if inspect.isclass(e) else e
                    for e in (edge if isinstance(edge, list) else [edge])
                ]
            valid_nodes = []
            edges = await self.source.edges(direction=direction)
            for n in filtered_nodes:
                connectors = [
                    e
                    for e in edges
                    if (e.source == self.source.id and e.target == n.id)
                    or (e.source == n.id and e.target == self.source.id)
                ]
                if edge_types:
                    connectors = [
                        e for e in connectors if e.__class__.__name__ in edge_types
                    ]
                if kwargs:
                    connectors = [
                        e
                        for e in connectors
                        if all(getattr(e, k, None) == v for k, v in kwargs.items())
                    ]
                if connectors:
                    valid_nodes.append(n)
            filtered_nodes = valid_nodes
        return filtered_nodes
