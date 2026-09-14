"""Node class for jvspatial graph entities."""

import logging
import weakref
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    ClassVar,
    Dict,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

from jvspatial.db.database import finalize_find_results

from ..annotations import attribute
from .edge import Edge
from .object import Object

# Import Walker at runtime for __init_subclass__ validation
from .walker import Walker

if TYPE_CHECKING:
    from ..context import GraphContext

logger = logging.getLogger(__name__)

# Record paths at the top level of node / edge documents. Any other bare
# property name in a neighbour filter refers to ``context.<name>`` — the same
# attribute ``_matches_property_filter`` reads.
_NODE_TOP_LEVEL_KEYS = frozenset({"id", "entity"})
_EDGE_TOP_LEVEL_KEYS = frozenset({"id", "entity", "source", "target", "bidirectional"})

# (edge_entities, edge_query, node_entities, node_query) — ``None`` entities
# mean "any type", ``None`` queries mean "no property filter".
NeighborSpec = Tuple[
    Optional[List[str]],
    Optional[Dict[str, Any]],
    Optional[List[str]],
    Optional[Dict[str, Any]],
]


def _record_query(criteria: Dict[str, Any], top_level: frozenset) -> Dict[str, Any]:
    """Map attribute-style criteria (``population``) to record paths (``context.population``)."""
    return {
        (
            key
            if key.startswith(("context.", "$")) or key in top_level
            else f"context.{key}"
        ): value
        for key, value in criteria.items()
    }


def _entity_name_of(cls: type) -> str:
    resolver = getattr(cls, "_entity_name", None)
    return resolver() if callable(resolver) else cls.__name__


def _node_class_entities(cls: type) -> Optional[List[str]]:
    """Entity names ``isinstance(x, cls)`` accepts: ``cls`` and every loaded subclass.

    ``None`` for the ``Node`` base itself, which every node matches.
    """
    if cls is Node:
        return None
    names = set()
    stack: List[type] = [cls]
    seen: set = set()
    while stack:
        klass = stack.pop()
        if klass in seen:
            continue
        seen.add(klass)
        names.add(_entity_name_of(klass))
        stack.extend(klass.__subclasses__())
    return sorted(names)


def _neighbor_filter_spec(
    flt: Any, *, node_side: bool
) -> Tuple[Optional[List[str]], Optional[Dict[str, Any]]]:
    """Normalise a ``nodes()`` node / edge filter to ``(entities, query)``.

    Accepts a name, a class, or a list of names, classes and
    ``{name: criteria}`` dicts. Node classes match subclasses (``isinstance``
    semantics); edge classes, names and dict keys match exactly. Criteria
    dicts become an ``$or`` of ``{"entity": name, <record-path criteria>}``
    branches, alongside ``{"entity": {"$in": [...]}}`` for plain items.
    """
    if flt is None:
        return None, None
    items = list(flt) if isinstance(flt, (list, tuple)) else [flt]
    if not items and not node_side:
        return None, None  # ``edge=[]`` has always meant "any edge type"
    top_level = _NODE_TOP_LEVEL_KEYS if node_side else _EDGE_TOP_LEVEL_KEYS
    entities: List[str] = []
    branches: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, str):
            entities.append(item)
        elif isinstance(item, type):
            if not node_side:
                entities.append(_entity_name_of(item))
                continue
            names = _node_class_entities(item)
            if names is None:
                return None, None
            entities.extend(names)
        elif isinstance(item, dict):
            for name, criteria in item.items():
                entity = name if isinstance(name, str) else _entity_name_of(name)
                branches.append(
                    {"entity": entity, **_record_query(dict(criteria or {}), top_level)}
                )
        else:
            side = "node" if node_side else "edge"
            raise TypeError(f"unsupported {side} filter item: {item!r}")
    entities = sorted(set(entities))
    if not branches:
        return entities, None
    if entities:
        branches.append({"entity": {"$in": entities}})
    return None, {"$or": branches}


def _deserialize_hint(node_filter: Any) -> type:
    """Class to hydrate neighbours as when the filter names exactly one class.

    ``_deserialize_entity`` resolves the stored ``entity`` against this
    class's subtree first, so when two Node subclasses share an entity name
    (an app ``User`` and an embedded-agent ``User``) the row hydrates as the
    class the caller asked for rather than the first global name match.
    """
    if isinstance(node_filter, type):
        return node_filter
    if (
        isinstance(node_filter, (list, tuple))
        and len(node_filter) == 1
        and isinstance(node_filter[0], type)
    ):
        return node_filter[0]
    return Node


class Node(Object):
    """Graph node with visitor tracking and connection capabilities.

    Attributes:
        id: Unique identifier for the node (protected - inherited from Object)
        visitor: Current walker visiting the node (transient - not persisted)
    """

    type_code: str = attribute(transient=True, default="n")
    _visitor_ref: Optional[weakref.ReferenceType] = attribute(
        private=True, default=None
    )
    _visit_hooks: ClassVar[
        Dict[Union[Optional[Type["Walker"]], str], List[Callable]]
    ] = {}

    @classmethod
    def _get_top_level_fields(cls: Type["Node"]) -> set:
        """Get top-level fields for Node persistence format."""
        return {"id"}

    @classmethod
    def get_indexes(cls: Type["Node"]) -> List[Dict[str, Any]]:
        """Default node indexes.

        Adds an index on the top-level ``entity`` discriminator. Every typed
        find (``ClassName.find(...)`` / ``GraphContext.find_by_class(...)``)
        is rewritten to ``{"entity": "<ClassName>", ...}``, so this index is
        the universal first cut for any multi-type node collection. Generic
        — it only touches fields jvspatial itself attaches to every node
        document.
        """
        indexes = super().get_indexes()
        indexes.append(
            {
                "field": "entity",
                "unique": False,
                "direction": 1,
                "name": "idx_node_entity",
            }
        )
        return indexes

    def __init_subclass__(cls: Type["Node"], **kwargs: Any) -> None:
        """Initialize subclass by registering visit hooks.

        Forwards through ``super().__init_subclass__`` so
        ``AttributeMixin.__init_subclass__`` runs and registers
        ``protected`` / ``transient`` / ``private`` attribute metadata
        for Node subclasses (audit §6.1). The visit-hook collection logic
        itself is shared with ``Edge`` via ``_visit_hooks.register_visit_hooks``.
        """
        super().__init_subclass__(**kwargs)
        from ._visit_hooks import register_visit_hooks

        cls._visit_hooks = register_visit_hooks(cls, label="Node")

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

        # The edge row is the adjacency — node rows are never rewritten.
        if matching_edge:
            return matching_edge

        # No existing edge found, create a new one
        try:
            connection = await edge.create(
                source=self.id, target=other.id, direction=direction, **kwargs
            )
        except Exception as e:
            if "duplicate" in str(e).lower() or "E11000" in str(e):
                # Concurrent connect() created the edge first; retrieve it
                retry_edges = await context.find_edges_between(
                    source_id=self.id,
                    target_id=other.id,
                    edge_class=edge,
                )
                if retry_edges:
                    return retry_edges[0]
            raise

        return connection

    async def edges(
        self: "Node", direction: str = "", limit: Optional[int] = None
    ) -> List["Edge"]:
        """Get edges connected to this node.

        Queries the edge collection by ``source`` / ``target`` — index-backed
        on SQL backends, one round trip.

        Args:
            direction: Filter edges by direction ('in', 'out', 'both')
            limit: Maximum number of edges to return (default: all)

        Returns:
            List of edge instances
        """
        context = await self.get_context()

        query: Dict[str, Any]
        if direction == "out":
            query = {"source": self.id}
        elif direction == "in":
            query = {"target": self.id}
        else:
            query = {"$or": [{"source": self.id}, {"target": self.id}]}
        rows = await context.database.find("edge", query, limit=limit)
        if limit is None and len(rows) > 10_000:
            logger.debug(
                "Node.edges(%s) loaded %d edges; pass limit= or use "
                "connection_count() for hub nodes",
                self.id,
                len(rows),
            )
        derived: List["Edge"] = []
        for row in rows:
            edge_obj = await context._deserialize_entity(Edge, row)
            if edge_obj:
                derived.append(edge_obj)
        return derived

    async def _incident_edges(self: "Node", context: "GraphContext") -> List["Edge"]:
        """Every edge touching this node, either endpoint (used by cascade delete)."""
        return await self.edges()

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

    @classmethod
    async def nodes_bulk(
        cls,
        node_ids: List[str],
        *,
        direction: str = "out",
        edge: Optional[List[Union[str, Type["Edge"]]]] = None,
        node: Optional[List[Union[str, Type["Node"]]]] = None,
        edge_filter: Optional[Dict[str, Any]] = None,
        node_filter: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
        limit_per_source: Optional[int] = None,
    ) -> Dict[str, List["Node"]]:
        """Batch version of ``nodes()`` for many source IDs.

        Returns a mapping of ``source_id -> connected nodes`` using a single
        edge-query pass in the active GraphContext. ``limit_per_source`` caps
        the neighbours per source (one windowed query on Postgres).
        """
        from ..context import get_default_context

        context = get_default_context()
        return await context.nodes_bulk(
            node_ids,
            direction=direction,
            edge=edge,
            node=node,
            edge_filter=edge_filter,
            node_filter=node_filter,
            limit=limit,
            limit_per_source=limit_per_source,
        )

    async def neighborhood(
        self,
        depth: int = 1,
        *,
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
        """Return all nodes reachable within ``depth`` hops from this node.

        Uses the backend ``traverse`` implementation when available (single
        round trip on Postgres); otherwise falls back to a Python BFS using
        :meth:`nodes` per hop.
        """
        from ..context import get_default_context
        from .edge import Edge

        if depth < 1:
            return []

        context = get_default_context()
        db = context.database
        traverse = getattr(db, "traverse", None)

        use_traverse = (
            callable(traverse)
            and not kwargs
            and node is None
            and direction in ("out", "in", "both")
            and not isinstance(edge, list)
        )

        if use_traverse:
            edge_coll = context._get_collection_name(
                context._get_entity_type_code(Edge)
            )

            try:
                rows = await traverse(
                    edge_coll,
                    self.id,
                    direction=direction,
                    max_depth=depth,
                    limit=limit,
                )
            except NotImplementedError:
                use_traverse = False
            else:
                node_ids = [row["node_id"] for row in rows]
                if not node_ids:
                    return []
                return await context.get_batch(Node, node_ids)

        # Python BFS fallback (all backends).
        seen: set = {self.id}
        frontier: List["Node"] = [self]
        collected: List["Node"] = []
        for _ in range(depth):
            next_frontier: List["Node"] = []
            for current in frontier:
                neighbors = await current.nodes(
                    direction=direction,
                    node=node,
                    edge=edge,
                    limit=limit,
                    **kwargs,
                )
                for nb in neighbors:
                    if nb.id in seen:
                        continue
                    seen.add(nb.id)
                    collected.append(nb)
                    next_frontier.append(nb)
            frontier = next_frontier
            if not frontier:
                break
        return collected

    async def count_neighbors(
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
    ) -> int:
        """Count neighbors (same filters as :meth:`nodes`) — alias of :meth:`count_nodes`.

        Named ``count_neighbors`` so this does not shadow :meth:`Object.count` on
        Node subclasses (e.g. ``User.count(query)`` remains the DB count API).

        Returns:
            Number of matching connected nodes.
        """
        return await self.count_nodes(
            direction=direction, node=node, edge=edge, **kwargs
        )

    async def count_nodes(
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
    ) -> int:
        """Count neighbours matching the same filters as :meth:`nodes`.

        One ``COUNT`` round trip on backends with ``count_connected_nodes``
        (Postgres, MongoDB, SQLite); elsewhere the neighbours are listed and
        counted. Use this instead of ``len(await node.nodes(...))``, which
        hydrates every neighbour.

        Returns:
            Number of distinct matching neighbours.
        """
        context = await self.get_context()
        spec = self._neighbor_spec(node, edge, kwargs)
        counter = getattr(context.database, "count_connected_nodes", None)
        if callable(counter):
            edge_entities, edge_query, node_entities, node_query = spec
            try:
                return int(
                    await counter(
                        context._get_collection_name("n"),
                        context._get_collection_name("e"),
                        self.id,
                        direction=direction,
                        edge_entities=edge_entities,
                        node_entities=node_entities,
                        edge_query=edge_query,
                        node_query=node_query,
                    )
                )
            except NotImplementedError as exc:
                logger.debug("count_nodes(): no pushdown (%s); listing instead", exc)
        return len(await self._neighbors(context, direction=direction, spec=spec))

    async def nodes_page(
        self,
        *,
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
        sort: Optional[List[Tuple[str, int]]] = None,
        cursor: Optional[str] = None,
        limit: int = 20,
        **kwargs: Any,
    ) -> Tuple[List["Node"], Optional[str]]:
        """One keyset-paginated page of neighbours: ``(nodes, next_cursor)``.

        Same filters as :meth:`nodes`. ``sort`` takes record paths
        (``[("context.created_at", -1)]``; default ``[("id", 1)]``, with ``id``
        appended as tiebreaker). Pass ``next_cursor`` back as ``cursor`` for
        the next page; ``None`` means there are no more. Neighbours inserted
        before the cursor never shift later pages. Cursors use the same
        opaque encoding as :meth:`GraphContext.find_page`.
        """
        from ..pager import (
            decode_keyset_cursor,
            encode_keyset_cursor,
            keyset_filter,
            keyset_sort_fields,
        )

        context = await self.get_context()
        page_limit = max(1, int(limit))
        sort_fields = keyset_sort_fields(sort)
        edge_entities, edge_query, node_entities, node_query = self._neighbor_spec(
            node, edge, kwargs
        )
        after = keyset_filter(sort_fields, decode_keyset_cursor(cursor))
        if after is not None:
            node_query = after if node_query is None else {"$and": [node_query, after]}
        found = await self._neighbors(
            context,
            direction=direction,
            spec=(edge_entities, edge_query, node_entities, node_query),
            deserialize_as=_deserialize_hint(node),
            sort=sort_fields,
            limit=page_limit + 1,
        )
        page = found[:page_limit]
        next_cursor = None
        if len(found) > page_limit and page:
            next_cursor = encode_keyset_cursor(await page[-1].export(), sort_fields)
        return page, next_cursor

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
        """Find connected nodes matching the node / edge filters.

        Every filter shape is normalised to entity lists plus record-path
        queries (:func:`_neighbor_filter_spec`) and pushed to the backend's
        ``find_connected_nodes`` in one round trip — ``limit`` included — when
        it has one. Otherwise (or when a criterion does not translate) the
        Python path still applies every filter; nothing is dropped.

        Args:
            context: GraphContext instance for database operations
            direction: Connection direction ('out', 'in', 'both')
            node_filter: Node filtering criteria
            edge_filter: Edge filtering criteria
            limit: Maximum number of nodes to return
            **kwargs: Simple property filters for connected nodes

        Returns:
            List of connected nodes matching the criteria (each at most once)
        """
        return await self._neighbors(
            context,
            direction=direction,
            spec=self._neighbor_spec(node_filter, edge_filter, kwargs),
            deserialize_as=_deserialize_hint(node_filter),
            limit=limit,
        )

    @staticmethod
    def _neighbor_spec(
        node_filter: Any, edge_filter: Any, properties: Dict[str, Any]
    ) -> NeighborSpec:
        """Normalise ``nodes()``-style filters plus property kwargs to a spec."""
        edge_entities, edge_query = _neighbor_filter_spec(edge_filter, node_side=False)
        node_entities, node_query = _neighbor_filter_spec(node_filter, node_side=True)
        if properties:
            props = _record_query(properties, _NODE_TOP_LEVEL_KEYS)
            node_query = props if node_query is None else {"$and": [node_query, props]}
        return edge_entities, edge_query, node_entities, node_query

    async def _neighbors(
        self,
        context: "GraphContext",
        *,
        direction: str,
        spec: NeighborSpec,
        deserialize_as: Optional[type] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
        limit: Optional[int] = None,
    ) -> List["Node"]:
        """Neighbours for a normalised spec — pushed down when the backend can."""
        if direction not in ("out", "in", "both"):
            raise ValueError(
                f"direction must be 'out', 'in' or 'both', got {direction!r}"
            )
        hint = deserialize_as or Node
        edge_entities, edge_query, node_entities, node_query = spec
        records: Optional[List[Dict[str, Any]]] = None
        find_connected = getattr(context.database, "find_connected_nodes", None)
        if callable(find_connected):
            try:
                records = await find_connected(
                    context._get_collection_name("n"),
                    context._get_collection_name("e"),
                    self.id,
                    direction=direction,
                    edge_entities=edge_entities,
                    node_entities=node_entities,
                    edge_query=edge_query,
                    node_query=node_query,
                    sort=sort,
                    limit=limit,
                )
            except NotImplementedError as exc:
                logger.debug("nodes(): no pushdown (%s); Python path", exc)
        if records is None:
            return await self._neighbors_fallback(
                context,
                direction=direction,
                spec=spec,
                deserialize_as=hint,
                sort=sort,
                limit=limit,
            )
        return await self._hydrate_neighbors(context, records, hint)

    async def _hydrate_neighbors(
        self,
        context: "GraphContext",
        records: List[Dict[str, Any]],
        deserialize_as: type,
    ) -> List["Node"]:
        found: List["Node"] = []
        for data in records:
            try:
                node_obj: Optional["Node"] = await context._deserialize_entity(
                    deserialize_as, data
                )
            except Exception as e:
                logger.debug("Skipping invalid neighbour record: %s", e)
                continue
            if node_obj:
                found.append(node_obj)
                await context._add_to_cache(node_obj.id, node_obj)
        return found

    async def _neighbors_fallback(
        self,
        context: "GraphContext",
        *,
        direction: str,
        spec: NeighborSpec,
        deserialize_as: type,
        sort: Optional[List[Tuple[str, int]]],
        limit: Optional[int],
    ) -> List["Node"]:
        """Python traversal for backends without ``find_connected_nodes``.

        One edge ``find`` (endpoint + entity ``$in`` + edge criteria), then the
        neighbours — filtered by entity and criteria in the node ``find``
        before hydration.
        """
        edge_entities, edge_query, node_entities, node_query = spec
        db = context.database
        endpoints: Dict[str, Dict[str, Any]] = {
            "out": {"source": self.id},
            "in": {"target": self.id},
            "both": {"$or": [{"source": self.id}, {"target": self.id}]},
        }
        edge_parts: List[Dict[str, Any]] = [endpoints[direction]]
        if edge_entities is not None:
            edge_parts.append({"entity": {"$in": edge_entities}})
        if edge_query:
            edge_parts.append(edge_query)
        edge_docs = await db.find(
            context._get_collection_name("e"),
            edge_parts[0] if len(edge_parts) == 1 else {"$and": edge_parts},
        )
        neighbor_ids: List[str] = []
        for doc in edge_docs:
            src, tgt = doc.get("source"), doc.get("target")
            if direction in ("out", "both") and src == self.id and tgt:
                neighbor_ids.append(tgt)
            if direction in ("in", "both") and tgt == self.id and src:
                neighbor_ids.append(src)
        neighbor_ids = list(dict.fromkeys(neighbor_ids))
        if not neighbor_ids:
            return []

        if node_entities is None and node_query is None and not sort:
            # Unfiltered: the cache-aware batch fetch (identity-map friendly).
            found = await context.get_batch(Node, neighbor_ids)
            return found if limit is None else found[:limit]

        records: List[Dict[str, Any]] = []
        for off in range(0, len(neighbor_ids), 500):
            node_parts: List[Dict[str, Any]] = [
                {"id": {"$in": neighbor_ids[off : off + 500]}}
            ]
            if node_entities is not None:
                node_parts.append({"entity": {"$in": node_entities}})
            if node_query:
                node_parts.append(node_query)
            records.extend(
                await db.find(context._get_collection_name("n"), {"$and": node_parts})
            )
        if sort:
            records = finalize_find_results(records, sort=sort, limit=limit)
        else:
            order = {nid: i for i, nid in enumerate(neighbor_ids)}
            records.sort(key=lambda r: order.get(str(r.get("id")), 0))
            if limit is not None:
                records = records[:limit]
        return await self._hydrate_neighbors(context, records, deserialize_as)

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
        # ``_entity_name()`` honors the ``__entity_name__`` override
        # (SPEC §1.2). Falls back to ``__name__`` if absent so this helper
        # works on non-Object types passed by mistake.
        resolver = getattr(node_obj.__class__, "_entity_name", None)
        obj_entity_name = (
            resolver() if callable(resolver) else node_obj.__class__.__name__
        )

        if isinstance(node_filter, str):
            # Simple string filter - match by entity_name
            return obj_entity_name == node_filter

        elif isinstance(node_filter, type):
            # Class type filter - match by class or inheritance
            return isinstance(node_obj, node_filter)

        elif isinstance(node_filter, list):
            for filter_item in node_filter:
                if isinstance(filter_item, str):
                    # String in list - match by entity_name
                    if obj_entity_name == filter_item:
                        return True
                elif isinstance(filter_item, type):
                    # Class type in list - match by class or inheritance
                    if isinstance(node_obj, filter_item):
                        return True
                elif isinstance(filter_item, dict):
                    # Dict filter - match by entity_name and criteria
                    for class_name, criteria in filter_item.items():
                        if (
                            obj_entity_name == class_name
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
        limit: Optional[int] = 1000,
        **kwargs: Any,
    ) -> List["Node"]:
        """Get all neighboring nodes (convenient alias for nodes()).

        Args:
            node: Node filtering (supports semantic filtering)
            edge: Edge filtering (supports semantic filtering)
            limit: Maximum number of neighbors to return (default 1000).
                   Pass None to disable the limit (logged at WARNING).
            **kwargs: Simple property filters for connected nodes

        Returns:
            List of neighboring nodes in connection order
        """
        if limit is None:
            import logging

            logging.getLogger(__name__).warning(
                "neighbors() called with limit=None — unbounded query on %s", self.id
            )
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

            for found_edge in edges:
                db = context.database
                await db.delete("edge", found_edge.id)
                await context._cache.delete(found_edge.id)

            return len(edges) > 0
        except Exception:
            logger.warning(
                "disconnect(%s, %s) failed",
                self.id,
                other.id,
                exc_info=True,
            )
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

        One ``COUNT`` over the edge collection's ``source`` / ``target``
        indexes — the canonical degree query.

        Returns:
            Number of connected edges
        """
        context = await self.get_context()
        return await context.database.count(
            "edge", {"$or": [{"source": self.id}, {"target": self.id}]}
        )

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
                        for edge in await node._incident_edges(context):  # type: ignore[attr-defined]
                            if edge.source == node_id:
                                # Only add nodes reachable via outgoing edges
                                nodes_to_check.add(edge.target)
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
                        candidate_edges = await candidate_node._incident_edges(  # type: ignore[attr-defined]
                            context
                        )

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

                                node_edges = await node._incident_edges(  # type: ignore[attr-defined]
                                    context
                                )

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
                await context.database.delete("edge", edge.id)
                await context._cache.delete(edge.id)
            except Exception:
                continue

        # Clean up outgoing edges from this node
        for edge in outgoing_edges:
            try:
                await context.database.delete("edge", edge.id)
                await context._cache.delete(edge.id)
            except Exception:
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

        # Finally, delete this node itself. Direct delete rather than
        # ``context.delete`` — its "no edges left?" check would cost a COUNT,
        # and the edges are already gone.
        await context.database.delete(context._get_collection_name("n"), self.id)
        await context._remove_from_cache(self.id)

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
        flat: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Export node to a dictionary.

        Returns a nested persistence format with id, entity, context for database storage.
        Includes all fields from the class hierarchy (class and parent classes, not child classes).

        Args:
            exclude_transient: Whether to automatically exclude transient fields (default: True)
            exclude: Additional fields to exclude (can be a set of field names or a dict)
            flat: If True, return attributes at top level instead of nested under context (for API responses)
            **kwargs: Additional arguments passed to base export/model_dump()

        Returns:
            Nested format dictionary with id, entity, context for database storage,
            or flat format {id, entity, **context} when flat=True
        """
        # Nested persistence format - structure for database storage
        # Exclude _visitor_ref from context (id and type_code are transient and auto-excluded)
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

        if flat:
            result = {"id": self.id, "entity": self.entity, **context_data}
        else:
            result = {
                "id": self.id,
                "entity": self.entity,
                "context": context_data,
            }

        return result
