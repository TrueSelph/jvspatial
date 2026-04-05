"""Core package for jvspatial entities and graph operations.

Provides the base entity classes (Object, Node, Edge, Walker) and
graph operations with simple, elegant API design. The GraphContext
is handled internally to maintain semantic simplicity.
"""

from .context import (
    GraphContext,
    async_graph_context,
    get_default_context,
    graph_context,
    set_default_context,
)
from .decorators import on_exit, on_visit

# Import all entities from entities/ package
from .entities import (
    Edge,
    Node,
    NodeQuery,
    Object,
    Root,
    Walker,
)
from .events import on_emit
from .graph import (
    export_graph,
    generate_graph_dot,
    generate_graph_mermaid,
)
from .graph_expansion import expand_node, subgraph_bfs
from .mixins import (
    DeferredSaveMixin,
    deferred_saves_globally_allowed,
    flush_deferred_entities,
)
from .pager import ObjectPager, paginate_by_field, paginate_objects
from .utils import find_subclass_by_name, generate_id, serialize_datetime

__all__ = [
    # Core entity classes
    "Object",
    "Node",
    "Edge",
    "Walker",
    "Root",
    "NodeQuery",
    # Mixins
    "DeferredSaveMixin",
    "deferred_saves_globally_allowed",
    "flush_deferred_entities",
    # Pagination
    "ObjectPager",
    "paginate_objects",
    "paginate_by_field",
    # Decorators
    "on_visit",
    "on_exit",
    "on_emit",
    # Utilities
    "generate_id",
    "find_subclass_by_name",
    "serialize_datetime",
    # Graph Visualization
    "export_graph",
    "generate_graph_dot",
    "generate_graph_mermaid",
    "expand_node",
    "subgraph_bfs",
    # Context (advanced usage)
    "GraphContext",
    "get_default_context",
    "set_default_context",
    "graph_context",
    "async_graph_context",
]
