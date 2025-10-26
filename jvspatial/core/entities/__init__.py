"""Entity classes and components for jvspatial.

This package contains all graph entity classes and their supporting components.
"""

from .edge import Edge
from .node import Node
from .node_query import NodeQuery

# Entity classes (now all in entities/)
from .object import Object
from .root import Root
from .walker import Walker
from .walker_components.event_system import WalkerEventSystem

# Walker components
from .walker_components.protection import TraversalProtection
from .walker_components.walker_queue import WalkerQueue
from .walker_components.walker_trail import WalkerTrail

__all__ = [
    # Core entities
    "Object",
    "Node",
    "Edge",
    "Root",
    "Walker",
    "NodeQuery",
    # Walker components
    "TraversalProtection",
    "WalkerQueue",
    "WalkerTrail",
    "WalkerEventSystem",
]
