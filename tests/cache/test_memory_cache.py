"""Tests for MemoryCache backend."""

import asyncio
import time

import pytest

from jvspatial.cache.memory import MemoryCache


@pytest.mark.asyncio
async def test_memory_cache_basic_operations():
    """Test basic get/set/delete operations."""
    cache = MemoryCache(max_size=100)

    # Set and get
    await cache.set("key1", "value1")
    result = await cache.get("key1")
    assert result == "value1"

    # Get non-existent key
    result = await cache.get("nonexistent")
    assert result is None

    # Delete
    await cache.delete("key1")
    result = await cache.get("key1")
    assert result is None


@pytest.mark.asyncio
async def test_memory_cache_ttl():
    """Test TTL (time-to-live) expiration."""
    cache = MemoryCache(max_size=100)

    # Set with 1 second TTL
    await cache.set("temp_key", "temp_value", ttl=1)

    # Should be available immediately
    result = await cache.get("temp_key")
    assert result == "temp_value"

    # Wait for expiration
    await asyncio.sleep(1.1)

    # Should be expired
    result = await cache.get("temp_key")
    assert result is None


@pytest.mark.asyncio
async def test_memory_cache_lru_eviction():
    """Test LRU eviction when cache is full."""
    cache = MemoryCache(max_size=3)

    # Fill cache
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")
    await cache.set("key3", "value3")

    # All should be present
    assert await cache.get("key1") == "value1"
    assert await cache.get("key2") == "value2"
    assert await cache.get("key3") == "value3"

    # Add one more - should evict key1 (oldest)
    await cache.set("key4", "value4")

    # key1 should be gone
    assert await cache.get("key1") is None
    assert await cache.get("key2") == "value2"
    assert await cache.get("key3") == "value3"
    assert await cache.get("key4") == "value4"


@pytest.mark.asyncio
async def test_memory_cache_lru_access_order():
    """Test that accessing an item updates LRU order."""
    cache = MemoryCache(max_size=3)

    # Fill cache
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")
    await cache.set("key3", "value3")

    # Access key1 to make it most recently used
    await cache.get("key1")

    # Add new item - should evict key2 (now oldest)
    await cache.set("key4", "value4")

    # key2 should be gone, key1 should still be there
    assert await cache.get("key1") == "value1"
    assert await cache.get("key2") is None
    assert await cache.get("key3") == "value3"
    assert await cache.get("key4") == "value4"


@pytest.mark.asyncio
async def test_memory_cache_update_existing():
    """Test updating an existing cache entry."""
    cache = MemoryCache(max_size=100)

    # Set initial value
    await cache.set("key1", "value1")
    assert await cache.get("key1") == "value1"

    # Update value
    await cache.set("key1", "value2")
    assert await cache.get("key1") == "value2"


@pytest.mark.asyncio
async def test_memory_cache_clear():
    """Test clearing all cache entries."""
    cache = MemoryCache(max_size=100)

    # Add multiple items
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")
    await cache.set("key3", "value3")

    # Clear cache
    await cache.clear()

    # Stats should be reset immediately after clear
    stats = cache.get_stats()
    assert stats["cache_size"] == 0
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 0

    # All items should be gone (checking this will add misses)
    assert await cache.get("key1") is None
    assert await cache.get("key2") is None
    assert await cache.get("key3") is None


@pytest.mark.asyncio
async def test_memory_cache_exists():
    """Test checking if keys exist."""
    cache = MemoryCache(max_size=100)

    # Non-existent key
    assert await cache.exists("key1") is False

    # Add key
    await cache.set("key1", "value1")
    assert await cache.exists("key1") is True

    # Delete key
    await cache.delete("key1")
    assert await cache.exists("key1") is False


@pytest.mark.asyncio
async def test_memory_cache_exists_with_ttl():
    """Test exists() with TTL expiration."""
    cache = MemoryCache(max_size=100)

    # Set with short TTL
    await cache.set("temp_key", "temp_value", ttl=1)

    # Should exist initially
    assert await cache.exists("temp_key") is True

    # Wait for expiration
    await asyncio.sleep(1.1)

    # Should not exist after expiration
    assert await cache.exists("temp_key") is False


@pytest.mark.asyncio
async def test_memory_cache_statistics():
    """Test cache statistics tracking."""
    cache = MemoryCache(max_size=100)

    # Initial stats
    stats = cache.get_stats()
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 0
    assert stats["cache_size"] == 0

    # Add item and miss
    await cache.get("nonexistent")
    stats = cache.get_stats()
    assert stats["cache_misses"] == 1

    # Set and hit
    await cache.set("key1", "value1")
    await cache.get("key1")
    stats = cache.get_stats()
    assert stats["cache_hits"] == 1
    assert stats["cache_size"] == 1

    # Hit rate
    assert stats["hit_rate"] == 0.5  # 1 hit, 1 miss = 50%


@pytest.mark.asyncio
async def test_memory_cache_disabled():
    """Test cache with size 0 (disabled)."""
    cache = MemoryCache(max_size=0)

    # Set should do nothing
    await cache.set("key1", "value1")

    # Get should return None
    result = await cache.get("key1")
    assert result is None

    # Stats should show cache is disabled
    stats = cache.get_stats()
    assert stats["max_size"] == 0
    assert stats["cache_size"] == 0


@pytest.mark.asyncio
async def test_memory_cache_close():
    """Test closing cache."""
    cache = MemoryCache(max_size=100)

    # Add items
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")

    # Close cache
    await cache.close()

    # Cache should be empty
    assert await cache.get("key1") is None
    assert await cache.get("key2") is None


@pytest.mark.asyncio
async def test_memory_cache_cleanup_expired():
    """Test manual cleanup of expired entries."""
    cache = MemoryCache(max_size=100)

    # Add items with different TTLs
    await cache.set("short", "value1", ttl=1)
    await cache.set("long", "value2", ttl=10)
    await cache.set("permanent", "value3")  # No TTL

    # Wait for short TTL to expire
    await asyncio.sleep(1.1)

    # Cleanup expired entries
    removed = cache.cleanup_expired()
    assert removed == 1

    # Short should be gone, others should remain
    assert await cache.get("short") is None
    assert await cache.get("long") == "value2"
    assert await cache.get("permanent") == "value3"


@pytest.mark.asyncio
async def test_memory_cache_complex_values():
    """Test caching complex Python objects."""
    cache = MemoryCache(max_size=100)

    # Cache dictionary
    dict_value = {"name": "Alice", "age": 30, "skills": ["python", "go"]}
    await cache.set("dict_key", dict_value)
    assert await cache.get("dict_key") == dict_value

    # Cache list
    list_value = [1, 2, 3, {"nested": "value"}]
    await cache.set("list_key", list_value)
    assert await cache.get("list_key") == list_value

    # Cache tuple
    tuple_value = ("a", "b", "c")
    await cache.set("tuple_key", tuple_value)
    assert await cache.get("tuple_key") == tuple_value

    # Cache custom object
    class CustomObject:
        def __init__(self, value):
            self.value = value

        def __eq__(self, other):
            return self.value == other.value

    obj = CustomObject(42)
    await cache.set("obj_key", obj)
    retrieved = await cache.get("obj_key")
    assert retrieved.value == 42


@pytest.mark.asyncio
async def test_memory_cache_concurrent_access():
    """Test concurrent cache access."""
    cache = MemoryCache(max_size=100)

    async def writer(key_num):
        """Write to cache."""
        await cache.set(f"key{key_num}", f"value{key_num}")

    async def reader(key_num):
        """Read from cache."""
        return await cache.get(f"key{key_num}")

    # Write concurrently
    await asyncio.gather(*[writer(i) for i in range(10)])

    # Read concurrently
    results = await asyncio.gather(*[reader(i) for i in range(10)])

    # All values should be present
    for i, result in enumerate(results):
        assert result == f"value{i}"


@pytest.mark.asyncio
async def test_memory_cache_stats_backend_field():
    """Test that stats include backend type."""
    cache = MemoryCache(max_size=100)
    stats = cache.get_stats()
    assert stats["backend"] == "memory"


@pytest.mark.asyncio
async def test_memory_cache_hit_rate_calculation():
    """Test hit rate calculation with various access patterns."""
    cache = MemoryCache(max_size=100)

    # 0 accesses
    stats = cache.get_stats()
    assert stats["hit_rate"] == 0.0

    # Add items
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")

    # 2 hits, 0 misses = 100%
    await cache.get("key1")
    await cache.get("key2")
    stats = cache.get_stats()
    assert stats["hit_rate"] == 1.0

    # 2 hits, 2 misses = 50%
    await cache.get("nonexistent1")
    await cache.get("nonexistent2")
    stats = cache.get_stats()
    assert stats["hit_rate"] == 0.5

    # 4 hits, 2 misses = 66.67%
    await cache.get("key1")
    await cache.get("key2")
    stats = cache.get_stats()
    assert abs(stats["hit_rate"] - 0.6667) < 0.01
