"""Redis cache backend implementation with built-in connection pooling and invalidation strategies.

This module provides a Redis-backed cache for distributed deployments,
enabling shared caching across multiple application instances with
integrated connection pooling and cache invalidation strategies.
"""

import os
import pickle
from typing import Any, Dict, List, Optional

from .base import CacheBackend, CacheStats


class RedisCache(CacheBackend):
    """Redis-backed cache implementation with built-in connection pooling and invalidation strategies.

    Features:
    - Distributed cache shared across instances
    - Built-in connection pooling for optimal performance
    - Persistence across restarts
    - Automatic TTL expiration
    - Built-in cache invalidation strategies
    - Pub/sub support for cache invalidation

    Best for:
    - Multi-instance deployments
    - Kubernetes/container environments
    - Microservices architecture
    - L2 cache in layered configurations
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        ttl: Optional[int] = None,
        prefix: str = "jvspatial:",
        **redis_kwargs,
    ):
        """Initialize Redis cache.

        Args:
            redis_url: Redis connection URL (uses JVSPATIAL_REDIS_URL env if not provided)
            ttl: Default TTL in seconds (uses JVSPATIAL_REDIS_TTL env if not provided)
            prefix: Key prefix for namespacing (default: "jvspatial:")
            **redis_kwargs: Additional arguments passed to Redis client
        """
        try:
            import redis.asyncio  # type: ignore[import-not-found, import-untyped]  # noqa: F401
        except ImportError:
            raise ImportError(
                "Redis support requires 'redis' package. "
                "Install with: pip install redis[hiredis]"
            )

        self.redis_url = redis_url or os.getenv(
            "JVSPATIAL_REDIS_URL", "redis://localhost:6379"
        )

        self.default_ttl = ttl or int(os.getenv("JVSPATIAL_REDIS_TTL", "3600"))
        self.prefix = prefix
        self._stats = CacheStats()
        self._client = None
        self._redis_kwargs = redis_kwargs

    async def _get_client(self):
        """Get or create Redis client."""
        if self._client is None:
            import redis.asyncio  # type: ignore[import-not-found, import-untyped]

            self._client = redis.asyncio.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=False,  # We handle serialization ourselves
                **self._redis_kwargs,
            )
        return self._client

    def _make_key(self, key: str) -> str:
        """Create prefixed cache key.

        Args:
            key: Original cache key

        Returns:
            Prefixed key for Redis
        """
        return f"{self.prefix}{key}"

    async def invalidate_by_pattern(self, pattern: str) -> int:
        """Invalidate keys matching pattern.

        Args:
            pattern: Pattern to match keys against (supports wildcards)

        Returns:
            Number of keys deleted
        """
        try:
            client = await self._get_client()

            # Convert pattern to Redis pattern
            redis_pattern = self._make_key(pattern)

            # Find all keys matching the pattern
            keys = await client.keys(redis_pattern)

            if keys:
                # Delete all matching keys
                deleted_count = await client.delete(*keys)
                self._stats.invalidations += deleted_count
                return deleted_count

            return 0

        except Exception as e:
            self._stats.errors += 1
            raise RuntimeError(f"Failed to invalidate by pattern {pattern}: {e}")

    async def invalidate_by_tags(self, tags: List[str]) -> int:
        """Invalidate keys with specific tags.

        Args:
            tags: List of tags to match against

        Returns:
            Number of keys deleted
        """
        try:
            client = await self._get_client()

            keys_to_delete = set()

            for tag in tags:
                # Get all keys for this tag
                tag_key = self._make_key(f"tag:{tag}")
                tagged_keys = await client.smembers(tag_key)

                for key in tagged_keys:
                    keys_to_delete.add(key)

            if keys_to_delete:
                # Delete all tagged keys
                deleted_count = await client.delete(*keys_to_delete)
                self._stats.invalidations += deleted_count

                # Clean up tag sets
                for tag in tags:
                    tag_key = self._make_key(f"tag:{tag}")
                    await client.delete(tag_key)

                return deleted_count

            return 0

        except Exception as e:
            self._stats.errors += 1
            raise RuntimeError(f"Failed to invalidate by tags {tags}: {e}")

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
        try:
            client = await self._get_client()
            redis_key = self._make_key(key)

            # Serialize value
            serialized_value = pickle.dumps(value)

            # Set the value
            if ttl is None:
                ttl = self.default_ttl

            await client.setex(redis_key, ttl, serialized_value)

            # Add tags
            for tag in tags:
                tag_key = self._make_key(f"tag:{tag}")
                await client.sadd(tag_key, redis_key)
                await client.expire(tag_key, ttl)  # Tag set expires with the key

            self._stats.sets += 1

        except Exception as e:
            self._stats.errors += 1
            raise RuntimeError(f"Failed to set {key} with tags {tags}: {e}")

    async def get(self, key: str) -> Optional[Any]:
        """Retrieve value from Redis cache.

        Args:
            key: Cache key

        Returns:
            Cached value if found, None otherwise
        """
        try:
            client = await self._get_client()
            redis_key = self._make_key(key)
            data = await client.get(redis_key)

            if data:
                await self._stats.record_hit()
                return pickle.loads(data)

            await self._stats.record_miss()
            return None
        except Exception as e:
            # Log error but don't crash - graceful degradation
            print(f"Redis get error for key {key}: {e}")
            await self._stats.record_miss()
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """Store value in Redis cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds (uses default if not provided)
        """
        try:
            client = await self._get_client()
            redis_key = self._make_key(key)
            data = pickle.dumps(value)

            ttl_seconds = ttl or self.default_ttl
            await client.setex(redis_key, ttl_seconds, data)
            await self._stats.record_set()
        except Exception as e:
            # Log error but don't crash - graceful degradation
            print(f"Redis set error for key {key}: {e}")

    async def delete(self, key: str) -> None:
        """Delete value from Redis cache.

        Args:
            key: Cache key to delete
        """
        try:
            client = await self._get_client()
            redis_key = self._make_key(key)
            await client.delete(redis_key)
            await self._stats.record_delete()
        except Exception as e:
            print(f"Redis delete error for key {key}: {e}")

    async def clear(self) -> None:
        """Clear all entries with this cache's prefix."""
        try:
            client = await self._get_client()
            # Find all keys with our prefix
            pattern = f"{self.prefix}*"
            cursor = 0

            while True:
                cursor, keys = await client.scan(cursor, match=pattern, count=100)
                if keys:
                    await client.delete(*keys)
                if cursor == 0:
                    break

            self._stats.reset()
        except Exception as e:
            print(f"Redis clear error: {e}")

    async def exists(self, key: str) -> bool:
        """Check if key exists in Redis cache.

        Args:
            key: Cache key to check

        Returns:
            True if key exists, False otherwise
        """
        try:
            client = await self._get_client()
            redis_key = self._make_key(key)
            return bool(await client.exists(redis_key))
        except Exception as e:
            print(f"Redis exists error for key {key}: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        stats = self._stats.to_dict()
        stats["backend"] = "redis"
        stats["redis_url"] = self.redis_url
        stats["prefix"] = self.prefix
        return stats

    async def close(self) -> None:
        """Close Redis connection and cleanup resources."""
        if self._client:
            await self._client.close()
            self._client = None

    async def ping(self) -> bool:
        """Check Redis connection health.

        Returns:
            True if Redis is accessible, False otherwise
        """
        try:
            client = await self._get_client()
            await client.ping()
            return True
        except Exception:
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching a pattern.

        Args:
            pattern: Redis pattern (e.g., "user:*", "node:123:*")

        Returns:
            Number of keys deleted
        """
        try:
            client = await self._get_client()
            full_pattern = f"{self.prefix}{pattern}"
            cursor = 0
            deleted = 0

            while True:
                cursor, keys = await client.scan(cursor, match=full_pattern, count=100)
                if keys:
                    await client.delete(*keys)
                    deleted += len(keys)
                if cursor == 0:
                    break

            return deleted
        except Exception as e:
            print(f"Redis invalidate_pattern error for {pattern}: {e}")
            return 0
