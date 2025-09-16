"""Entity and Decorator classes."""

import asyncio
import inspect

# math import removed - no longer needed after spatial function extraction
import weakref
from collections import deque
from contextlib import contextmanager, suppress
from functools import wraps
from typing import Any, Callable, ClassVar, Generator, List, Optional, Type, Union

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr
from typing_extensions import override

from jvspatial.db.database import Database

from .lib import generate_id

# ----------------- HELPER FUNCTIONS -----------------


def find_subclass_by_name(base_class: Type, name: str) -> Optional[Type]:
    """Find a subclass by name recursively."""
    if base_class.__name__ == name:
        return base_class

    # Collect all matches first
    matches = []

    def collect_matches(cls: Type) -> None:
        for subclass in cls.__subclasses__():
            if subclass.__name__ == name:
                matches.append(subclass)
            collect_matches(subclass)

    collect_matches(base_class)

    if not matches:
        return None

    # Prefer classes defined in the same module as the caller
    import inspect

    caller_frame = inspect.currentframe()
    if caller_frame and caller_frame.f_back and caller_frame.f_back.f_back:
        caller_module = caller_frame.f_back.f_back.f_globals.get("__name__")
        if caller_module:
            for match in matches:
                if match.__module__ == caller_module:
                    return match

    # Return the first match if no module preference
    return matches[0]


# ----------------- CORE CLASSES -----------------


class Object(BaseModel):
    """Base object with persistence capabilities.

    Attributes:
        id: Unique identifier for the object
        db: Class-level database reference
        type_code: Type identifier for database partitioning
    """

    id: str = Field(default="")
    db: ClassVar[Optional[Database]] = None
    type_code: ClassVar[str] = "o"
    _initializing: bool = PrivateAttr(default=True)

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    @classmethod
    def set_db(cls: Type["Object"], db: Optional[Database] = None) -> None:
        """Set the database instance for this class.

        Args:
            db: Database instance to use for persistence
        """
        cls.db = db

    @classmethod
    def get_db(cls: Type["Object"]) -> Database:
        """Get the database instance, initializing it if necessary.

        Returns:
            Database instance
        """
        if cls.db is None:
            from jvspatial.db.factory import get_database

            cls.db = get_database()
        return cls.db

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
        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context,
        }

    def get_collection_name(self: "Object") -> str:
        """Get the database collection name for this object type.

        Returns:
            Collection name
        """
        collection_map = {"n": "node", "e": "edge", "o": "object", "w": "walker"}
        return collection_map.get(self.type_code, "object")

    async def save(self: "Object") -> "Object":
        """Persist the object to the database.

        Returns:
            The saved object instance
        """
        record = self.export()
        collection = self.get_collection_name()
        await self.get_db().save(collection, record)
        return self

    @classmethod
    def get_collection_name_for_class(cls: Type["Object"]) -> str:
        """Get the database collection name for this class type.

        Returns:
            Collection name
        """
        collection_map = {"n": "node", "e": "edge", "o": "object", "w": "walker"}
        return collection_map.get(cls.type_code, "object")

    @classmethod
    async def get(cls: Type["Object"], id: str) -> Optional["Object"]:
        """Retrieve an object from the database by ID.

        Args:
            id: ID of the object to retrieve

        Returns:
            Object instance if found, else None
        """
        collection = cls.get_collection_name_for_class()
        data = await cls.get_db().get(collection, id)
        if not data:
            return None

        # Handle subclass instantiation based on stored name
        stored_name = data.get("name", cls.__name__)
        target_class = find_subclass_by_name(cls, stored_name) or cls

        # Create object with proper subclass - use the right class from the start
        context_data = data["context"].copy()
        if cls.type_code == "n":
            if "edges" in data:
                context_data["edge_ids"] = data["edges"]
            elif "edge_ids" in data["context"]:  # Handle legacy format
                context_data["edge_ids"] = data["context"]["edge_ids"]

        obj = target_class(id=data["id"], **context_data)
        return obj

    async def destroy(self: "Object", cascade: bool = True) -> None:
        """Delete the object and optionally related objects.

        Args:
            cascade: Whether to delete related objects (default: True)
        """
        collection = self.get_collection_name()

        if cascade and self.type_code == "n":
            await self._cascade_delete()
        await self.get_db().delete(collection, self.id)

    async def _cascade_delete(self: "Object") -> None:
        """Delete related objects when cascading.

        For nodes, this deletes all connected edges.
        """
        if self.type_code == "n" and hasattr(self, "edge_ids"):
            # Delete all connected edges
            for edge_id in getattr(self, "edge_ids", []):
                try:
                    edge = await Edge.get(edge_id)
                    if edge:
                        await edge.destroy(cascade=False)
                except Exception as e:
                    print(f"Warning: Could not delete edge {edge_id}: {e}")


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
        collection = cls.get_collection_name_for_class()
        data = await cls.get_db().get(collection, id)
        if not data:
            return None

        # Handle both new and legacy data formats
        if "source" in data and "target" in data:
            # New format: source/target at top level
            source = data["source"]
            target = data["target"]
            direction = data.get("direction", "both")
        else:
            # Legacy format: source/target in context
            source = data["context"].get("source", "")
            target = data["context"].get("target", "")
            direction = data["context"].get("direction", "both")

        # Handle subclass instantiation based on stored name
        stored_name = data.get("name", cls.__name__)
        target_class = find_subclass_by_name(cls, stored_name) or cls

        # Create edge with proper fields using the right class from the start
        context_data = {
            k: v
            for k, v in data["context"].items()
            if k not in ["source", "target", "direction"]
        }

        obj = target_class(
            id=data["id"],
            source=source,
            target=target,
            direction=direction,
            **context_data,
        )

        return obj

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
        collection = cls.get_collection_name_for_class()
        edges_data = await cls.get_db().find(collection, {})
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

            edge = target_class(
                id=data["id"],
                source=source,
                target=target,
                direction=direction,
                **context_data,
            )

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
        for _, method in inspect.getmembers(cls):
            if hasattr(method, "_on_visit_target"):
                registered_method = _register_hook(cls, method)
                target_type = getattr(registered_method, "_on_visit_target", None)
                cls._visit_hooks[target_type] = registered_method

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
        self: "Node",
        other: "Node",
        edge: Type["Edge"] = Edge,
        direction: str = "out",
        **kwargs: Any,
    ) -> "Edge":
        """Connect this node to another node.

        Args:
            other: Target node to connect to
            edge: Edge class to use for connection
            direction: Connection direction
            **kwargs: Additional edge properties

        Returns:
            Created edge instance
        """
        # Create edge using the new async pattern
        connection = await edge.create(
            left=self, right=other, direction=direction, **kwargs
        )

        # Update node edge lists
        if connection.id not in self.edge_ids:
            self.edge_ids.append(connection.id)
        if connection.id not in other.edge_ids:
            other.edge_ids.append(connection.id)

        # Save both nodes
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

    async def nodes(self: "Node", direction: str = "both") -> "NodeQuery":
        """Get nodes connected to this node.

        Args:
            direction: Filter connections by direction ('in', 'out', 'both')

        Returns:
            NodeQuery instance for further filtering
        """
        edges = await self.edges(direction=direction)
        nodes = []
        for edge_obj in edges:
            target_id = None
            if edge_obj.source == self.id:
                target_id = edge_obj.target
            else:
                target_id = edge_obj.source

            if target_id:
                # Always use base Node class for retrieval, subclass instantiation happens automatically
                node = await Node.get(target_id)
                if node:
                    nodes.append(node)

        unique_nodes = {}
        for node in nodes:
            unique_nodes[node.id] = node
        return NodeQuery(list(unique_nodes.values()), source=self)

    @classmethod
    async def all(cls: Type["Node"]) -> List["Node"]:
        """Retrieve all nodes from the database.

        Returns:
            List of node instances
        """
        collection = cls.get_collection_name_for_class()
        nodes_data = await cls.get_db().find(collection, {})
        nodes = []
        for data in nodes_data:
            # Handle subclass instantiation based on stored name
            stored_name = data.get("name", cls.__name__)

            # Only process nodes that match the calling class or if calling base Node class
            if cls.__name__ == "Node" or stored_name == cls.__name__:
                target_class = find_subclass_by_name(cls, stored_name) or cls
                try:
                    context_data = data["context"].copy()
                    if "edges" in data:
                        context_data["edge_ids"] = data["edges"]
                    elif "edge_ids" in data["context"]:  # Handle legacy format
                        context_data["edge_ids"] = data["context"]["edge_ids"]

                    node = target_class(id=data["id"], **context_data)
                    nodes.append(node)
                except Exception:
                    # Skip nodes that can't be instantiated as this class
                    continue
        return nodes

    # Spatial query methods removed - too specific for generic entities

    def export(self: "Node") -> dict:
        """Export node to a dictionary for persistence.

        Returns:
            Dictionary representation of the node
        """
        context_data = self.model_dump(
            exclude={"id", "_visitor_ref", "is_root", "edge_ids"}, exclude_none=False
        )
        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context_data,
            "edges": self.edge_ids,
        }


class NodeQuery:
    """Query object for filtering connected nodes.

    Attributes:
        nodes: List of nodes to query
        source: Source node for the query
    """

    def __init__(
        self: "NodeQuery", nodes: List["Node"], source: Optional["Node"] = None
    ) -> None:
        """Initialize a NodeQuery.

        Args:
            nodes: List of nodes query
            source: Source node for the query
        """
        self.source = source
        self.nodes = nodes

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
            node_data = await cls.get_db().get("node", id)
            if node_data:
                return cls(id=node_data["id"], **node_data["context"])
            node = cls(id=id, is_root=True, edge_ids=[], _visitor_ref=None)
            await node.save()
            existing = await cls.get_db().get("node", id)
            if existing and existing["id"] != node.id:
                raise RuntimeError("Root node singleton violation detected")
            return node


class Walker(BaseModel):
    """Base class for graph walkers that traverse nodes.

    Attributes:
        id: Unique walker ID
        queue: Queue of nodes to visit
        response: Response data from traversal
        current_node: Currently visited node
        paused: Whether traversal is paused
    """

    model_config = ConfigDict(extra="ignore")
    type_code: ClassVar[str] = "w"
    id: str = Field(default="")
    queue: deque = Field(default_factory=deque)
    response: dict = Field(default_factory=dict)
    current_node: Optional[Node] = None
    _visit_hooks: ClassVar[dict] = {}
    paused: bool = Field(default=False, exclude=True)

    def __init_subclass__(cls: Type["Walker"]) -> None:
        """Handle subclass initialization."""
        cls._visit_hooks = {}
        for _name, method in inspect.getmembers(cls):
            if hasattr(method, "_on_visit_target"):
                method = _register_hook(cls, method)
                target_type = getattr(method, "_on_visit_target", None)
                cls._visit_hooks[target_type] = method
        if issubclass(cls, (Node, Edge)):
            cls._visit_hooks = {}
            for _name, method in inspect.getmembers(cls):
                if hasattr(method, "_on_visit_target"):
                    registered_method = _register_hook(cls, method)
                    target_type = getattr(registered_method, "_on_visit_target", None)
                    cls._visit_hooks[target_type] = registered_method

    async def resume(self: "Walker") -> "Walker":
        """Resume a paused traversal.

        Returns:
            The walker instance
        """
        if not self.paused:
            return self
        self.paused = False
        try:
            while self.queue and not self.paused:
                current = self.queue.popleft()
                with self.visiting(current):
                    await self._process_hooks(current)
            if not self.paused:
                await self._process_exit_hooks()
        except TraversalPaused:
            pass
        except Exception as e:
            self.response = {"status": 500, "messages": [f"Traversal error: {str(e)}"]}
            with suppress(Exception):
                await self._process_exit_hooks()
        return self

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

    def __init__(self: "Walker", **kwargs: Any) -> None:
        """Initialize a walker with auto-generated ID if not provided."""
        if "id" not in kwargs:
            kwargs["id"] = generate_id(self.type_code, self.__class__.__name__)
        super().__init__(**kwargs)

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

    @contextmanager
    def visiting(self: "Walker", node: Node) -> Generator[None, None, None]:
        """Context manager for visiting a node.

        Args:
            node: Node to visit
        """
        self.current_node = node
        node.visitor = self
        try:
            yield
        finally:
            node.visitor = None
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
        self.queue = deque([root])
        self.paused = False
        try:
            while self.queue and not self.paused:
                current = self.queue.popleft()
                with self.visiting(current):
                    await self._process_hooks(current)
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

    async def nodes(self: "Walker", direction: str = "both") -> "NodeQuery":
        """Get nodes connected to this node.

        Args:
            direction: Filter connections by direction ('in', 'out', 'both')

        Returns:
            NodeQuery instance for further filtering
        """
        if self.here is None:
            return NodeQuery([], source=None)

        edges = await self.here.edges(direction=direction)
        nodes = []
        for edge_obj in edges:
            if edge_obj.source == self.here.id:
                node = await Node.get(edge_obj.target)
            else:
                node = await Node.get(edge_obj.source)
            if node:
                nodes.append(node)
        unique_nodes = {}
        for node in nodes:
            unique_nodes[node.id] = node
        return NodeQuery(list(unique_nodes.values()), source=self.here)

    async def _process_hooks(self: "Walker", node: Node) -> None:
        """Process all visit hooks for a node.

        Args:
            node: Node to process hooks for
        """
        hooks = await self._get_hooks_for_node(node)
        for hook in hooks:
            await self._execute_hook(hook)

    async def _get_hooks_for_node(self: "Walker", node: Node) -> list:
        """Get all applicable visit hooks for a node.

        Args:
            node: Node to get hooks for

        Returns:
            List of hook functions
        """
        hooks = []
        node_type = type(node)
        walker_type = type(self)

        # Walker hooks for specific node type
        if node_type in self._visit_hooks:
            hooks.append(self._visit_hooks[node_type])

        # Node hooks for specific walker type
        if hasattr(node, "_visit_hooks"):
            node_hooks = node._visit_hooks
            if walker_type in node_hooks:
                hooks.append(node_hooks[walker_type])
            if None in node_hooks:
                hooks.append(node_hooks[None])

        # Generic hooks
        if None in self._visit_hooks:
            hooks.append(self._visit_hooks[None])

        return hooks

    async def _execute_hook(self: "Walker", hook: Callable) -> None:
        """Execute a single visit hook.

        Args:
            hook: Hook function to execute
        """
        try:
            context = None
            if hasattr(hook, "_context_var"):
                if hook._context_var == "here":
                    context = self.here
                elif hook._context_var == "visitor":
                    context = self.visitor

            if context is not None:
                # Call with context parameter
                if inspect.iscoroutinefunction(hook):
                    await hook(self, context)
                else:
                    hook(self, context)
            else:
                # Call without context parameter
                if inspect.iscoroutinefunction(hook):
                    await hook(self)
                else:
                    hook(self)
        except Exception as e:
            print(f"Error executing hook {hook.__name__}: {e}")
            # Set error response if not already set, but preserve existing response data
            if not self.response.get("status"):
                self.response["status"] = 500
                if "messages" not in self.response:
                    self.response["messages"] = []
                self.response["messages"].append(f"Hook error: {str(e)}")
            # Continue with other hooks despite this error

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


class TraversalPaused(Exception):
    """Exception raised to pause a traversal."""


# ----------------- DECORATOR FUNCTIONS -----------------


"""Register visit hooks for graph traversal."""


def on_visit(
    target_type: Optional[Union[Type[Union["Node", "Edge", "Walker"]], Callable]] = None
) -> Callable[..., Any]:
    """Register visit hooks that set context variables.

    Args:
        target_type: The target type for the visit hook (Node, Edge, Walker or None)
    """

    def actual_decorator(
        func: Callable[..., Any],
        t_type: Optional[Type[Union["Node", "Edge", "Walker"]]],
    ) -> Callable[..., Any]:
        # Set visit target attributes
        func.__visit_target__ = t_type  # type: ignore[attr-defined]
        func._on_visit_target = t_type  # type: ignore[attr-defined]
        is_async = inspect.iscoroutinefunction(func)
        orig_attrs = {
            "_context_var": getattr(func, "_context_var", None),
            "__visit_target__": getattr(func, "__visit_target__", None),
        }
        if is_async:

            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                return await func(*args, **kwargs)

        else:

            @wraps(func)
            def wrapper(*args: Any, **kwargs: Any) -> Any:
                return func(*args, **kwargs)

        for attr, value in orig_attrs.items():
            setattr(wrapper, attr, value)
        wrapper.__annotations__ = func.__annotations__

        # Avoid setting __signature__ if not present in original
        if hasattr(func, "__signature__"):
            wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
        return wrapper

    if target_type is None:

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return actual_decorator(func, None)

        return decorator

    if inspect.isclass(target_type) and issubclass(target_type, (Node, Edge, Walker)):

        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            return actual_decorator(func, target_type)

        return decorator

    if callable(target_type):
        return actual_decorator(target_type, None)

    raise ValueError(f"Invalid @on_visit target type: {type(target_type)}")


def _register_hook(
    cls: Type[Union["Node", "Edge", "Walker"]], func: Callable[..., Any]
) -> Callable[..., Any]:
    """Register visit hook with context-sensitive validation.

    Args:
        cls: The class being registered
        func: The hook function to register
    """
    target_type = getattr(func, "__visit_target__", None)
    if (
        issubclass(cls, Walker)
        and target_type
        and not issubclass(target_type, (Node, Edge))
    ):
        raise TypeError(
            f"Walker @on_visit must target Node/Edge, got {target_type.__name__}"
        )
    elif (
        issubclass(cls, (Node, Edge))
        and target_type
        and not issubclass(target_type, Walker)
    ):
        raise TypeError(
            f"Node/Edge @on_visit must target Walker, got {target_type.__name__}"
        )
    if target_type is None:
        # Only set _context_var if it exists
        if hasattr(func, "_context_var"):
            func._context_var = "here" if issubclass(cls, Walker) else "visitor"
    else:
        # Only set _context_var if it exists
        if hasattr(func, "_context_var"):
            func._context_var = "visitor" if issubclass(target_type, Walker) else "here"
    return func


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
