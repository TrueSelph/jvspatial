import inspect
import weakref
import asyncio
from contextlib import contextmanager
from pydantic import PrivateAttr
from typing import Callable, ClassVar, List, Optional, Type, Union
from collections import deque
from pydantic import BaseModel, Field, ConfigDict
from functools import wraps
from jvspatial.db.database import Database
from jvspatial.lib import generate_id


class Object(BaseModel):
    """Base object with persistence capabilities."""

    id: str = Field(default="")
    db: ClassVar[Optional[Database]] = None
    type_code: ClassVar[str] = "o"
    _initializing: bool = PrivateAttr(default=True)

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    @classmethod
    def configure_db(cls, db: Database = None):
        """Override the default database with a custom instance"""
        cls.db = db

    @classmethod
    def _get_db(cls) -> Database:
        """Get database adapter instance with automatic configuration"""
        if cls.db is None:
            # Auto-configure from environment on first use
            from jvspatial.db.factory import get_database

            cls.db = get_database()
        return cls.db

    def __init__(self, **kwargs):
        self._initializing = True
        if "id" not in kwargs:
            # Use class name in ID generation
            kwargs["id"] = generate_id(self.type_code, self.__class__.__name__)
        super().__init__(**kwargs)
        self._initializing = False
        asyncio.create_task(self.save())

    def __setattr__(self, name, value):
        """Automatically save on attribute change"""
        super().__setattr__(name, value)
        if (
            not self._initializing
            and hasattr(self, "id")
            and name not in ["_initializing"]
        ):
            asyncio.create_task(self.save())

    def export(self) -> dict:
        """Convert to persistence record based on object type"""

        context = self.model_dump(
            exclude={"id", "db", "_initializing"}, exclude_none=False
        )

        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context,
        }

    async def save(self):
        """Persist the object to the database."""
        record = self.export()
        collection = (
            "node"
            if isinstance(self, Node)
            else "edge" if isinstance(self, Edge) else "object"
        )
        await self._get_db().save(collection, record)
        return self

    @classmethod
    async def get(cls, id: str):
        """Retrieve an object from the database by ID."""
        # Determine collection based on type
        collection = (
            "node"
            if issubclass(cls, Node)
            else "edge" if issubclass(cls, Edge) else "object"
        )

        data = await cls._get_db().get(collection, id)
        if not data:
            return None

        # Reconstruct object from record
        obj = cls(id=data["id"], **data["context"])
        # Set edge_ids from the record's "edges" field if present
        if "edges" in data:
            obj.edge_ids = data["edges"]
        return obj

    async def destroy(self, cascade: bool = True):
        """Delete the object and optionally related objects."""
        collection = (
            "node"
            if isinstance(self, Node)
            else "edge" if isinstance(self, Edge) else "object"
        )

        if cascade and isinstance(self, Node):
            await self._cascade_delete()

        await self._get_db().delete(collection, self.id)


class Edge(Object):
    """Graph edge connecting two nodes."""

    type_code: ClassVar[str] = "e"
    id: str = Field(default="")
    source: str
    target: str
    direction: str = "both"  # out | in

    def __init__(
        self, left: Optional["Node"] = None, right: Optional["Node"] = None, **kwargs
    ):
        # Initialize with default values
        source = ""
        target = ""
        direction = kwargs.pop("direction", "out")

        # Set from left/right if provided
        if left and right:
            if direction == "out":
                source = left.id
                target = right.id
            elif direction == "in":
                source = right.id
                target = left.id
            else:  # both
                source = left.id
                target = right.id

        # Override with kwargs if provided
        if "source" in kwargs:
            source = kwargs.pop("source")
        if "target" in kwargs:
            target = kwargs.pop("target")

        # Pass all values to superclass
        super().__init__(
            id=generate_id("e", self.__class__.__name__),
            source=source,
            target=target,
            direction=direction,
            **kwargs,
        )

    def export(self) -> dict:
        """Convert to persistence record based on object type"""

        # Include source/target directly and use model_dump for context
        context = self.model_dump(
            exclude={"id", "source", "target", "direction"}, exclude_none=False
        )

        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context,
            "source": self.source,
            "target": self.target,
            "bidrectional": self.direction == "both",
        }

    @classmethod
    async def get(cls, id: str):
        """Retrieve an edge with proper source/target initialization"""
        # Determine collection based on type
        collection = "edge"

        data = await cls._get_db().get(collection, id)
        if not data:
            return None

        # Create edge with source/target from top-level fields
        context = data["context"].copy()

        # Remove source and target from context to avoid duplicate keyword arguments
        context.pop("source", None)
        context.pop("target", None)

        obj = cls(
            id=data["id"],
            source=data["context"].get("source", ""),
            target=data["context"].get("target", ""),
            **context,
        )
        return obj

    async def save(self):
        """Persist the edge to the database."""
        return await super().save()

    @classmethod
    async def all(cls) -> List["Edge"]:
        """Get all edges of this type from the database."""
        edges_data = await cls._get_db().find(cls.__name__, {})
        edges = []
        for data in edges_data:
            edge = cls(
                id=data["id"],
                source=data.get("source", ""),
                target=data.get("target", ""),
                **data["context"],
            )
            edges.append(edge)
        return edges


class Node(Object):
    """Graph node with visitor tracking and connection capabilities."""

    type_code: ClassVar[str] = "n"
    id: str = Field(default="")
    _visitor_ref: Optional[weakref.ReferenceType] = None
    is_root: bool = False
    edge_ids: List[str] = Field(default_factory=list)
    _visit_hooks: ClassVar[dict] = {}

    def __init_subclass__(cls):
        """Initialize visit hooks for Node subclasses"""
        cls._visit_hooks = {}
        for name, method in inspect.getmembers(cls):
            if hasattr(method, "_on_visit_target"):
                # Validate and register the hook
                registered_method = _register_hook(cls, method)
                target_type = registered_method._on_visit_target
                cls._visit_hooks[target_type] = registered_method

    @property
    def visitor(self) -> Optional["Walker"]:
        """Get the current visitor walker as a weak reference."""
        return self._visitor_ref() if self._visitor_ref else None

    @visitor.setter
    def visitor(self, value: "Walker"):
        """Set the visitor walker using a weak reference."""
        self._visitor_ref = weakref.ref(value) if value else None

    async def connect(
        self, other: "Node", edge: Type["Edge"] = Edge, direction: str = "out", **kwargs
    ) -> "Edge":
        """Create connection with directional control"""
        try:
            connection = edge(left=self, right=other, direction=direction, **kwargs)
            await connection.save()

            # Add edge to both nodes' edge lists
            self.edge_ids.append(connection.id)
            other.edge_ids.append(connection.id)

            # Save nodes to persist edge references
            await self.save()
            await other.save()

            return connection
        except Exception as e:
            raise

    async def edges(self, direction: str = "out") -> List["Edge"]:
        """Retrieve edges connected to this node."""
        # Fetch edges by their IDs
        edges = []
        for edge_id in self.edge_ids:
            edge = await Edge.get(edge_id)
            if edge:
                edges.append(edge)

        # Filter by direction
        if direction == "out":
            return [e for e in edges if e.source == self.id]
        elif direction == "in":
            return [e for e in edges if e.target == self.id]
        else:  # both
            return edges

    async def nodes(self, direction: str = "both") -> "NodeQuery":
        edges = await self.edges(direction=direction)
        nodes = []
        for e in edges:
            if e.source == self.id:
                node = await Node.get(e.target)
            else:
                node = await Node.get(e.source)
            if node:
                nodes.append(node)

        # Deduplicate nodes by ID
        unique_nodes = {}
        for node in nodes:
            unique_nodes[node.id] = node
        return NodeQuery(list(unique_nodes.values()), source=self)

    @classmethod
    async def all(cls) -> List["Node"]:
        """Get all nodes of this type from the database."""
        nodes_data = await cls._get_db().find(cls.__name__, {})
        return [cls(**data) for data in nodes_data]

    def export(self) -> dict:
        """Convert to persistence record based on node type"""

        # Use Pydantic's model dumping with proper exclusions
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
    def __init__(self, nodes: List["Node"], source: Optional["Node"] = None):
        self.source = source
        self.nodes = nodes

    async def filter(
        self,
        *,
        node: Union[str, List[str]] = None,
        edge: Union[str, Type["Edge"], List[Union[str, Type["Edge"]]]] = None,
        direction: str = "both",
        **kwargs,
    ) -> List["Node"]:
        filtered_nodes = self.nodes.copy()

        # Node type filtering
        if node:
            node_types = [node] if isinstance(node, str) else node
            filtered_nodes = [
                n for n in filtered_nodes if n.__class__.__name__ in node_types
            ]

        # Edge-based filtering
        if edge or direction != "both" or kwargs:
            edge_types = []
            if edge:
                edge_types = [
                    e.__name__ if inspect.isclass(e) else e
                    for e in (edge if isinstance(edge, list) else [edge])
                ]

            valid_nodes = []
            # Await the edges() call since it's async
            edges = await self.source.edges(direction=direction)
            for n in filtered_nodes:
                connectors = [
                    e
                    for e in edges
                    if (e.source == self.source.id and e.target == n.id)
                    or (e.source == n.id and e.target == self.source.id)
                ]

                # Type filtering
                if edge_types:
                    connectors = [e for e in connectors if e.type in edge_types]

                # Property filtering
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


class RootNode(Node):
    """Singleton root node implementation."""

    id: str = "n:RootNode:root"
    is_root: bool = True
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    async def get(cls) -> "RootNode":
        """Retrieve the root node, creating it if it doesn't exist."""
        async with cls._lock:
            # Double-check after acquiring lock
            node_data = await cls._get_db().get("node", "n:RootNode:root")
            if node_data:
                return cls(id=node_data["id"], **node_data["context"])

            # Create new instance with explicit context
            node = cls(
                id="n:RootNode:root", is_root=True, edge_ids=[], _visitor_ref=None
            )
            await node.save()

            # Verify singleton constraint
            existing = await cls._get_db().get("node", "n:RootNode:root")
            if existing and existing["id"] != node.id:
                raise RuntimeError("Root node singleton violation detected")

            return node


class Walker(BaseModel):
    """Graph traversal agent with hook capabilities."""

    model_config = ConfigDict(extra="ignore")

    type_code: ClassVar[str] = "w"
    id: str = Field(default="")
    queue: deque = Field(default_factory=deque)
    response: dict = Field(default_factory=dict)
    current_node: Optional[Node] = None
    _visit_hooks: ClassVar[dict] = {}
    paused: bool = Field(default=False, exclude=True)

    def __init_subclass__(cls):
        # Collect and register all on_visit decorated methods
        cls._visit_hooks = {}
        for name, method in inspect.getmembers(cls):
            if hasattr(method, "_on_visit_target"):
                # Register hook with context validation
                method = _register_hook(cls, method)
                # Store by target type (None for automatic context)
                cls._visit_hooks[method._on_visit_target] = method

        # For Node/Edge classes, initialize _visit_hooks
        if issubclass(cls, (Node, Edge)):
            cls._visit_hooks = {}
            for name, method in inspect.getmembers(cls):
                if hasattr(method, "_on_visit_target"):
                    # Validate and register the hook
                    registered_method = _register_hook(cls, method)
                    target_type = registered_method._on_visit_target
                    cls._visit_hooks[target_type] = registered_method

    async def resume(self) -> "Walker":
        """Resume a paused traversal."""
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
            await self._process_exit_hooks()
        return self

    def __init__(self, **kwargs):
        if "id" not in kwargs:
            # Use class name in ID generation
            kwargs["id"] = generate_id(self.type_code, self.__class__.__name__)
        super().__init__(**kwargs)

    @property
    def here(self) -> Optional[Node]:
        """Current node being visited."""
        return self.current_node

    @property
    def visitor(self) -> Optional["Walker"]:
        """Visitor reference for node context."""
        return self

    @contextmanager
    def visiting(self, node: Node):
        """Context manager for setting the current node and visitor."""
        self.current_node = node
        node.visitor = self
        try:
            yield
        finally:
            node.visitor = None
            self.current_node = None

    async def spawn(self, start: Optional[Node] = None) -> "Walker":
        """Asynchronously traverse the graph from a given node."""
        from collections import deque

        root = start or await RootNode.get()
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
            self.response = {"status": 500, "messages": [f"Traversal error: {str(e)}"]}
            await self._process_exit_hooks()
        return self

    async def _process_hooks(self, node: Node):
        """Process hooks using centralized registry"""
        try:
            # Get hooks from registry
            hooks = await self._get_hooks_for_node(node)
            for hook in hooks:
                await self._execute_hook(hook)
        except Exception as e:
            raise

    async def _get_hooks_for_node(self, node: Node) -> list:
        """Retrieve hooks for node from registry"""
        hooks = []
        node_type = type(node)
        walker_type = type(self)

        # Add walker-level hooks for node type
        if node_type in self._visit_hooks:
            hooks.append(self._visit_hooks[node_type])

        # Add node-level hooks for current walker type or any walker (None)
        if hasattr(node, "_visit_hooks"):
            # Check for hooks targeting this specific walker type
            if walker_type in node._visit_hooks:
                hooks.append(node._visit_hooks[walker_type])

            # Check for hooks targeting any walker (None)
            if None in node._visit_hooks:
                hooks.append(node._visit_hooks[None])

        return hooks

    async def _execute_hook(self, hook):
        """Execute hook with proper async handling and context setting"""
        try:
            # Set context variable based on hook type
            context = None
            if hasattr(hook, "_context_var"):
                if hook._context_var == "here":
                    context = self.here
                elif hook._context_var == "visitor":
                    context = self.visitor

            # Call hook with context if needed
            if context:
                # Check original function in case of decorators
                original_hook = getattr(hook, "__wrapped__", hook)
                if inspect.iscoroutinefunction(
                    original_hook
                ) or asyncio.iscoroutinefunction(original_hook):
                    await hook(self, context)
                else:
                    hook(self, context)
            else:
                if inspect.iscoroutinefunction(hook):
                    await hook(self)
                else:
                    hook(self)
        except Exception as e:
            # Log hook errors but continue traversal
            self.response.setdefault("hook_errors", []).append(
                f"Hook {hook.__name__} failed: {str(e)}"
            )

    async def _process_exit_hooks(self):
        """Execute all registered exit hooks."""
        for attr in dir(self):
            try:
                method = getattr(self, attr)
                if method and hasattr(method, "_on_exit"):
                    if inspect.iscoroutinefunction(method):
                        await method()
                    else:
                        method()
            except AttributeError:
                continue

    async def visit(self, nodes: Union[Node, List[Node]]) -> list:
        """Add nodes to the traversal queue."""
        nodes_list = nodes if isinstance(nodes, list) else [nodes]
        self.queue.extend(nodes_list)
        return nodes_list


class TraversalPaused(Exception):
    """Raised to pause the traversal."""


# ----------------- DECORATORS -----------------


def on_visit(target_type=None):
    """Decorator for visit hooks that intelligently sets context variables."""

    def actual_decorator(func, t_type):
        func.__visit_target__ = t_type
        func._on_visit_target = t_type  # Backward compatibility

        # Preserve async nature and hook metadata
        is_async = inspect.iscoroutinefunction(func)
        orig_attrs = {
            "_context_var": getattr(func, "_context_var", None),
            "__visit_target__": getattr(func, "__visit_target__", None),
        }

        if is_async:

            @wraps(func)
            async def wrapper(*args, **kwargs):
                return await func(*args, **kwargs)

        else:

            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)

        # Copy hook metadata to wrapper
        for attr, value in orig_attrs.items():
            setattr(wrapper, attr, value)

        wrapper.__annotations__ = func.__annotations__
        wrapper.__signature__ = inspect.signature(func)
        return wrapper

    # Handle different decorator usage patterns
    if target_type is None:
        # Case 1: @on_visit or @on_visit()
        def decorator(func):
            return actual_decorator(func, None)

        return decorator

    if inspect.isclass(target_type) and issubclass(target_type, (Node, Edge, Walker)):
        # Case 2: @on_visit(RootNode)
        def decorator(func):
            return actual_decorator(func, target_type)

        return decorator

    if callable(target_type):
        # Case 3: @on_visit used without parentheses on a function
        return actual_decorator(target_type, None)

    raise ValueError(f"Invalid @on_visit target type: {type(target_type)}")


def _register_hook(cls, func):
    """Register visit hook with context-sensitive validation."""
    target_type = getattr(func, "__visit_target__", None)

    print(
        f"Registering {cls.__name__}.{func.__name__} for target: {target_type.__name__ if target_type else 'Any'}"
    )

    # Validate usage rules
    if issubclass(cls, Walker):
        if target_type and not (issubclass(target_type, (Node, Edge))):
            raise TypeError(
                f"Walker @on_visit must target Node/Edge, got {target_type.__name__}"
            )
    elif issubclass(cls, (Node, Edge)):
        if target_type and not issubclass(target_type, Walker):
            raise TypeError(
                f"Node/Edge @on_visit must target Walker, got {target_type.__name__}"
            )

    # For automatic context detection when no target specified
    if target_type is None:
        if issubclass(cls, Walker):
            # Walker methods get 'here' context
            func._context_var = "here"
        else:
            # Node/Edge methods get 'visitor' context
            func._context_var = "visitor"
    else:
        if issubclass(target_type, Walker):
            func._context_var = "visitor"
        else:
            func._context_var = "here"

    return func


def on_exit(func: Callable) -> Callable:
    """Decorate methods to execute when walker completes traversal."""
    if inspect.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await func(*args, **kwargs)

        async_wrapper._on_exit = True
        return async_wrapper
    else:

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            return func(*args, **kwargs)

        sync_wrapper._on_exit = True
        return sync_wrapper
