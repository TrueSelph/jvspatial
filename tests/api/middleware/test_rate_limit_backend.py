"""Tests for rate limiting backend implementations."""

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from jvspatial.api.middleware.rate_limit_backend import (
    MemoryRateLimitBackend,
    RateLimitBackend,
)


class TestMemoryRateLimitBackend:
    """Test MemoryRateLimitBackend implementation."""

    @pytest.fixture
    def backend(self):
        """Create MemoryRateLimitBackend instance."""
        return MemoryRateLimitBackend(cleanup_interval=60)

    @pytest.mark.asyncio
    async def test_increment(self, backend):
        """Test incrementing request count."""
        key = "test_key"
        window = 60

        # First increment
        count1 = await backend.increment(key, window)
        assert count1 == 1

        # Second increment
        count2 = await backend.increment(key, window)
        assert count2 == 2

        # Third increment
        count3 = await backend.increment(key, window)
        assert count3 == 3

    @pytest.mark.asyncio
    async def test_get_count(self, backend):
        """Test getting current count."""
        key = "test_key"
        window = 60

        # Initially zero
        count = await backend.get_count(key, window)
        assert count == 0

        # After increment
        await backend.increment(key, window)
        count = await backend.get_count(key, window)
        assert count == 1

        # Multiple increments
        await backend.increment(key, window)
        await backend.increment(key, window)
        count = await backend.get_count(key, window)
        assert count == 3

    @pytest.mark.asyncio
    async def test_reset(self, backend):
        """Test resetting counter."""
        key = "test_key"
        window = 60

        # Increment a few times
        await backend.increment(key, window)
        await backend.increment(key, window)
        count = await backend.get_count(key, window)
        assert count == 2

        # Reset
        await backend.reset(key)
        count = await backend.get_count(key, window)
        assert count == 0

    @pytest.mark.asyncio
    async def test_window_expiration(self, backend):
        """Test that entries expire after window."""
        key = "test_key"
        window = 1  # 1 second window

        # Make requests
        await backend.increment(key, window)
        await backend.increment(key, window)
        count = await backend.get_count(key, window)
        assert count == 2

        # Wait for window to expire
        time.sleep(1.1)

        # Count should be 0 (all entries expired)
        count = await backend.get_count(key, window)
        assert count == 0

        # New increment should work
        count = await backend.increment(key, window)
        assert count == 1

    @pytest.mark.asyncio
    async def test_cleanup_interval(self, backend):
        """Test cleanup interval behavior."""
        # Create backend with short cleanup interval
        backend = MemoryRateLimitBackend(cleanup_interval=1)

        # Create multiple keys
        for i in range(5):
            await backend.increment(f"key_{i}", 60)

        # Verify all keys exist
        for i in range(5):
            count = await backend.get_count(f"key_{i}", 60)
            assert count == 1

        # Wait for cleanup interval
        time.sleep(1.1)

        # Trigger cleanup by checking a key (this calls _maybe_cleanup)
        # Don't increment again, just check - keys should still exist
        count = await backend.get_count("key_0", 60)
        assert count == 1

        # All keys should still exist (not old enough to clean)
        for i in range(5):
            count = await backend.get_count(f"key_{i}", 60)
            assert count == 1

    @pytest.mark.asyncio
    async def test_multiple_keys(self, backend):
        """Test that different keys are tracked separately."""
        key1 = "key1"
        key2 = "key2"
        window = 60

        # Increment key1
        count1 = await backend.increment(key1, window)
        assert count1 == 1

        # Increment key2
        count2 = await backend.increment(key2, window)
        assert count2 == 1

        # Both should be independent
        assert await backend.get_count(key1, window) == 1
        assert await backend.get_count(key2, window) == 1

        # Increment key1 again
        await backend.increment(key1, window)
        assert await backend.get_count(key1, window) == 2
        assert await backend.get_count(key2, window) == 1


class TestRedisRateLimitBackend:
    """Test RedisRateLimitBackend implementation (if redis available)."""

    @pytest.fixture
    def redis_available(self):
        """Check if redis is available."""
        try:
            import redis.asyncio as aioredis  # type: ignore[import-untyped]

            return True
        except ImportError:
            try:
                import aioredis  # type: ignore[import-untyped]

                return True
            except ImportError:
                return False

    @pytest.mark.asyncio
    async def test_redis_backend_initialization(self, redis_available):
        """Test Redis backend initialization."""
        if not redis_available:
            pytest.skip("Redis not available")

        from jvspatial.api.middleware.rate_limit_backend import RedisRateLimitBackend

        # Mock redis client
        mock_redis = MagicMock()

        # Mock pipeline - needs to be async
        mock_pipeline = MagicMock()
        mock_pipeline.zadd = MagicMock(return_value=mock_pipeline)  # Chainable
        mock_pipeline.zremrangebyscore = MagicMock(
            return_value=mock_pipeline
        )  # Chainable
        mock_pipeline.zcard = MagicMock(return_value=mock_pipeline)  # Chainable
        mock_pipeline.expire = MagicMock(return_value=mock_pipeline)  # Chainable
        mock_pipeline.execute = AsyncMock(
            return_value=[None, None, 1, None]
        )  # [zadd, zrem, zcard, expire]

        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
        mock_redis.zcount = AsyncMock(return_value=1)
        mock_redis.delete = AsyncMock()

        backend = RedisRateLimitBackend(mock_redis)

        # Test increment
        count = await backend.increment("test_key", 60)
        assert count == 1

        # Test get_count
        count = await backend.get_count("test_key", 60)
        assert count == 1

        # Test reset
        await backend.reset("test_key")
        mock_redis.delete.assert_called_once()


class TestRateLimitBackendProtocol:
    """Test that backends implement the protocol correctly."""

    @pytest.mark.asyncio
    async def test_memory_backend_protocol_compliance(self):
        """Test that MemoryRateLimitBackend implements RateLimitBackend protocol."""
        backend = MemoryRateLimitBackend()

        # Check that it's a runtime checkable protocol
        from jvspatial.api.middleware.rate_limit_backend import RateLimitBackend

        assert isinstance(backend, RateLimitBackend)

        # Test protocol methods exist and work
        count = await backend.increment("test", 60)
        assert isinstance(count, int)

        count = await backend.get_count("test", 60)
        assert isinstance(count, int)

        await backend.reset("test")
        count = await backend.get_count("test", 60)
        assert count == 0
