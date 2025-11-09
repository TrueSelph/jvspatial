"""Layered cache implementation combining L1 (memory) and L2 (Redis) caches.

This module provides a two-tier caching strategy that combines the speed
of in-memory caching with the distributed capabilities of Redis.
"""

import os
from typing import Any, Dict, Optional

from .base import CacheBackend
from .memory import MemoryCache
from .redis import RedisCache


class LayeredCache(CacheBackend):
    """Two-tier cache combining memory (L1) and Redis (L2).

    Features:
    - Fast local L1 cache for hot data (<1ms latency)
    - Distributed L2 cache for shared data (~1-5ms latency)
    - Automatic promotion of L2 hits to L1
    - Graceful degradation if Redis is unavailable

    Best for:
    - Kubernetes/multi-instance deployments
    - Production environments with Redis available
    - Optimal balance of speed and distribution

    Cache flow:
    1. Check L1 (memory) - fastest
    2. If miss, check L2 (Redis)
    3. If L2 hit, promote to L1
    4. On write, update both L1 and L2
    """

    def __init__(
        self,
        l1_size: Optional[int] = None,
        l2_url: Optional[str] = None,
        l2_ttl: Optional[int] = None,
        l2_prefix: str = "jvspatial:",
        fallback_to_l1: bool = True,
    ):
        """Initialize layered cache.

        Args:
            l1_size: L1 cache size (reads from JVSPATIAL_L1_CACHE_SIZE or defaults to 500)
            l2_url: Redis URL for L2 (reads from JVSPATIAL_REDIS_URL)
            l2_ttl: L2 TTL in seconds (reads from JVSPATIAL_REDIS_TTL or defaults to 3600)
            l2_prefix: Redis key prefix
            fallback_to_l1: Continue with L1 only if Redis unavailable
        """
        # Initialize L1 cache (fast local memory)
        l1_size = l1_size or int(os.getenv("JVSPATIAL_L1_CACHE_SIZE", "500"))
        self.l1 = MemoryCache(max_size=l1_size)

        # Initialize L2 cache (shared Redis)
        self.l2 = None
        self.l2_available = False
        self.fallback_to_l1 = fallback_to_l1

        try:
            self.l2 = RedisCache(redis_url=l2_url, ttl=l2_ttl, prefix=l2_prefix)
            self.l2_available = True
        except ImportError:
            # Redis not installed
            if not fallback_to_l1:
                raise
            print("Redis not available, using L1 (memory) cache only")
        except Exception as e:
            # Redis connection error
            if not fallback_to_l1:
                raise
            print(f"Redis connection failed: {e}. Using L1 (memory) cache only")

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve value from layered cache.

        Checks L1 first, then L2, promoting L2 hits to L1.

        Args:
            key: Cache key

        Returns:
            Cached value if found, None otherwise
        """
        # Check L1 (fast local cache)
        value = await self.l1.get(key)
        if value is not None:
            return value

        # Check L2 (distributed cache) if available
        if self.l2_available and self.l2:
            value = await self.l2.get(key)
            if value is not None:
                # Promote to L1 for faster subsequent access
                await self.l1.set(key, value)
                return value

        return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store value in both cache layers.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (applied to L2 only)
        """
        # Always set in L1 (fast local cache)
        await self.l1.set(key, value, ttl=ttl)

        # Also set in L2 (distributed cache) if available
        if self.l2_available and self.l2:
            await self.l2.set(key, value, ttl=ttl)

    async def delete(self, key: str) -> None:
        """Delete value from both cache layers.

        Args:
            key: Cache key to delete
        """
        # Delete from both caches
        await self.l1.delete(key)
        if self.l2_available and self.l2:
            await self.l2.delete(key)

    async def clear(self) -> None:
        """Clear all entries from both cache layers."""
        await self.l1.clear()
        if self.l2_available and self.l2:
            await self.l2.clear()

    async def exists(self, key: str) -> bool:
        """Check if key exists in either cache layer.

        Args:
            key: Cache key to check

        Returns:
            True if key exists in L1 or L2, False otherwise
        """
        # Check L1 first
        if await self.l1.exists(key):
            return True

        # Check L2 if available
        if self.l2_available and self.l2:
            return await self.l2.exists(key)

        return False

    def get_stats(self) -> Dict[str, Any]:
        """Get combined cache statistics.

        Returns:
            Dictionary with statistics from both cache layers
        """
        l1_stats = self.l1.get_stats()

        stats = {
            "backend": "layered",
            "l1_backend": "memory",
            "l1_cache_size": l1_stats.get("cache_size", 0),
            "l1_hits": l1_stats.get("cache_hits", 0),
            "l1_misses": l1_stats.get("cache_misses", 0),
            "l1_hit_rate": l1_stats.get("hit_rate", 0.0),
            "l2_available": self.l2_available,
        }

        if self.l2_available and self.l2:
            l2_stats = self.l2.get_stats()
            stats.update(
                {
                    "l2_backend": "redis",
                    "l2_hits": l2_stats.get("cache_hits", 0),
                    "l2_misses": l2_stats.get("cache_misses", 0),
                    "l2_hit_rate": l2_stats.get("hit_rate", 0.0),
                    "l2_redis_url": l2_stats.get("redis_url", ""),
                }
            )

        # Calculate combined statistics
        total_hits = stats.get("l1_hits", 0) + stats.get("l2_hits", 0)
        total_misses = stats.get("l1_misses", 0) + stats.get("l2_misses", 0)
        total_requests = total_hits + total_misses

        stats["combined_hits"] = total_hits
        stats["combined_misses"] = total_misses
        stats["combined_hit_rate"] = (
            total_hits / total_requests if total_requests > 0 else 0.0
        )

        return stats

    async def close(self) -> None:
        """Close both cache layers and cleanup resources."""
        await self.l1.close()
        if self.l2_available and self.l2:
            await self.l2.close()

    async def check_l2_health(self) -> bool:
        """Check if L2 (Redis) cache is healthy.

        Returns:
            True if L2 is available and responsive, False otherwise
        """
        if not self.l2_available or not self.l2:
            return False

        try:
            return await self.l2.ping()
        except Exception:
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate keys matching pattern in both cache layers.

        Args:
            pattern: Pattern to match (e.g., "user:*", "node:123:*")

        Returns:
            Number of keys deleted from L2 (L1 doesn't support patterns)
        """
        # Clear entire L1 cache (doesn't support pattern matching)
        await self.l1.clear()

        # Invalidate pattern in L2
        deleted = 0
        if self.l2_available and self.l2:
            deleted = await self.l2.invalidate_pattern(pattern)

        return deleted

    async def invalidate_by_pattern(self, pattern: str) -> int:
        """Invalidate keys matching pattern in both cache layers.

        Args:
            pattern: Pattern to match (e.g., "user:*", "node:123:*")

        Returns:
            Number of keys deleted from L2 (L1 doesn't support patterns)
        """
        return await self.invalidate_pattern(pattern)

    async def invalidate_by_tags(self, tags: list) -> int:
        """Invalidate keys associated with specific tags.

        Args:
            tags: List of tags to invalidate

        Returns:
            Number of keys deleted
        """
        # Clear entire L1 cache (doesn't support tags)
        await self.l1.clear()

        # Invalidate tags in L2
        deleted = 0
        if self.l2_available and self.l2:
            deleted = await self.l2.invalidate_by_tags(tags)

        return deleted

    async def set_with_tags(
        self, key: str, value: Any, tags: list = None, ttl: Optional[int] = None
    ) -> None:
        """Store value in cache with associated tags.

        Args:
            key: Cache key
            value: Value to store
            tags: List of tags to associate with the key
            ttl: Time to live in seconds
        """
        # Store in L1
        await self.l1.set(key, value, ttl)

        # Store in L2 with tags
        if self.l2_available and self.l2:
            await self.l2.set_with_tags(key, value, tags, ttl)
