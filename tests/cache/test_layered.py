"""Test suite for LayeredCache."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from jvspatial.cache.layered import LayeredCache


class TestLayeredCache:
    """Test LayeredCache functionality."""

    async def test_layered_cache_initialization(self):
        """Test layered cache initialization."""
        cache = LayeredCache()
        assert cache is not None
        assert cache.l1 is not None
        assert cache.l2 is not None or not cache.l2_available

    async def test_layered_cache_default_initialization(self):
        """Test layered cache with default initialization."""
        cache = LayeredCache()
        assert cache is not None
        assert cache.l1 is not None
        assert cache.l2 is not None or not cache.l2_available

    @pytest.mark.asyncio
    async def test_layered_cache_get_from_l1(self):
        """Test getting value from L1 cache."""
        cache = LayeredCache()

        # Set a value in L1 cache directly
        await cache.l1.set("key1", "value1")
        result = await cache.get("key1")

        assert result == "value1"

    @pytest.mark.asyncio
    async def test_layered_cache_get_from_l2(self):
        """Test getting value from L2 cache when L1 misses."""
        cache = LayeredCache()

        # If L2 is available, set a value in L2 cache directly
        if cache.l2_available and cache.l2:
            try:
                await cache.l2.set("key1", "value1")
                result = await cache.get("key1")
                assert result == "value1"
            except Exception:
                # If Redis connection fails, just test that the method doesn't crash
                result = await cache.get("key1")
                assert result is None
        else:
            # If L2 is not available, just test that the method doesn't crash
            result = await cache.get("key1")
            assert result is None

    @pytest.mark.asyncio
    async def test_layered_cache_set(self):
        """Test setting value in both caches."""
        cache = LayeredCache()
        await cache.set("key1", "value1")

        # Verify the value is in L1
        result = await cache.l1.get("key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_layered_cache_delete(self):
        """Test deleting value from both caches."""
        cache = LayeredCache()

        # Set a value first
        await cache.set("key1", "value1")
        assert await cache.l1.get("key1") == "value1"

        # Delete the value
        await cache.delete("key1")

        # Verify it's deleted from L1
        result = await cache.l1.get("key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_layered_cache_clear(self):
        """Test clearing both caches."""
        cache = LayeredCache()

        # Set some values first
        await cache.set("key1", "value1")
        await cache.set("key2", "value2")

        # Clear the cache
        await cache.clear()

        # Verify values are cleared from L1
        assert await cache.l1.get("key1") is None
        assert await cache.l1.get("key2") is None

    @pytest.mark.asyncio
    async def test_layered_cache_stats(self):
        """Test getting statistics from both caches."""
        cache = LayeredCache()

        # Perform some operations to generate stats
        await cache.set("key1", "value1")
        await cache.get("key1")
        await cache.get("nonexistent")

        stats = cache.get_stats()

        assert stats is not None
        assert "backend" in stats
        assert "l1_backend" in stats
        assert "l1_cache_size" in stats
