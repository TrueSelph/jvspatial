"""jvspatial caching system.

This package provides pluggable cache backends for high-performance
distributed and single-server deployments.

Available backends:
- MemoryCache: Fast in-memory cache for single-server deployments
- RedisCache: Distributed Redis-backed cache for multi-instance deployments
- LayeredCache: Two-tier cache combining memory (L1) and Redis (L2)

Quick Start:
    # Automatic backend selection based on environment
    from jvspatial.cache import get_cache_backend
    cache = get_cache_backend()

    # Explicit backend selection
    from jvspatial.cache import MemoryCache, RedisCache, LayeredCache

    # Memory cache
    cache = MemoryCache(max_size=1000)

    # Redis cache
    cache = RedisCache(redis_url='redis://localhost:6379')

    # Layered cache (recommended for production)
    cache = LayeredCache(l1_size=500)
"""

from .base import CacheBackend, CacheStats
from .factory import create_default_cache, get_cache_backend
from .memory import MemoryCache

# Optional imports (only if Redis is installed)
try:
    from .layered import LayeredCache
    from .redis import RedisCache

    _REDIS_AVAILABLE = True
except ImportError:
    _REDIS_AVAILABLE = False
    RedisCache = None  # type: ignore
    LayeredCache = None  # type: ignore

__all__ = [
    # Base classes
    "CacheBackend",
    "CacheStats",
    # Backends
    "MemoryCache",
    "RedisCache",
    "LayeredCache",
    # Factory functions
    "get_cache_backend",
    "create_default_cache",
    # Constants
    "_REDIS_AVAILABLE",
]
