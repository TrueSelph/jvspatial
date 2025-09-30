"""Cache factory for creating cache backends based on configuration.

This module provides utilities for creating cache backends from
environment variables or explicit configuration.
"""

import os
from typing import Optional

from .base import CacheBackend
from .memory import MemoryCache


def get_cache_backend(
    backend: Optional[str] = None, cache_size: Optional[int] = None, **kwargs
) -> CacheBackend:
    """Create a cache backend based on configuration.

    Args:
        backend: Backend type ('memory', 'redis', 'layered').
                If None, reads from JVSPATIAL_CACHE_BACKEND environment variable.
                Defaults to 'memory' for single-server, 'layered' if Redis is configured.
        cache_size: Cache size (for memory backend).
                   If None, reads from JVSPATIAL_CACHE_SIZE environment variable.
        **kwargs: Additional backend-specific arguments

    Returns:
        Configured cache backend instance

    Examples:
        # Use environment variables
        cache = get_cache_backend()

        # Explicit memory cache
        cache = get_cache_backend('memory', cache_size=1000)

        # Explicit Redis cache
        cache = get_cache_backend('redis', redis_url='redis://localhost:6379')

        # Layered cache
        cache = get_cache_backend('layered', l1_size=500)
    """
    # Determine backend type
    if backend is None:
        backend = os.getenv("JVSPATIAL_CACHE_BACKEND", "").lower()

        # Auto-detect based on environment
        if not backend:
            # Check if Redis is configured
            redis_url = os.getenv("JVSPATIAL_REDIS_URL")
            if redis_url:
                backend = "layered"  # Default to layered for distributed
            else:
                backend = "memory"  # Default to memory for single-server

    # Get cache size from environment if not provided
    if cache_size is None:
        cache_size = int(os.getenv("JVSPATIAL_CACHE_SIZE", "1000"))

    # Create backend
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

    This is a convenience function that automatically selects
    the best cache backend based on available configuration.

    Selection logic:
    1. If JVSPATIAL_CACHE_BACKEND is set, use that
    2. If JVSPATIAL_REDIS_URL is set, use layered cache
    3. Otherwise, use memory cache

    Returns:
        Configured cache backend instance
    """
    return get_cache_backend()
