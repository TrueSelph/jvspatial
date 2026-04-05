"""Mixins for jvspatial entities.

This module provides optional mixins that can be composed with
jvspatial entity classes (Object, Node, Edge, Walker) to add
additional functionality.
"""

from .deferred_save import (
    DeferredSaveMixin,
    deferred_saves_globally_allowed,
    flush_deferred_entities,
)

__all__ = [
    "DeferredSaveMixin",
    "deferred_saves_globally_allowed",
    "flush_deferred_entities",
]
