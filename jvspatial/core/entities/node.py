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
        edge_ids: List of connected edge IDs
    """

    type_code: str = attribute(transient=True, default="n")
    _visitor_ref: Optional[weakref.ReferenceType] = attribute(
        private=True, default=None
    )
    edge_ids: List[str] = attribute(
        transient=True, default_factory=list, description="List of connected edge IDs"
    )
    _visit_hooks: ClassVar[
        Dict[Union[Optional[Type["Walker"]], str], List[Callable]]
    ] = {}

    @classmethod
    def _get_top_level_fields(cls: Type["Node"]) -> set:
        """Get top-level fields for Node persistence format."""
        return {
            "edges"
        }  # edge_ids is stored as "edges" at top level in database exports

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
                        # Accept both classes and strings for forward references
                        # Strings will be resolved at runtime when the walker visits
                        if isinstance(target, str):
                            # String target - store for later resolution
                            if target not in cls._visit_hooks:
                                cls._visit_hooks[target] = []
                            cls._visit_hooks[target].append(method)
                        elif inspect.isclass(target):
                            # Class target - validate it's a Walker subclass
                            if issubclass(target, Walker):  # type: ignore[arg-type]
                                if target not in cls._visit_hooks:
                                    cls._visit_hooks[target] = []
                                cls._visit_hooks[target].append(method)
                            else:
                                target_name = (
                                    target.__name__
                                    if hasattr(target, "__name__")
                                    else target
                                )
                                raise ValidationError(
                                    f"Node @on_visit must target Walker types "
                                    f"(or string names), got {target_name}",
                                    details={
                                        "target_type": str(target),
                                        "expected_type": "Walker or string",
                                    },
                                )
                        else:
                            target_name = (
                                target.__name__
                                if hasattr(target, "__name__")
                                else target
                            )
                            raise ValidationError(
                                f"Node @on_visit must target Walker types "
                                f"(or string names), got {target_name}",
                                details={
                                    "target_type": str(target),
                                    "expected_type": "Walker or string",
                                },
                            )

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

        This method is idempotent - if an edge already exists between the nodes
        (matching the edge type and direction), it will return the existing edge
        instead of creating a duplicate.

        Args:
            other: Target node to connect to
            edge: Edge class to use for connection. If omitted or None, defaults
                  to the base Edge class, creating a generic directed edge.
            direction: Connection direction ('out', 'in', 'both').
                       Defaults to 'out' for forward connections (unidirectional).
                       Use 'both' for bidirectional connections.
            **kwargs: Additional edge properties (e.g., name, distance)

        Returns:
            Existing edge instance if one exists, otherwise a newly created edge

        Examples:
            # Create a default directed edge (most common case)
            await node1.connect(node2, name="relationship")

            # Create a custom edge type
            await node1.connect(node2, Highway, distance=100, lanes=4)

            # Bidirectional connection
            await node1.connect(node2, direction="both", name="mutual")
        """
        context = await self.get_context()

        if edge is None:
            edge = Edge

        # Check if an edge already exists between these nodes
        # This prevents duplicate edges from being created on repeated calls
        # Check both directions (self->other and other->self) to catch all existing edges
        existing_edges_forward = await context.find_edges_between(
            source_id=self.id,
            target_id=other.id,
            edge_class=edge,
        )
        existing_edges_reverse = await context.find_edges_between(
            source_id=other.id,
            target_id=self.id,
            edge_class=edge,
        )

        # Combine both directions
        all_existing_edges = existing_edges_forward + existing_edges_reverse

        # Filter existing edges by direction if specified
        # For bidirectional edges, we accept any edge between these nodes
        # For unidirectional edges, we need to match the direction
        matching_edge = None
        for existing_edge in all_existing_edges:
            # Check if direction matches
            # If direction is "both", accept any edge between these nodes
            # If direction is "out", accept edges where source=self.id and target=other.id
            # If direction is "in", accept edges where source=other.id and target=self.id
            if direction == "both":
                # For bidirectional, accept any edge between these nodes
                matching_edge = existing_edge
                break
            elif direction == "out":
                # For outgoing, check source and target match
                if existing_edge.source == self.id and existing_edge.target == other.id:
                    matching_edge = existing_edge
                    break
            elif (
                direction == "in"
                and existing_edge.source == other.id
                and existing_edge.target == self.id
            ):
                # For incoming, check source and target are reversed
                matching_edge = existing_edge
                break

        # If an existing edge is found, return it instead of creating a duplicate
        if matching_edge:
            # Ensure edge IDs are in both nodes' edge_ids lists (in case they're missing)
            if matching_edge.id not in self.edge_ids:
                self.edge_ids.append(matching_edge.id)
                await self.save()
            if matching_edge.id not in other.edge_ids:
                other.edge_ids.append(matching_edge.id)
                await other.save()
            return matching_edge

        # No existing edge found, create a new one
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
        node: Optional[
            Union[str, type, List[Union[str, type, Dict[str, Dict[str, Any]]]]]
        ] = None,
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
        node: Optional[
            Union[str, type, List[Union[str, type, Dict[str, Dict[str, Any]]]]]
        ] = None,
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
            Union[str, type, List[Union[str, type, Dict[str, Dict[str, Any]]]]]
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
        node_filter: Union[
            str, type, List[Union[str, type, Dict[str, Dict[str, Any]]]]
        ],
    ) -> bool:
        """Check if a node matches the node filter criteria.

        Args:
            node_obj: Node object to test
            node_filter: Filter criteria - can be:
                - String: entity name (e.g., "Memory")
                - Type: class type (e.g., Memory)
                - List of strings/types
                - List of dicts with entity name as key and criteria as value

        Returns:
            True if node matches the filter
        """
        if isinstance(node_filter, str):
            # Simple string filter - match by class name
            return node_obj.__class__.__name__ == node_filter

        elif isinstance(node_filter, type):
            # Class type filter - match by class or inheritance
            return isinstance(node_obj, node_filter)

        elif isinstance(node_filter, list):
            for filter_item in node_filter:
                if isinstance(filter_item, str):
                    # String in list - match by class name
                    if node_obj.__class__.__name__ == filter_item:
                        return True
                elif isinstance(filter_item, type):
                    # Class type in list - match by class or inheritance
                    if isinstance(node_obj, filter_item):
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
                # Unknown operator - ignore
                continue

        return True

    async def neighbors(
        self,
        node: Optional[
            Union[str, type, List[Union[str, type, Dict[str, Dict[str, Any]]]]]
        ] = None,
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
        node: Optional[
            Union[str, type, List[Union[str, type, Dict[str, Dict[str, Any]]]]]
        ] = None,
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
        node: Optional[
            Union[str, type, List[Union[str, type, Dict[str, Dict[str, Any]]]]]
        ] = None,
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

    async def delete(self: "Node", cascade: bool = True) -> None:
        """Delete this node and cascade deletion of all related edges and dependent nodes.

        This method performs a clean cascade deletion for Node entities:
        1. Finds all incoming edges to this node (edges where this node is the target)
        2. If cascade is enabled, recursively finds all dependent nodes:
           - A node is dependent if it's reachable FROM this node via outgoing edges
           - A node is considered dependent if ALL its edges connect to nodes in the deletion set
           - This ensures only nodes solely reachable through this node are deleted
           - Ancestors and nodes with other connections are preserved
        3. Deletes all incoming edges to this node
        4. Deletes all dependent nodes recursively (each dependent node will also
           cascade delete its own dependent nodes)
        5. Finally deletes this node itself

        Note: Node entities are the only entities that can be connected by edges on the graph.
        Object entities are fundamental entities not connected by edges and use Object.delete()
        which simply removes the entity.

        Args:
            cascade: Whether to cascade deletion to dependent nodes (default: True)
                    If False, only deletes incoming edges and the node itself

        Examples:
            # Full cascade deletion (default)
            # Deletes the node, its incoming edges, and all nodes solely reachable from it
            await node.delete()

            # Delete node and incoming edges only, don't cascade to dependent nodes
            await node.delete(cascade=False)
        """
        context = await self.get_context()

        # Get only incoming edges to this node (edges where this node is the target)
        # We only delete incoming edges, not outgoing edges
        incoming_edges = []

        # Query database for edges where target is this node's ID
        from .edge import Edge as EdgeClass

        edge_query = {"target": self.id}
        edge_results = await context.database.find("edge", edge_query)
        for edge_data in edge_results:
            try:
                edge_obj = await context._deserialize_entity(EdgeClass, edge_data)
                if edge_obj:
                    incoming_edges.append(edge_obj)
            except Exception:
                continue

        # Also check edges from edge_ids where this node is the target
        for edge_id in self.edge_ids:
            try:
                edge = await Edge.get(edge_id)
                # Only include edges where this node is the target (incoming)
                if edge and edge.target == self.id and edge not in incoming_edges:
                    incoming_edges.append(edge)
            except Exception:
                continue

        # Remove duplicates
        seen_edge_ids = set()
        unique_incoming_edges = []
        for edge in incoming_edges:
            if edge.id not in seen_edge_ids:
                seen_edge_ids.add(edge.id)
                unique_incoming_edges.append(edge)
        incoming_edges = unique_incoming_edges

        # Get outgoing edges to find nodes reachable FROM this node
        outgoing_edges = await context.find_edges_between(source_id=self.id)

        # Build complete set of all nodes reachable FROM this node (via outgoing edges, recursively)
        # This includes nodes reachable through multiple hops
        reachable_node_ids = set()
        nodes_to_explore = {self.id}
        explored = set()

        while nodes_to_explore:
            current_id = nodes_to_explore.pop()
            if current_id in explored:
                continue
            explored.add(current_id)

            # Get all outgoing edges from current node
            current_outgoing = await context.find_edges_between(source_id=current_id)
            for edge in current_outgoing:
                if edge.source == current_id:
                    target_id = edge.target
                    if target_id not in explored:
                        reachable_node_ids.add(target_id)
                        nodes_to_explore.add(target_id)

        # If cascade is enabled, recursively find all dependent nodes to delete
        # Strategy: Only delete nodes that are:
        # 1. Reachable FROM this node (via outgoing edges)
        # 2. ONLY connected to nodes in the deletion set (no connections to nodes outside)
        # This ensures ancestors and nodes with other connections are preserved
        nodes_to_delete = set()
        if cascade:
            # Start with nodes directly reachable from this node (via outgoing edges)
            # Only consider nodes reachable FROM this node, not nodes that can reach TO this node
            nodes_to_delete.add(self.id)

            changed = True
            max_iterations = 100  # Safety limit to prevent infinite loops
            iteration = 0

            while changed and iteration < max_iterations:
                changed = False
                iteration += 1

                # Get all nodes reachable FROM nodes in the deletion set (via outgoing edges only)
                nodes_to_check = set()
                for node_id in nodes_to_delete:
                    try:
                        node = await Node.get(node_id)
                        if not node:
                            continue
                        # Only follow outgoing edges (where this node is the source)
                        for edge_id in node.edge_ids:  # type: ignore[attr-defined]
                            try:
                                edge = await Edge.get(edge_id)
                                if edge and edge.source == node_id:
                                    # Only add nodes reachable via outgoing edges
                                    nodes_to_check.add(edge.target)
                            except Exception:
                                continue
                    except Exception:
                        continue

                # For each candidate node, check if it should be deleted
                for candidate_id in nodes_to_check:
                    if candidate_id in nodes_to_delete:
                        continue  # Already marked for deletion

                    try:
                        candidate_node = await Node.get(candidate_id)
                        if not candidate_node:
                            continue

                        # Get all edges of the candidate node
                        candidate_edges = []
                        for edge_id in candidate_node.edge_ids:  # type: ignore[attr-defined]
                            try:
                                edge = await Edge.get(edge_id)
                                if edge:
                                    candidate_edges.append(edge)
                            except Exception:
                                continue

                        # If the node has no edges, it's orphaned and should be deleted
                        if not candidate_edges:
                            nodes_to_delete.add(candidate_id)
                            changed = True
                            continue

                        # Check if ALL edges connect to nodes in the deletion set
                        # OR to nodes that are themselves only reachable from the deletion set
                        # We use a recursive check: if all neighbors are in deletion set or will be deleted, delete this node
                        async def is_node_only_connected_to_deletion_set(
                            node_id: str,
                            deletion_set: set,
                            visited: set,
                            root_node_id: str,
                        ) -> bool:
                            """Check if a node is only connected to nodes in deletion set or nodes that will be deleted.

                            Args:
                                node_id: Node to check
                                deletion_set: Set of node IDs marked for deletion
                                visited: Set of visited nodes (to prevent cycles)
                                root_node_id: The original node being deleted (to check reachability)
                            """
                            if node_id in deletion_set:
                                return True
                            if node_id in visited:
                                # For cycles, check if we can reach the root node
                                # If we're in a cycle and all nodes in the cycle are candidates, allow deletion
                                return True

                            visited.add(node_id)

                            try:
                                node = await Node.get(node_id)
                                if not node:
                                    return True

                                node_edges = []
                                for edge_id in node.edge_ids:  # type: ignore[attr-defined]
                                    try:
                                        edge = await Edge.get(edge_id)
                                        if edge:
                                            node_edges.append(edge)
                                    except Exception:
                                        continue

                                # If no edges, it's orphaned and should be deleted
                                if not node_edges:
                                    return True

                                # Check all neighbors
                                for edge in node_edges:
                                    other_id = None
                                    if edge.source == node_id:
                                        other_id = edge.target
                                    elif edge.target == node_id:
                                        other_id = edge.source

                                    if other_id:
                                        # If neighbor is in deletion set, it's fine
                                        if other_id in deletion_set:
                                            continue

                                        # Check if the neighbor is reachable FROM the root node
                                        # If not, then this node has an external connection and shouldn't be deleted
                                        if other_id not in reachable_node_ids:
                                            # This node has a connection to a node not reachable from root
                                            # This means it has an external connection, so don't delete it
                                            return False

                                        # If neighbor is reachable from root, recursively check if it should be deleted
                                        # If the neighbor won't be deleted (has external connections), this node shouldn't be deleted either
                                        neighbor_will_be_deleted = await is_node_only_connected_to_deletion_set(
                                            other_id,
                                            deletion_set,
                                            visited.copy(),
                                            root_node_id,
                                        )
                                        if not neighbor_will_be_deleted:
                                            # Neighbor has external connections, so this node shouldn't be deleted
                                            return False

                                return True
                            except Exception:
                                return False

                        # Check if candidate is only connected to deletion set
                        if await is_node_only_connected_to_deletion_set(
                            candidate_id, nodes_to_delete, set(), self.id
                        ):
                            nodes_to_delete.add(candidate_id)
                            changed = True
                    except Exception:
                        # Continue even if check fails
                        continue

            # Remove self from nodes_to_delete (we'll delete it separately at the end)
            nodes_to_delete.discard(self.id)

        # Delete incoming edges to this node
        for edge in incoming_edges:
            try:
                # Remove edge from source node's edge_ids list
                if edge.source != self.id:
                    source_node = await Node.get(edge.source)
                    if source_node and edge.id in source_node.edge_ids:  # type: ignore[attr-defined]
                        source_node.edge_ids.remove(edge.id)  # type: ignore[attr-defined]
                        await source_node.save()

                # Remove edge from this node's edge_ids list
                if edge.id in self.edge_ids:
                    self.edge_ids.remove(edge.id)

                # Delete the edge
                await context.delete(edge, cascade=False)
            except Exception:
                # Continue even if edge deletion fails
                continue

        # Clean up outgoing edges from this node
        # Remove outgoing edges from target nodes' edge_ids and delete the edges
        for edge in outgoing_edges:
            try:
                # Remove edge from target node's edge_ids list
                if edge.target != self.id:
                    target_node = await Node.get(edge.target)
                    if target_node and edge.id in target_node.edge_ids:  # type: ignore[attr-defined]
                        target_node.edge_ids.remove(edge.id)  # type: ignore[attr-defined]
                        await target_node.save()

                # Remove edge from this node's edge_ids list (if not already removed)
                if edge.id in self.edge_ids:
                    self.edge_ids.remove(edge.id)

                # Delete the edge
                await context.delete(edge, cascade=False)
            except Exception:
                # Continue even if edge deletion fails
                continue

        # If cascade is enabled, delete all dependent nodes
        if cascade and nodes_to_delete:
            # Get all nodes to delete
            dependent_nodes = []
            for node_id in nodes_to_delete:
                try:
                    node = await Node.get(node_id)
                    if node:
                        dependent_nodes.append(node)
                except Exception:
                    continue

            # Delete dependent nodes recursively
            # Each node will delete its own incoming edges and any further dependent nodes
            for dependent_node in dependent_nodes:
                try:
                    # Recursively delete with cascade=True to handle nested dependencies
                    await dependent_node.delete(cascade=True)
                except Exception:
                    # Continue even if dependent node deletion fails
                    continue

        # Clear edge_ids before final deletion to avoid recursion in context.delete()
        # All edges have already been deleted from the database
        self.edge_ids = []

        # Finally, delete this node itself (no cascade needed, we've already handled it)
        await context.delete(self, cascade=False)

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

    async def export(
        self: "Node",
        exclude_transient: bool = True,
        exclude: Optional[Union[set, Dict[str, Any]]] = None,
        include_edges: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Export node to a dictionary.

        Returns a nested persistence format with id, entity, context for database storage.
        Includes all fields from the class hierarchy (class and parent classes, not child classes).
        Edges are excluded by default but can be included for database persistence.

        Args:
            exclude_transient: Whether to automatically exclude transient fields (default: True)
            exclude: Additional fields to exclude (can be a set of field names or a dict)
            include_edges: Whether to include edges in export (default: False, set to True for database persistence)
            **kwargs: Additional arguments passed to base export/model_dump()

        Returns:
            Nested format dictionary with id, entity, context (and optionally edges) for database storage
        """
        # Nested persistence format - structure for database storage
        # Exclude _visitor_ref from context (id, edge_ids, and type_code are transient and auto-excluded)
        # Object.export() returns nested format, extract the context
        parent_export = await super().export(
            exclude={"_visitor_ref"},
            exclude_none=False,
            exclude_transient=exclude_transient,
            **kwargs,
        )

        # Extract context from nested format (Object.export() returns {id, entity, context})
        context_data = parent_export["context"]

        # Serialize datetime objects to ensure JSON compatibility
        from jvspatial.utils.serialization import serialize_datetime

        context_data = serialize_datetime(context_data)

        result = {
            "id": self.id,
            "entity": self.entity,
            "context": context_data,
        }

        # Include edges only when explicitly requested (e.g., for database persistence)
        if include_edges:
            result["edges"] = self.edge_ids

        return result
