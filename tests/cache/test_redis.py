"""Test suite for Redis cache backend."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Check if redis is available
try:
    from jvspatial.cache.redis import RedisCache

    redis_available = True
except ImportError:
    redis_available = False
    RedisCache = None  # type: ignore

# Check if Redis server is actually running
redis_server_available = False
if redis_available:
    try:

        async def check_redis_server():
            cache = RedisCache(redis_url="redis://localhost:6379")
            return await cache.ping()

        # Try to check if Redis server is running
        redis_server_available = asyncio.run(check_redis_server())
    except Exception:
        redis_server_available = False

pytestmark = pytest.mark.skipif(
    not redis_available or not redis_server_available,
    reason="redis package not installed or Redis server not running",
)


class TestRedisCache:
    """Test RedisCache functionality."""

    def test_redis_cache_initialization(self):
        """Test Redis cache initialization."""
        cache = RedisCache(redis_url="redis://localhost:6379")
        assert cache is not None
        assert cache.redis_url == "redis://localhost:6379"

    def test_redis_cache_default_config(self):
        """Test Redis cache with default configuration."""
        cache = RedisCache()
        assert cache is not None

    @pytest.mark.asyncio
    async def test_redis_cache_operations(self):
        """Test Redis cache operations."""
        cache = RedisCache(redis_url="redis://localhost:6379")

        # Test basic operations with Redis server
        await cache.set("key1", "value1")
        result = await cache.get("key1")
        assert result == "value1"

        # Test delete
        await cache.delete("key1")
        result = await cache.get("key1")
        assert result is None

        # Test clear
        await cache.set("key2", "value2")
        await cache.clear()
        result = await cache.get("key2")
        assert result is None

    @pytest.mark.asyncio
    async def test_redis_cache_ttl(self):
        """Test Redis cache TTL functionality."""
        cache = RedisCache(redis_url="redis://localhost:6379")

        # Test set with TTL
        await cache.set("key1", "value1", ttl=3600)
        result = await cache.get("key1")
        assert result == "value1"

        # Test that key exists
        exists = await cache.exists("key1")
        assert exists is True

    @pytest.mark.asyncio
    async def test_redis_cache_pattern_invalidation(self):
        """Test Redis cache pattern invalidation."""
        cache = RedisCache(redis_url="redis://localhost:6379")

        # Set multiple keys with pattern
        await cache.set("user:1:profile", "data1")
        await cache.set("user:2:profile", "data2")
        await cache.set("user:1:settings", "settings1")

        # Invalidate all user:1:* keys
        deleted = await cache.invalidate_pattern("user:1:*")
        assert deleted == 2

        # Check that user:1:* keys are gone
        assert await cache.get("user:1:profile") is None
        assert await cache.get("user:1:settings") is None

        # Check that user:2:* key still exists
        assert await cache.get("user:2:profile") == "data2"

    def test_redis_cache_stats(self):
        """Test Redis cache statistics."""
        cache = RedisCache(redis_url="redis://localhost:6379")
        stats = cache.get_stats()

        assert stats is not None
        assert "backend" in stats
        assert "redis_url" in stats
        assert "prefix" in stats
