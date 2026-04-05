"""Unit tests for Redis cache serialization (no Redis server required)."""

import pickle

import pytest

pytest.importorskip("redis.asyncio")

from jvspatial.cache.redis import (
    _JSON_VALUE_PREFIX,
    RedisCache,
    _redis_serialization_mode,
)


def test_redis_serialization_mode_default(monkeypatch):
    monkeypatch.delenv("JVSPATIAL_REDIS_SERIALIZATION", raising=False)
    assert _redis_serialization_mode() == "json"


def test_redis_serialization_mode_pickle(monkeypatch):
    monkeypatch.setenv("JVSPATIAL_REDIS_SERIALIZATION", "pickle")
    assert _redis_serialization_mode() == "pickle"


def test_json_mode_roundtrip():
    cache = RedisCache(redis_url="redis://localhost:6379", serialization="json")
    for value in ({"a": 1, "b": [2, 3]}, "text", 42, None, True):
        raw = cache._serialize(value)
        assert raw.startswith(_JSON_VALUE_PREFIX)
        assert cache._deserialize(raw) == value


def test_json_mode_reads_legacy_pickle():
    cache = RedisCache(redis_url="redis://localhost:6379", serialization="json")
    legacy = pickle.dumps({"legacy": True})
    assert not legacy.startswith(_JSON_VALUE_PREFIX)
    assert cache._deserialize(legacy) == {"legacy": True}


def test_pickle_mode_roundtrip():
    cache = RedisCache(redis_url="redis://localhost:6379", serialization="pickle")
    obj = {"x": 1}
    raw = cache._serialize(obj)
    assert cache._deserialize(raw) == obj


def test_json_mode_rejects_non_serializable():
    cache = RedisCache(redis_url="redis://localhost:6379", serialization="json")

    class Opaque:
        pass

    with pytest.raises((TypeError, ValueError)):
        cache._serialize({"o": Opaque()})
