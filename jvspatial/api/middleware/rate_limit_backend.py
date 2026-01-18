"""Rate limiting backend interfaces and implementations.

This module provides pluggable backends for rate limiting storage,
enabling horizontal scaling and proper memory management.
"""

import logging
import time
from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class RateLimitBackend(Protocol):
    """Protocol for rate limiting storage backends.

    Backends must implement increment and get_count methods for
    tracking request counts within time windows.
    """

    async def increment(self, key: str, window: int) -> int:
        """Increment request count for a key within a time window.

        Args:
            key: Unique identifier for the rate limit counter
            window: Time window in seconds

        Returns:
            Current count after increment
        """
        ...

    async def get_count(self, key: str, window: int) -> int:
        """Get current request count for a key within a time window.

        Args:
            key: Unique identifier for the rate limit counter
            window: Time window in seconds

        Returns:
            Current count
        """
        ...

    async def reset(self, key: str) -> None:
        """Reset the counter for a key.

        Args:
            key: Unique identifier for the rate limit counter
        """
        ...


class MemoryRateLimitBackend:
    """In-memory rate limiting backend (for testing/single-instance deployments).

    This backend stores counters in memory with automatic cleanup of expired entries.
    Not suitable for multi-worker deployments as counters are not shared.

    Attributes:
        _counters: Dictionary mapping keys to lists of timestamps
        _cleanup_interval: Interval in seconds between cleanup runs
        _last_cleanup: Timestamp of last cleanup
    """

    def __init__(self, cleanup_interval: int = 300):
        """Initialize memory backend.

        Args:
            cleanup_interval: Seconds between cleanup runs (default: 5 minutes)
        """
        self._counters: Dict[str, list] = {}
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()
        self._logger = logging.getLogger(__name__)

    async def increment(self, key: str, window: int) -> int:
        """Increment request count for a key within a time window.

        Args:
            key: Unique identifier for the rate limit counter
            window: Time window in seconds

        Returns:
            Current count after increment
        """
        now = time.time()
        self._maybe_cleanup(now)

        # Get or create counter for this key
        if key not in self._counters:
            self._counters[key] = []

        # Clean old entries outside the window
        window_start = now - window
        self._counters[key] = [
            timestamp for timestamp in self._counters[key] if timestamp > window_start
        ]

        # Record this request
        self._counters[key].append(now)

        return len(self._counters[key])

    async def get_count(self, key: str, window: int) -> int:
        """Get current request count for a key within a time window.

        Args:
            key: Unique identifier for the rate limit counter
            window: Time window in seconds

        Returns:
            Current count
        """
        now = time.time()
        self._maybe_cleanup(now)

        if key not in self._counters:
            return 0

        # Count entries within the window
        window_start = now - window
        return len([ts for ts in self._counters[key] if ts > window_start])

    async def reset(self, key: str) -> None:
        """Reset the counter for a key.

        Args:
            key: Unique identifier for the rate limit counter
        """
        if key in self._counters:
            del self._counters[key]

    def _maybe_cleanup(self, now: float) -> None:
        """Clean up expired entries if cleanup interval has passed.

        Args:
            now: Current timestamp
        """
        if now - self._last_cleanup < self._cleanup_interval:
            return

        # Clean up entries that haven't been accessed recently
        # Remove keys with empty lists or very old entries
        keys_to_remove = []
        for key, timestamps in self._counters.items():
            if not timestamps or (
                now - max(timestamps) > 3600
            ):  # No activity in last hour
                keys_to_remove.append(key)

        for key in keys_to_remove:
            del self._counters[key]

        self._last_cleanup = now


class RedisRateLimitBackend:
    """Redis-based rate limiting backend (for production/multi-worker deployments).

    This backend uses Redis for distributed rate limiting, enabling
    horizontal scaling across multiple server instances.

    Attributes:
        _redis: Redis client instance
        _key_prefix: Prefix for all rate limit keys
    """

    def __init__(self, redis_client: Any, key_prefix: str = "rate_limit:"):
        """Initialize Redis backend.

        Args:
            redis_client: Redis client instance (aioredis or redis.asyncio)
            key_prefix: Prefix for all rate limit keys
        """
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._logger = logging.getLogger(__name__)

    async def increment(self, key: str, window: int) -> int:
        """Increment request count for a key within a time window.

        Args:
            key: Unique identifier for the rate limit counter
            window: Time window in seconds

        Returns:
            Current count after increment
        """
        redis_key = f"{self._key_prefix}{key}"
        now = time.time()

        # Use Redis sorted set to track timestamps
        # Score is timestamp, value is also timestamp (for uniqueness)
        pipe = self._redis.pipeline()
        pipe.zadd(redis_key, {str(now): now})
        pipe.zremrangebyscore(redis_key, 0, now - window)
        pipe.zcard(redis_key)
        pipe.expire(redis_key, window + 60)  # Expire slightly after window

        results = await pipe.execute()
        return results[2]  # Count from zcard

    async def get_count(self, key: str, window: int) -> int:
        """Get current request count for a key within a time window.

        Args:
            key: Unique identifier for the rate limit counter
            window: Time window in seconds

        Returns:
            Current count
        """
        redis_key = f"{self._key_prefix}{key}"
        now = time.time()

        # Count entries within the window
        count = await self._redis.zcount(redis_key, now - window, now)
        return count

    async def reset(self, key: str) -> None:
        """Reset the counter for a key.

        Args:
            key: Unique identifier for the rate limit counter
        """
        redis_key = f"{self._key_prefix}{key}"
        await self._redis.delete(redis_key)


__all__ = [
    "RateLimitBackend",
    "MemoryRateLimitBackend",
    "RedisRateLimitBackend",
]
