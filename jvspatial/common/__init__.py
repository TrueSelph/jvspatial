"""Common utilities shared across the library.

This package contains foundational utilities that are backend-agnostic and
safe to import from any layer (core, db, api). Keep dependencies minimal.
"""

from .context import GlobalContext
from .factory import PluginFactory
from .serialization import deserialize_datetime, serialize_datetime
from .validation import PathValidator

__all__ = [
    "PluginFactory",
    "GlobalContext",
    "serialize_datetime",
    "deserialize_datetime",
    "PathValidator",
]
