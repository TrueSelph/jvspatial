import inspect
import weakref
import asyncio
from contextlib import contextmanager
from functools import wraps
from pydantic import PrivateAttr
from typing import ClassVar, List, Optional, Type, Union, Callable
from collections import deque
from pydantic import BaseModel, Field, ConfigDict
from jvspatial.db.database import Database
from .lib import generate_id

# ----------------- DECORATOR FUNCTIONS -----------------

def on_visit(target_type=None):
    """Decorator for visit hooks that intelligently sets context variables."""
    def actual_decorator(func, t_type):
        func.__visit_target__ = t_type
        func._on_visit_target = t_type  # Backward compatibility
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
        for attr, value in orig_attrs.items():
            setattr(wrapper, attr, value)
        wrapper.__annotations__ = func.__annotations__
        wrapper.__signature__ = inspect.signature(func)
        return wrapper

    if target_type is None:
        def decorator(func):
            return actual_decorator(func, None)
        return decorator

    if inspect.isclass(target_type) and issubclass(target_type, (Node, Edge, Walker)):
        def decorator(func):
            return actual_decorator(func, target_type)
        return decorator

    if callable(target_type):
        return actual_decorator(target_type, None)

    raise ValueError(f"Invalid @on_visit target type: {type(target_type)}")

def _register_hook(cls, func):
    """Register visit hook with context-sensitive validation."""
    target_type = getattr(func, "__visit_target__", None)
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
    if target_type is None:
        if issubclass(cls, Walker):
            func._context_var = "here"
        else:
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

# ----------------- CORE CLASSES -----------------

class Object(BaseModel):
    """Base object with persistence capabilities."""

    id: str = Field(default="")
    db: ClassVar[Optional[Database]] = None
    type_code: ClassVar[str] = "o"
    _initializing: bool = PrivateAttr(default=True)

    model_config = ConfigDict(arbitrary_types_allowed=True, validate_assignment=True)

    @classmethod
    def set_db(cls, db: Database = None):
        """Override the default database with a custom instance"""
        cls.db = db

    @classmethod
    def get_db(cls) -> Database:
        """Get database adapter instance with automatic configuration"""
        if cls.db is None:
            from jvspatial.db.factory import get_database
            cls.db = get_database()
        return cls.db

    def __init__(self, **kwargs):
        self._initializing = True
        if "id" not in kwargs:
            kwargs["id"] = generate_id(self.type_code, self.__class__.__name__)
        super().__init__(**kwargs)
        self._initializing = False
        asyncio.create_task(self.save())

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        if not self._initializing and hasattr(self, "id") and name not in ["_initializing"]:
            asyncio.create_task(self.save())

    def export(self) -> dict:
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
        if self.type_code == 'n':
            collection = "node"
        elif self.type_code == 'e':
            collection = "edge"
        else:
            collection = "object"
        await self.get_db().save(collection, record)
        return self

    @classmethod
    async def get(cls, id: str):
        """Retrieve an object from the database by ID."""
        if cls.type_code == 'n':
            collection = "node"
        elif cls.type_code == 'e':
            collection = "edge"
        else:
            collection = "object"

        data = await cls.get_db().get(collection, id)
        if not data:
            return None
        obj = cls(id=data["id"], **data["context"])
        if "edges" in data:
            obj.edge_ids = data["edges"]
        return obj

    async def destroy(self, cascade: bool = True):
        """Delete the object and optionally related objects."""
        if self.type_code == 'n':
            collection = "node"
        elif self.type_code == 'e':
            collection = "edge"
        else:
            collection = "object"

        if cascade and self.type_code == 'n':
            await self._cascade_delete()
        await self.get_db().delete(collection, self.id)

class Edge(Object):
    """Graph edge connecting two nodes."""
    type_code: ClassVar[str] = "e"
    id: str = Field(default="")
    source: str
    target: str
    direction: str = "both"

    def __init__(
        self, left: Optional["Node"] = None, right: Optional["Node"] = None, **kwargs
    ):
        source = ""
        target = ""
        direction = kwargs.pop("direction", "out")

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

        super().__init__(
            id=generate_id("e", self.__class__.__name__),
            source=source,
            target=target,
            direction=direction,
            **kwargs,
        )

    def export(self) -> dict:
        context = self.model_dump(
            exclude={"id", "source", "target", "direction"}, exclude_none=False
        )
        return {
            "id": self.id,
            "name": self.__class__.__name__,
            "context": context,
            "source": self.source,
            "target": self.target,
            "bidirectional": self.direction == "both",
        }

    @classmethod
    async def get(cls, id: str):
        collection = "edge"
        data = await cls.get_db().get(collection, id)
        if not data:
            return None
        context = data["context"].copy()
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
        return await super().save()

    @classmethod
    async def all(cls) -> List["Edge"]:
        edges_data = await cls.get_db().find(cls.__name__, {})
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
        cls._visit_hooks = {}
        for name, method in inspect.getmembers(cls):
            if hasattr(method, "_on_visit_target"):
                registered_method = _register_hook(cls, method)
                target_type = registered_method._on_visit_target
                cls._visit_hooks[target_type] = registered_method

    @property
    def visitor(self) -> Optional["Walker"]:
        return self._visitor_ref() if self._visitor_ref else None

    @visitor.setter
    def visitor(self, value: "Walker"):
        self._visitor_ref = weakref.ref(value) if value else None

    async def connect(
        self, other: "Node", edge: Type["Edge"] = Edge, direction: str = "out", **kwargs
    ) -> "Edge":
        try:
            connection = edge(left=self, right=other, direction=direction, **kwargs)
            await connection.save()
            self.edge_ids.append(connection.id)
            other.edge_ids.append(connection.id)
            await self.save()
            await other.save()
            return connection
        except Exception as e:
            raise

    async def edges(self, direction: str = "out") -> List["Edge"]:
        edges = []
        for edge_id in self.edge_ids:
            edge = await Edge.get(edge_id)
            if edge:
                edges.append(edge)
        if direction == "out":
            return [e for e in edges if e.source == self.id]
        elif direction == "in":
            return [e for e in edges if e.target == self.id]
        else:
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
        unique_nodes = {}
        for node in nodes:
            unique_nodes[node.id] = node
        return NodeQuery(list(unique_nodes.values()), source=self)

    @classmethod
    async def all(cls) -> List["Node"]:
        nodes_data = await cls.get_db().find(cls.__name__, {})
        return [cls(**data) for data in nodes_data]

    def export(self) -> dict:
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
                    connectors = [e for e in connectors if e.type in edge_types]
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
    id: str = "n:RootNode:root"
    is_root: bool = True
    _lock: ClassVar[asyncio.Lock] = asyncio.Lock()

    @classmethod
    async def get(cls) -> "RootNode":
        async with cls._lock:
            node_data = await cls.get_db().get("node", "n:RootNode:root")
            if node_data:
                return cls(id=node_data["id"], **node_data["context"])
            node = cls(
                id="n:RootNode:root", is_root=True, edge_ids=[], _visitor_ref=None
            )
            await node.save()
            existing = await cls.get_db().get("node", "n:RootNode:root")
            if existing and existing["id"] != node.id:
                raise RuntimeError("Root node singleton violation detected")
            return node

class Walker(BaseModel):
    model_config = ConfigDict(extra="ignore")
    type_code: ClassVar[str] = "w"
    id: str = Field(default="")
    queue: deque = Field(default_factory=deque)
    response: dict = Field(default_factory=dict)
    current_node: Optional[Node] = None
    _visit_hooks: ClassVar[dict] = {}
    paused: bool = Field(default=False, exclude=True)

    def __init_subclass__(cls):
        cls._visit_hooks = {}
        for name, method in inspect.getmembers(cls):
            if hasattr(method, "_on_visit_target"):
                method = _register_hook(cls, method)
                cls._visit_hooks[method._on_visit_target] = method
        if issubclass(cls, (Node, Edge)):
            cls._visit_hooks = {}
            for name, method in inspect.getmembers(cls):
                if hasattr(method, "_on_visit_target"):
                    registered_method = _register_hook(cls, method)
                    target_type = registered_method._on_visit_target
                    cls._visit_hooks[target_type] = registered_method

    async def resume(self) -> "Walker":
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
            kwargs["id"] = generate_id(self.type_code, self.__class__.__name__)
        super().__init__(**kwargs)

    @property
    def here(self) -> Optional[Node]:
        return self.current_node

    @property
    def visitor(self) -> Optional["Walker"]:
        return self

    @contextmanager
    def visiting(self, node: Node):
        self.current_node = node
        node.visitor = self
        try:
            yield
        finally:
            node.visitor = None
            self.current_node = None

    async def spawn(self, start: Optional[Node] = None) -> "Walker":
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
        try:
            hooks = await self._get_hooks_for_node(node)
            for hook in hooks:
                await self._execute_hook(hook)
        except Exception as e:
            raise

    async def _get_hooks_for_node(self, node: Node) -> list:
        hooks = []
        node_type = type(node)
        walker_type = type(self)
        if node_type in self._visit_hooks:
            hooks.append(self._visit_hooks[node_type])
        if hasattr(node, "_visit_hooks"):
            if walker_type in node._visit_hooks:
                hooks.append(node._visit_hooks[walker_type])
            if None in node._visit_hooks:
                hooks.append(node._visit_hooks[None])
        return hooks

    async def _execute_hook(self, hook):
        try:
            context = None
            if hasattr(hook, "_context_var"):
                if hook._context_var == "here":
                    context = self.here
                elif hook._context_var == "visitor":
                    context = self.visitor
            if context:
                original_hook = getattr(hook, "__wrapped__", hook)
                if inspect.iscoroutinefunction(original_hook) or asyncio.iscoroutinefunction(original_hook):
                    await hook(self, context)
                else:
                    hook(self, context)
            else:
                if inspect.iscoroutinefunction(hook):
                    await hook(self)
                else:
                    hook(self)
        except Exception as e:
            self.response.setdefault("hook_errors", []).append(
                f"Hook {hook.__name__} failed: {str(e)}"
            )

    async def _process_exit_hooks(self):
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
        nodes_list = nodes if isinstance(nodes, list) else [nodes]
        self.queue.extend(nodes_list)
        return nodes_list

class TraversalPaused(Exception):
    """Raised to pause the traversal."""