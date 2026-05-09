"""Tests for the new honest transaction semantics.

JsonDBTransaction is now strict by default (every operation raises
NotImplementedError) and offers an opt-in best_effort mode that buffers
writes/deletes in memory and applies them at commit time.
"""

import tempfile
from typing import Iterator

import pytest

from jvspatial.db.jsondb import JsonDB
from jvspatial.db.transaction import JsonDBTransaction


@pytest.fixture
def jsondb() -> Iterator[JsonDB]:
    with tempfile.TemporaryDirectory() as tmp:
        yield JsonDB(base_path=tmp)


class TestStrictMode:
    @pytest.mark.asyncio
    async def test_save_raises_in_strict_mode(self, jsondb: JsonDB) -> None:
        txn = JsonDBTransaction(jsondb)
        with pytest.raises(NotImplementedError):
            await txn.save("node", {"id": "x", "val": 1})

    @pytest.mark.asyncio
    async def test_get_raises_in_strict_mode(self, jsondb: JsonDB) -> None:
        txn = JsonDBTransaction(jsondb)
        with pytest.raises(NotImplementedError):
            await txn.get("node", "x")

    @pytest.mark.asyncio
    async def test_delete_raises_in_strict_mode(self, jsondb: JsonDB) -> None:
        txn = JsonDBTransaction(jsondb)
        with pytest.raises(NotImplementedError):
            await txn.delete("node", "x")

    @pytest.mark.asyncio
    async def test_find_raises_in_strict_mode(self, jsondb: JsonDB) -> None:
        txn = JsonDBTransaction(jsondb)
        with pytest.raises(NotImplementedError):
            await txn.find("node", {})

    @pytest.mark.asyncio
    async def test_strict_commit_succeeds(self, jsondb: JsonDB) -> None:
        """In strict mode, commit/rollback must still finalize cleanly --
        the only way to use a strict transaction is to detect the
        capability and avoid doing IO; we don't want commit() itself to
        raise."""
        txn = JsonDBTransaction(jsondb)
        await txn.commit()
        assert txn.is_committed


class TestBestEffortMode:
    @pytest.mark.asyncio
    async def test_save_buffers_until_commit(self, jsondb: JsonDB) -> None:
        txn = JsonDBTransaction(jsondb, best_effort=True)
        await txn.save("node", {"id": "x", "val": 1})
        # Not yet visible to the underlying database.
        assert await jsondb.get("node", "x") is None

        await txn.commit()

        persisted = await jsondb.get("node", "x")
        assert persisted is not None
        assert persisted["val"] == 1

    @pytest.mark.asyncio
    async def test_read_your_writes(self, jsondb: JsonDB) -> None:
        txn = JsonDBTransaction(jsondb, best_effort=True)
        await txn.save("node", {"id": "x", "val": 7})
        observed = await txn.get("node", "x")
        assert observed is not None
        assert observed["val"] == 7
        # And the buffered copy is independent of the caller's reference.
        observed["val"] = 9999
        observed_again = await txn.get("node", "x")
        assert observed_again["val"] == 7

    @pytest.mark.asyncio
    async def test_delete_buffered(self, jsondb: JsonDB) -> None:
        await jsondb.save("node", {"id": "y", "val": 0})
        txn = JsonDBTransaction(jsondb, best_effort=True)
        await txn.delete("node", "y")
        # Underlying still has the record before commit.
        assert await jsondb.get("node", "y") is not None
        # Within the transaction, it's gone.
        assert await txn.get("node", "y") is None
        await txn.commit()
        assert await jsondb.get("node", "y") is None

    @pytest.mark.asyncio
    async def test_rollback_discards_buffer(self, jsondb: JsonDB) -> None:
        txn = JsonDBTransaction(jsondb, best_effort=True)
        await txn.save("node", {"id": "z", "val": 1})
        await txn.rollback()
        assert await jsondb.get("node", "z") is None
        assert txn.is_rolled_back

    @pytest.mark.asyncio
    async def test_find_overlay_includes_buffered_writes(self, jsondb: JsonDB) -> None:
        await jsondb.save("node", {"id": "a", "name": "alpha"})
        await jsondb.save("node", {"id": "b", "name": "bravo"})

        txn = JsonDBTransaction(jsondb, best_effort=True)
        await txn.save("node", {"id": "c", "name": "charlie"})
        await txn.delete("node", "a")

        results = await txn.find("node", {})
        names = sorted(r["name"] for r in results)
        assert names == ["bravo", "charlie"]

    @pytest.mark.asyncio
    async def test_save_requires_id(self, jsondb: JsonDB) -> None:
        txn = JsonDBTransaction(jsondb, best_effort=True)
        with pytest.raises(ValueError):
            await txn.save("node", {"val": 1})


class TestCapabilityFlag:
    def test_jsondb_does_not_advertise_transactions(self) -> None:
        from jvspatial.db.jsondb import JsonDB

        assert JsonDB.supports_transactions is False

    def test_mongodb_advertises_transactions(self) -> None:
        from jvspatial.db.mongodb import MongoDB

        assert MongoDB.supports_transactions is True
