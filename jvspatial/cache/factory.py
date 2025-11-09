"""Simplified cache creation utilities.

This module provides simple utilities for creating cache backends,
replacing the complex factory pattern with direct instantiation.
"""

import os

from .base import CacheBackend
from .memory import MemoryCache


def create_cache(
    backend: str = "memory", cache_size: int = 1000, **kwargs
) -> CacheBackend:
    """Create a cache backend with direct instantiation.

    Args:
        backend: Backend type ('memory', 'redis', 'layered')
        cache_size: Cache size for memory backend
        **kwargs: Additional backend-specific arguments

    Returns:
        Configured cache backend instance

    Examples:
        # Memory cache
        cache = create_cache("memory", cache_size=1000)

        # Redis cache
        cache = create_cache("redis", redis_url="redis://localhost:6379")

        # Layered cache
        cache = create_cache("layered", l1_size=500)
    """
    if backend == "memory":
        return MemoryCache(max_size=cache_size)

    elif backend == "redis":
        from .redis import RedisCache

        return RedisCache(
            redis_url=kwargs.get("redis_url"),
            ttl=kwargs.get("ttl"),
            prefix=kwargs.get("prefix", "jvspatial:"),
        )

    elif backend == "layered":
        from .layered import LayeredCache

        return LayeredCache(
            l1_size=kwargs.get("l1_size", cache_size),
            l2_url=kwargs.get("l2_url"),
            l2_ttl=kwargs.get("l2_ttl"),
            l2_prefix=kwargs.get("l2_prefix", "jvspatial:"),
            fallback_to_l1=kwargs.get("fallback_to_l1", True),
        )

    else:
        raise ValueError(
            f"Unknown cache backend: {backend}. "
            f"Valid options: 'memory', 'redis', 'layered'"
        )


def create_default_cache() -> CacheBackend:
    """Create the default cache backend based on environment.

    Returns:
        Configured cache backend instance
    """
    # Check environment variables
    backend = os.getenv("JVSPATIAL_CACHE_BACKEND", "memory")
    cache_size = int(os.getenv("JVSPATIAL_CACHE_SIZE", "1000"))

    # Auto-detect Redis if available
    if backend == "memory" and os.getenv("JVSPATIAL_REDIS_URL"):
        backend = "layered"

    return create_cache(backend, cache_size)
