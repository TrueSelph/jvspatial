"""Tests for the read-through cache wrapper, CachingDatabase."""

import asyncio
import tempfile
import time
from typing import Iterator
from unittest.mock import patch

import pytest

from jvspatial.db._cache import CachingDatabase
from jvspatial.db.factory import create_database
from jvspatial.db.jsondb import JsonDB


@pytest.fixture
def jsondb() -> Iterator[JsonDB]:
    with tempfile.TemporaryDirectory() as tmp:
        yield JsonDB(base_path=tmp)


# ----- basic correctness ---------------------------------------------


class TestPositiveCache:
    async def test_get_caches_first_call(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8, ttl_seconds=60)
        await jsondb.save("node", {"id": "x", "v": 1})

        first = await cached.get("node", "x")
        second = await cached.get("node", "x")

        assert first == second == {"id": "x", "v": 1}
        stats = cached.cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 1

    async def test_returned_dict_is_a_copy(self, jsondb):
        """Mutating a returned dict must not poison the cache."""
        cached = CachingDatabase(jsondb, max_entries=8)
        await jsondb.save("node", {"id": "x", "v": 1})
        first = await cached.get("node", "x")
        first["v"] = 9999
        second = await cached.get("node", "x")
        assert second["v"] == 1


class TestNegativeCache:
    async def test_missing_id_negative_cached(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8, ttl_seconds=60)
        # Two consecutive misses -> only one underlying call.
        with patch.object(jsondb, "get", wraps=jsondb.get) as wrapped:
            assert await cached.get("node", "ghost") is None
            assert await cached.get("node", "ghost") is None
        assert wrapped.call_count == 1
        stats = cached.cache_stats()
        assert stats["misses"] == 1
        assert stats["hits"] == 1


# ----- invalidation ---------------------------------------------------


class TestInvalidation:
    async def test_save_refreshes_cached_entry(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8)
        await cached.save("node", {"id": "x", "v": 1})
        # Update via cached path -- cache should now reflect the new state.
        await cached.save("node", {"id": "x", "v": 2})
        result = await cached.get("node", "x")
        assert result["v"] == 2
        # Second get is a hit.
        await cached.get("node", "x")
        assert cached.cache_stats()["hits"] >= 1

    async def test_delete_invalidates(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8)
        await jsondb.save("node", {"id": "x", "v": 1})
        await cached.get("node", "x")  # populate cache
        await cached.delete("node", "x")
        # Next get must hit the backend, not the stale cache.
        result = await cached.get("node", "x")
        assert result is None
        # Stats record the invalidation.
        assert cached.cache_stats()["invalidations"] == 1

    async def test_find_one_and_delete_invalidates(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8)
        await jsondb.save("node", {"id": "x", "v": 1})
        await cached.get("node", "x")  # populate
        deleted = await cached.find_one_and_delete("node", {"_id": "x"})
        assert deleted is not None
        assert await cached.get("node", "x") is None

    async def test_find_one_and_update_refreshes(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8)
        await jsondb.save("node", {"id": "x", "v": 1, "_id": "x"})
        await cached.get("node", "x")  # populate
        updated = await cached.find_one_and_update(
            "node", {"_id": "x"}, {"$set": {"v": 99}}
        )
        assert updated["v"] == 99
        # Reads come from the freshly-cached value.
        result = await cached.get("node", "x")
        assert result["v"] == 99


# ----- TTL ------------------------------------------------------------


class TestTTL:
    async def test_ttl_expiry_forces_refresh(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8, ttl_seconds=0.05)
        await jsondb.save("node", {"id": "x", "v": 1})
        await cached.get("node", "x")  # cache populated

        # Mutate the underlying record OUT OF BAND so the cached value
        # is now stale. This is exactly the case TTL is meant to catch.
        await jsondb.save("node", {"id": "x", "v": 2})

        # Within TTL: still see stale cached value.
        result = await cached.get("node", "x")
        assert result["v"] == 1

        # After TTL: re-fetch sees the fresh value.
        await asyncio.sleep(0.08)
        result = await cached.get("node", "x")
        assert result["v"] == 2


# ----- LRU bound ------------------------------------------------------


class TestLRUBound:
    async def test_evicts_oldest_when_at_capacity(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=3, ttl_seconds=60)
        for i in range(5):
            await jsondb.save("node", {"id": f"r{i}", "v": i})
            await cached.get("node", f"r{i}")
        # Cache holds at most 3 entries.
        assert cached.cache_stats()["size"] == 3
        assert cached.cache_stats()["evictions"] == 2


# ----- Disabled / serverless -----------------------------------------


class TestDisabled:
    async def test_max_entries_zero_disables_caching(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=0)
        await jsondb.save("node", {"id": "x", "v": 1})
        # Two reads -> two underlying calls, no caching.
        with patch.object(jsondb, "get", wraps=jsondb.get) as wrapped:
            await cached.get("node", "x")
            await cached.get("node", "x")
        assert wrapped.call_count == 2

    async def test_serverless_mode_disables_caching(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8)
        await jsondb.save("node", {"id": "x", "v": 1})
        with patch("jvspatial.db._cache.is_serverless_mode", return_value=True):
            with patch.object(jsondb, "get", wraps=jsondb.get) as wrapped:
                await cached.get("node", "x")
                await cached.get("node", "x")
            assert wrapped.call_count == 2


# ----- Wiring ---------------------------------------------------------


class TestFactoryWiring:
    async def test_create_database_wraps_when_cache_size_set(self, tmp_path):
        db = create_database(
            "json",
            base_path=str(tmp_path),
            cache_get_size=16,
            cache_get_ttl=30.0,
        )
        assert isinstance(db, CachingDatabase)
        assert db._max_entries == 16
        assert db._ttl == 30.0

    async def test_create_database_no_wrap_by_default(self, tmp_path):
        db = create_database("json", base_path=str(tmp_path))
        assert not isinstance(db, CachingDatabase)


# ----- Pass-through ---------------------------------------------------


class TestPassThrough:
    async def test_supports_transactions_mirrors_inner(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8)
        assert cached.supports_transactions == jsondb.supports_transactions

    async def test_attribute_access_falls_through(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8)
        # base_path is a JsonDB attribute, not on Database.
        assert cached.base_path == jsondb.base_path

    async def test_count_passes_through(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8)
        await jsondb.save("node", {"id": "a", "v": 1})
        await jsondb.save("node", {"id": "b", "v": 2})
        assert await cached.count("node") == 2
        assert await cached.count("node", {"v": 1}) == 1

    async def test_find_passes_through_uncached(self, jsondb):
        cached = CachingDatabase(jsondb, max_entries=8)
        await jsondb.save("node", {"id": "a", "v": 1})
        await jsondb.save("node", {"id": "b", "v": 2})
        results = await cached.find("node", {})
        assert len(results) == 2
        # Crucially, find() doesn't populate the cache.
        assert cached.cache_stats()["size"] == 0
