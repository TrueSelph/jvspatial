"""Simplified jvspatial caching system.

This package provides simplified cache backends with direct instantiation.
"""

from .base import CacheBackend
from .factory import create_cache, create_default_cache
from .memory import MemoryCache

# Optional imports (only if Redis is installed)
try:
    from .layered import LayeredCache  # noqa: F401
    from .redis import RedisCache  # noqa: F401

    __all__ = [
        "CacheBackend",
        "create_cache",
        "create_default_cache",
        "MemoryCache",
        "RedisCache",
        "LayeredCache",
    ]
except ImportError:
    __all__ = [
        "CacheBackend",
        "create_cache",
        "create_default_cache",
        "MemoryCache",
    ]
