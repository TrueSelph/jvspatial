"""Entity classes and components for jvspatial.

This package maintains the original inheritance hierarchy:
Object → Node → Edge/Walker

The enhanced classes preserve all original functionality while adding
simplified decorator support and other improvements.
"""

from .edge import Edge
from .node import Node

# Import additional components
from .node_query import NodeQuery

# Import enhanced entity classes (maintaining original hierarchy)
from .object import Object
from .root import Root
from .walker import Walker
from .walker_components.event_system import WalkerEventSystem
from .walker_components.protection import TraversalProtection
from .walker_components.walker_queue import WalkerQueue
from .walker_components.walker_trail import WalkerTrail

__all__ = [
    # Enhanced entity classes (maintaining original hierarchy)
    "Object",
    "Node",
    "Edge",
    "Walker",
    "Root",
    # Additional components
    "NodeQuery",
    "TraversalProtection",
    "WalkerQueue",
    "WalkerTrail",
    "WalkerEventSystem",
]
