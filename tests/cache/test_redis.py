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

    async def check_redis_server():
        cache = RedisCache(redis_url="redis://localhost:6379")
        return await cache.ping()

    try:
        # Try to check if Redis server is running
        import asyncio

        redis_server_available = asyncio.run(check_redis_server())
    except Exception:
        redis_server_available = False

pytestmark = pytest.mark.skipif(
    not redis_available or not redis_server_available,
    reason="redis package not installed or Redis server not running",
)


class TestRedisCache:
    """Test RedisCache functionality."""

    async def test_redis_cache_initialization(self):
        """Test Redis cache initialization."""
        cache = RedisCache(redis_url="redis://localhost:6379")
        assert cache is not None
        assert cache.redis_url == "redis://localhost:6379"

    async def test_redis_cache_default_config(self):
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

    async def test_redis_cache_stats(self):
        """Test Redis cache statistics."""
        cache = RedisCache(redis_url="redis://localhost:6379")
        stats = cache.get_stats()

        assert stats is not None
        assert "backend" in stats
        assert "redis_url" in stats
        assert "prefix" in stats


class TestRedisCacheInvalidationStrategies:
    """Test Redis cache invalidation strategies."""

    @pytest.mark.asyncio
    async def test_invalidate_by_pattern(self):
        """Test cache invalidation by pattern."""
        cache = RedisCache(redis_url="redis://localhost:6379")

        # Set multiple keys with pattern
        await cache.set("user:1:profile", "data1")
        await cache.set("user:2:profile", "data2")
        await cache.set("user:1:settings", "settings1")
        await cache.set("product:1:info", "product1")

        # Invalidate all user:1:* keys
        deleted = await cache.invalidate_by_pattern("user:1:*")
        assert deleted == 2

        # Check that user:1:* keys are gone
        assert await cache.get("user:1:profile") is None
        assert await cache.get("user:1:settings") is None

        # Check that other keys still exist
        assert await cache.get("user:2:profile") == "data2"
        assert await cache.get("product:1:info") == "product1"

    @pytest.mark.asyncio
    async def test_invalidate_by_tags(self):
        """Test cache invalidation by tags."""
        cache = RedisCache(redis_url="redis://localhost:6379")

        # Set keys with tags
        await cache.set_with_tags("key1", "value1", tags=["tag1", "tag2"])
        await cache.set_with_tags("key2", "value2", tags=["tag2", "tag3"])
        await cache.set_with_tags("key3", "value3", tags=["tag1", "tag3"])

        # Invalidate by tag
        deleted = await cache.invalidate_by_tags(["tag1"])
        assert deleted == 2  # key1 and key3

        # Check that tagged keys are gone
        assert await cache.get("key1") is None
        assert await cache.get("key3") is None

        # Check that key2 still exists
        assert await cache.get("key2") == "value2"

    @pytest.mark.asyncio
    async def test_set_with_tags(self):
        """Test setting cache values with tags."""
        cache = RedisCache(redis_url="redis://localhost:6379")

        # Set key with tags
        await cache.set_with_tags(
            "tagged_key", "tagged_value", tags=["important", "user"]
        )

        # Verify key exists
        assert await cache.get("tagged_key") == "tagged_value"

        # Invalidate by one tag
        deleted = await cache.invalidate_by_tags(["important"])
        assert deleted == 1

        # Verify key is gone
        assert await cache.get("tagged_key") is None

    @pytest.mark.asyncio
    async def test_complex_invalidation_scenarios(self):
        """Test complex invalidation scenarios."""
        cache = RedisCache(redis_url="redis://localhost:6379")

        # Set up complex cache structure
        await cache.set("user:1:profile", "profile1")
        await cache.set("user:1:settings", "settings1")
        await cache.set("user:2:profile", "profile2")
        await cache.set_with_tags("session:1", "session1", tags=["user:1", "active"])
        await cache.set_with_tags("session:2", "session2", tags=["user:2", "active"])

        # Invalidate user:1 pattern
        deleted_pattern = await cache.invalidate_by_pattern("user:1:*")
        assert deleted_pattern == 2

        # Invalidate active sessions
        deleted_tags = await cache.invalidate_by_tags(["active"])
        assert deleted_tags == 2

        # Verify all user:1 keys are gone
        assert await cache.get("user:1:profile") is None
        assert await cache.get("user:1:settings") is None

        # Verify all sessions are gone
        assert await cache.get("session:1") is None
        assert await cache.get("session:2") is None

        # Verify user:2 profile still exists
        assert await cache.get("user:2:profile") == "profile2"
