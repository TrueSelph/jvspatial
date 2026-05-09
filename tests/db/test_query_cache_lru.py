"""LRU bounding behavior of QueryEngine's optimization cache."""

import pytest

from jvspatial.db.query import DEFAULT_QUERY_CACHE_SIZE, QueryEngine


class TestQueryCacheLRU:
    def test_default_size_constant_exposed(self):
        # Sanity: the constant is accessible to operators tuning the cap.
        assert DEFAULT_QUERY_CACHE_SIZE > 0

    def test_cache_bounded_to_max_size(self):
        engine = QueryEngine(cache_size=4)
        for i in range(50):
            engine.optimize_query({"key": i})
        assert len(engine._query_cache) == 4

    def test_lru_promotion_keeps_hot_entries(self):
        engine = QueryEngine(cache_size=3)
        for i in range(3):
            engine.optimize_query({"k": i})
        # Touch entry 0 so it becomes the most-recently-used.
        engine.optimize_query({"k": 0})
        # Insert a new entry. The LRU victim should be 1, not 0.
        engine.optimize_query({"k": 99})
        keys = [str(sorted(d.items())) for d in [{"k": 0}, {"k": 2}, {"k": 99}]]
        for key in keys:
            assert key in engine._query_cache
        assert str(sorted({"k": 1}.items())) not in engine._query_cache

    def test_eviction_count_tracked_in_stats(self):
        engine = QueryEngine(cache_size=2)
        for i in range(5):
            engine.optimize_query({"k": i})
        assert engine._optimization_stats["cache_evictions"] == 3

    def test_disabled_cache_zero_size(self):
        engine = QueryEngine(cache_size=0)
        for i in range(10):
            engine.optimize_query({"k": i})
        assert len(engine._query_cache) == 0
        # Cache hits stat must remain zero.
        assert engine._optimization_stats["cache_hits"] == 0

    def test_negative_cache_size_rejected(self):
        with pytest.raises(ValueError):
            QueryEngine(cache_size=-1)

    def test_cache_hit_returns_cached_value(self):
        engine = QueryEngine(cache_size=8)
        first = engine.optimize_query({"k": 1})
        second = engine.optimize_query({"k": 1})
        assert engine._optimization_stats["cache_hits"] == 1
        # Same object identity since we return the cached reference.
        assert first is second
