"""Edge class for jvspatial graph relationships."""

import inspect
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
from ..utils import find_subclass_by_name, generate_id
from .object import Object

if TYPE_CHECKING:
    from .node import Node

# Import Walker at runtime for __init_subclass__ validation
from .walker import Walker


class Edge(Object):
    """Graph edge connecting two nodes.

    Attributes:
        id: Unique identifier for the edge (protected - inherited from Object)
        source: Source node ID
        target: Target node ID
        bidirectional: Whether the edge is bidirectional
        _visit_hooks: Dict mapping target walker types to visit hook functions
        _is_visit_hook: Dict mapping method names to visit hook flags
    """

    type_code: str = attribute(transient=True, default="e")
    id: str = Field(..., description="Unique identifier for the edge")
    source: str
    target: str
    bidirectional: bool = True

    @classmethod
    def _get_top_level_fields(cls: Type["Edge"]) -> set:
        """Get top-level fields for Edge persistence format."""
        return {"source", "target", "bidirectional"}

    # Visit hooks for edges
    _visit_hooks: ClassVar[Dict[Optional[Type["Walker"]], List[Callable]]] = {}
    _is_visit_hook: ClassVar[Dict[str, bool]] = {}

    @property
    async def direction(self: "Edge") -> str:
        """Get the edge direction based on bidirectional flag.

        Returns:
            'both' if bidirectional, 'out' otherwise
        """
        return "both" if self.bidirectional else "out"

    def __init_subclass__(cls: Type["Edge"]) -> None:
        """Initialize subclass by registering visit hooks."""
        cls._visit_hooks = {}
        cls._is_visit_hook = {}

        for _, method in inspect.getmembers(cls, inspect.isfunction):
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
                                f"Edge @on_visit must target Walker types, got {target.__name__ if hasattr(target, '__name__') else target}",
                                details={
                                    "target_type": str(target),
                                    "expected_type": "Walker",
                                },
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

    def export(
        self: "Edge",
        exclude_transient: bool = True,
        exclude: Optional[Union[set, Dict[str, Any]]] = None,
        for_persistence: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Export edge to a dictionary.

        Uses the standard Object.export() method. By default, returns a clean
        flat dictionary suitable for API responses.
        Set for_persistence=True to get the nested database format.

        Args:
            exclude_transient: Whether to automatically exclude transient fields (default: True)
            exclude: Additional fields to exclude (can be a set of field names or a dict)
            for_persistence: If True, returns nested persistence format with id, name, context, source, target, bidirectional (default: False)
            **kwargs: Additional arguments passed to base export/model_dump()

        Returns:
            Dictionary representation of the edge:
            - If for_persistence=False: Clean flat dictionary (standard format)
            - If for_persistence=True: Nested format with id, name, context, source, target, bidirectional for database storage
        """
        if for_persistence:
            # Legacy persistence format - nested structure for database storage
            context = super().export(
                exclude={"id", "source", "target", "bidirectional"},
                exclude_none=False,
                exclude_transient=exclude_transient,
                **kwargs,
            )

            # Include _data if it exists
            if hasattr(self, "_data"):
                context["_data"] = self._data

            # Serialize datetime objects to ensure JSON compatibility
            from jvspatial.utils.serialization import serialize_datetime

            context = serialize_datetime(context)

            return {
                "id": self.id,
                "name": self.__class__.__name__,
                "context": context,
                "source": self.source,
                "target": self.target,
                "bidirectional": self.bidirectional,
            }
        else:
            # Standard export - clean flat dictionary for API responses
            # Exclude internal edge fields by default
            default_exclude = {"type_code", "_graph_context", "_data", "_initializing"}
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

    @classmethod
    async def get(cls: Type["Edge"], id: str) -> Optional["Edge"]:
        """Retrieve an edge from the database by ID.

        Args:
            id: ID of the edge to retrieve

        Returns:
            Edge instance if found, else None
        """
        from ..context import get_default_context

        context = get_default_context()
        from typing import cast as _cast

        return _cast(Optional[Edge], await context.get(cls, id))

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

        # Update connected nodes - use context to retrieve nodes
        from typing import cast

        from ..context import get_default_context

        # Lazy import to avoid circular dependency
        from .node import Node

        context = get_default_context()
        source_node = cast(
            Optional[Node],
            await context.get(Node, edge.source) if edge.source else None,
        )
        target_node = cast(
            Optional[Node],
            await context.get(Node, edge.target) if edge.target else None,
        )

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
        from typing import cast as _cast

        return _cast("Edge", await super().save())

    @classmethod
    async def all(cls: Type["Edge"]) -> List["Object"]:
        """Retrieve all edges from the database.

        Returns:
            List of edge instances
        """
        from ..context import get_default_context

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
