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

from jvspatial.exceptions import GraphError, ValidationError

from ..annotations import private
from ..utils import serialize_datetime
from .edge import Edge
from .object import Object

if TYPE_CHECKING:
    from ..context import GraphContext
    from .walker import Walker


class Node(Object):
    """Graph node with visitor tracking and connection capabilities.

    Attributes:
        id: Unique identifier for the node (protected - inherited from Object)
        visitor: Current walker visiting the node (transient - not persisted)
        is_root: Whether this is the root node
        edge_ids: List of connected edge IDs
    """

    type_code: str = Field(default="n")
    id: str = Field(..., description="Unique identifier for the node")
    _visitor_ref: Optional[weakref.ReferenceType] = private(default=None)
    is_root: bool = False
    edge_ids: List[str] = Field(default_factory=list)
    _visit_hooks: ClassVar[Dict[Optional[Type["Walker"]], List[Callable]]] = {}

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

        Args:
            other: Target node to connect to
            edge: Edge class to use for connection (defaults to base Edge)
            direction: Connection direction ('out', 'in', 'both')
            **kwargs: Additional edge properties

        Returns:
            Created edge instance
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
            direction: Connection direction ('out', 'in', 'both')
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
        return await self._execute_optimized_nodes_query(
            context, direction, node, edge, limit, kwargs
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

    async def _execute_optimized_nodes_query(
        self,
        context: "GraphContext",
        direction: str,
        node_filter: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]],
        edge_filter: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ],
        limit: Optional[int],
        kwargs: Dict[str, Any],
    ) -> List["Node"]:
        """Execute optimized database query for connected nodes with filtering."""
        try:
            # For now, use an optimized approach that works with all database types
            return await self._execute_semantic_filtering(
                context, direction, node_filter, edge_filter, limit, kwargs
            )
        except Exception as e:
            # Log the warning and fallback to basic approach
            print(f"Warning: Optimized query failed ({e}), using basic approach")
            try:
                # Fallback to basic node retrieval
                return await self._execute_basic_nodes_query(context, direction, limit)
            except Exception as fallback_error:
                raise GraphError(
                    "Failed to execute node query with both optimized and basic approaches",
                    details={
                        "original_error": str(e),
                        "fallback_error": str(fallback_error),
                        "direction": direction,
                    },
                )

    async def _execute_semantic_filtering(
        self,
        context: "GraphContext",
        direction: str,
        node_filter: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]],
        edge_filter: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ],
        limit: Optional[int],
        kwargs: Dict[str, Any],
    ) -> List["Node"]:
        """Execute semantic filtering with database-level optimization where possible."""
        # Step 1: Build and execute edge query
        edge_query = self._build_edge_query(direction, edge_filter)
        edges_data = await context.database.find("edge", edge_query)

        if not edges_data:
            return []

        # Step 2: Extract target node IDs and maintain order
        target_ids = []
        edge_order = {}

        for idx, edge_data in enumerate(edges_data):
            # Determine target node ID based on direction
            if edge_data["source"] == self.id:
                target_id = edge_data["target"]
            else:
                target_id = edge_data["source"]

            if target_id not in target_ids:
                target_ids.append(target_id)
                # Preserve edge connection order
                if edge_data["id"] in self.edge_ids:
                    edge_order[target_id] = self.edge_ids.index(edge_data["id"])
                else:
                    edge_order[target_id] = 1000 + idx

        # Apply limit early for efficiency
        if limit:
            target_ids = target_ids[:limit]

        if not target_ids:
            return []

        # Step 3: Build and execute node query with filtering
        node_query = self._build_node_query(target_ids, node_filter, kwargs)
        nodes_data = await context.database.find("node", node_query)

        # Step 4: Deserialize nodes and maintain order
        node_map = {}
        for node_data in nodes_data:
            try:
                node_obj = await context._deserialize_entity(Node, node_data)
                if node_obj is not None:
                    node_map[node_obj.id] = node_obj
            except Exception:
                continue

        # Step 5: Return nodes in connection order
        ordered_nodes = []
        for target_id in sorted(target_ids, key=lambda x: edge_order.get(x, 1000)):
            if target_id in node_map:
                ordered_nodes.append(node_map[target_id])

        return ordered_nodes

    def _build_edge_query(
        self,
        direction: str,
        edge_filter: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ],
    ) -> Dict[str, Any]:
        """Build optimized database query for edges."""
        query: Dict[str, Any] = {}

        # Add direction filtering
        if direction == "out":
            query["source"] = self.id
        elif direction == "in":
            query["target"] = self.id
        else:  # "both"
            query["$or"] = [{"source": self.id}, {"target": self.id}]

        # Add edge type filtering
        edge_types = self._parse_edge_types(edge_filter)
        if edge_types:
            query["name"] = {"$in": edge_types}

        # Add edge property filtering from dicts
        edge_props = self._parse_edge_properties_from_filter(edge_filter)
        if edge_props:
            query.update(edge_props)

        return query

    def _build_node_query(
        self,
        target_ids: List[str],
        node_filter: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]],
        kwargs: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build optimized database query for nodes."""
        query: Dict[str, Any] = {"id": {"$in": target_ids}}

        # Add node type filtering
        node_types = self._parse_node_types(node_filter)
        if node_types:
            query["name"] = {"$in": node_types}

        # Add node property filtering from kwargs (semantic simplicity)
        for key, value in kwargs.items():
            # Add context. prefix for node properties
            if not key.startswith("context.") and not key.startswith(
                ("id", "name", "edges")
            ):
                query[f"context.{key}"] = value
            else:
                query[key] = value

        # Add node property filtering from dicts
        node_props = self._parse_node_properties_from_filter(node_filter)
        if node_props:
            query.update(node_props)

        return query

    def _parse_edge_types(
        self,
        edge_filter: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ],
    ) -> List[str]:
        """Extract edge type names from various filter formats."""
        if not edge_filter:
            return []

        edge_types = []
        if isinstance(edge_filter, str):
            edge_types.append(edge_filter)
        elif inspect.isclass(edge_filter):
            edge_types.append(edge_filter.__name__)
        elif isinstance(edge_filter, list):
            for item in edge_filter:
                if isinstance(item, str):
                    edge_types.append(item)
                elif inspect.isclass(item):
                    edge_types.append(item.__name__)
                elif isinstance(item, dict):
                    edge_types.extend(item.keys())

        return edge_types

    def _parse_edge_properties_from_filter(
        self,
        edge_filter: Optional[
            Union[
                str,
                Type["Edge"],
                List[Union[str, Type["Edge"], Dict[str, Dict[str, Any]]]],
            ]
        ],
    ) -> Dict[str, Any]:
        """Extract edge property filters from dict-based edge filters."""
        props = {}

        if isinstance(edge_filter, list):
            for item in edge_filter:
                if isinstance(item, dict):
                    for _edge_type, conditions in item.items():
                        if isinstance(conditions, dict):
                            props.update(conditions)

        return props

    def _parse_node_types(
        self,
        node_filter: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]],
    ) -> List[str]:
        """Extract node type names from various filter formats."""
        if not node_filter:
            return []

        node_types = []
        if isinstance(node_filter, str):
            node_types.append(node_filter)
        elif isinstance(node_filter, list):
            for item in node_filter:
                if isinstance(item, str):
                    node_types.append(item)
                elif isinstance(item, dict):
                    node_types.extend(item.keys())

        return node_types

    def _parse_node_properties_from_filter(
        self,
        node_filter: Optional[Union[str, List[Union[str, Dict[str, Dict[str, Any]]]]]],
    ) -> Dict[str, Any]:
        """Extract node property filters from dict-based node filters."""
        props = {}

        if isinstance(node_filter, list):
            for item in node_filter:
                if isinstance(item, dict):
                    for _node_type, conditions in item.items():
                        if isinstance(conditions, dict):
                            props.update(conditions)

        return props

    async def _execute_basic_nodes_query(
        self, context: "GraphContext", direction: str, limit: Optional[int]
    ) -> List["Node"]:
        """Execute basic fallback approach for node retrieval.

        CRITICAL: This method ONLY uses edges that are explicitly connected
        to the current node (stored in self.edge_ids).
        """
        if not self.edge_ids:
            return []  # No connected edges, no connected nodes

        # Get ONLY edges that are connected to this node
        edge_query = {"id": {"$in": self.edge_ids}}
        edges_data = await context.database.find("edge", edge_query)

        # Convert to edge objects and filter by direction
        target_ids = []
        for edge_data in edges_data:
            edge_source = edge_data["source"]
            edge_target = edge_data["target"]

            # Skip if edge is not actually connected to this node (safety check)
            if edge_source != self.id and edge_target != self.id:
                continue

            # Apply direction filtering and get target node ID
            target_id = None
            if direction == "out" and edge_source == self.id:
                target_id = edge_target
            elif direction == "in" and edge_target == self.id:
                target_id = edge_source
            elif direction == "both":
                if edge_source == self.id:
                    target_id = edge_target
                elif edge_target == self.id:
                    target_id = edge_source

            if target_id and target_id not in target_ids:
                target_ids.append(target_id)

        # Apply limit
        if limit:
            target_ids = target_ids[:limit]

        if not target_ids:
            return []

        # Get target nodes
        nodes_data = await context.database.find("node", {"id": {"$in": target_ids}})
        nodes = []
        for data in nodes_data:
            try:
                node_obj = await context._deserialize_entity(Node, data)
                if node_obj is not None:
                    nodes.append(node_obj)
            except Exception:
                continue

        return nodes

    # Convenient semantic methods for better API
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
        self: "Node", exclude_transient: bool = True, **kwargs: Any
    ) -> Dict[str, Any]:
        """Export node to a dictionary for persistence.

        Args:
            exclude_transient: Whether to exclude @transient fields (default: True)
            **kwargs: Additional arguments passed to base export

        Returns:
            Dictionary representation of the node
        """
        context_data = self.model_dump(
            exclude={"id", "_visitor_ref", "is_root", "edge_ids"}, exclude_none=False
        )

        # Include _data if it exists
        if hasattr(self, "_data"):
            context_data["_data"] = self._data

        # Serialize datetime objects to ensure JSON compatibility
        context_data = serialize_datetime(context_data)

        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context_data,
            "edges": self.edge_ids,
        }
