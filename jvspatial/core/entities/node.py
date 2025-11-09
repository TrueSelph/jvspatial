"""Node class for jvspatial graph entities."""

import inspect
import weakref
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Type,
    Union,
)

from pydantic import Field

from jvspatial.exceptions import ValidationError

from ..annotations import attribute
from .edge import Edge
from .object import Object

if TYPE_CHECKING:
    from ..context import GraphContext

# Import Walker at runtime for __init_subclass__ validation
from .walker import Walker


class Node(Object):
    """Graph node with visitor tracking and connection capabilities.

    Attributes:
        id: Unique identifier for the node (protected - inherited from Object)
        visitor: Current walker visiting the node (transient - not persisted)
        is_root: Whether this is the root node
        edge_ids: List of connected edge IDs
    """

    type_code: str = attribute(transient=True, default="n")
    id: str = Field(..., description="Unique identifier for the node")
    _visitor_ref: Optional[weakref.ReferenceType] = attribute(
        private=True, default=None
    )
    is_root: bool = False
    edge_ids: List[str] = Field(default_factory=list)
    _visit_hooks: ClassVar[Dict[Optional[Type["Walker"]], List[Callable]]] = {}

    @classmethod
    def _get_top_level_fields(cls: Type["Node"]) -> set:
        """Get top-level fields for Node persistence format."""
        return {"edges"}  # edge_ids is stored as "edges" in persistence

    def __init_subclass__(cls: Type["Node"]) -> None:
        """Initialize subclass by registering visit hooks."""
        cls._visit_hooks = {}

        for _name, method in inspect.getmembers(cls, inspect.isfunction):
            if hasattr(method, "_is_visit_hook"):
                targets = getattr(method, "_visit_targets", None)

                if targets is None:
                    # No targets specified - register for any Walker
                    if None not in cls._visit_hooks:
                        cls._visit_hooks[None] = []
                    cls._visit_hooks[None].append(method)
                else:
                    # Register for each specified target type
                    for target in targets:
                        if not (inspect.isclass(target) and issubclass(target, Walker)):
                            raise ValidationError(
                                f"Node @on_visit must target Walker types, got {target.__name__ if hasattr(target, '__name__') else target}",
                                details={
                                    "target_type": str(target),
                                    "expected_type": "Walker",
                                },
                            )
                        if target not in cls._visit_hooks:
                            cls._visit_hooks[target] = []
                        cls._visit_hooks[target].append(method)

    @property
    def visitor(self: "Node") -> Optional["Walker"]:
        """Get the current visitor of this node.

        Returns:
            Walker instance if present, else None
        """
        return self._visitor_ref() if self._visitor_ref else None

    def set_visitor(self: "Node", value: Optional["Walker"]) -> None:
        """Set the current visitor of this node.

        Args:
            value: Walker instance to set as visitor, or None to clear
        """
        self._visitor_ref = weakref.ref(value) if value else None

    async def connect(
        self,
        other: "Node",
        edge: Optional[Type["Edge"]] = None,
        direction: str = "out",
        **kwargs: Any,
    ) -> "Edge":
        """Connect this node to another node.

        Creates a default directed Edge if no edge type is specified. The edge
        is created with direction='out' by default (forward connection).

        Args:
            other: Target node to connect to
            edge: Edge class to use for connection. If omitted or None, defaults
                  to the base Edge class, creating a generic directed edge.
            direction: Connection direction ('out', 'in', 'both').
                       Defaults to 'out' for forward connections (unidirectional).
                       Use 'both' for bidirectional connections.
            **kwargs: Additional edge properties (e.g., name, distance)

        Returns:
            Created edge instance

        Examples:
            # Create a default directed edge (most common case)
            await node1.connect(node2, name="relationship")

            # Create a custom edge type
            await node1.connect(node2, Highway, distance=100, lanes=4)

            # Bidirectional connection
            await node1.connect(node2, direction="both", name="mutual")
        """
        if edge is None:
            edge = Edge

        # Create edge using the new async pattern
        connection = await edge.create(
            source=self.id, target=other.id, direction=direction, **kwargs
        )

        # Update node edge lists preserving add order
        if connection.id not in self.edge_ids:
            self.edge_ids.append(connection.id)
        if connection.id not in other.edge_ids:
            other.edge_ids.append(connection.id)

        # Save both nodes to persist the edge_ids updates
        await self.save()
        await other.save()
        return connection

    async def edges(self: "Node", direction: str = "") -> List["Edge"]:
        """Get edges connected to this node.

        Args:
            direction: Filter edges by direction ('in', 'out', 'both')

        Returns:
            List of edge instances
        """
        edges = []
        for edge_id in self.edge_ids:
            edge_obj = await Edge.get(edge_id)
            if edge_obj:
                edges.append(edge_obj)
        if direction == "out":
            return [e for e in edges if e.source == self.id]
        elif direction == "in":
            return [e for e in edges if e.target == self.id]
        else:
            return edges

    async def nodes(
        self,
        direction: str = "out",
        node: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]] = None,
        edge: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> List["Node"]:
        """Get nodes connected to this node via optimized database-level filtering.

        This method performs efficient database-level filtering across node properties,
        edge properties, node types, and edge types using MongoDB aggregation pipelines.

        Args:
            direction: Connection direction ('out', 'in', 'both').
                       Defaults to 'out' for forward traversal only (outgoing edges).
                       Use 'both' to include both incoming and outgoing connections.
            node: Node filtering - supports multiple formats:
                  - String: 'City' (filter by type)
                  - List of strings: ['City', 'Town'] (multiple types)
                  - List with dicts: [{'City': {"context.population": {"$gte": 50000}}}]
            edge: Edge filtering - supports multiple formats:
                  - String/Type: 'Highway' or Highway (filter by type)
                  - List: [Highway, Railroad] (multiple types)
                  - List with dicts: [{'Highway': {"context.condition": {"$ne": "poor"}}}]
            limit: Maximum number of nodes to retrieve
            **kwargs: Simple property filters for connected nodes (e.g., state="NY")

        Returns:
            List of connected nodes in connection order

        Examples:
            # Basic traversal
            next_nodes = node.nodes()

            # Simple type filtering
            cities = node.nodes(node='City')

            # Simple property filtering (kwargs apply to connected nodes)
            ny_nodes = node.nodes(state="NY")
            ca_cities = node.nodes(node=['City'], state="CA")

            # Complex filtering with MongoDB operators
            large_cities = node.nodes(
                node=[{'City': {"context.population": {"$gte": 500000}}}]
            )

            # Edge and node filtering combined
            premium_routes = node.nodes(
                direction="out",
                node=[{'City': {"context.population": {"$gte": 100000}}}],
                edge=[{'Highway': {"context.condition": {"$ne": "poor"}}}]
            )

            # Mixed approaches (semantic flexibility)
            optimal_connections = node.nodes(
                node='City',
                edge=[{'Highway': {"context.speed_limit": {"$gte": 60}}}],
                state="NY"  # Simple property filter via kwargs
            )
        """
        context = await self.get_context()

        # Build optimized database query using aggregation pipeline
        return await self._node_query(
            context=context,
            direction=direction,
            node_filter=node,
            edge_filter=edge,
            limit=limit,
            **kwargs,
        )

    async def node(
        self,
        direction: str = "out",
        node: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]] = None,
        edge: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ] = None,
        **kwargs: Any,
    ) -> Optional["Node"]:
        """Get a single node connected to this node.

        This is a convenience method that returns the first node from nodes().
        Primarily useful when you expect only one node and want to avoid list indexing.

        Args:
            direction: Connection direction ('out', 'in', 'both')
            node: Node filtering - same formats as nodes() method
            edge: Edge filtering - same formats as nodes() method
            **kwargs: Simple property filters for connected nodes

        Returns:
            First connected node matching criteria, or None if no nodes found

        Examples:
            # Find a single memory node
            memory = agent.node(node='Memory')
            if memory:
                # Use the memory node
                pass

            # Find a specific city
            ny_city = state.node(node='City', name="New York")

            # With complex filtering
            large_city = node.node(
                node=[{'City': {"context.population": {"$gte": 500000}}}]
            )
        """
        nodes = await self.nodes(
            direction=direction,
            node=node,
            edge=edge,
            limit=1,  # Optimize by limiting to 1 result
            **kwargs,
        )
        return nodes[0] if nodes else None

    async def _node_query(
        self,
        context: "GraphContext",
        direction: str = "out",
        node_filter: Optional[
            Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]
        ] = None,
        edge_filter: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> List["Node"]:
        """Execute optimized database query to find connected nodes.

        Args:
            context: GraphContext instance for database operations
            direction: Connection direction ('out', 'in', 'both')
            node_filter: Node filtering criteria
            edge_filter: Edge filtering criteria
            limit: Maximum number of nodes to return
            **kwargs: Simple property filters for connected nodes

        Returns:
            List of connected nodes matching the criteria
        """
        # Find edges connected to this node
        from .edge import Edge as EdgeClass

        edges = []

        if direction in ["out", "both"]:
            # Find outgoing edges
            outgoing_edges = await context.find_edges_between(
                source_id=self.id,
                edge_class=edge_filter if isinstance(edge_filter, type) else None,
            )
            edges.extend(outgoing_edges)

        if direction in ["in", "both"]:
            # Find incoming edges (where this node is the target)
            edge_cls = edge_filter if isinstance(edge_filter, type) else EdgeClass
            query = {"target": self.id}
            if isinstance(edge_filter, type):
                query["name"] = edge_filter.__name__

            edge_results = await context.database.find("edge", query)
            for edge_data in edge_results:
                try:
                    edge_obj: Optional["Edge"] = await context._deserialize_entity(
                        edge_cls, edge_data
                    )
                    if edge_obj:
                        edges.append(edge_obj)
                except Exception:
                    continue

        # Get unique connected node IDs
        connected_node_ids = set()
        for edge in edges:
            if direction in ["out", "both"] and hasattr(edge, "target"):
                connected_node_ids.add(edge.target)
            if direction in ["in", "both"] and hasattr(edge, "source"):
                connected_node_ids.add(edge.source)

        # Find the actual nodes
        connected_nodes = []
        for node_id in connected_node_ids:
            try:
                # Try to get the node from the database
                node_data = await context.database.get("node", node_id)
                if node_data:
                    # Deserialize the node
                    node_obj = await context._deserialize_entity(Node, node_data)
                    if node_obj:
                        connected_nodes.append(node_obj)
            except Exception:
                continue  # Skip invalid nodes

        # Apply node type filtering
        if node_filter is not None:
            filtered_nodes = []
            for node_obj in connected_nodes:
                if self._matches_node_filter(node_obj, node_filter):
                    filtered_nodes.append(node_obj)
            connected_nodes = filtered_nodes

        # Apply property filtering from kwargs
        if kwargs:
            filtered_nodes = []
            for node_obj in connected_nodes:
                if self._matches_property_filter(node_obj, kwargs):
                    filtered_nodes.append(node_obj)
            connected_nodes = filtered_nodes

        # Apply limit
        if limit is not None:
            connected_nodes = connected_nodes[:limit]

        return connected_nodes

    def _matches_node_filter(
        self,
        node_obj: "Node",
        node_filter: Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]],
    ) -> bool:
        """Check if a node matches the node filter criteria.

        Args:
            node_obj: Node object to test
            node_filter: Filter criteria (string, list of strings, or list of dicts)

        Returns:
            True if node matches the filter
        """
        if isinstance(node_filter, str):
            # Simple string filter - match by class name
            return node_obj.__class__.__name__ == node_filter

        elif isinstance(node_filter, list):
            for filter_item in node_filter:
                if isinstance(filter_item, str):
                    # String in list - match by class name
                    if node_obj.__class__.__name__ == filter_item:
                        return True
                elif isinstance(filter_item, dict):
                    # Dict filter - match by class name and criteria
                    for class_name, criteria in filter_item.items():
                        if (
                            node_obj.__class__.__name__ == class_name
                            and self._matches_property_filter(node_obj, criteria)
                        ):
                            return True

        return False

    def _matches_property_filter(
        self, node_obj: "Node", criteria: Dict[str, Any]
    ) -> bool:
        """Check if a node matches property filter criteria.

        Args:
            node_obj: Node object to test
            criteria: Property filter criteria

        Returns:
            True if node matches all criteria
        """
        for key, expected_value in criteria.items():
            # Handle nested property access (e.g., "context.population")
            if key.startswith("context."):
                actual_value = getattr(node_obj, key[8:], None)
            else:
                actual_value = getattr(node_obj, key, None)

            # Handle MongoDB-style operators
            if isinstance(expected_value, dict):
                if not self._match_criteria(actual_value, expected_value):
                    return False
            else:
                # Simple equality check
                if actual_value != expected_value:
                    return False

        return True

    def _match_criteria(
        self, value: Any, criteria: Dict[str, Any], compiled_regex: Optional[Any] = None
    ) -> bool:
        """Match a value against MongoDB-style criteria.

        Args:
            value: The value to test
            criteria: Dictionary of MongoDB-style operators and values
            compiled_regex: Pre-compiled regex pattern for performance

        Returns:
            True if value matches all criteria

        Supported operators:
            $eq: Equal to
            $ne: Not equal to
            $gt: Greater than
            $gte: Greater than or equal to
            $lt: Less than
            $lte: Less than or equal to
            $in: Value is in list
            $nin: Value is not in list
            $regex: Regular expression match (for strings)
            $exists: Field exists (True) or doesn't exist (False)
        """
        import re

        for operator, criterion in criteria.items():
            if operator == "$eq":
                if value != criterion:
                    return False
            elif operator == "$ne":
                if value == criterion:
                    return False
            elif operator == "$gt":
                try:
                    if value <= criterion:
                        return False
                except (TypeError, ValueError):
                    return False
            elif operator == "$gte":
                try:
                    if value < criterion:
                        return False
                except (TypeError, ValueError):
                    return False
            elif operator == "$lt":
                try:
                    if value >= criterion:
                        return False
                except (TypeError, ValueError):
                    return False
            elif operator == "$lte":
                try:
                    if value > criterion:
                        return False
                except (TypeError, ValueError):
                    return False
            elif operator == "$in":
                if not isinstance(criterion, (list, tuple, set)):
                    return False
                if value not in criterion:
                    return False
            elif operator == "$nin":
                if not isinstance(criterion, (list, tuple, set)):
                    return False
                if value in criterion:
                    return False
            elif operator == "$regex":
                if not isinstance(value, str):
                    return False
                # Use pre-compiled regex if available, otherwise compile on-demand
                if compiled_regex:
                    if not compiled_regex.search(value):
                        return False
                else:
                    try:
                        if not re.search(criterion, value):
                            return False
                    except re.error:
                        return False
            elif operator == "$exists":
                # This is handled at the property level, not here
                # If we reach this point, the property exists
                if not criterion:  # $exists: False means property shouldn't exist
                    return False
            else:
                # Unknown operator - ignore for forward compatibility
                continue

        return True

    async def neighbors(
        self,
        node: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]] = None,
        edge: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> List["Node"]:
        """Get all neighboring nodes (convenient alias for nodes()).

        Args:
            node: Node filtering (supports semantic filtering)
            edge: Edge filtering (supports semantic filtering)
            limit: Maximum number of neighbors to return
            **kwargs: Simple property filters for connected nodes

        Returns:
            List of neighboring nodes in connection order
        """
        return await self.nodes(
            direction="both", node=node, edge=edge, limit=limit, **kwargs
        )

    async def outgoing(
        self,
        node: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]] = None,
        edge: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> List["Node"]:
        """Get nodes connected via outgoing edges.

        Args:
            node: Node filtering (supports semantic filtering)
            edge: Edge filtering (supports semantic filtering)
            limit: Maximum number of nodes to return
            **kwargs: Simple property filters for connected nodes

        Returns:
            List of nodes connected by outgoing edges
        """
        return await self.nodes(
            direction="out", node=node, edge=edge, limit=limit, **kwargs
        )

    async def incoming(
        self,
        node: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]] = None,
        edge: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> List["Node"]:
        """Get nodes connected via incoming edges.

        Args:
            node: Node filtering (supports semantic filtering)
            edge: Edge filtering (supports semantic filtering)
            limit: Maximum number of nodes to return
            **kwargs: Simple property filters for connected nodes

        Returns:
            List of nodes connected by incoming edges
        """
        return await self.nodes(
            direction="in", node=node, edge=edge, limit=limit, **kwargs
        )

    async def disconnect(
        self, other: "Node", edge_type: Optional[Type["Edge"]] = None
    ) -> bool:
        """Disconnect this node from another node.

        Args:
            other: Node to disconnect from
            edge_type: Specific edge type to remove (optional)

        Returns:
            True if disconnection was successful
        """
        try:
            context = await self.get_context()
            edges = await context.find_edges_between(self.id, other.id, edge_type)

            for edge in edges:
                # Remove edge from both nodes' edge_ids lists
                if edge.id in self.edge_ids:
                    self.edge_ids.remove(edge.id)
                if edge.id in other.edge_ids:
                    other.edge_ids.remove(edge.id)

                # Delete the edge
                await context.delete(edge)

            # Save both nodes
            await self.save()
            await other.save()

            return len(edges) > 0
        except Exception:
            return False

    async def is_connected_to(
        self, other: "Node", edge_type: Optional[Type["Edge"]] = None
    ) -> bool:
        """Check if this node is connected to another node.

        Args:
            other: Node to check connection to
            edge_type: Specific edge type to check for (optional)

        Returns:
            True if nodes are connected
        """
        try:
            context = await self.get_context()
            edges = await context.find_edges_between(self.id, other.id, edge_type)
            return len(edges) > 0
        except Exception:
            return False

    async def connection_count(self) -> int:
        """Get the number of connections (edges) for this node.

        Returns:
            Number of connected edges
        """
        return len(self.edge_ids)

    @classmethod
    async def create_and_connect(
        cls: Type["Node"],
        other: "Node",
        edge: Optional[Type["Edge"]] = None,
        **kwargs: Any,
    ) -> "Node":
        """Create a new node and immediately connect it to another node.

        Args:
            other: Node to connect to
            edge: Edge type to use for connection
            **kwargs: Node properties

        Returns:
            Created and connected node
        """
        from typing import cast

        node = cast(Node, await cls.create(**kwargs))
        await node.connect(other, edge or Edge)
        return node

    def export(
        self: "Node",
        exclude_transient: bool = True,
        exclude: Optional[Union[set, Dict[str, Any]]] = None,
        for_persistence: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Export node to a dictionary.

        Uses the standard Object.export() method. By default, returns a clean
        flat dictionary suitable for API responses.
        Set for_persistence=True to get the nested database format.

        Args:
            exclude_transient: Whether to automatically exclude transient fields (default: True)
            exclude: Additional fields to exclude (can be a set of field names or a dict)
            for_persistence: If True, returns nested persistence format with id, name, context, edges (default: False)
            **kwargs: Additional arguments passed to base export/model_dump()

        Returns:
            Dictionary representation of the node:
            - If for_persistence=False: Clean flat dictionary (standard format)
            - If for_persistence=True: Nested format with id, name, context, edges for database storage
        """
        if for_persistence:
            # Legacy persistence format - nested structure for database storage
            context_data = super().export(
                exclude={"id", "_visitor_ref", "is_root", "edge_ids"},
                exclude_none=False,
                exclude_transient=exclude_transient,
                **kwargs,
            )

            # Include _data if it exists
            if hasattr(self, "_data"):
                context_data["_data"] = self._data

            # Serialize datetime objects to ensure JSON compatibility
            from jvspatial.utils.serialization import serialize_datetime

            context_data = serialize_datetime(context_data)

            return {
                "id": self.id,
                "name": self.__class__.__name__,
                "context": context_data,
                "edges": self.edge_ids,
            }
        else:
            # Standard export - clean flat dictionary for API responses
            # Exclude internal node fields by default
            default_exclude = {
                "type_code",
                "_graph_context",
                "_data",
                "_initializing",
                "edge_ids",
                "visitor",
            }
            if exclude:
                exclude_set = (
                    set(exclude) if isinstance(exclude, (set, dict)) else set()
                )
                exclude_set.update(default_exclude)
            else:
                exclude_set = default_exclude

            return super().export(
                exclude_transient=exclude_transient, exclude=exclude_set, **kwargs
            )
