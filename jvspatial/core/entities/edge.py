"""Edge class for jvspatial graph relationships."""

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
    source: str
    target: str
    bidirectional: bool = True

    @classmethod
    def _get_top_level_fields(cls: Type["Edge"]) -> set:
        """Get top-level fields for Edge persistence format."""
        return {"source", "target", "bidirectional"}

    # Visit hooks for edges
    _visit_hooks: ClassVar[
        Dict[Union[Optional[Type["Walker"]], str], List[Callable]]
    ] = {}
    _is_visit_hook: ClassVar[Dict[str, bool]] = {}

    @property
    async def direction(self: "Edge") -> str:
        """Get the edge direction based on bidirectional flag.

        Returns:
            'both' if bidirectional, 'out' otherwise
        """
        return "both" if self.bidirectional else "out"

    def __init_subclass__(cls: Type["Edge"], **kwargs: Any) -> None:
        """Initialize subclass by registering visit hooks.

        Forwards through ``super().__init_subclass__`` so
        ``AttributeMixin.__init_subclass__`` runs (audit §6.2). The
        visit-hook collection logic itself is shared with ``Node`` via
        ``_visit_hooks.register_visit_hooks``.
        """
        super().__init_subclass__(**kwargs)
        from ._visit_hooks import register_visit_hooks

        cls._visit_hooks = register_visit_hooks(cls, label="Edge")
        cls._is_visit_hook = {}

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
            kwargs["id"] = generate_id("e", self.__class__._entity_name())

        kwargs.update(
            {"source": source, "target": target, "bidirectional": bidirectional}
        )

        # Call super().__init__() first to initialize Pydantic model (including __pydantic_private__)
        # The Object.__init__ will set _initializing = True, then False after initialization
        super().__init__(**kwargs)

    async def export(
        self: "Edge",
        exclude_transient: bool = True,
        exclude: Optional[Union[set, Dict[str, Any]]] = None,
        flat: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Export edge to a dictionary.

        Returns a nested persistence format with id, name, context, source, target, bidirectional
        for database storage. Includes all fields from the class hierarchy (class and parent classes, not child classes).

        Args:
            exclude_transient: Whether to automatically exclude transient fields (default: True)
            exclude: Additional fields to exclude (can be a set of field names or a dict)
            flat: If True, return attributes at top level instead of nested under context (for API responses)
            **kwargs: Additional arguments passed to base export/model_dump()

        Returns:
            Nested format dictionary with id, name, context, source, target, bidirectional for database storage,
            or flat format {id, entity, source, target, bidirectional, **context} when flat=True
        """
        # Nested persistence format - structure for database storage
        # Exclude source, target, bidirectional from context (id and type_code are transient and auto-excluded)
        # Object.export() returns nested format, extract the context
        parent_export = await super().export(
            exclude={"source", "target", "bidirectional"},
            exclude_none=False,
            exclude_transient=exclude_transient,
            **kwargs,
        )

        # Extract context from nested format (Object.export() returns {id, entity, context})
        context = parent_export["context"]

        # Serialize datetime objects to ensure JSON compatibility
        from jvspatial.utils.serialization import serialize_datetime

        context = serialize_datetime(context)

        if flat:
            return {
                "id": self.id,
                "entity": self.entity,
                "source": self.source,
                "target": self.target,
                "bidirectional": self.bidirectional,
                **context,
            }
        return {
            "id": self.id,
            "entity": self.entity,
            "context": context,
            "source": self.source,
            "target": self.target,
            "bidirectional": self.bidirectional,
        }

    @classmethod
    def get_indexes(cls: Type["Edge"]) -> List[Dict[str, Any]]:
        """Default indexes for every edge collection.

        ``idx_source_target_entity_unique`` enforces edge uniqueness and serves
        outgoing traversal via leftmost-prefix on ``source``. The remaining
        indexes cover traversal shapes the unique index cannot:

        - ``idx_target_entity`` — incoming traversal (``direction="in"``).
        - ``idx_entity_source`` / ``idx_entity_target`` — typed-edge sweeps
          that filter by ``entity`` without pinning a node.

        All four are domain-agnostic — they only reference fields every Edge
        document carries (``entity``, ``source``, ``target``).
        """
        indexes = super().get_indexes()
        indexes.append(
            {
                "fields": [("source", 1), ("target", 1), ("entity", 1)],
                "unique": True,
                "name": "idx_source_target_entity_unique",
            }
        )
        indexes.append(
            {
                "fields": [("target", 1), ("entity", 1)],
                "unique": False,
                "name": "idx_target_entity",
            }
        )
        indexes.append(
            {
                "fields": [("entity", 1), ("source", 1)],
                "unique": False,
                "name": "idx_entity_source",
            }
        )
        indexes.append(
            {
                "fields": [("entity", 1), ("target", 1)],
                "unique": False,
                "name": "idx_entity_target",
            }
        )
        return indexes

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
        """Create and save a new edge instance.

        Node ``edge_ids`` updates are handled by ``Node.connect()``, which is
        the canonical entry-point for creating edges between nodes.  Callers
        that create edges directly must update ``edge_ids`` themselves (or use
        ``GraphContext.atomic_add_edge_id``).

        Args:
            **kwargs: Edge attributes including 'left' and 'right' nodes

        Returns:
            Created and saved edge instance
        """
        edge = cls(**kwargs)
        await edge.save()
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

            # Handle subclass instantiation based on stored entity
            stored_entity = data.get("entity", cls._entity_name())
            target_class = find_subclass_by_name(cls, stored_entity) or cls

            context_data = {
                k: v
                for k, v in data["context"].items()
                if k not in ["source", "target", "bidirectional"]
            }

            edge = target_class(
                id=data["id"],
                source=source,
                target=target,
                bidirectional=bidirectional,
                **context_data,
            )

            edges.append(edge)
        return edges
