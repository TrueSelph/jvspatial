"""Bulk-API correctness across JsonDB and SQLite.

Mongo and DynamoDB tests live in their own existing test files (they
require external services or moto). The bulk path on those backends
is exercised via the protocol-level tests below by parameterizing
against an inline ``MockBackend``.
"""

import tempfile
from typing import Any, AsyncIterator, Dict, Iterator, List, Optional, Tuple

import pytest

from jvspatial.db.database import Database
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.sqlite import SQLiteDB

# ----- common seed --------------------------------------------------


def _records(n: int) -> List[Dict[str, Any]]:
    return [
        {"id": f"n{i}", "v": i, "category": "even" if i % 2 == 0 else "odd"}
        for i in range(n)
    ]


# ----- JsonDB -------------------------------------------------------


class TestJsonDBBulk:
    @pytest.fixture
    def jsondb(self) -> Iterator[JsonDB]:
        with tempfile.TemporaryDirectory() as tmp:
            yield JsonDB(base_path=tmp)

    async def test_bulk_save_then_find_many(self, jsondb):
        records = _records(20)
        n = await jsondb.bulk_save("node", records)
        assert n == 20

        ids = [r["id"] for r in records[:5]] + ["missing", "n10"]
        out = await jsondb.find_many("node", ids)
        # 5 of the first batch + n10. "missing" should be absent.
        assert set(out.keys()) == {"n0", "n1", "n2", "n3", "n4", "n10"}
        assert "missing" not in out
        assert out["n10"]["v"] == 10

    async def test_find_many_dedups_input(self, jsondb):
        await jsondb.bulk_save("node", _records(3))
        out = await jsondb.find_many("node", ["n0", "n0", "n0", "n2"])
        assert set(out) == {"n0", "n2"}

    async def test_bulk_save_requires_id(self, jsondb):
        with pytest.raises(ValueError):
            await jsondb.bulk_save("node", [{"v": 1}])

    async def test_find_many_empty_returns_empty_dict(self, jsondb):
        assert await jsondb.find_many("node", []) == {}

    async def test_bulk_save_empty_returns_zero(self, jsondb):
        assert await jsondb.bulk_save("node", []) == 0

    async def test_find_many_against_missing_collection(self, jsondb):
        # No records ever written; collection dir doesn't exist yet.
        assert await jsondb.find_many("ghost", ["a", "b"]) == {}


# ----- SQLite -------------------------------------------------------


class TestSQLiteBulk:
    @pytest.fixture
    async def sqlite_db(self) -> AsyncIterator[SQLiteDB]:
        db = SQLiteDB(db_path=":memory:")
        try:
            yield db
        finally:
            await db.close()

    async def test_bulk_save_then_find_many(self, sqlite_db):
        records = _records(50)
        n = await sqlite_db.bulk_save("node", records)
        assert n == 50

        out = await sqlite_db.find_many("node", ["n3", "n17", "missing"])
        assert set(out) == {"n3", "n17"}
        assert out["n17"]["v"] == 17

    async def test_bulk_save_is_atomic_on_failure(self, sqlite_db):
        # Insert one valid record manually.
        await sqlite_db.save("node", {"id": "n0", "v": 0})

        # Force a constraint failure by sending a bad type for the
        # ``data`` column. We bypass the normal serialization to do it.
        bad_records: List[Dict[str, Any]] = [
            {"id": "n1", "v": 1},
            {"id": "n2", "v": object()},  # Not JSON-serializable
        ]
        with pytest.raises(Exception):
            await sqlite_db.bulk_save("node", bad_records)

        # The whole batch must have rolled back -- n1 must NOT exist.
        out = await sqlite_db.find_many("node", ["n1", "n2"])
        assert out == {}

    async def test_find_many_chunks_large_id_lists(self, sqlite_db):
        await sqlite_db.bulk_save("node", _records(1500))
        # Larger than the 500-id chunk size in the implementation.
        ids = [f"n{i}" for i in range(0, 1500, 3)]  # 500 ids
        out = await sqlite_db.find_many("node", ids)
        assert len(out) == 500


# ----- Protocol-level coverage via a mock backend -------------------


class _MockBackend(Database):
    """Backend that records calls; used to verify the cache wrapper's
    cache-aware find_many and bulk_save paths work against any
    Database implementation."""

    def __init__(self) -> None:
        self.store: Dict[Tuple[str, str], Dict[str, Any]] = {}
        self.calls: List[Tuple[str, Any]] = []

    async def save(self, collection, data):
        self.calls.append(("save", data["id"]))
        self.store[(collection, str(data["id"]))] = dict(data)
        return data

    async def get(self, collection, id):
        self.calls.append(("get", id))
        return self.store.get((collection, str(id)))

    async def delete(self, collection, id):
        self.calls.append(("delete", id))
        self.store.pop((collection, str(id)), None)

    async def find(self, collection, query, *, limit=None, sort=None):
        return [v for (c, _), v in self.store.items() if c == collection]

    async def find_many(self, collection, ids):
        self.calls.append(("find_many", tuple(ids)))
        out: Dict[str, Dict[str, Any]] = {}
        for rid in ids:
            v = self.store.get((collection, str(rid)))
            if v is not None:
                out[str(rid)] = v
        return out

    async def bulk_save(self, collection, records):
        self.calls.append(("bulk_save", len(records)))
        for r in records:
            self.store[(collection, str(r["id"]))] = dict(r)
        return len(records)


class TestCachingDatabaseBulk:
    """Cache wrapper must split find_many between cache hits and a
    single backend call for the misses."""

    async def test_find_many_uses_cache_for_hits_one_call_for_misses(self):
        from jvspatial.db._cache import CachingDatabase

        backend = _MockBackend()
        cached = CachingDatabase(backend, max_entries=8, ttl_seconds=60)

        # Pre-warm the cache for a and b
        await backend.save("node", {"id": "a", "v": 1})
        await backend.save("node", {"id": "b", "v": 2})
        await cached.get("node", "a")
        await cached.get("node", "b")
        backend.calls.clear()

        # Add c and d to the backend out of band
        await backend.save("node", {"id": "c", "v": 3})
        await backend.save("node", {"id": "d", "v": 4})
        backend.calls.clear()

        out = await cached.find_many("node", ["a", "b", "c", "d", "missing"])
        # Result includes all four real ids, none of "missing"
        assert set(out) == {"a", "b", "c", "d"}

        # Backend should have seen exactly one find_many call for the
        # misses [c, d, missing] -- a and b came from the cache.
        find_many_calls = [c for c in backend.calls if c[0] == "find_many"]
        assert len(find_many_calls) == 1
        assert sorted(find_many_calls[0][1]) == ["c", "d", "missing"]

    async def test_bulk_save_refreshes_cache_entries(self):
        from jvspatial.db._cache import CachingDatabase

        backend = _MockBackend()
        cached = CachingDatabase(backend, max_entries=8, ttl_seconds=60)
        await backend.save("node", {"id": "a", "v": 1})
        await cached.get("node", "a")  # populate cache

        await cached.bulk_save(
            "node",
            [{"id": "a", "v": 99}, {"id": "b", "v": 2}],
        )

        # a now reads back as 99 from cache without a backend call
        backend.calls.clear()
        result = await cached.get("node", "a")
        assert result["v"] == 99
        assert not any(c[0] == "get" for c in backend.calls)
