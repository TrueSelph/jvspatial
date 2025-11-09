"""Walker class for jvspatial graph traversal."""

import asyncio
import inspect
import os
from collections import deque
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

from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from .node import Node
    from .edge import Edge

from jvspatial.exceptions import JVSpatialError

from ..annotations import AttributeMixin, attribute
from ..events import event_bus
from ..utils import generate_id
from .walker_components.event_system import WalkerEventSystem
from .walker_components.protection import TraversalProtection
from .walker_components.walker_queue import WalkerQueue
from .walker_components.walker_trail import WalkerTrail


class WalkerVisitingContext:
    """Context manager for visiting a node with a walker."""

    def __init__(
        self,
        walker: "Walker",
        node: Union["Node", "Edge"],
        edge_id: Optional[str] = None,
    ) -> None:
        """Initialize the visiting context.

        Args:
            walker: The walker instance
            node: The node to visit
            edge_id: Optional edge ID used to reach the node
        """
        self.walker = walker
        self.node = node
        self.edge_id = edge_id

    def __enter__(self) -> "WalkerVisitingContext":
        """Enter the visiting context."""
        # Set the current node
        self.walker.current_node = self.node
        # Set the visitor on the node (only if it's a Node)
        if hasattr(self.node, "set_visitor"):
            self.node.set_visitor(self.walker)
        # Record the visit in the trail
        self.walker._trail_tracker.record_step(
            node_id=self.node.id,
            edge_id=self.edge_id,
            timestamp=self.walker._trail_tracker.get_length() + 1,
            node_type=self.node.__class__.__name__,
            queue_length=len(self.walker.queue),
        )
        # Record the visit in the protection system
        self.walker._protection.record_visit(self.node.id)
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit the visiting context."""
        # Clear the current node
        self.walker.current_node = None
        # Clear the visitor on the node (only if it's a Node)
        if hasattr(self.node, "set_visitor"):
            self.node.set_visitor(None)


class Walker(AttributeMixin, BaseModel):
    """Base class for graph walkers that traverse nodes along edges.

    Walkers are designed to traverse the graph by visiting nodes and following edges.
    They maintain a queue of nodes to visit and can carry state and reports during traversal.
    They also track their traversal trail for path reconstruction and analysis.

    Infinite Walk Protection:
    Walkers include comprehensive protection against infinite loops and runaway traversals
    through multiple configurable limits and automatic halting mechanisms.

    Attributes:
        id: Unique walker ID (protected - cannot be modified after initialization)
        queue: Queue of nodes to visit (transient - not persisted)
        current_node: Currently visited node (transient - not persisted)
        paused: Whether traversal is paused (transient - not persisted)

        # Trail Tracking (all transient - not persisted)
        trail: Trail of visited node IDs in order (read-only)
        trail_edges: Trail of edge IDs traversed between nodes (read-only)
        trail_metadata: Additional metadata for each trail step (read-only)
        trail_enabled: Whether trail tracking is enabled (configurable)
        max_trail_length: Maximum trail length (0 = unlimited, configurable)

        # Infinite Walk Protection (all transient - runtime only)
        max_steps: Maximum number of steps before auto-halt (default: 10000)
        max_visits_per_node: Maximum visits per node before auto-halt (default: 100)
        max_execution_time: Maximum execution time in seconds (default: 300.0)
        max_queue_size: Maximum queue size before limiting additions (default: 1000)
        protection_enabled: Whether protection mechanisms are enabled (default: True)
        step_count: Current number of steps taken (read-only)
        node_visit_counts: Dictionary of per-node visit counts (read-only)
    """

    model_config = ConfigDict(extra="allow")
    type_code: str = attribute(transient=True, default="w")
    id: str = attribute(protected=True, description="Unique identifier for the walker")

    # Reporting system
    _report: List[Any] = attribute(private=True, default_factory=list)

    # Event system
    _event_handlers: Dict[str, List[Callable]] = attribute(
        private=True, default_factory=dict
    )

    # Walker core attributes
    _current_node: Optional[Union["Node", "Edge"]] = attribute(
        private=True, default=None
    )
    _visit_hooks: ClassVar[
        Dict[Union[Type[Union["Node", "Edge"]], str, None], List[Callable]]
    ] = {}
    _paused: bool = attribute(private=True, default=False)

    # Trail tracking
    _trail_tracker: WalkerTrail = attribute(private=True, default_factory=WalkerTrail)

    # Trail-related methods (sync for pure computations, async for I/O)
    def get_trail(self) -> List[str]:
        """Get the complete trail of visited nodes."""
        trail_data = self._trail_tracker.get_trail()
        result = []
        for step in trail_data:
            node = step.get("node")
            if node is not None and isinstance(node, str):
                result.append(node)
        return result

    async def get_trail_nodes(self) -> List["Node"]:
        """Get the nodes from the trail (requires database access)."""
        trail = self._trail_tracker.get_trail()
        nodes: List["Node"] = []
        if not trail:
            return nodes

        from ..context import get_default_context
        from .node import Node

        context = get_default_context()

        for step in trail:
            node_id = step.get("node")
            if node_id:
                node = await context.get(Node, node_id)
                if node:
                    nodes.append(node)
        return nodes

    def get_trail_path(self) -> List[str]:
        """Get the path of node IDs from the trail (pure computation)."""
        return self.get_trail()

    def get_trail_length(self) -> int:
        """Get the length of the trail (pure computation)."""
        return self._trail_tracker.get_length()

    def is_visited(self, node: Union[str, "Node", "Edge"]) -> bool:
        """Check if a node has been visited before (excluding current visit).

        Args:
            node: Node ID (str) or Node/Edge instance to check

        Returns:
            True if the node appears in the trail more than once (visited before),
            False if this is the first visit or not in trail

        Examples:
            # Check by node ID
            if walker.is_visited("n:City:abc123"):
                print("Already visited before")

            # Check by node instance
            if walker.is_visited(city_node):
                print("Already visited before")
        """
        # Extract node ID if node is an object
        node_id = node.id if hasattr(node, "id") else node

        # Get trail and extract node IDs
        trail = self.get_trail()
        node_ids = []
        for step in trail:
            if isinstance(step, dict):
                node_ids.append(step.get("node", ""))
            else:
                node_ids.append(str(step))

        # Check if node ID appears more than once
        # (meaning it was visited before this current visit)
        count = node_ids.count(node_id)
        return count > 1  # More than once means visited before

    def get_recent_trail(self, count: int) -> List[str]:
        """Get the most recent trail entries (pure computation)."""
        trail = self._trail_tracker.get_trail()
        recent_steps = trail[-count:] if count > 0 else []
        result = []
        for step in recent_steps:
            node = step.get("node")
            if node is not None and isinstance(node, str):
                result.append(node)
        return result

    def has_visited(self, node_id: str) -> bool:
        """Check if a node has been visited (pure computation)."""
        trail = self._trail_tracker._trail
        return any(step.get("node") == node_id for step in trail)

    async def get_visit_count(self, node_id: str) -> int:
        """Get the number of times a node has been visited (pure computation)."""
        trail = self._trail_tracker.get_trail()
        return sum(1 for step in trail if step.get("node") == node_id)

    async def detect_cycles(self) -> List[List[str]]:
        """Detect cycles in the trail (requires computation)."""
        cycles = await self._trail_tracker.detect_cycles()
        trail = self._trail_tracker.get_trail()
        cycle_paths = []
        for start_pos, end_pos in cycles:
            cycle_path = []
            for i in range(start_pos, end_pos + 1):
                node = trail[i].get("node")
                if node is not None and isinstance(node, str):
                    cycle_path.append(node)
            cycle_paths.append(cycle_path)
        return cycle_paths

    def get_trail_summary(self) -> Dict[str, Any]:
        """Get a summary of the trail (pure computation)."""
        trail = self._trail_tracker.get_trail()
        unique_nodes = {step.get("node") for step in trail if step.get("node")}
        # Simple cycle detection: if we have more steps than unique nodes, there might be cycles
        has_cycles = len(trail) > len(unique_nodes) if unique_nodes else False
        cycles_detected = 1 if has_cycles else 0

        return {
            "total_steps": len(trail),
            "length": len(trail),  # Alias for compatibility
            "unique_nodes": len(unique_nodes),
            "nodes": list(unique_nodes),
            "has_cycles": has_cycles,
            "cycles_detected": cycles_detected,
            "cycle_ranges": [("0", str(len(trail) - 1))] if has_cycles else [],
            "most_visited": None,  # Simple implementation for now
            "recent_nodes": [],  # Simple implementation for now
        }

    def clear_trail(self) -> None:
        """Clear the trail (pure computation)."""
        self._trail_tracker.clear_trail()

    # Decorator-applied class attributes
    _endpoint_path: ClassVar[Optional[str]] = None
    _endpoint_methods: ClassVar[List[str]] = []
    _endpoint_server: ClassVar[Optional[str]] = None
    _webhook_required: bool = False
    _hmac_secret: ClassVar[Optional[str]] = None
    _idempotency_key_field: ClassVar[Optional[str]] = None
    _idempotency_ttl_hours: ClassVar[int] = 24
    _async_processing: bool = False
    _path_key_auth: ClassVar[bool] = False
    _is_webhook: bool = False

    @classmethod
    def _get_node_class(cls) -> Type["Node"]:
        """Get Node class (lazy import to avoid circular dependency)."""
        from .node import Node

        return Node

    @classmethod
    def _get_edge_class(cls) -> Type["Edge"]:
        """Get Edge class (lazy import to avoid circular dependency)."""
        from .edge import Edge

        return Edge

    def __init__(self: "Walker", **kwargs: Any) -> None:
        """Initialize a walker with auto-generated ID if not provided."""
        if "id" not in kwargs:
            # Use class-level type_code or default from Field
            type_code = kwargs.get("type_code", "w")
            kwargs["id"] = generate_id(type_code, self.__class__.__name__)

        # Extract component configuration from kwargs (before super().__init__)
        max_steps = kwargs.pop(
            "max_steps", int(os.getenv("JVSPATIAL_WALKER_MAX_STEPS", "10000"))
        )
        max_visits_per_node = kwargs.pop(
            "max_visits_per_node",
            int(os.getenv("JVSPATIAL_WALKER_MAX_VISITS_PER_NODE", "100")),
        )
        max_execution_time = kwargs.pop(
            "max_execution_time",
            float(os.getenv("JVSPATIAL_WALKER_MAX_EXECUTION_TIME", "300.0")),
        )
        max_queue_size = kwargs.pop(
            "max_queue_size", int(os.getenv("JVSPATIAL_WALKER_MAX_QUEUE_SIZE", "1000"))
        )
        paused = kwargs.pop("paused", False)

        super().__init__(**kwargs)

        # Set instance attributes after BaseModel initialization
        self._max_execution_time = max_execution_time
        self._max_queue_size = max_queue_size
        self._paused = paused

        # Initialize reporting system
        self._report = []

        # Initialize event system
        self._event_handlers = {}
        self._register_event_handlers()

        # Initialize composition components
        self._queue: deque[Any] = deque()  # Create new deque for queue manager
        self.queue = WalkerQueue(backing_deque=self._queue, max_size=max_queue_size)
        # Trail is initialized as _trail_tracker class attribute
        self._protection = TraversalProtection(
            max_steps=max_steps,
            max_visits_per_node=max_visits_per_node,
            max_execution_time=max_execution_time,
        )
        self._walker_events = WalkerEventSystem()

        # Register with global event bus
        # Note: We need to register asynchronously, so we'll do it in spawn()

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
                            inspect.isclass(target)
                            and issubclass(
                                target, (cls._get_node_class(), cls._get_edge_class())
                            )
                        ):
                            # Store string targets for later resolution or class targets directly
                            if target not in cls._visit_hooks:
                                cls._visit_hooks[target] = []
                            cls._visit_hooks[target].append(method)
                        else:
                            raise TypeError(
                                f"Walker @on_visit must target Node/Edge types or string names, got {target.__name__ if hasattr(target, '__name__') else target}"
                            )

    def _register_event_handlers(self):
        """Register all @on_emit methods for event handling."""
        for _name, method in inspect.getmembers(self.__class__, inspect.isfunction):
            if hasattr(method, "_is_event_handler"):
                event_types = getattr(method, "_event_types", [])
                for event_type in event_types:
                    if event_type not in self._event_handlers:
                        self._event_handlers[event_type] = []
                    self._event_handlers[event_type].append(method)

    async def report(self, data: Any) -> None:
        """Add data to the walker's report.

        Args:
            data: Any data to add to the report
        """
        self._report.append(data)

    async def get_report(self) -> List[Any]:
        """Get the current report list.

        Returns:
            The list of all reported items
        """
        return self._report

    async def emit(
        self,
        event: str,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        """Emit event using the global event bus."""
        # Remove source_id from kwargs if it exists to avoid duplicate argument
        kwargs.pop("source_id", None)
        # Pass data as first argument after event_type, then source_id
        data = args[0] if args else None
        await event_bus.emit(event, data, source_id=self.id)

    @property
    def current_node(self: "Walker") -> Optional[Union["Node", "Edge"]]:
        """Get the current node or edge being visited."""
        return self._current_node

    @current_node.setter
    def current_node(self: "Walker", value: Optional[Union["Node", "Edge"]]) -> None:
        """Set the current node or edge being visited."""
        self._current_node = value

    @property
    def paused(self: "Walker") -> bool:
        """Get the paused state."""
        return self._paused

    @paused.setter
    def paused(self: "Walker", value: bool) -> None:
        """Set the paused state."""
        self._paused = value

    async def visiting(
        self: "Walker",
        node: Union["Node", "Edge"],
        edge_from_previous: Optional[str] = None,
    ) -> "WalkerVisitingContext":
        """Create a context manager for visiting a node.

        Args:
            node: The node to visit
            edge_from_previous: Optional edge ID from previous node

        Returns:
            Context manager for visiting the node
        """
        return WalkerVisitingContext(self, node, edge_from_previous)

    @property
    def step_count(self: "Walker") -> int:
        """Get current step count from protection."""
        return self._protection.step_count

    @property
    def node_visit_counts(self: "Walker") -> Dict[str, int]:
        """Get node visit counts from protection."""
        return self._protection.visit_counts

    @property
    def here(self: "Walker") -> Optional["Node"]:
        """Get the current node being visited.

        Returns:
            Current node if present, else None
        """
        cn = self.current_node
        # Use lazy import to avoid circular dependency
        from .node import Node

        return cn if isinstance(cn, Node) else None

    @property
    def visitor(self: "Walker") -> Optional["Walker"]:
        """Get the walker instance itself (as visitor).

        With the visitor property, nodes can call methods on the walker that's visiting them,
        enabling a conversation between the node and walker during traversal.

        Returns:
            The walker instance
        """
        return self

    async def visit(self: "Walker", nodes: Union["Node", List["Node"]]) -> list:
        """Add nodes to the traversal queue for later processing.

        Args:
            nodes: Node or list of nodes to visit

        Returns:
            List of nodes added to the queue
        """
        return await self.append(nodes)

    async def dequeue(
        self: "Walker", nodes: Union["Node", List["Node"]]
    ) -> List["Node"]:
        """Remove specified node(s) from the walker's queue.

        Args:
            nodes: Node or list of nodes to remove from queue

        Returns:
            List of nodes that were successfully removed from the queue
        """
        return await self.queue.dequeue(nodes)  # type: ignore[return-value]

    async def prepend(
        self: "Walker", nodes: Union["Node", List["Node"]]
    ) -> List["Node"]:
        """Add node(s) to the head of the queue.

        Args:
            nodes: Node or list of nodes to add to the beginning of the queue

        Returns:
            List of nodes added to the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]

        await self.queue.prepend(nodes_list)
        return nodes_list

    async def append(
        self: "Walker", nodes: Union["Node", List["Node"]]
    ) -> List["Node"]:
        """Add node(s) to the end of the queue.

        Args:
            nodes: Node or list of nodes to add to the end of the queue

        Returns:
            List of nodes added to the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]
        await self.queue.append(nodes_list)
        return nodes_list

    async def add_next(
        self: "Walker", nodes: Union["Node", List["Node"]]
    ) -> List["Node"]:
        """Add node(s) to the front of the queue in the order provided.

        Args:
            nodes: Node or list of nodes to add to the front of the queue

        Returns:
            List of nodes added to the queue
        """
        nodes_list = nodes if isinstance(nodes, list) else [nodes]
        await self.queue.add_next(nodes_list)
        return nodes_list

    async def get_queue(self: "Walker") -> List[Union["Node", "Edge"]]:
        """Return the entire queue as a list.

        Returns:
            List of all nodes and edges currently in the queue
        """
        from .edge import Edge
        from .node import Node

        return [item for item in self.queue.to_list() if isinstance(item, (Node, Edge))]

    async def clear_queue(self: "Walker") -> None:
        """Clear the queue of all nodes."""
        await self.queue.clear()

    async def is_queued(self: "Walker", node: Union["Node", "Edge"]) -> bool:
        """Check if a node is in the queue.

        Args:
            node: The node to check

        Returns:
            True if the node is in the queue, False otherwise
        """
        return node in self.queue

    async def insert_after(
        self: "Walker",
        target_node: Union["Node", "Edge"],
        nodes: List[Union["Node", "Edge"]],
    ) -> List[Union["Node", "Edge"]]:
        """Insert nodes after a target node in the queue.

        Args:
            target_node: The node to insert after
            nodes: Nodes to insert

        Returns:
            List of inserted nodes
        """
        from .edge import Edge
        from .node import Node

        result = await self.queue.insert_after(target_node, nodes)
        return [item for item in result if isinstance(item, (Node, Edge))]

    async def insert_before(
        self: "Walker",
        target_node: Union["Node", "Edge"],
        nodes: List[Union["Node", "Edge"]],
    ) -> List[Union["Node", "Edge"]]:
        """Insert nodes before a target node in the queue.

        Args:
            target_node: The node to insert before
            nodes: Nodes to insert

        Returns:
            List of inserted nodes
        """
        from .edge import Edge
        from .node import Node

        result = await self.queue.insert_before(target_node, nodes)
        return [item for item in result if isinstance(item, (Node, Edge))]

    async def run(self: "Walker") -> List[Any]:
        """Run the walker traversal.

        Returns:
            List of all reported items
        """
        # Reset protection state
        await self._protection.reset()

        # Process queue until empty or paused
        while self.queue and not self._paused:
            try:
                # Check protection limits
                if not await self._protection.check_limits():
                    break

                # Get next node from queue
                from .edge import Edge
                from .node import Node

                current = self.queue.popleft()
                if not isinstance(current, (Node, Edge)):
                    continue
                self.current_node = current

                # Record visit in protection
                if hasattr(current, "id"):
                    self._protection.record_visit(current.id)

                # Record step in trail
                self._trail_tracker.record_step(
                    current.id if hasattr(current, "id") else str(current)
                )

                # Increment step count
                await self._protection.increment_step()

                # Execute visit hooks
                await self._execute_visit_hooks(current)

            except Exception as e:
                # Handle errors gracefully
                await self.report(f"Error during traversal: {e}")
                break

        return await self.get_report()

    async def _execute_visit_hooks(self, target: Union["Node", "Edge"]) -> None:
        """Execute visit hooks for the target.

        Args:
            target: Node or Edge being visited
        """
        target_type = type(target)
        target_name = target_type.__name__

        # Get hooks for this specific type
        hooks = list(self._visit_hooks.get(target_type, []))

        # Include hooks registered for base classes (support subclass matching)
        for base in target_type.mro()[1:]:  # skip the exact class (already added)
            if base in self._visit_hooks:
                hooks.extend(self._visit_hooks.get(base, []))

        # Get hooks for string name (forward references)
        hooks.extend(self._visit_hooks.get(target_name, []))

        # Get general hooks (None key)
        hooks.extend(self._visit_hooks.get(None, []))

        # Execute hooks (ensure stable order and no duplicates)
        seen = set()
        for hook in hooks:
            if hook in seen:
                continue
            seen.add(hook)
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(self, target)
                else:
                    hook(self, target)
            except Exception as e:
                # Check if this is a skip exception
                if "Node skipped" in str(e):
                    # Skip this node and continue
                    return
                else:
                    # Report error as structured data
                    await self.report(
                        {
                            "hook_error": str(e),
                            "hook_name": hook.__name__,
                            "node_id": getattr(target, "id", str(target)),
                        }
                    )

    async def _execute_exit_hooks(self) -> None:
        """Execute all @on_exit decorated methods."""
        for _name, method in inspect.getmembers(self.__class__, inspect.isfunction):
            if hasattr(method, "_on_exit") and method._on_exit:
                try:
                    if asyncio.iscoroutinefunction(method):
                        await method(self)
                    else:
                        method(self)
                except Exception as e:
                    await self.report(f"Error in exit hook: {e}")

    async def spawn(
        self, start_node: Optional[Union["Node", "Edge"]] = None
    ) -> "Walker":
        """Spawn a new walker instance and start traversal from the given node.

        Args:
            start_node: The node to start traversal from (defaults to root if not provided)

        Returns:
            The walker instance (self)
        """
        # Register with global event bus
        await event_bus.register_entity(self)

        # If no start_node provided, default to root
        if start_node is None:
            from .root import Root

            start_node = await Root.get(None)  # type: ignore[assignment]

        # Add the start node to the queue and begin traversal
        # Only add if not already in queue to avoid duplicates
        if start_node not in self.queue._backing:
            await self.queue.append([start_node])
        await self.run()
        # Execute exit hooks
        await self._execute_exit_hooks()
        return self

    async def skip(self) -> None:
        """Skip the current node and continue traversal.

        This method allows the walker to skip processing the current node
        and continue with the next node in the queue.
        """
        # Raise an exception to stop current node processing
        raise JVSpatialError("Node skipped")

    def pause(self, message: str = "Traversal paused") -> None:
        """Pause the walker's traversal.

        The walker will stop processing new nodes until resume() is called.

        Args:
            message: Optional message describing why the traversal was paused
        """
        self._paused = True
        # Raise exception to indicate pause
        from jvspatial.exceptions import WalkerError

        raise WalkerError(message)

    async def resume(self) -> "Walker":
        """Resume the walker's traversal.

        The walker will continue processing nodes from where it left off.

        Returns:
            The walker instance for chaining
        """
        self._paused = False
        # Continue processing the queue
        await self.run()
        return self

    async def disengage(self) -> "Walker":
        """Disengage the walker from traversal.

        This stops the walker and clears its queue.

        Returns:
            The walker instance for chaining
        """
        self._paused = True
        # Clear visitor from current node
        if self.current_node and hasattr(self.current_node, "set_visitor"):
            self.current_node.set_visitor(None)
        self.current_node = None
        await self.queue.clear()
        return self

    def export(
        self: "Walker",
        exclude_transient: bool = True,
        exclude: Optional[Union[set, Dict[str, Any]]] = None,
        for_persistence: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Export walker to a dictionary.

        Uses the standard Object.export() method. By default, returns a clean
        flat dictionary suitable for API responses.
        Set for_persistence=True to get the nested database format.

        Args:
            exclude_transient: Whether to automatically exclude transient fields (default: True)
            exclude: Additional fields to exclude (can be a set of field names or a dict)
            for_persistence: If True, returns nested persistence format with id, name, context (default: False)
            **kwargs: Additional arguments passed to base export/model_dump()

        Returns:
            Dictionary representation of the walker:
            - If for_persistence=False: Clean flat dictionary (standard format)
            - If for_persistence=True: Nested format with id, name, context for database storage
        """
        if for_persistence:
            # Legacy persistence format - nested structure for database storage
            context_data = super().export(
                exclude={
                    "id",
                    "_report",
                    "_event_handlers",
                    "_current_node",
                    "_paused",
                    "_queue",
                    "queue",
                },
                exclude_none=False,
                exclude_transient=exclude_transient,
                **kwargs,
            )

            # Include _data if it exists
            if hasattr(self, "_data"):
                context_data["_data"] = self._data

            return {
                "id": self.id,
                "name": self.__class__.__name__,
                "context": context_data,
            }
        else:
            # Standard export - clean flat dictionary for API responses
            # Exclude internal walker fields by default
            default_exclude = {
                "type_code",
                "_graph_context",
                "_data",
                "_initializing",
                "_report",
                "_event_handlers",
                "_current_node",
                "_paused",
                "_queue",
                "queue",
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
