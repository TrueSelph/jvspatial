"""Entity and Decorator classes."""

import asyncio
import inspect
import uuid

# math import removed - no longer needed after spatial function extraction
import weakref
from collections import deque
from contextlib import contextmanager, suppress
from datetime import datetime
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


def serialize_datetime(obj: Any) -> Any:
    """Recursively serialize datetime objects to ISO format strings.

    Args:
        obj: Any object that might contain datetime objects

    Returns:
        Object with datetime objects converted to ISO format strings
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: serialize_datetime(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [serialize_datetime(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(serialize_datetime(item) for item in obj)
    else:
        return obj


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

        # Serialize datetime objects to ensure JSON compatibility
        context = serialize_datetime(context)

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
        bidirectional: Whether the edge is bidirectional
    """

    type_code: ClassVar[str] = "e"
    id: str = Field(default="")
    source: str
    target: str
    bidirectional: bool = True

    @property
    def direction(self: "Edge") -> str:
        """Get the edge direction based on bidirectional flag.

        Returns:
            'both' if bidirectional, 'out' otherwise
        """
        return "both" if self.bidirectional else "out"

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
        """Initialize an Edge with source and target nodes.

        Args:
            left: First node
            right: Second node
            direction: Direction used to orient source/target and set bidirectional
                      'out': left->source, right->target, bidirectional=False
                      'in': left->target, right->source, bidirectional=False
                      'both': left->source, right->target, bidirectional=True
            **kwargs: Additional edge attributes
        """
        self._initializing = True

        source: str = ""
        target: str = ""
        bidirectional: bool = direction == "both"

        if left and right:
            if direction == "out":
                source = left.id
                target = right.id
            elif direction == "in":
                source = right.id
                target = left.id
            else:  # direction == "both"
                source = left.id
                target = right.id

        # Allow override of computed values
        if "source" in kwargs:
            source = kwargs.pop("source")
        if "target" in kwargs:
            target = kwargs.pop("target")
        if "bidirectional" in kwargs:
            bidirectional = kwargs.pop("bidirectional")

        # Don't override ID if already provided
        if "id" not in kwargs:
            kwargs["id"] = generate_id("e", self.__class__.__name__)

        kwargs.update(
            {"source": source, "target": target, "bidirectional": bidirectional}
        )

        super().__init__(**kwargs)
        self._initializing = False

    def export(self: "Edge") -> dict:
        """Export edge to a dictionary for persistence.

        Returns:
            Dictionary representation of the edge
        """
        context = self.model_dump(
            exclude={"id", "source", "target", "bidirectional"}, exclude_none=False
        )

        # Include _data if it exists
        if hasattr(self, "_data"):
            context["_data"] = self._data

        # Serialize datetime objects to ensure JSON compatibility
        context = serialize_datetime(context)

        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context,
            "source": self.source,
            "target": self.target,
            "bidirectional": self.bidirectional,
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
            # Handle data format with bidirectional field
            if "source" in data and "target" in data:
                source = data["source"]
                target = data["target"]
                bidirectional = data.get("bidirectional", True)
            else:
                source = data["context"].get("source", "")
                target = data["context"].get("target", "")
                bidirectional = data["context"].get("bidirectional", True)

            # Handle subclass instantiation based on stored name
            stored_name = data.get("name", cls.__name__)
            target_class = find_subclass_by_name(cls, stored_name) or cls

            context_data = {
                k: v
                for k, v in data["context"].items()
                if k not in ["source", "target", "bidirectional"]
            }

            # Extract _data if present
            stored_data = context_data.pop("_data", {})

            edge = target_class(
                id=data["id"],
                source=source,
                target=target,
                bidirectional=bidirectional,
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

        # Serialize datetime objects to ensure JSON compatibility
        context_data = serialize_datetime(context_data)

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
    They also track their traversal trail for path reconstruction and analysis.

    Infinite Walk Protection:
    Walkers include comprehensive protection against infinite loops and runaway traversals
    through multiple configurable limits and automatic halting mechanisms.

    Attributes:
        id: Unique walker ID
        queue: Queue of nodes to visit
        response: Response data from traversal
        current_node: Currently visited node
        paused: Whether traversal is paused

        # Trail Tracking
        trail: Trail of visited node IDs in order (read-only)
        trail_edges: Trail of edge IDs traversed between nodes (read-only)
        trail_metadata: Additional metadata for each trail step (read-only)
        trail_enabled: Whether trail tracking is enabled (configurable)
        max_trail_length: Maximum trail length (0 = unlimited, configurable)

        # Infinite Walk Protection
        max_steps: Maximum number of steps before auto-halt (default: 10000)
        max_visits_per_node: Maximum visits per node before auto-halt (default: 100)
        max_execution_time: Maximum execution time in seconds (default: 300.0)
        max_queue_size: Maximum queue size before limiting additions (default: 1000)
        protection_enabled: Whether protection mechanisms are enabled (default: True)
        step_count: Current number of steps taken (read-only)
        node_visit_counts: Dictionary of per-node visit counts (read-only)
    """

    # Trail properties are maintained internally during traversal:
    # - trail, trail_edges, trail_metadata: Read-only, managed by walker
    # - trail_enabled, max_trail_length: Configurable settings

    model_config = ConfigDict(extra="allow")
    type_code: ClassVar[str] = "w"
    id: str = Field(default="")
    response: dict = Field(default_factory=dict)
    _queue: deque = PrivateAttr(default_factory=deque)
    _current_node: Optional[Node] = PrivateAttr(default=None)
    _visit_hooks: ClassVar[dict] = {}
    _paused: bool = PrivateAttr(default=False)

    # Trail tracking attributes
    _trail: List[str] = PrivateAttr(default_factory=list)  # Node IDs in visit order
    _trail_edges: List[Optional[str]] = PrivateAttr(
        default_factory=list
    )  # Edge IDs between nodes
    _trail_metadata: List[Dict[str, Any]] = PrivateAttr(
        default_factory=list
    )  # Metadata per step
    _trail_enabled: bool = PrivateAttr(default=True)  # Whether to track trail
    _max_trail_length: int = PrivateAttr(default=0)  # 0 = unlimited

    # Infinite walk protection attributes
    _step_count: int = PrivateAttr(default=0)  # Current number of steps taken
    _node_visit_counts: Dict[str, int] = PrivateAttr(
        default_factory=dict
    )  # Per-node visit counts
    _start_time: Optional[float] = PrivateAttr(default=None)  # Traversal start time
    _max_steps: int = PrivateAttr(default=10000)  # Maximum steps before halting
    _max_visits_per_node: int = PrivateAttr(default=100)  # Maximum visits per node
    _max_execution_time: float = PrivateAttr(
        default=300.0
    )  # Maximum execution time in seconds
    _max_queue_size: int = PrivateAttr(default=1000)  # Maximum queue size
    _protection_enabled: bool = PrivateAttr(
        default=True
    )  # Whether protection is enabled

    def __init__(self: "Walker", **kwargs: Any) -> None:
        """Initialize a walker with auto-generated ID if not provided."""
        if "id" not in kwargs:
            kwargs["id"] = generate_id(self.type_code, self.__class__.__name__)

        # Import os for environment variable access
        import os

        # Extract private attr values from kwargs before calling super()
        private_attrs = {
            "trail_enabled": kwargs.pop("trail_enabled", True),
            "max_trail_length": kwargs.pop("max_trail_length", 0),
            "paused": kwargs.pop("paused", False),
            # Infinite walk protection attributes with environment variable support
            "max_steps": kwargs.pop(
                "max_steps", int(os.getenv("JVSPATIAL_WALKER_MAX_STEPS", "10000"))
            ),
            "max_visits_per_node": kwargs.pop(
                "max_visits_per_node",
                int(os.getenv("JVSPATIAL_WALKER_MAX_VISITS_PER_NODE", "100")),
            ),
            "max_execution_time": kwargs.pop(
                "max_execution_time",
                float(os.getenv("JVSPATIAL_WALKER_MAX_EXECUTION_TIME", "300.0")),
            ),
            "max_queue_size": kwargs.pop(
                "max_queue_size",
                int(os.getenv("JVSPATIAL_WALKER_MAX_QUEUE_SIZE", "1000")),
            ),
            "protection_enabled": kwargs.pop(
                "protection_enabled",
                os.getenv("JVSPATIAL_WALKER_PROTECTION_ENABLED", "true").lower()
                == "true",
            ),
        }

        super().__init__(**kwargs)

        # Set private attributes after initialization
        self._trail_enabled = private_attrs["trail_enabled"]
        self._max_trail_length = private_attrs["max_trail_length"]
        self._paused = private_attrs["paused"]

        # Set protection attributes
        self._max_steps = private_attrs["max_steps"]
        self._max_visits_per_node = private_attrs["max_visits_per_node"]
        self._max_execution_time = private_attrs["max_execution_time"]
        self._max_queue_size = private_attrs["max_queue_size"]
        self._protection_enabled = private_attrs["protection_enabled"]

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
                        # Accept both classes and strings for forward references
                        if isinstance(target, str) or (
                            inspect.isclass(target) and issubclass(target, (Node, Edge))
                        ):
                            # Store string targets for later resolution or class targets directly
                            if target not in cls._visit_hooks:
                                cls._visit_hooks[target] = []
                            cls._visit_hooks[target].append(method)
                        else:
                            raise TypeError(
                                f"Walker @on_visit must target Node/Edge types or string names, got {target.__name__ if hasattr(target, '__name__') else target}"
                            )

    # Properties for backward compatibility
    @property
    def queue(self: "Walker") -> deque:
        """Get the walker's queue."""
        return self._queue

    @queue.setter
    def queue(self: "Walker", value: deque) -> None:
        """Set the walker's queue."""
        self._queue = value

    @property
    def current_node(self: "Walker") -> Optional[Node]:
        """Get the current node being visited."""
        return self._current_node

    @current_node.setter
    def current_node(self: "Walker", value: Optional[Node]) -> None:
        """Set the current node being visited."""
        self._current_node = value

    @property
    def paused(self: "Walker") -> bool:
        """Get the paused state."""
        return self._paused

    @paused.setter
    def paused(self: "Walker", value: bool) -> None:
        """Set the paused state."""
        self._paused = value

    @property
    def trail(self: "Walker") -> List[str]:
        """Get the trail of visited node IDs (read-only).

        The trail is maintained internally by the walker during traversal
        and cannot be modified externally. Use clear_trail() to clear it.

        Returns:
            Copy of the trail list to prevent external modification
        """
        return self._trail.copy()

    @property
    def trail_edges(self: "Walker") -> List[Optional[str]]:
        """Get the trail edges (read-only).

        Returns:
            Copy of the trail edges list to prevent external modification
        """
        return self._trail_edges.copy()

    @property
    def trail_metadata(self: "Walker") -> List[Dict[str, Any]]:
        """Get the trail metadata (read-only).

        Returns:
            Copy of the trail metadata list to prevent external modification
        """
        import copy

        return copy.deepcopy(self._trail_metadata)

    @property
    def trail_enabled(self: "Walker") -> bool:
        """Get trail tracking enabled state."""
        return self._trail_enabled

    @trail_enabled.setter
    def trail_enabled(self: "Walker", value: bool) -> None:
        """Set trail tracking enabled state."""
        self._trail_enabled = value

    @property
    def max_trail_length(self: "Walker") -> int:
        """Get max trail length."""
        return self._max_trail_length

    @max_trail_length.setter
    def max_trail_length(self: "Walker", value: int) -> None:
        """Set max trail length."""
        self._max_trail_length = value

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

        With the visitor property, nodes can call methods on the walker that's visiting them,
        enabling a conversation between the node and walker during traversal.

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

        # Check queue size protection
        if (
            self._protection_enabled
            and (len(self.queue) + len(nodes_list)) > self._max_queue_size
        ):
            # Add only nodes that fit within the limit
            available_space = max(0, self._max_queue_size - len(self.queue))
            nodes_list = nodes_list[:available_space]
            if available_space == 0:
                # Queue is full, return empty list
                return []

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
        self: "Walker",
        item: Union["Node", Tuple[str, "Edge"]],
        edge_from_previous: Optional[str] = None,
    ) -> Generator[None, None, None]:
        """Context manager for visiting a node or edge.

        Args:
            item: Node, Edge, or tuple ('edge', Edge) to visit
            edge_from_previous: Edge ID used to reach this node (for trail tracking)
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

                # Record trail step for this node
                if self.trail_enabled:
                    import time

                    metadata = {
                        "timestamp": time.time(),
                        "node_type": node.__class__.__name__,
                        "queue_length": (
                            len(self.queue) if hasattr(self, "queue") else 0
                        ),
                    }
                    self._record_trail_step(node, edge_from_previous, metadata)

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
        import time
        from collections import deque

        # Initialize protection tracking
        self._step_count = 0
        self._node_visit_counts.clear()
        self._start_time = time.time() if self._protection_enabled else None

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
            connecting_edge_id = None

            while self.queue and not self.paused:
                current = self.queue.popleft()
                connecting_edge_id = None  # Reset for each iteration

                # Track step and node visits for protection BEFORE processing
                if self._protection_enabled and isinstance(current, Node):
                    self._step_count += 1
                    node_id = current.id
                    self._node_visit_counts[node_id] = (
                        self._node_visit_counts.get(node_id, 0) + 1
                    )

                    # Check infinite walk protection after updating counters
                    if not await self._check_protection_limits():
                        break

                # If we have a previous node and current node, find connecting edge and traverse
                if (
                    previous_node
                    and isinstance(current, Node)
                    and not isinstance(current, tuple)
                ):
                    # Find the edge connecting these nodes for trail tracking
                    connecting_edge_id = await self._find_connecting_edge(
                        previous_node, current
                    )
                    await self._traverse_edge_between_nodes(previous_node, current)

                with self.visiting(current, connecting_edge_id):
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
            connecting_edge_id = None

            # Resume protection tracking if start time was not set
            if self._protection_enabled and self._start_time is None:
                import time

                self._start_time = time.time()

            while self.queue and not self.paused:
                current = self.queue.popleft()
                connecting_edge_id = None  # Reset for each iteration

                # Track step and node visits for protection BEFORE processing
                if self._protection_enabled and isinstance(current, Node):
                    self._step_count += 1
                    node_id = current.id
                    self._node_visit_counts[node_id] = (
                        self._node_visit_counts.get(node_id, 0) + 1
                    )

                    # Check infinite walk protection after updating counters
                    if not await self._check_protection_limits():
                        break

                # If we have a previous node and current node, find connecting edge and traverse
                if (
                    previous_node
                    and isinstance(current, Node)
                    and not isinstance(current, tuple)
                ):
                    # Find the edge connecting these nodes for trail tracking
                    connecting_edge_id = await self._find_connecting_edge(
                        previous_node, current
                    )
                    await self._traverse_edge_between_nodes(previous_node, current)

                with self.visiting(current, connecting_edge_id):
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

    async def _find_connecting_edge(
        self: "Walker", from_node: Node, to_node: Node
    ) -> Optional[str]:
        """Find the edge connecting two nodes and return its ID.

        Args:
            from_node: Source node
            to_node: Target node

        Returns:
            The edge ID if found, None otherwise
        """
        try:
            # Get all edges connected to the source node
            edges = await from_node.edges()

            # Find edge that connects from_node to to_node
            for edge in edges:
                if (edge.source == from_node.id and edge.target == to_node.id) or (
                    edge.target == from_node.id and edge.source == to_node.id
                ):
                    return edge.id

        except Exception:
            # If there's an error, return None
            pass

        return None

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

    # ============== TRAIL TRACKING METHODS ==============

    def _record_trail_step(
        self: "Walker",
        node: Node,
        edge_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Record a step in the walker's trail.

        Args:
            node: Node being visited
            edge_id: ID of edge traversed to reach this node (None for starting node)
            metadata: Additional metadata for this step
        """
        if not self._trail_enabled:
            return

        # Add node to trail
        self._trail.append(node.id)
        self._trail_edges.append(edge_id)
        self._trail_metadata.append(metadata or {})

        # Enforce max trail length if set
        if self._max_trail_length > 0 and len(self._trail) > self._max_trail_length:
            # Remove oldest entries
            excess = len(self._trail) - self._max_trail_length
            self._trail = self._trail[excess:]
            self._trail_edges = self._trail_edges[excess:]
            self._trail_metadata = self._trail_metadata[excess:]

    def get_trail(self: "Walker") -> List[str]:
        """Get the trail of visited node IDs.

        Returns:
            List of node IDs in the order they were visited
        """
        return self._trail.copy()

    async def get_trail_nodes(self: "Walker") -> List[Node]:
        """Get the actual Node objects from the trail.

        Returns:
            List of Node objects in the order they were visited
        """
        nodes = []
        for node_id in self._trail:
            try:
                node = await Node.get(node_id)
                if node:
                    nodes.append(node)
            except Exception:
                continue  # Skip nodes that can't be retrieved
        return nodes

    async def get_trail_path(self: "Walker") -> List[Tuple[Node, Optional["Edge"]]]:
        """Get the full trail path with nodes and connecting edges.

        Returns:
            List of tuples (node, edge) where edge is the edge used to reach the node
            The first tuple will have edge=None (starting node)
        """
        path = []
        nodes = await self.get_trail_nodes()

        for i, node in enumerate(nodes):
            edge = None
            if i < len(self._trail_edges) and self._trail_edges[i] is not None:
                edge_id = self._trail_edges[i]
                if edge_id is not None:
                    with suppress(Exception):
                        edge = await Edge.get(edge_id)
            path.append((node, edge))

        return path

    def get_trail_length(self: "Walker") -> int:
        """Get the current length of the trail.

        Returns:
            Number of nodes in the trail
        """
        return len(self._trail)

    def get_trail_metadata(self: "Walker", step: int = -1) -> Dict[str, Any]:
        """Get metadata for a specific trail step.

        Args:
            step: Trail step index (negative for from-end indexing, default is last)

        Returns:
            Metadata dictionary for the specified step
        """
        if not self._trail_metadata:
            return {}
        try:
            import copy

            return copy.deepcopy(self._trail_metadata[step])
        except IndexError:
            return {}

    def clear_trail(self: "Walker") -> None:
        """Clear the entire trail history."""
        self._trail.clear()
        self._trail_edges.clear()
        self._trail_metadata.clear()

    def get_recent_trail(self: "Walker", count: int = 5) -> List[str]:
        """Get the most recent N steps from the trail.

        Args:
            count: Number of recent steps to return

        Returns:
            List of node IDs from most recent steps
        """
        if count <= 0:
            return []
        return self._trail[-count:] if self._trail else []

    def has_visited(self: "Walker", node_id: str) -> bool:
        """Check if a node has been visited in this walker's trail.

        Args:
            node_id: ID of the node to check

        Returns:
            True if the node has been visited, False otherwise
        """
        return node_id in self._trail

    def get_visit_count(self: "Walker", node_id: str) -> int:
        """Get the number of times a node has been visited.

        Args:
            node_id: ID of the node to count visits for

        Returns:
            Number of times the node appears in the trail
        """
        return self._trail.count(node_id)

    def detect_cycles(self: "Walker") -> List[Tuple[int, int]]:
        """Detect cycles in the trail.

        Returns:
            List of tuples (start_index, end_index) representing cycle boundaries
        """
        cycles = []
        seen_positions: Dict[str, int] = {}

        for i, node_id in enumerate(self._trail):
            if node_id in seen_positions:
                # Found a cycle
                start = seen_positions[node_id]
                cycles.append((start, i))
            else:
                seen_positions[node_id] = i

        return cycles

    def get_trail_summary(self: "Walker") -> Dict[str, Any]:
        """Get a summary of the current trail.

        Returns:
            Dictionary with trail statistics and information
        """
        cycles = self.detect_cycles()
        unique_nodes = set(self._trail)

        return {
            "length": len(self._trail),
            "unique_nodes": len(unique_nodes),
            "cycles_detected": len(cycles),
            "cycle_ranges": cycles,
            "trail_enabled": self._trail_enabled,
            "max_trail_length": self._max_trail_length,
            "most_visited": (
                max(self._trail, key=self._trail.count) if self._trail else None
            ),
            "recent_nodes": self.get_recent_trail(3),
        }

    def enable_trail_tracking(self: "Walker", max_length: int = 0) -> None:
        """Enable trail tracking with optional maximum length.

        Args:
            max_length: Maximum trail length (0 for unlimited)
        """
        self.trail_enabled = True
        self.max_trail_length = max_length

    def disable_trail_tracking(self: "Walker") -> None:
        """Disable trail tracking."""
        self.trail_enabled = False

    # ============== INFINITE WALK PROTECTION METHODS ==============

    async def _check_protection_limits(self: "Walker") -> bool:
        """Check if walker has exceeded any protection limits.

        Returns:
            True if walker can continue, False if limits exceeded
        """
        if not self._protection_enabled:
            return True

        import time

        # Check step limit
        if self._step_count >= self._max_steps:
            self.response["protection_triggered"] = "max_steps"
            self.response["steps_taken"] = self._step_count
            self.response["max_steps"] = self._max_steps
            await self.disengage()
            return False

        # Check execution time limit
        if (
            self._start_time
            and (time.time() - self._start_time) >= self._max_execution_time
        ):
            self.response["protection_triggered"] = "timeout"
            self.response["execution_time"] = time.time() - self._start_time
            self.response["max_execution_time"] = self._max_execution_time
            await self.disengage()
            return False

        # Check node visit frequency limits
        for node_id, visit_count in self._node_visit_counts.items():
            if visit_count > self._max_visits_per_node:
                self.response["protection_triggered"] = "max_visits_per_node"
                self.response["node_id"] = node_id
                self.response["visit_count"] = visit_count
                self.response["max_visits_per_node"] = self._max_visits_per_node
                await self.disengage()
                return False

        return True

    @property
    def max_steps(self: "Walker") -> int:
        """Get maximum steps limit."""
        return self._max_steps

    @max_steps.setter
    def max_steps(self: "Walker", value: int) -> None:
        """Set maximum steps limit."""
        self._max_steps = max(0, value)

    @property
    def max_visits_per_node(self: "Walker") -> int:
        """Get maximum visits per node limit."""
        return self._max_visits_per_node

    @max_visits_per_node.setter
    def max_visits_per_node(self: "Walker", value: int) -> None:
        """Set maximum visits per node limit."""
        self._max_visits_per_node = max(0, value)

    @property
    def max_execution_time(self: "Walker") -> float:
        """Get maximum execution time limit."""
        return self._max_execution_time

    @max_execution_time.setter
    def max_execution_time(self: "Walker", value: float) -> None:
        """Set maximum execution time limit."""
        self._max_execution_time = max(0.0, value)

    @property
    def max_queue_size(self: "Walker") -> int:
        """Get maximum queue size limit."""
        return self._max_queue_size

    @max_queue_size.setter
    def max_queue_size(self: "Walker", value: int) -> None:
        """Set maximum queue size limit."""
        self._max_queue_size = max(0, value)

    @property
    def protection_enabled(self: "Walker") -> bool:
        """Get protection enabled state."""
        return self._protection_enabled

    @protection_enabled.setter
    def protection_enabled(self: "Walker", value: bool) -> None:
        """Set protection enabled state."""
        self._protection_enabled = value

    @property
    def step_count(self: "Walker") -> int:
        """Get current step count."""
        return self._step_count

    @property
    def node_visit_counts(self: "Walker") -> Dict[str, int]:
        """Get dictionary of node visit counts."""
        return self._node_visit_counts.copy()

    def get_protection_status(self: "Walker") -> Dict[str, Any]:
        """Get comprehensive protection status information.

        Returns:
            Dictionary with protection limits, current values, and percentages
        """
        import time

        status = {
            "protection_enabled": self._protection_enabled,
            "step_count": self._step_count,
            "max_steps": self._max_steps,
            "step_usage_percent": (self._step_count / max(1, self._max_steps)) * 100,
            "queue_size": len(self.queue),
            "max_queue_size": self._max_queue_size,
            "queue_usage_percent": (len(self.queue) / max(1, self._max_queue_size))
            * 100,
            "max_visits_per_node": self._max_visits_per_node,
            "node_visit_counts": self._node_visit_counts.copy(),
        }

        if self._start_time:
            elapsed_time = time.time() - self._start_time
            status["elapsed_time"] = elapsed_time
            status["max_execution_time"] = self._max_execution_time
            status["time_usage_percent"] = (
                elapsed_time / max(1.0, self._max_execution_time)
            ) * 100
        else:
            status["elapsed_time"] = None
            status["max_execution_time"] = self._max_execution_time
            status["time_usage_percent"] = 0

        # Find most visited node
        if self._node_visit_counts:
            most_visited_node = max(self._node_visit_counts.items(), key=lambda x: x[1])
            status["most_visited_node"] = most_visited_node[0]
            status["most_visited_count"] = most_visited_node[1]
            status["most_visited_usage_percent"] = (
                most_visited_node[1] / max(1, self._max_visits_per_node)
            ) * 100
        else:
            status["most_visited_node"] = None
            status["most_visited_count"] = 0
            status["most_visited_usage_percent"] = 0

        return status

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
    *target_types: Union[Type["Node"], Type["Edge"], Type["Walker"], str]
) -> Union[Callable, Callable[[Callable], Callable]]:
    """Register a visit hook for one or more target types.

    Args:
        *target_types: One or more target types (Node, Edge, Walker subclasses, or string names)
                      If empty, defaults to any valid type based on context
                      Strings will be resolved to actual classes at runtime

    Examples:
        @on_visit(NodeA, NodeB)           # Triggers for NodeA OR NodeB
        @on_visit(WalkerA, WalkerB)       # Triggers for WalkerA OR WalkerB
        @on_visit()                       # Triggers for any valid type
        @on_visit                         # Triggers for any valid type (no parentheses)
        @on_visit(Highway, Railroad)      # Triggers for Highway OR Railroad edges
        @on_visit("WebhookEvent")         # Triggers for WebhookEvent (string resolved at runtime)
    """
    # Handle case where @on_visit is used without parentheses
    if (
        len(target_types) == 1
        and callable(target_types[0])
        and not inspect.isclass(target_types[0])
        and not isinstance(target_types[0], str)
    ):
        # This is the case: @on_visit (without parentheses)
        func = target_types[0]
        func._visit_targets = None  # type: ignore[attr-defined]
        func._is_visit_hook = True  # type: ignore[attr-defined]
        return func

    def decorator(func: Callable) -> Callable:
        # Validate target types - allow strings for forward references
        if target_types:
            for target_type in target_types:
                if not (inspect.isclass(target_type) or isinstance(target_type, str)):
                    raise ValueError(
                        f"Target type must be a class or string, got {target_type}"
                    )

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
