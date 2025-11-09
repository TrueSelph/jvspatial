"""In-memory cache backend implementation.

This module provides a fast, local in-memory cache suitable for
single-instance deployments or as an L1 cache in layered configurations.
"""

import time
from typing import Any, Dict, Optional

from .base import CacheBackend, CacheStats


class MemoryCache(CacheBackend):
    """In-memory cache implementation with LRU eviction.

    Features:
    - Fast local access (<1ms latency)
    - LRU eviction when cache is full
    - Optional TTL support
    - Statistics tracking

    Best for:
    - Single-instance deployments
    - L1 cache in layered configurations
    - Development and testing
    """

    def __init__(self, max_size: int = 1000):
        """Initialize memory cache.

        Args:
            max_size: Maximum number of items to cache (0 to disable)
        """
        self.max_size = max_size
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._stats = CacheStats()

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve value from memory cache.

        Args:
            key: Cache key

        Returns:
            Cached value if found and not expired, None otherwise
        """
        if key in self._cache:
            entry = self._cache[key]

            # Check TTL expiration
            if entry.get("expires_at") and time.time() > entry["expires_at"]:
                # Expired, remove it
                del self._cache[key]
                await self._stats.record_miss()
                return None

            # Move to end for LRU
            self._cache[key] = self._cache.pop(key)
            await self._stats.record_hit()
            return entry["value"]

        await self._stats.record_miss()
        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store value in memory cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None for no expiration)
        """
        if self.max_size == 0:
            return

        # LRU eviction if cache is full
        if len(self._cache) >= self.max_size and key not in self._cache:
            # Remove oldest (first) item
            oldest_key = next(iter(self._cache))
            del self._cache[oldest_key]

        # Calculate expiration time
        expires_at = None
        if ttl:
            expires_at = time.time() + ttl

        # Store entry
        self._cache[key] = {"value": value, "expires_at": expires_at}
        await self._stats.record_set()

    async def delete(self, key: str) -> None:
        """Delete value from memory cache.

        Args:
            key: Cache key to delete
        """
        if key in self._cache:
            del self._cache[key]
            await self._stats.record_delete()

    async def clear(self) -> None:
        """Clear all entries from memory cache."""
        self._cache.clear()
        self._stats.reset()

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists and not expired, False otherwise
        """
        if key not in self._cache:
            return False

        entry = self._cache[key]
        if entry.get("expires_at") and time.time() > entry["expires_at"]:
            # Expired
            del self._cache[key]
            return False

        return True

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        stats = self._stats.to_dict()
        stats["cache_size"] = len(self._cache)
        stats["max_size"] = self.max_size
        stats["backend"] = "memory"
        return stats

    async def close(self) -> None:
        """Close cache and cleanup resources."""
        self._cache.clear()

    def cleanup_expired(self) -> int:
        """Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        current_time = time.time()
        expired_keys = [
            key
            for key, entry in self._cache.items()
            if entry.get("expires_at") and current_time > entry["expires_at"]
        ]

        for key in expired_keys:
            del self._cache[key]

        return len(expired_keys)

    # Cache invalidation strategies
    async def invalidate_by_pattern(self, pattern: str) -> int:
        """Invalidate cache keys matching a pattern.

        Args:
            pattern: Pattern to match against keys (supports * wildcard)

        Returns:
            Number of keys invalidated
        """
        import fnmatch

        matching_keys = [
            key for key in self._cache.keys() if fnmatch.fnmatch(key, pattern)
        ]

        for key in matching_keys:
            del self._cache[key]

        return len(matching_keys)

    async def invalidate_by_tags(self, tags: list) -> int:
        """Invalidate cache keys associated with specific tags.

        Args:
            tags: List of tags to match against

        Returns:
            Number of keys invalidated
        """
        # MemoryCache doesn't support tags, so this is a no-op
        return 0

    async def set_with_tags(
        self, key: str, value: Any, tags: list = None, ttl: Optional[int] = None
    ) -> None:
        """Store value in cache with associated tags.

        Args:
            key: Cache key
            value: Value to cache
            tags: List of tags to associate with this key
            ttl: Time-to-live in seconds (None for no expiration)
        """
        # MemoryCache doesn't support tags, so we just use the regular set method
        await self.set(key, value, ttl)
