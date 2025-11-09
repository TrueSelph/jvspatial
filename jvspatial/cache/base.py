"""Abstract cache backend interface for jvspatial with built-in invalidation strategies.

This module defines the base interface for all cache backends,
enabling pluggable caching strategies for different deployment scenarios.
Includes built-in cache invalidation strategies as core features.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional


class CacheBackend(ABC):
    """Abstract base class for cache backend implementations with built-in invalidation strategies.

    All cache backends must implement this interface to ensure
    consistent behavior across different caching strategies.
    Includes built-in cache invalidation strategies as core features.
    """

    @abstractmethod
    async def invalidate_by_pattern(self, pattern: str) -> int:
        """Invalidate keys matching pattern.

        Args:
            pattern: Pattern to match keys against (supports wildcards)

        Returns:
            Number of keys deleted
        """
        pass

    @abstractmethod
    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """Invalidate keys with specific tags.

        Args:
            tags: List of tags to match against

        Returns:
            Number of keys deleted
        """
        pass

    @abstractmethod
    async def set_with_tags(
        self, key: str, value: Any, tags: List[str], ttl: Optional[int] = None
    ) -> None:
        """Store a value in the cache with tags for invalidation.

        Args:
            key: Cache key
            value: Value to cache
            tags: List of tags for invalidation
            ttl: Time-to-live in seconds (None for no expiration)
        """
        pass

    @abstractmethod
    async def get(self, key: str) -> Optional[Any]:
        """Retrieve a value from the cache.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached value if found, None otherwise
        """
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store a value in the cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (None for no expiration)
        """
        pass

    @abstractmethod
    async def delete(self, key: str) -> None:
        """Delete a value from the cache.

        Args:
            key: Cache key to delete
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all entries from the cache."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in the cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        pass

    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary containing cache statistics such as:
            - cache_size: Number of items in cache
            - cache_hits: Number of successful cache retrievals
            - cache_misses: Number of failed cache retrievals
            - hit_rate: Cache hit rate as a float (0.0 to 1.0)
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close cache connections and cleanup resources."""
        pass


class CacheStats:
    """Cache statistics tracking helper."""

    def __init__(self) -> None:
        """Initialize cache statistics."""
        self.hits: int = 0
        self.misses: int = 0
        self.sets: int = 0
        self.deletes: int = 0
        self.invalidations: int = 0
        self.errors: int = 0

    async def record_hit(self) -> None:
        """Record a cache hit."""
        self.hits += 1

    async def record_miss(self) -> None:
        """Record a cache miss."""
        self.misses += 1

    async def record_set(self) -> None:
        """Record a cache set operation."""
        self.sets += 1

    async def record_delete(self) -> None:
        """Record a cache delete operation."""
        self.deletes += 1

    def get_hit_rate(self) -> float:
        """Calculate cache hit rate.

        Returns:
            Hit rate as a float between 0.0 and 1.0
        """
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0

    def reset(self) -> None:
        """Reset all statistics."""
        self.hits = 0
        self.misses = 0
        self.sets = 0
        self.deletes = 0
        self.invalidations = 0
        self.errors = 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert statistics to dictionary.

        Returns:
            Dictionary with all statistics
        """
        return {
            "cache_hits": self.hits,
            "cache_misses": self.misses,
            "cache_sets": self.sets,
            "cache_deletes": self.deletes,
            "cache_invalidations": self.invalidations,
            "cache_errors": self.errors,
            "hit_rate": self.get_hit_rate(),
            "total_requests": self.hits + self.misses,
        }
