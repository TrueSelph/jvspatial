"""Tests for the session store wrapper used by AuthService.

Covers:

* InProcessSessionStore TTL + delete semantics.
* The contract that AuthService relies on (get/set/delete with optional TTL).
* The wiring path: AuthenticationService accepts ``session_store=`` and
  delegates blacklist cache reads/writes through it.

RedisSessionStore live behavior is exercised by the cache layer's own
integration tests; here we cover the contract path with a stub.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, Optional

import pytest

from jvspatial.api.auth._session_store import (
    InProcessSessionStore,
    RedisSessionStore,
    SessionStore,
    create_session_store,
)

pytestmark = pytest.mark.asyncio


class TestInProcessSessionStore:
    async def test_round_trip(self) -> None:
        store = InProcessSessionStore()
        await store.set("k", True)
        assert await store.get("k") is True
        await store.delete("k")
        assert await store.get("k") is None

    async def test_missing_key_returns_none(self) -> None:
        store = InProcessSessionStore()
        assert await store.get("nope") is None

    async def test_ttl_expiry(self) -> None:
        store = InProcessSessionStore(default_ttl=1)
        await store.set("temp", "value")
        assert await store.get("temp") == "value"
        # Force expiry by advancing the store's view of time.
        store._data["temp"] = (store._data["temp"][0], time.time() - 1)
        assert await store.get("temp") is None
        # Stale entry pruned on miss.
        assert "temp" not in store._data

    async def test_ttl_zero_means_no_expiry(self) -> None:
        store = InProcessSessionStore(default_ttl=0)
        await store.set("forever", 42)
        # Even after waiting, entry persists.
        await asyncio.sleep(0.01)
        assert await store.get("forever") == 42

    async def test_explicit_ttl_overrides_default(self) -> None:
        store = InProcessSessionStore(default_ttl=3600)
        await store.set("k", "v", ttl=0)  # no expiry
        # Stored with no expiry regardless of default.
        _, expires_at = store._data["k"]
        assert expires_at is None


class TestCreateSessionStore:
    def test_default_returns_inprocess(self) -> None:
        store = create_session_store(None)
        assert isinstance(store, InProcessSessionStore)

    def test_memory_returns_inprocess(self) -> None:
        store = create_session_store("memory")
        assert isinstance(store, InProcessSessionStore)

    def test_redis_string_without_env_raises(self, monkeypatch) -> None:
        monkeypatch.delenv("JVSPATIAL_REDIS_URL", raising=False)
        with pytest.raises(ValueError, match="JVSPATIAL_REDIS_URL"):
            create_session_store("redis")

    def test_url_string_routes_to_redis_wrapper(self, monkeypatch) -> None:
        # We can't reach a live Redis here; just verify the URL string
        # path produces a RedisSessionStore (the construction call
        # itself is the unit; the actual Redis connection happens
        # lazily inside RedisCache on first op).
        # Mock the redis backend to avoid network.
        from jvspatial.cache import factory as cache_factory

        class _Stub:
            async def get(self, key):
                return None

            async def set(self, key, value, ttl=None):
                pass

            async def delete(self, key):
                pass

        monkeypatch.setattr(cache_factory, "create_cache", lambda *a, **kw: _Stub())
        store = create_session_store("redis://localhost:6379/0")
        assert isinstance(store, RedisSessionStore)


class _FakeCache:
    """Stub mimicking enough of RedisCache for RedisSessionStore tests.

    Stores raw set() arguments so we can assert on them without
    needing a live Redis. Returns values verbatim from ``get`` so
    we can verify the JSON envelope our wrapper produces.
    """

    def __init__(self) -> None:
        self.data: Dict[str, Any] = {}
        self.sets: list = []

    async def get(self, key: str) -> Optional[Any]:
        return self.data.get(key)

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        self.data[key] = value
        self.sets.append((key, value, ttl))

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)


class TestRedisSessionStore:
    async def test_set_json_encodes(self) -> None:
        cache = _FakeCache()
        store = RedisSessionStore(cache, prefix="jvs:test:")
        await store.set("k", {"hello": "world"})
        key, value, _ = cache.sets[0]
        assert key == "jvs:test:k"
        # Stored as JSON.
        assert value == '{"hello": "world"}'

    async def test_get_json_decodes(self) -> None:
        cache = _FakeCache()
        cache.data["jvs:test:k"] = '{"flag": true}'
        store = RedisSessionStore(cache, prefix="jvs:test:")
        assert await store.get("k") == {"flag": True}

    async def test_get_handles_missing(self) -> None:
        store = RedisSessionStore(_FakeCache(), prefix="jvs:test:")
        assert await store.get("nope") is None

    async def test_get_falls_back_on_bad_json(self) -> None:
        cache = _FakeCache()
        cache.data["jvs:test:k"] = "not-json"
        store = RedisSessionStore(cache, prefix="jvs:test:")
        # Falls back to the raw string rather than raising.
        assert await store.get("k") == "not-json"

    async def test_explicit_ttl_passed_through(self) -> None:
        cache = _FakeCache()
        store = RedisSessionStore(cache, default_ttl=300, prefix="jvs:test:")
        await store.set("k", True, ttl=60)
        _, _, ttl = cache.sets[0]
        assert ttl == 60

    async def test_default_ttl_used_when_unset(self) -> None:
        cache = _FakeCache()
        store = RedisSessionStore(cache, default_ttl=300, prefix="jvs:test:")
        await store.set("k", True)
        _, _, ttl = cache.sets[0]
        assert ttl == 300

    async def test_get_error_returns_none(self) -> None:
        class _BadCache(_FakeCache):
            async def get(self, key: str) -> Any:
                raise RuntimeError("redis unreachable")

        store = RedisSessionStore(_BadCache(), prefix="jvs:test:")
        # Treat failure as a miss so the caller falls back to the DB
        # rather than crashing.
        assert await store.get("k") is None


# ---- AuthenticationService integration -------------------------------------


class TestAuthServiceSessionStoreIntegration:
    """Smoke test the wiring path — full auth integration lives in
    test_auth_service.py."""

    async def test_session_store_default_is_inprocess(self) -> None:
        import tempfile

        from jvspatial.api.auth.service import AuthenticationService
        from jvspatial.core.context import GraphContext
        from jvspatial.db.jsondb import JsonDB

        with tempfile.TemporaryDirectory() as tmp:
            ctx = GraphContext(database=JsonDB(base_path=tmp))
            svc = AuthenticationService(
                context=ctx, jwt_secret="x-test-jwt-secret-1234567890"
            )
            assert isinstance(svc._session_store, InProcessSessionStore)

    async def test_session_store_can_be_overridden(self) -> None:
        import tempfile

        from jvspatial.api.auth.service import AuthenticationService
        from jvspatial.core.context import GraphContext
        from jvspatial.db.jsondb import JsonDB

        custom = InProcessSessionStore(default_ttl=999)
        with tempfile.TemporaryDirectory() as tmp:
            ctx = GraphContext(database=JsonDB(base_path=tmp))
            svc = AuthenticationService(
                context=ctx,
                jwt_secret="x-test-jwt-secret-1234567890",
                session_store=custom,
            )
            assert svc._session_store is custom
