"""Native count() behavior on JsonDB.

Empty queries should resolve via dirent counting (no JSON parsing).
Filtered queries should match through QueryEngine without materializing
a result list.
"""

import tempfile
from typing import Iterator

import pytest

from jvspatial.db.jsondb import JsonDB


@pytest.fixture
def jsondb() -> Iterator[JsonDB]:
    with tempfile.TemporaryDirectory() as tmp:
        yield JsonDB(base_path=tmp)


class TestEmptyQueryCount:
    async def test_empty_collection_count_is_zero(self, jsondb):
        assert await jsondb.count("node") == 0

    async def test_count_after_inserts(self, jsondb):
        for i in range(7):
            await jsondb.save("node", {"id": f"n{i}", "value": i})
        assert await jsondb.count("node") == 7

    async def test_count_ignores_jvtmp_files(self, jsondb):
        await jsondb.save("node", {"id": "n0", "value": 0})
        # Drop a stranded .jvtmp into the collection dir.
        coll = jsondb._get_collection_dir("node")
        stale = coll / "n0.json.99.aa.jvtmp"
        stale.write_bytes(b'{"id":"WRONG"}')
        assert await jsondb.count("node") == 1


class TestFilteredCount:
    async def test_simple_equality_count(self, jsondb):
        await jsondb.save("node", {"id": "1", "category": "a"})
        await jsondb.save("node", {"id": "2", "category": "b"})
        await jsondb.save("node", {"id": "3", "category": "a"})
        assert await jsondb.count("node", {"category": "a"}) == 2
        assert await jsondb.count("node", {"category": "c"}) == 0

    async def test_count_with_or(self, jsondb):
        await jsondb.save("node", {"id": "1", "name": "alice", "active": True})
        await jsondb.save("node", {"id": "2", "name": "bob", "active": False})
        await jsondb.save("node", {"id": "3", "name": "carol", "active": True})
        n = await jsondb.count("node", {"$or": [{"name": "alice"}, {"active": False}]})
        assert n == 2  # alice + bob


class TestCountAgreesWithFindLen:
    async def test_count_matches_find_len_for_random_queries(self, jsondb):
        for i in range(20):
            await jsondb.save(
                "node",
                {"id": f"n{i}", "category": "even" if i % 2 == 0 else "odd", "v": i},
            )
        for q in [
            {},
            {"category": "even"},
            {"v": 5},
            {"$or": [{"v": 1}, {"v": 2}, {"v": 3}]},
        ]:
            count = await jsondb.count("node", q)
            rows = await jsondb.find("node", q)
            assert count == len(rows), (q, count, len(rows))
