"""Entity and Decorator classes."""

import asyncio
import inspect
import uuid

# math import removed - no longer needed after spatial function extraction
import weakref
from collections import deque
from contextlib import contextmanager, suppress
from functools import wraps
from typing import (
    Any,
    Callable,
    ClassVar,
    Dict,
    Generator,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from typing_extensions import override

from jvspatial.core.context import GraphContext

# ----------------- HELPER FUNCTIONS -----------------


def generate_id(type_: str, class_name: str) -> str:
    """Generate an ID string for graph objects.

    Args:
        type_: Object type ('n' for node, 'e' for edge, 'w' for walker, 'o' for object)
        class_name: Name of the class (e.g., 'City', 'Highway')

    Returns:
        Unique ID string in the format "type:class_name:hex_id"
    """
    hex_id = uuid.uuid4().hex[:24]
    return f"{type_}:{class_name}:{hex_id}"


def find_subclass_by_name(base_class: Type, name: str) -> Optional[Type]:
    """Find a subclass by name recursively.

    Returns the base class if it matches the name, otherwise returns
    the first matching subclass found.
    """
    if base_class.__name__ == name:
        return base_class

    def find_subclass(cls: Type) -> Optional[Type]:
        for subclass in cls.__subclasses__():
            if subclass.__name__ == name:
                return subclass
            found = find_subclass(subclass)
            if found:
                return found
        return None

    return find_subclass(base_class)


# ----------------- CORE CLASSES -----------------


class Object(BaseModel):
    """Base object with persistence capabilities.

    Attributes:
        id: Unique identifier for the object
        type_code: Type identifier for database partitioning
        _graph_context: GraphContext instance for database operations
    """

    id: str = Field(default="")
    type_code: ClassVar[str] = "o"
    _initializing: bool = PrivateAttr(default=True)
    _data: dict = PrivateAttr(default_factory=dict)
    _graph_context: Optional["GraphContext"] = PrivateAttr(default=None)

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    def set_context(self: "Object", context: "GraphContext") -> None:
        """Set the GraphContext for this object.

        Args:
            context: GraphContext instance to use for database operations
        """
        self._graph_context = context

    def get_context(self: "Object") -> "GraphContext":
        """Get the GraphContext, using default if not set.

        Returns:
            GraphContext instance
        """
        if self._graph_context is None:
            from .context import get_default_context

            self._graph_context = get_default_context()
        return self._graph_context

    def __init__(self: "Object", **kwargs: Any) -> None:
        """Initialize an Object with auto-generated ID if not provided."""
        self._initializing = True
        if "id" not in kwargs:
            kwargs["id"] = generate_id(self.type_code, self.__class__.__name__)
        super().__init__(**kwargs)
        self._initializing = False

    def __setattr__(self: "Object", name: str, value: Any) -> None:
        """Set attribute without automatic save operations."""
        super().__setattr__(name, value)

    @classmethod
    async def create(cls: Type["Object"], **kwargs: Any) -> "Object":
        """Create and save a new object instance.

        Args:
            **kwargs: Object attributes

        Returns:
            Created and saved object instance
        """
        obj = cls(**kwargs)
        await obj.save()
        return obj

    def export(self: "Object") -> dict:
        """Export the object to a dictionary for persistence.

        Returns:
            Dictionary representation of the object
        """
        context = self.model_dump(
            exclude={"id", "db", "_initializing"}, exclude_none=False
        )

        # Include _data if it exists
        if hasattr(self, "_data"):
            context["_data"] = self._data

        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context,
        }

    def get_collection_name(
        self: "Object", cls: Optional[Type["Object"]] = None
    ) -> str:
        """Get the database collection name for this object type.

        Args:
            cls: Optional class to use for type code lookup (defaults to self's class)

        Returns:
            Collection name
        """
        collection_map = {"n": "node", "e": "edge", "o": "object", "w": "walker"}
        type_code = cls.type_code if cls is not None else self.type_code
        return collection_map.get(type_code, "object")

    async def save(self: "Object") -> "Object":
        """Persist the object to the database.

        Returns:
            The saved object instance
        """
        context = self.get_context()
        await context.save(self)
        return self

    async def delete(self: "Object", cascade: bool = True) -> None:
        """Delete the object from the database.

        Args:
            cascade: Whether to delete related objects (applies to Node entities)
        """
        context = self.get_context()
        await context.delete(self, cascade=cascade)

    @property
    def data(self: "Object") -> dict:
        """Simple property access to object data.

        Usage:
            obj.data['key'] = value
            value = obj.data.get('key', default)
        """
        return self._data

    @classmethod
    async def get(cls: Type["Object"], id: str) -> Optional["Object"]:
        """Retrieve an object from the database by ID.

        Args:
            id: ID of the object to retrieve

        Returns:
            Object instance if found, else None
        """
        from .context import get_default_context

        context = get_default_context()
        return await context.get(cls, id)

    @classmethod
    async def find(
        cls: Type["Object"],
        query: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List["Object"]:
        """Find objects using MongoDB-style database queries.

        Args:
            query: MongoDB-style query parameters (optional)
            limit: Maximum number of results

        Returns:
            List of matching objects

        Examples:
            # Find by field equality
            objects = await MyClass.find({"context.name": "John"})

            # Find with comparison operators
            objects = await MyClass.find({"context.age": {"$gte": 18}})

            # Find with logical operators
            objects = await MyClass.find({"$and": [
                {"context.category": "person"},
                {"context.active": True}
            ]})
        """
        from .context import get_default_context

        context = get_default_context()
        collection = context._get_collection_name(cls.type_code)

        # Add class name filter to query for type safety
        db_query = {"name": cls.__name__}
        if query:
            db_query.update(query)

        results = await context.database.find(collection, db_query)

        if limit:
            results = results[:limit]

        objects = []
        for data in results:
            try:
                obj = await context._deserialize_entity(cls, data)
                if obj:
                    objects.append(obj)
            except Exception:
                continue  # Skip invalid objects

        return objects

    @classmethod
    async def find_by(cls: Type["Object"], **kwargs: Any) -> List["Object"]:
        """Find objects by property values using MongoDB-style queries.

        This is a convenience method that automatically prefixes fields with 'context.'
        since object properties are stored in the context field.

        Args:
            **kwargs: Property values to match

        Returns:
            List of matching objects

        Examples:
            # Find by name
            objects = await MyClass.find_by(name="John")

            # Find by multiple properties
            objects = await MyClass.find_by(category="person", active=True)

            # For complex queries, use find() instead:
            # objects = await MyClass.find({"context.age": {"$gte": 18}})
        """
        # Convert kwargs to context-based query
        query = {f"context.{k}": v for k, v in kwargs.items()}
        return await cls.find(query)

    @classmethod
    async def find_one(
        cls: Type["Object"], query: Optional[Dict[str, Any]] = None
    ) -> Optional["Object"]:
        """Find the first object matching a MongoDB-style query.

        Args:
            query: MongoDB-style query parameters (optional)

        Returns:
            First matching object or None

        Examples:
            # Find first object by name
            obj = await MyClass.find_one({"context.name": "John"})

            # Find first active object
            obj = await MyClass.find_one({"context.active": True})
        """
        objects = await cls.find(query, limit=1)
        return objects[0] if objects else None

    @classmethod
    async def count(cls: Type["Object"], query: Optional[Dict[str, Any]] = None) -> int:
        """Count objects matching a MongoDB-style query.

        Args:
            query: MongoDB-style query parameters (optional)

        Returns:
            Number of matching objects

        Examples:
            # Count all objects of this type
            count = await MyClass.count()

            # Count with filter
            count = await MyClass.count({"context.active": True})

            # Count with complex query
            count = await MyClass.count({"$and": [
                {"context.category": "person"},
                {"context.age": {"$gte": 18}}
            ]})
        """
        from .context import get_default_context

        context = get_default_context()
        collection = context._get_collection_name(cls.type_code)

        # Add class name filter to query
        db_query = {"name": cls.__name__}
        if query:
            db_query.update(query)

        return await context.database.count(collection, db_query)

    @classmethod
    async def distinct(
        cls: Type["Object"], field: str, query: Optional[Dict[str, Any]] = None
    ) -> List[Any]:
        """Get distinct values for a field from objects matching a query.

        Args:
            field: Field name (will be prefixed with 'context.' if needed)
            query: Optional MongoDB-style query to filter objects

        Returns:
            List of distinct values

        Examples:
            # Get all distinct categories
            categories = await MyClass.distinct("category")

            # Get distinct values with filter
            names = await MyClass.distinct("name", {"context.active": True})
        """
        from .context import get_default_context

        context = get_default_context()
        collection = context._get_collection_name(cls.type_code)

        # Add class name filter to query
        db_query = {"name": cls.__name__}
        if query:
            db_query.update(query)

        # Ensure field is properly prefixed if it's an object property
        if not field.startswith("context.") and not field.startswith(
            ("id", "name", "edges")
        ):
            field = f"context.{field}"

        return await context.database.distinct(collection, field, db_query)

    @classmethod
    async def all(cls: Type["Object"]) -> List["Object"]:
        """Retrieve all objects of this type from the database.

        Returns:
            List of object instances
        """
        return await cls.find()

    async def destroy(self: "Object", cascade: bool = True) -> None:
        """Delete the object and optionally related objects.

        Args:
            cascade: Whether to delete related objects (default: True)
        """
        context = self.get_context()
        await context.delete(self, cascade=cascade)


class Edge(Object):
    """Graph edge connecting two nodes.

    Attributes:
        source: Source node ID
        target: Target node ID
        direction: Edge direction ('in', 'out', 'both')
    """

    type_code: ClassVar[str] = "e"
    id: str = Field(default="")
    source: str
    target: str
    direction: str = "both"

    def __init_subclass__(cls: Type["Edge"]) -> None:
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
                            raise TypeError(
                                f"Edge @on_visit must target Walker types, got {target.__name__ if hasattr(target, '__name__') else target}"
                            )
                        if target not in cls._visit_hooks:
                            cls._visit_hooks[target] = []
                        cls._visit_hooks[target].append(method)

    def __init__(
        self: "Edge",
        left: Optional["Node"] = None,
        right: Optional["Node"] = None,
        direction: str = "both",
        **kwargs: Any,
    ) -> None:
        """Initialize an Edge with source and target nodes."""
        self._initializing = True

        source: str = ""
        target: str = ""

        if left and right:
            if direction == "out":
                source = left.id
                target = right.id
            elif direction == "in":
                source = right.id
                target = left.id
            else:
                source = left.id
                target = right.id

        if "source" in kwargs:
            source = kwargs.pop("source")
        if "target" in kwargs:
            target = kwargs.pop("target")

        # Don't override ID if already provided
        if "id" not in kwargs:
            kwargs["id"] = generate_id("e", self.__class__.__name__)

        kwargs.update({"source": source, "target": target, "direction": direction})

        super().__init__(**kwargs)
        self._initializing = False

    def export(self: "Edge") -> dict:
        """Export edge to a dictionary for persistence.

        Returns:
            Dictionary representation of the edge
        """
        context = self.model_dump(
            exclude={"id", "source", "target", "direction"}, exclude_none=False
        )

        # Include _data if it exists
        if hasattr(self, "_data"):
            context["_data"] = self._data

        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context,
            "source": self.source,
            "target": self.target,
            "direction": self.direction,
            "bidirectional": self.direction == "both",  # For backward compatibility
        }

    @classmethod
    async def get(cls: Type["Edge"], id: str) -> Optional["Edge"]:
        """Retrieve an edge from the database by ID.

        Args:
            id: ID of the edge to retrieve

        Returns:
            Edge instance if found, else None
        """
        from .context import get_default_context

        context = get_default_context()
        return await context.get(cls, id)

    @classmethod
    async def create(cls: Type["Edge"], **kwargs: Any) -> "Edge":
        """Create and save a new edge instance, updating connected nodes.

        Args:
            **kwargs: Edge attributes including 'left' and 'right' nodes

        Returns:
            Created and saved edge instance
        """
        edge = cls(**kwargs)
        await edge.save()

        # Update connected nodes' edge_ids
        source_node = await Node.get(edge.source) if edge.source else None
        target_node = await Node.get(edge.target) if edge.target else None

        if source_node and edge.id not in source_node.edge_ids:
            source_node.edge_ids.append(edge.id)
            await source_node.save()

        if target_node and edge.id not in target_node.edge_ids:
            target_node.edge_ids.append(edge.id)
            await target_node.save()

        return edge

    async def save(self: "Edge") -> "Edge":
        """Persist the edge to the database.

        Returns:
            The saved edge instance
        """
        return await super().save()

    @classmethod
    async def all(cls: Type["Edge"]) -> List["Edge"]:
        """Retrieve all edges from the database.

        Returns:
            List of edge instances
        """
        from .context import get_default_context

        context = get_default_context()
        # Create temporary instance to get collection name
        temp_instance = cls.__new__(cls)
        # Initialize the instance with the type_code directly
        temp_instance.__dict__["type_code"] = cls.type_code
        collection = temp_instance.get_collection_name()
        edges_data = await context.database.find(collection, {})
        edges = []
        for data in edges_data:
            # Handle both new and legacy data formats
            if "source" in data and "target" in data:
                source = data["source"]
                target = data["target"]
                direction = data.get("direction", "both")
            else:
                source = data["context"].get("source", "")
                target = data["context"].get("target", "")
                direction = data["context"].get("direction", "both")

            # Handle subclass instantiation based on stored name
            stored_name = data.get("name", cls.__name__)
            target_class = find_subclass_by_name(cls, stored_name) or cls

            context_data = {
                k: v
                for k, v in data["context"].items()
                if k not in ["source", "target", "direction"]
            }

            # Extract _data if present
            stored_data = context_data.pop("_data", {})

            edge = target_class(
                id=data["id"],
                source=source,
                target=target,
                direction=direction,
                **context_data,
            )

            # Restore _data after object creation
            if stored_data:
                edge._data.update(stored_data)

            edges.append(edge)
        return edges


class Node(Object):
    """Graph node with visitor tracking and connection capabilities.

    Attributes:
        visitor: Current walker visiting the node
        is_root: Whether this is the root node
        edge_ids: List of connected edge IDs
    """

    type_code: ClassVar[str] = "n"
    id: str = Field(default="")
    _visitor_ref: Optional[weakref.ReferenceType] = None
    is_root: bool = False
    edge_ids: List[str] = Field(default_factory=list)
    _visit_hooks: ClassVar[dict] = {}

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
                            raise TypeError(
                                f"Node @on_visit must target Walker types, got {target.__name__ if hasattr(target, '__name__') else target}"
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

    @visitor.setter
    def visitor(self: "Node", value: "Walker") -> None:
        """Set the current visitor of this node.

        Args:
            value: Walker instance to set as visitor
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
            left=self, right=other, direction=direction, **kwargs
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
            next_nodes = await node.nodes()

            # Simple type filtering
            cities = await node.nodes(node='City')

            # Simple property filtering (kwargs apply to connected nodes)
            ny_nodes = await node.nodes(state="NY")
            ca_cities = await node.nodes(node=['City'], state="CA")

            # Complex filtering with MongoDB operators
            large_cities = await node.nodes(
                node=[{'City': {"context.population": {"$gte": 500000}}}]
            )

            # Edge and node filtering combined
            premium_routes = await node.nodes(
                direction="out",
                node=[{'City': {"context.population": {"$gte": 100000}}}],
                edge=[{'Highway': {"context.condition": {"$ne": "poor"}}}]
            )

            # Mixed approaches (semantic flexibility)
            optimal_connections = await node.nodes(
                node='City',
                edge=[{'Highway': {"context.speed_limit": {"$gte": 60}}}],
                state="NY"  # Simple property filter via kwargs
            )
        """
        context = self.get_context()

        # Build optimized database query using aggregation pipeline
        return await self._execute_optimized_nodes_query(
            context, direction, node, edge, limit, kwargs
        )

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
            print(f"Warning: Optimized query failed ({e}), using basic approach")
            # Fallback to basic node retrieval
            return await self._execute_basic_nodes_query(context, direction, limit)

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
                if node_obj:
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

        types = []
        if isinstance(edge_filter, str):
            types.append(edge_filter)
        elif inspect.isclass(edge_filter):
            types.append(edge_filter.__name__)
        elif isinstance(edge_filter, list):
            for item in edge_filter:
                if isinstance(item, str):
                    types.append(item)
                elif inspect.isclass(item):
                    types.append(item.__name__)
                elif isinstance(item, dict):
                    types.extend(item.keys())

        return types

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

        types = []
        if isinstance(node_filter, str):
            types.append(node_filter)
        elif isinstance(node_filter, list):
            for item in node_filter:
                if isinstance(item, str):
                    types.append(item)
                elif isinstance(item, dict):
                    types.extend(item.keys())

        return types

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
                if node_obj:
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
            context = self.get_context()
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
            context = self.get_context()
            edges = await context.find_edges_between(self.id, other.id, edge_type)
            return len(edges) > 0
        except Exception:
            return False

    @property
    def connection_count(self) -> int:
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
        node = await cls.create(**kwargs)
        await node.connect(other, edge or Edge)
        return node

    # Spatial query methods removed - too specific for generic entities

    def export(self: "Node") -> dict:
        """Export node to a dictionary for persistence.

        Returns:
            Dictionary representation of the node
        """
        context_data = self.model_dump(
            exclude={"id", "_visitor_ref", "is_root", "edge_ids"}, exclude_none=False
        )

        # Include _data if it exists
        if hasattr(self, "_data"):
            context_data["_data"] = self._data

        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context_data,
            "edges": self.edge_ids,
        }


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


class Root(Node):
    """Singleton root node for the graph.

    Attributes:
        id: Fixed ID for the root node
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
            from .context import get_default_context

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


class Walker(BaseModel):
    """Base class for graph walkers that traverse nodes along edges.

    Walkers are designed to traverse the graph by visiting nodes and following edges.
    They maintain a queue of nodes to visit and can carry state and responses during traversal.

    Attributes:
        id: Unique walker ID
        queue: Queue of nodes to visit
        response: Response data from traversal
        current_node: Currently visited node
        paused: Whether traversal is paused
        visited: Set of visited node IDs to avoid cycles
    """

    model_config = ConfigDict(extra="allow")
    type_code: ClassVar[str] = "w"
    id: str = Field(default="")
    queue: deque = Field(default_factory=deque)
    response: dict = Field(default_factory=dict)
    current_node: Optional[Node] = None
    _visit_hooks: ClassVar[dict] = {}
    paused: bool = Field(default=False, exclude=True)

    def __init__(self: "Walker", **kwargs: Any) -> None:
        """Initialize a walker with auto-generated ID if not provided."""
        if "id" not in kwargs:
            kwargs["id"] = generate_id(self.type_code, self.__class__.__name__)
        super().__init__(**kwargs)

    def __init_subclass__(cls: Type["Walker"]) -> None:
        """Handle subclass initialization."""
        cls._visit_hooks = {}

        for _name, method in inspect.getmembers(cls, inspect.isfunction):
            if hasattr(method, "_is_visit_hook"):
                targets = getattr(method, "_visit_targets", None)

                if targets is None:
                    # No targets specified - register for any Node/Edge
                    if None not in cls._visit_hooks:
                        cls._visit_hooks[None] = []
                    cls._visit_hooks[None].append(method)
                else:
                    # Register for each specified target type
                    for target in targets:
                        if not (
                            inspect.isclass(target) and issubclass(target, (Node, Edge))
                        ):
                            raise TypeError(
                                f"Walker @on_visit must target Node/Edge types, got {target.__name__ if hasattr(target, '__name__') else target}"
                            )
                        if target not in cls._visit_hooks:
                            cls._visit_hooks[target] = []
                        cls._visit_hooks[target].append(method)

    @property
    def here(self: "Walker") -> Optional[Node]:
        """Get the current node being visited.

        Returns:
            Current node if present, else None
        """
        return self.current_node

    @property
    def visitor(self: "Walker") -> Optional["Walker"]:
        """Get the walker instance itself (as visitor).

        Returns:
            The walker instance
        """
        return self

    async def visit(self: "Walker", nodes: Union[Node, List[Node]]) -> list:
        """Add nodes to the traversal queue for later processing.

        Args:
            nodes: Node or list of nodes to visit

        Returns:
            List of nodes added to the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]
        self.queue.extend(nodes_list)
        return nodes_list

    def dequeue(self: "Walker", nodes: Union[Node, List[Node]]) -> List[Node]:
        """Remove specified node(s) from the walker's queue.

        Args:
            nodes: Node or list of nodes to remove from queue

        Returns:
            List of nodes that were successfully removed from the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]
        removed_nodes = []

        # Convert deque to list for easier manipulation
        queue_list = list(self.queue)

        for node in nodes_list:
            # Remove all occurrences of the node from the queue
            while node in queue_list:
                queue_list.remove(node)
                removed_nodes.append(node)

        # Rebuild the queue with remaining nodes
        self.queue = deque(queue_list)
        return removed_nodes

    def prepend(self: "Walker", nodes: Union[Node, List[Node]]) -> List[Node]:
        """Add node(s) to the head of the queue.

        Args:
            nodes: Node or list of nodes to add to the beginning of the queue

        Returns:
            List of nodes added to the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]

        # Add nodes in reverse order to maintain their relative order
        for node in reversed(nodes_list):
            self.queue.appendleft(node)

        return nodes_list

    def append(self: "Walker", nodes: Union[Node, List[Node]]) -> List[Node]:
        """Add node(s) to the end of the queue.

        Args:
            nodes: Node or list of nodes to add to the end of the queue

        Returns:
            List of nodes added to the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]
        self.queue.extend(nodes_list)
        return nodes_list

    def add_next(self: "Walker", nodes: Union[Node, List[Node]]) -> List[Node]:
        """Add node(s) next in the queue after the currently visited item.

        If no node is currently being visited, adds to the beginning of the queue.

        Args:
            nodes: Node or list of nodes to add next in queue

        Returns:
            List of nodes added to the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]

        # If queue is empty or no current traversal, add to front
        if not self.queue:
            self.queue.extend(nodes_list)
        else:
            # Add nodes to the front of the queue (next to be processed)
            for node in reversed(nodes_list):
                self.queue.appendleft(node)

        return nodes_list

    def get_queue(self: "Walker") -> List[Node]:
        """Return the entire queue as a list.

        Returns:
            List of all nodes currently in the queue
        """
        return list(self.queue)

    def clear_queue(self: "Walker") -> None:
        """Clear the queue of all nodes."""
        self.queue.clear()

    def insert_after(
        self: "Walker", target_node: Node, nodes: Union[Node, List[Node]]
    ) -> List[Node]:
        """Insert node(s) after the specified target node in the queue.

        Args:
            target_node: Node after which to insert the new nodes
            nodes: Node or list of nodes to insert

        Returns:
            List of nodes that were successfully inserted

        Raises:
            ValueError: If target_node is not found in the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]

        # Convert deque to list for easier manipulation
        queue_list = list(self.queue)

        try:
            # Find the index of the target node
            target_index = queue_list.index(target_node)

            # Insert nodes after the target node
            for i, node in enumerate(nodes_list):
                queue_list.insert(target_index + 1 + i, node)

            # Rebuild the queue
            self.queue = deque(queue_list)
            return nodes_list

        except ValueError:
            raise ValueError(f"Target node {target_node} not found in queue")

    def insert_before(
        self: "Walker", target_node: Node, nodes: Union[Node, List[Node]]
    ) -> List[Node]:
        """Insert node(s) before the specified target node in the queue.

        Args:
            target_node: Node before which to insert the new nodes
            nodes: Node or list of nodes to insert

        Returns:
            List of nodes that were successfully inserted

        Raises:
            ValueError: If target_node is not found in the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]

        # Convert deque to list for easier manipulation
        queue_list = list(self.queue)

        try:
            # Find the index of the target node
            target_index = queue_list.index(target_node)

            # Insert nodes before the target node
            for i, node in enumerate(nodes_list):
                queue_list.insert(target_index + i, node)

            # Rebuild the queue
            self.queue = deque(queue_list)
            return nodes_list

        except ValueError:
            raise ValueError(f"Target node {target_node} not found in queue")

    def is_queued(self: "Walker", node: Node) -> bool:
        """Check if the specified node is in the walker's queue.

        Args:
            node: Node to check for in the queue

        Returns:
            True if the node is in the queue, False otherwise
        """
        return node in self.queue

    def skip(self: "Walker") -> None:
        """Skip processing of the current node and proceed to the next node in the queue.

        This function works similar to 'continue' in typical loops. When called during
        node traversal (within a visit hook), it immediately halts execution of the
        current node's hooks and proceeds to the next node in the queue.

        Can only be called from within visit hooks during active traversal.

        Raises:
            TraversalSkipped: Internal exception used to control traversal flow

        Example:
            @on_visit(Node)
            async def process_node(self, here):
                if here.should_be_skipped:
                    self.skip()  # Skip to next node
                    return  # This line won't be reached

                # Process the node normally
                await self.do_heavy_processing(here)
        """
        raise TraversalSkipped()

    @contextmanager
    def visiting(
        self: "Walker", item: Union["Node", Tuple[str, "Edge"]]
    ) -> Generator[None, None, None]:
        """Context manager for visiting a node or edge.

        Args:
            item: Node, Edge, or tuple ('edge', Edge) to visit
        """
        if isinstance(item, tuple) and item[0] == "edge":
            # Visiting an edge
            edge = item[1]
            self.current_node = edge  # type: ignore[assignment]
            try:
                yield
            finally:
                self.current_node = None
        else:
            # Visiting a node (existing logic)
            if isinstance(item, Node):
                node = item
                self.current_node = node
                node.visitor = self
                try:
                    yield
                finally:
                    node.visitor = None
                    self.current_node = None
            else:
                # This shouldn't happen but handle gracefully
                self.current_node = None  # type: ignore[assignment]
                try:
                    yield
                finally:
                    self.current_node = None

    async def spawn(self: "Walker", start: Optional[Node] = None) -> "Walker":
        """Start traversing the graph from a given node.

        Args:
            start: Starting node (defaults to root node)

        Returns:
            The walker instance after traversal
        """
        from collections import deque

        root = start or await Root.get()  # type: ignore[call-arg]
        # Preserve any existing queue items (like edges) and add the root at the beginning
        existing_items = (
            list(self.queue) if hasattr(self, "queue") and self.queue else []
        )
        # Remove root from existing items to avoid duplicates
        filtered_existing = [item for item in existing_items if item != root]
        self.queue = deque([root] + filtered_existing)
        self.paused = False
        try:
            previous_node = None
            while self.queue and not self.paused:
                current = self.queue.popleft()

                # If we have a previous node and current node, traverse edges between them
                if (
                    previous_node
                    and isinstance(current, Node)
                    and not isinstance(current, tuple)
                ):
                    await self._traverse_edge_between_nodes(previous_node, current)

                with self.visiting(current):
                    try:
                        await self._process_hooks(current)
                    except TraversalSkipped:
                        # Skip was called - continue to next item in queue
                        continue

                # Update previous_node for next iteration (only for actual nodes, not edges)
                if isinstance(current, Node) and not isinstance(current, tuple):
                    previous_node = current

            if not self.paused:
                await self._process_exit_hooks()
        except TraversalPaused:
            self.paused = True
        except Exception as e:
            print(f"Walker error: {str(e)}")
            self.response = {"status": 500, "messages": [f"Traversal error: {str(e)}"]}
            with suppress(Exception):
                await self._process_exit_hooks()
        return self

    async def resume(self: "Walker") -> "Walker":
        """Resume a paused traversal.

        Returns:
            The walker instance
        """
        if not self.paused:
            return self
        self.paused = False
        try:
            previous_node = getattr(self, "_last_node", None)
            while self.queue and not self.paused:
                current = self.queue.popleft()

                # If we have a previous node and current node, traverse edges between them
                if (
                    previous_node
                    and isinstance(current, Node)
                    and not isinstance(current, tuple)
                ):
                    await self._traverse_edge_between_nodes(previous_node, current)

                with self.visiting(current):
                    try:
                        await self._process_hooks(current)
                    except TraversalSkipped:
                        # Skip was called - continue to next item in queue
                        continue

                # Update previous_node for next iteration (only for actual nodes, not edges)
                if isinstance(current, Node) and not isinstance(current, tuple):
                    previous_node = current
                    self._last_node = current

            if not self.paused:
                await self._process_exit_hooks()
        except TraversalPaused:
            pass
        except Exception as e:
            self.response = {"status": 500, "messages": [f"Traversal error: {str(e)}"]}
            with suppress(Exception):
                await self._process_exit_hooks()
        return self

    def pause(self: "Walker", reason: str = "Walker paused") -> None:
        """Pause the walker, preserving its state for later resumption.

        This method raises a TraversalPaused exception to immediately interrupt
        the current traversal. The walker's queue and state are preserved and
        can be resumed later with resume().

        Args:
            reason: Optional reason for pausing (for logging/debugging)

        Raises:
            TraversalPaused: Always raised to interrupt current traversal
        """
        raise TraversalPaused(reason)

    async def disengage(self: "Walker") -> "Walker":
        """Halt the walk and return the walker in its current state.

        This method removes the walker from its current node (if any),
        clears the current node reference, and sets the paused flag to True.

        Returns:
            The walker instance in its disengaged state
        """
        # Remove walker from current node if present
        if self.current_node:
            self.current_node.visitor = None
            self.current_node = None

        # Pause the walker
        self.paused = True
        return self

    async def _process_hooks(
        self: "Walker", item: Union["Node", "Edge", Tuple[str, "Edge"]]
    ) -> None:
        """Process all visit hooks for a node or edge.

        Args:
            item: Node, Edge, or tuple ('edge', Edge) to process hooks for
        """
        with suppress(TraversalSkipped):
            if isinstance(item, tuple) and item[0] == "edge":
                # Process edge hooks
                edge = item[1]
                self.current_node = edge  # Set current context to the edge
                hooks = await self._get_hooks_for_edge(edge)
                for hook in hooks:
                    await self._execute_hook(hook)
            else:
                # Process node hooks only - no automatic edge discovery
                node = item  # type: ignore[assignment]
                if not isinstance(node, Node):
                    return

                # Mark node as visited to prevent cycles
                if not hasattr(self, "_visited_nodes"):
                    self._visited_nodes = set()
                self._visited_nodes.add(node.id)

                hooks = await self._get_hooks_for_node(node)
                for hook in hooks:
                    await self._execute_hook(hook)

    async def _get_hooks_for_node(self: "Walker", node: Node) -> List[Callable]:
        """Get all applicable visit hooks for a node.

        Args:
            node: Node to get hooks for

        Returns:
            List of hook functions
        """
        hooks = []
        node_type = type(node)
        walker_type = type(self)

        # 1. Walker hooks for specific node types or catch-all
        for target_type, hook_list in self._visit_hooks.items():
            if (target_type is None) or (
                target_type == node_type or issubclass(node_type, target_type)
            ):
                hooks.extend(hook_list if isinstance(hook_list, list) else [hook_list])

        # 2. Node hooks for specific walker types or catch-all
        if hasattr(node, "_visit_hooks"):
            for target_type, hook_list in node._visit_hooks.items():
                if (target_type is None) or (
                    target_type == walker_type or issubclass(walker_type, target_type)
                ):
                    hooks.extend(
                        hook_list if isinstance(hook_list, list) else [hook_list]
                    )

        return hooks

    async def _traverse_edge_between_nodes(
        self: "Walker", from_node: Node, to_node: Node
    ) -> None:
        """Traverse edge between two specific nodes during active walk.

        This method finds and processes the edge connecting two nodes that are
        consecutive in the walker's queue. It ONLY processes edges during active
        traversal between queued nodes, not for discovery.

        Args:
            from_node: Source node we're walking from
            to_node: Target node we're walking to
        """
        try:
            # Get all edges connected to the source node
            edges = await from_node.edges()

            # Find edge(s) that connect from_node to to_node
            connecting_edges = []
            for edge in edges:
                if (edge.source == from_node.id and edge.target == to_node.id) or (
                    edge.target == from_node.id and edge.source == to_node.id
                ):
                    connecting_edges.append(edge)

            # Process hooks for each connecting edge
            for edge in connecting_edges:
                previous_node = self.current_node
                self.current_node = edge

                try:
                    hooks = await self._get_hooks_for_edge(edge)
                    for hook in hooks:
                        await self._execute_hook(hook)

                except TraversalSkipped:
                    # If edge processing is skipped, continue with other edges
                    continue
                finally:
                    # Restore the node context
                    self.current_node = previous_node

        except Exception as e:
            # Don't let edge traversal errors break the main traversal
            print(f"Error during edge traversal between nodes: {e}")

    async def _get_hooks_for_edge(self: "Walker", edge: Edge) -> List[Callable]:
        """Get all applicable visit hooks for an edge.

        Args:
            edge: Edge to get hooks for

        Returns:
            List of hook functions
        """
        hooks = []
        edge_type = type(edge)
        walker_type = type(self)

        # 1. Walker hooks for specific edge types or catch-all
        for target_type, hook_list in self._visit_hooks.items():
            if (target_type is None) or (
                target_type == edge_type
                or inspect.isclass(target_type)
                and issubclass(edge_type, target_type)
            ):
                hooks.extend(hook_list if isinstance(hook_list, list) else [hook_list])

        # 2. Edge hooks for specific walker types or catch-all
        if hasattr(edge, "_visit_hooks"):
            for target_type, hook_list in edge._visit_hooks.items():
                if (target_type is None) or (
                    target_type == walker_type
                    or inspect.isclass(target_type)
                    and issubclass(walker_type, target_type)
                ):
                    hooks.extend(
                        hook_list if isinstance(hook_list, list) else [hook_list]
                    )

        return hooks

    async def _execute_hook(self: "Walker", hook: Callable) -> None:
        """Execute a single visit hook.

        Args:
            hook: Hook function to execute
        """
        from jvspatial.core.context import perf_monitor

        hook_name = f"{hook.__module__}.{hook.__qualname__}"
        start_time = asyncio.get_event_loop().time()
        context = None

        try:
            # Determine if this is a Walker hook or a Node/Edge hook
            context = self.current_node

            # Check if the hook belongs to the current node/edge being visited
            context_owns_hook = False
            if context is not None and hasattr(context, "_visit_hooks"):
                for hook_list in context._visit_hooks.values():
                    if (isinstance(hook_list, list) and hook in hook_list) or (
                        hook == hook_list
                    ):
                        context_owns_hook = True
                        break

            if context_owns_hook:
                # This is a Node/Edge hook - call with (node/edge, walker) pattern
                if inspect.iscoroutinefunction(hook):
                    await hook(context, self)
                else:
                    hook(context, self)
            else:
                # This is a Walker hook - call with (walker, node/edge) pattern
                if inspect.iscoroutinefunction(hook):
                    await hook(self, context)
                else:
                    hook(self, context)
        except TraversalSkipped:
            raise  # Re-raise to skip processing
        except TraversalPaused:
            raise  # Re-raise to pause traversal
        except Exception as e:
            print(f"Error executing hook {hook.__name__}: {e}")
            if not self.response.get("status"):
                self.response["status"] = 500
                if "messages" not in self.response:
                    self.response["messages"] = []
                self.response["messages"].append(f"Hook error: {str(e)}")
        finally:
            duration = asyncio.get_event_loop().time() - start_time
            if perf_monitor:
                perf_monitor.record_hook_execution(
                    hook_name=hook_name,
                    duration=duration,
                    walker_type=self.__class__.__name__,
                    target_type=context.__class__.__name__ if context else None,
                )

    async def _process_exit_hooks(self: "Walker") -> None:
        """Process all exit hooks after traversal completes."""
        # Use model inspection instead of dir() to avoid Pydantic warnings
        for name in self.__class__.__dict__:
            try:
                method = getattr(self, name)
                if callable(method) and hasattr(method, "_on_exit"):
                    if inspect.iscoroutinefunction(method):
                        await method()
                    else:
                        method()
            except (AttributeError, TypeError):
                continue


class TraversalPaused(Exception):
    """Exception raised to pause a traversal."""


class TraversalSkipped(BaseException):
    """Exception raised to skip processing of the current node and continue to the next node."""


# ----------------- DECORATOR FUNCTIONS -----------------


"""Register visit hooks for graph traversal."""


def on_visit(
    *target_types: Union[Type["Node"], Type["Edge"], Type["Walker"]]
) -> Union[Callable, Callable[[Callable], Callable]]:
    """Register a visit hook for one or more target types.

    Args:
        *target_types: One or more target types (Node, Edge, Walker subclasses)
                      If empty, defaults to any valid type based on context

    Examples:
        @on_visit(NodeA, NodeB)           # Triggers for NodeA OR NodeB
        @on_visit(WalkerA, WalkerB)       # Triggers for WalkerA OR WalkerB
        @on_visit()                       # Triggers for any valid type
        @on_visit                         # Triggers for any valid type (no parentheses)
        @on_visit(Highway, Railroad)      # Triggers for Highway OR Railroad edges
    """
    # Handle case where @on_visit is used without parentheses
    if (
        len(target_types) == 1
        and callable(target_types[0])
        and not inspect.isclass(target_types[0])
    ):
        # This is the case: @on_visit (without parentheses)
        func = target_types[0]
        func._visit_targets = None  # type: ignore[attr-defined]
        func._is_visit_hook = True  # type: ignore[attr-defined]
        return func

    def decorator(func: Callable) -> Callable:
        # Validate target types
        if target_types:
            for target_type in target_types:
                if not inspect.isclass(target_type):
                    raise ValueError(f"Target type must be a class, got {target_type}")

        # Store all target types as a tuple
        func._visit_targets = target_types if target_types else None  # type: ignore[attr-defined]
        func._is_visit_hook = True  # type: ignore[attr-defined]
        return func

    return decorator


def on_exit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorate methods to execute when walker completes traversal.

    Args:
        func: The function to decorate
    """
    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await func(*args, **kwargs)

        async_wrapper._on_exit = True  # type: ignore[attr-defined]
        return async_wrapper
    else:

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return func(*args, **kwargs)

        sync_wrapper._on_exit = True  # type: ignore[attr-defined]
        return sync_wrapper
