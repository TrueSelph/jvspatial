"""Mixins for jvspatial entities.

This module provides optional mixins that can be composed with
jvspatial entity classes (Object, Node, Edge, Walker) to add
additional functionality.
"""

from .deferred_save import ENABLE_DEFERRED_SAVES, DeferredSaveMixin

__all__ = ["DeferredSaveMixin", "ENABLE_DEFERRED_SAVES"]
