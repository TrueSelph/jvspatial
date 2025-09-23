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
from .entities import (
    Edge,
    Node,
    NodeQuery,
    Object,
    Root,
    Walker,
    find_subclass_by_name,
    generate_id,
    on_exit,
    on_visit,
)
from .events import on_emit
from .pager import ObjectPager, paginate_by_field, paginate_objects

__all__ = [
    # Core entity classes
    "Object",
    "Node",
    "Edge",
    "Walker",
    "Root",
    "NodeQuery",
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
    # Context (advanced usage)
    "GraphContext",
    "get_default_context",
    "set_default_context",
    "graph_context",
    "async_graph_context",
]
