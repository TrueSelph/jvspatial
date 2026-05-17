"""Entity classes and components for jvspatial.

This package maintains the original inheritance hierarchy:
Object → Node → Edge/Walker

The enhanced classes preserve all original functionality while adding
simplified decorator support and other improvements.
"""

from jvspatial.exceptions import JVSpatialError

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


class TraversalSkipped(JVSpatialError):
    """Walker-skip signal raised by ``Walker.skip()``.

    Abandons processing of the current node and continues with the
    next queued node. Replaces the historical
    ``raise JVSpatialError("Node skipped")`` pattern that relied on
    substring-matching the error message — a fragile contract that any
    unrelated exception containing the phrase would silently trigger
    (audit §2.9 / SPEC §6.5).
    """


class TraversalPaused(JVSpatialError):
    """Walker-pause signal raised by ``Walker.pause()``.

    Callers catch this exception to resume later via
    ``Walker.resume()``.
    """


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
    # Walker control-flow exceptions
    "TraversalSkipped",
    "TraversalPaused",
]
