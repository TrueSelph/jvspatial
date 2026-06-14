"""Tests for the walker TrailStore + Walker.restore cold-start path.

Covers:

* InMemoryTrailStore basic semantics (append / load / clear / since).
* DBTrailStore round-trip via JsonDB (a portable backend that needs no
  external service).
* Walker.restore() rehydrates the trail and the in-process counter so
  subsequent steps continue past the persisted history.
"""

from __future__ import annotations

import tempfile
from typing import Iterator

import pytest

from jvspatial.core.entities.walker import Walker
from jvspatial.core.entities.walker_components.trail_store import (
    DBTrailStore,
    InMemoryTrailStore,
)
from jvspatial.db.jsondb import JsonDB

pytestmark = pytest.mark.asyncio


# ---- InMemoryTrailStore ----------------------------------------------------


class TestInMemoryTrailStore:
    async def test_append_then_load(self) -> None:
        store = InMemoryTrailStore()
        await store.append("w.1", {"node": "n.A"})
        await store.append("w.1", {"node": "n.B"})
        loaded = await store.load("w.1")
        assert loaded == [{"node": "n.A"}, {"node": "n.B"}]

    async def test_load_with_since(self) -> None:
        store = InMemoryTrailStore()
        for i in range(5):
            await store.append("w.1", {"node": f"n.{i}"})
        loaded = await store.load("w.1", since=2)
        assert [s["node"] for s in loaded] == ["n.2", "n.3", "n.4"]

    async def test_load_missing_walker_returns_empty(self) -> None:
        store = InMemoryTrailStore()
        assert await store.load("w.nope") == []

    async def test_clear_removes_walker(self) -> None:
        store = InMemoryTrailStore()
        await store.append("w.1", {"node": "n.A"})
        await store.clear("w.1")
        assert await store.load("w.1") == []

    async def test_max_length_bound(self) -> None:
        store = InMemoryTrailStore(max_length=3)
        for i in range(5):
            await store.append("w.1", {"node": f"n.{i}"})
        # Older steps dropped — only the last 3 remain.
        loaded = await store.load("w.1")
        assert [s["node"] for s in loaded] == ["n.2", "n.3", "n.4"]

    async def test_multiple_walkers_isolated(self) -> None:
        store = InMemoryTrailStore()
        await store.append("a", {"node": "n.a1"})
        await store.append("b", {"node": "n.b1"})
        a = await store.load("a")
        b = await store.load("b")
        assert [s["node"] for s in a] == ["n.a1"]
        assert [s["node"] for s in b] == ["n.b1"]


# ---- DBTrailStore (JsonDB) -------------------------------------------------


@pytest.fixture
def jsondb_fixture() -> Iterator[JsonDB]:
    with tempfile.TemporaryDirectory() as tmp:
        yield JsonDB(base_path=tmp)


class TestDBTrailStoreJsonDB:
    async def test_round_trip(self, jsondb_fixture: JsonDB) -> None:
        store = DBTrailStore(jsondb_fixture)
        await store.append("w.1", {"node": "n.A", "edge": "e.1"})
        await store.append("w.1", {"node": "n.B", "edge": "e.2"})
        loaded = await store.load("w.1")
        # Order preserved by sequence.
        assert [s["node"] for s in loaded] == ["n.A", "n.B"]

    async def test_clear_drops_walker_records(self, jsondb_fixture: JsonDB) -> None:
        store = DBTrailStore(jsondb_fixture)
        await store.append("w.x", {"node": "n.A"})
        await store.append("w.y", {"node": "n.Y"})
        await store.clear("w.x")
        assert await store.load("w.x") == []
        # Other walker untouched.
        assert [s["node"] for s in await store.load("w.y")] == ["n.Y"]

    async def test_since_filter_via_seq(self, jsondb_fixture: JsonDB) -> None:
        store = DBTrailStore(jsondb_fixture)
        for i in range(5):
            await store.append("w.1", {"node": f"n.{i}"})
        loaded = await store.load("w.1", since=3)
        assert [s["node"] for s in loaded] == ["n.3", "n.4"]


# ---- Walker.restore --------------------------------------------------------


class TestWalkerRestore:
    async def test_inmemory_resume_replays_trail(self) -> None:
        store = InMemoryTrailStore()
        w = Walker(trail_store=store)
        await w._trail_tracker.arecord_step("n.A", edge_id="e.1")
        await w._trail_tracker.arecord_step("n.B", edge_id="e.2")

        # Fresh process — restore from store.
        restored = await Walker.restore(w.id, store=store)
        assert restored.id == w.id
        assert restored._trail_tracker.get_length() == 2
        assert restored.get_trail() == ["n.A", "n.B"]

    async def test_restore_resumes_persistence(self) -> None:
        store = InMemoryTrailStore()
        w = Walker(trail_store=store)
        await w._trail_tracker.arecord_step("n.A")
        await w._trail_tracker.arecord_step("n.B")

        restored = await Walker.restore(w.id, store=store)
        # Steps recorded post-restore must also persist.
        await restored._trail_tracker.arecord_step("n.C")

        persisted = await store.load(w.id)
        assert [s["node"] for s in persisted] == ["n.A", "n.B", "n.C"]

    async def test_restore_via_dbtrailstore(self, jsondb_fixture: JsonDB) -> None:
        store = DBTrailStore(jsondb_fixture)
        w = Walker(trail_store=store)
        await w._trail_tracker.arecord_step("n.A")
        await w._trail_tracker.arecord_step("n.B")

        # Simulate cold start: discard the old store-counter cache by
        # constructing a fresh DBTrailStore wrapping the same DB.
        fresh_store = DBTrailStore(jsondb_fixture)
        restored = await Walker.restore(w.id, store=fresh_store)
        assert restored.id == w.id
        assert restored.get_trail() == ["n.A", "n.B"]

        # New step lands at seq=2 (counter rehydrated from load()).
        await restored._trail_tracker.arecord_step("n.C")
        persisted = await fresh_store.load(w.id)
        assert [s["node"] for s in persisted] == ["n.A", "n.B", "n.C"]

    async def test_walker_without_store_unaffected(self) -> None:
        # Backward-compat: legacy walkers still work.
        w = Walker()
        assert w._trail_tracker._store is None
        # ``record_step`` is a sync method and must not raise without a
        # store + walker_id.
        w._trail_tracker.record_step("n.A")
        assert w._trail_tracker.get_length() == 1
