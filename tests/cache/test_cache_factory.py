"""Tests for cache factory and configuration."""

import os

import pytest

from jvspatial.cache.factory import create_cache, create_default_cache
from jvspatial.cache.memory import MemoryCache


@pytest.mark.asyncio
async def test_create_cache_explicit_memory():
    """Test explicit memory cache creation."""
    cache = create_cache("memory", cache_size=500)

    assert isinstance(cache, MemoryCache)
    assert cache.max_size == 500

    # Test it works
    await cache.set("test", "value")
    assert await cache.get("test") == "value"


@pytest.mark.asyncio
async def test_get_cache_backend_default_memory(monkeypatch):
    """Test default memory cache creation via environment."""
    monkeypatch.setenv("JVSPATIAL_CACHE_BACKEND", "memory")
    monkeypatch.setenv("JVSPATIAL_CACHE_SIZE", "2000")

    cache = create_default_cache()

    assert isinstance(cache, MemoryCache)
    assert cache.max_size == 2000


@pytest.mark.asyncio
async def test_get_cache_backend_no_env_defaults_to_memory(monkeypatch):
    """Test that cache defaults to memory when no env vars set."""
    # Clear any cache-related env vars
    monkeypatch.delenv("JVSPATIAL_CACHE_BACKEND", raising=False)
    monkeypatch.delenv("JVSPATIAL_REDIS_URL", raising=False)
    monkeypatch.delenv("JVSPATIAL_CACHE_SIZE", raising=False)

    cache = create_default_cache()

    assert isinstance(cache, MemoryCache)
    # Should use default size of 1000
    assert cache.max_size == 1000


@pytest.mark.asyncio
async def test_get_cache_backend_invalid_backend():
    """Test error handling for invalid backend type."""
    with pytest.raises(ValueError) as exc_info:
        create_cache("invalid_backend")

    assert "Unknown cache backend" in str(exc_info.value)
    assert "invalid_backend" in str(exc_info.value)


@pytest.mark.asyncio
async def test_get_cache_backend_cache_size_zero():
    """Test creating disabled cache with size 0."""
    cache = create_cache("memory", cache_size=0)

    assert isinstance(cache, MemoryCache)
    assert cache.max_size == 0

    # Verify caching is disabled
    await cache.set("test", "value")
    assert await cache.get("test") is None


@pytest.mark.asyncio
async def test_create_default_cache_no_config(monkeypatch):
    """Test create_default_cache with no configuration."""
    monkeypatch.delenv("JVSPATIAL_CACHE_BACKEND", raising=False)
    monkeypatch.delenv("JVSPATIAL_REDIS_URL", raising=False)

    cache = create_default_cache()

    assert isinstance(cache, MemoryCache)


@pytest.mark.asyncio
async def test_get_cache_backend_env_cache_size(monkeypatch):
    """Test that JVSPATIAL_CACHE_SIZE env var is respected."""
    monkeypatch.setenv("JVSPATIAL_CACHE_SIZE", "5000")

    cache = create_default_cache()

    assert cache.max_size == 5000


@pytest.mark.asyncio
async def test_get_cache_backend_explicit_overrides_env(monkeypatch):
    """Test that explicit cache_size overrides environment."""
    monkeypatch.setenv("JVSPATIAL_CACHE_SIZE", "5000")

    cache = create_cache("memory", cache_size=3000)

    # Explicit parameter should win
    assert cache.max_size == 3000


@pytest.mark.asyncio
async def test_cache_backend_case_insensitive(monkeypatch):
    """Test that backend names are case-insensitive."""
    monkeypatch.setenv("JVSPATIAL_CACHE_BACKEND", "MEMORY")

    cache = create_cache()

    assert isinstance(cache, MemoryCache)


@pytest.mark.asyncio
async def test_cache_factory_integration():
    """Test full integration of cache factory."""
    # Create cache with explicit config
    cache = create_cache("memory", cache_size=100)

    # Use it
    await cache.set("key1", "value1")
    await cache.set("key2", "value2")
    await cache.set("key3", "value3")

    # Verify
    assert await cache.get("key1") == "value1"
    assert await cache.get("key2") == "value2"
    assert await cache.get("key3") == "value3"

    # Check stats
    stats = cache.get_stats()
    assert stats["cache_size"] == 3
    assert stats["max_size"] == 100
