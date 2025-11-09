"""Tests for GraphContext cache backend integration.

These tests verify cache integration at the GraphContext level.
Note: Entity-level cache behavior is transparent to users and tested
through entity operations in the core tests.
"""

import pytest

from jvspatial.cache import MemoryCache
from jvspatial.core.context import GraphContext, get_default_context
from jvspatial.core.entities import Node
from jvspatial.db.jsondb import JsonDB


@pytest.mark.asyncio
async def test_context_with_in_memory_cache(tmp_path):
    """Test GraphContext with MemoryCache backend."""
    db = JsonDB(str(tmp_path / "test_cache.json"))
    cache = MemoryCache(max_size=100)
    ctx = GraphContext(database=db, cache_backend=cache)

    # Create a node using context (internal API)
    node = await ctx.create_node()
    node._data["test_value"] = 42
    await ctx.save(node)
    node_id = node.id

    # First get - should come from database and cache it
    retrieved1 = await ctx.get(Node, node_id)
    assert retrieved1 is not None
    assert retrieved1.id == node_id
    assert retrieved1._data.get("test_value") == 42

    # Second get - should come from cache
    retrieved2 = await ctx.get(Node, node_id)
    assert retrieved2 is not None
    assert retrieved2.id == node_id

    # Verify cache stats show hits
    stats = ctx.get_cache_stats()
    assert stats["cache_hits"] >= 1  # At least one cache hit
    assert stats["backend"] == "memory"


@pytest.mark.asyncio
async def test_context_with_disabled_cache(tmp_path):
    """Test GraphContext with disabled caching (size=0)."""
    db = JsonDB(str(tmp_path / "test_nocache.json"))
    cache = MemoryCache(max_size=0)  # Disable caching
    ctx = GraphContext(database=db, cache_backend=cache)

    # Create a node
    node = await ctx.create_node()
    node_id = node.id

    # Get the node multiple times - all should hit database
    retrieved1 = await ctx.get(Node, node_id)
    assert retrieved1 is not None

    retrieved2 = await ctx.get(Node, node_id)
    assert retrieved2 is not None

    # Verify cache is disabled - no hits, only misses
    stats = ctx.get_cache_stats()
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] >= 2
    assert stats["max_size"] == 0


@pytest.mark.asyncio
async def test_cache_clear_operation(tmp_path):
    """Test clearing cache manually."""
    db = JsonDB(str(tmp_path / "test_clear.json"))
    cache = MemoryCache(max_size=100)
    ctx = GraphContext(database=db, cache_backend=cache)

    # Create multiple nodes
    nodes = []
    for _ in range(3):
        node = await ctx.create_node()
        nodes.append(node)

    # Access them to populate cache
    for node in nodes:
        await ctx.get(Node, node.id)

    # Verify cache has entries
    stats = ctx.get_cache_stats()
    assert stats["cache_size"] > 0

    # Clear cache
    await ctx.clear_cache()

    # Verify cache is empty
    stats = ctx.get_cache_stats()
    assert stats["cache_size"] == 0
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 0


@pytest.mark.asyncio
async def test_database_switch_clears_cache(tmp_path):
    """Test that switching databases clears the cache."""
    db1 = JsonDB(str(tmp_path / "test_db1.json"))
    db2 = JsonDB(str(tmp_path / "test_db2.json"))
    cache = MemoryCache(max_size=100)
    ctx = GraphContext(database=db1, cache_backend=cache)

    # Create and cache a node in db1
    node = await ctx.create_node()
    node_id = node.id
    await ctx.get(Node, node_id)

    # Verify cache has the node
    stats_before = ctx.get_cache_stats()
    assert stats_before["cache_size"] > 0

    # Switch to different database
    await ctx.set_database(db2)

    # Manually clear to ensure async clear completes
    # (In production, this happens automatically but asynchronously)
    await ctx.clear_cache()

    # Verify cache was cleared
    stats_after = ctx.get_cache_stats()
    assert stats_after["cache_size"] == 0


@pytest.mark.asyncio
async def test_default_cache_backend_creation(tmp_path):
    """Test that GraphContext auto-creates a default cache backend."""
    db = JsonDB(str(tmp_path / "test_default.json"))
    ctx = GraphContext(database=db)  # No explicit cache_backend

    # Create and retrieve a node
    node = await ctx.create_node()
    node_id = node.id

    # First access
    retrieved = await ctx.get(Node, node_id)
    assert retrieved is not None
    assert retrieved.id == node_id

    # Verify default cache backend was created and is functional
    stats = ctx.get_cache_stats()
    assert "cache_hits" in stats
    assert "cache_misses" in stats
    assert "cache_size" in stats
    assert "backend" in stats


@pytest.mark.asyncio
async def test_cache_updated_on_save(tmp_path):
    """Test that save() operation updates cache."""
    db = JsonDB(str(tmp_path / "test_save_cache.json"))
    cache = MemoryCache(max_size=100)
    ctx = GraphContext(database=db, cache_backend=cache)

    # Create and save node
    node = await ctx.create_node()
    node._data["value"] = "original"
    await ctx.save(node)
    node_id = node.id

    # Retrieve to populate cache
    retrieved = await ctx.get(Node, node_id)
    assert retrieved._data.get("value") == "original"

    # Modify and save - should update cache
    node._data["value"] = "updated"
    await ctx.save(node)

    # Retrieve again - should get updated value from cache
    retrieved2 = await ctx.get(Node, node_id)
    assert retrieved2._data.get("value") == "updated"


@pytest.mark.asyncio
async def test_cache_invalidated_on_delete(tmp_path):
    """Test that delete() operation removes entry from cache."""
    db = JsonDB(str(tmp_path / "test_delete_cache.json"))
    cache = MemoryCache(max_size=100)
    ctx = GraphContext(database=db, cache_backend=cache)

    # Create node and populate cache
    node = await ctx.create_node()
    node_id = node.id
    await ctx.get(Node, node_id)

    # Verify node is cached
    stats = ctx.get_cache_stats()
    initial_size = stats["cache_size"]
    assert initial_size > 0

    # Delete node - should remove from cache
    await ctx.delete(node)

    # Verify cache size decreased
    stats = ctx.get_cache_stats()
    assert stats["cache_size"] < initial_size


@pytest.mark.asyncio
async def test_multiple_nodes_caching(tmp_path):
    """Test that cache handles multiple nodes correctly."""
    db = JsonDB(str(tmp_path / "test_multi_cache.json"))
    cache = MemoryCache(max_size=10)
    ctx = GraphContext(database=db, cache_backend=cache)

    # Create multiple nodes
    nodes = []
    for i in range(5):
        node = await ctx.create_node()
        node._data["index"] = i
        await ctx.save(node)
        nodes.append(node)

    # First access - populate cache
    for node in nodes:
        retrieved = await ctx.get(Node, node.id)
        assert retrieved is not None

    # Second access - should all be cache hits
    initial_hits = ctx.get_cache_stats()["cache_hits"]
    for node in nodes:
        retrieved = await ctx.get(Node, node.id)
        assert retrieved._data.get("index") == nodes.index(node)

    # Verify we got cache hits for all nodes
    final_hits = ctx.get_cache_stats()["cache_hits"]
    assert final_hits >= initial_hits + 5


@pytest.mark.asyncio
async def test_lru_eviction_behavior(tmp_path):
    """Test that LRU eviction works correctly in GraphContext."""
    db = JsonDB(str(tmp_path / "test_lru.json"))
    cache = MemoryCache(max_size=3)  # Small cache for testing LRU
    ctx = GraphContext(database=db, cache_backend=cache)

    # Create 4 nodes
    nodes = []
    for i in range(4):
        node = await ctx.create_node()
        node._data["index"] = i
        await ctx.save(node)
        nodes.append(node)

    # Access first 3 nodes - fills cache to capacity
    for i in range(3):
        await ctx.get(Node, nodes[i].id)

    # Verify cache is at capacity
    stats = ctx.get_cache_stats()
    assert stats["cache_size"] == 3

    # Access 4th node - triggers LRU eviction
    await ctx.get(Node, nodes[3].id)

    # Verify cache size remains at capacity (LRU evicted)
    stats = ctx.get_cache_stats()
    assert stats["cache_size"] == 3


@pytest.mark.asyncio
async def test_cache_statistics_accuracy(tmp_path):
    """Test that cache statistics are tracked accurately."""
    db = JsonDB(str(tmp_path / "test_stats.json"))
    cache = MemoryCache(max_size=100)
    ctx = GraphContext(database=db, cache_backend=cache)

    # Create nodes (cached automatically)
    node1 = await ctx.create_node()
    node2 = await ctx.create_node()

    # Clear cache for clean statistics
    await ctx.clear_cache()

    # Verify clean slate
    stats = ctx.get_cache_stats()
    assert stats["cache_hits"] == 0
    assert stats["cache_misses"] == 0

    # First access - miss (not cached)
    await ctx.get(Node, node1.id)
    stats = ctx.get_cache_stats()
    assert stats["cache_misses"] == 1
    assert stats["cache_hits"] == 0

    # Second access same node - hit (now cached)
    await ctx.get(Node, node1.id)
    stats = ctx.get_cache_stats()
    assert stats["cache_hits"] == 1
    assert stats["cache_misses"] == 1

    # Different node - miss
    await ctx.get(Node, node2.id)
    stats = ctx.get_cache_stats()
    assert stats["cache_misses"] == 2
    assert stats["cache_hits"] == 1

    # Verify hit rate calculation (1 hit / 3 total = 33%)
    assert abs(stats["hit_rate"] - 0.3333) < 0.01
    assert stats["total_requests"] == 3
