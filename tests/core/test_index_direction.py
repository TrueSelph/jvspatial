"""Index direction pass-through from ``attribute(index_direction=...)``.

``GraphContext.ensure_indexes`` historically dropped the ``direction`` key
from single-field index definitions, so every single-field index was built
ascending regardless of what the annotation declared. On Postgres that makes
a "newest N" sort (``ORDER BY ... DESC NULLS LAST``) unable to use the index.

These tests run against the JSON backend (fastest iteration, per AGENTS.md)
with a recording database so the exact ``create_index`` call shape is asserted.
"""

from __future__ import annotations

from typing import Any, ClassVar, Dict, List, Optional, Tuple, Union

import pytest

from jvspatial.core.annotations import attribute, compound_index
from jvspatial.core.context import GraphContext, _ensured_indexes
from jvspatial.core.entities import Node
from jvspatial.db.jsondb import JsonDB

pytestmark = pytest.mark.asyncio


class RecordingDB(JsonDB):
    """JsonDB that records every ``create_index`` call verbatim."""

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.index_calls: List[Tuple[str, Any, bool, Dict[str, Any]]] = []

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        **kwargs: Any,
    ) -> None:
        self.index_calls.append((collection, field_or_fields, unique, dict(kwargs)))


@pytest.fixture(autouse=True)
def _clear_ensured_indexes() -> Any:
    """``_ensured_indexes`` is module-global; reset around each test."""
    _ensured_indexes.clear()
    yield
    _ensured_indexes.clear()


class DescendingIndexNode(Node):
    __entity_name__: ClassVar[Optional[str]] = "TestDescendingIndexNode"

    created_at: str = attribute(default="", indexed=True, index_direction=-1)


class AscendingIndexNode(Node):
    __entity_name__: ClassVar[Optional[str]] = "TestAscendingIndexNode"

    name: str = attribute(default="", indexed=True)


class UniqueDescendingIndexNode(Node):
    __entity_name__: ClassVar[Optional[str]] = "TestUniqueDescIndexNode"

    seq: str = attribute(
        default="", indexed=True, index_unique=True, index_direction=-1
    )


@compound_index([("a", 1), ("b", -1)], name="idx_test_ab")
class CompoundIndexNode(Node):
    __entity_name__: ClassVar[Optional[str]] = "TestCompoundIndexNode"

    a: str = attribute(default="")
    b: str = attribute(default="")


def _index_call(db: RecordingDB, needle: str) -> Tuple[str, Any, bool, Dict[str, Any]]:
    matches = [c for c in db.index_calls if needle in str(c[1])]
    assert matches, f"no create_index call for {needle!r} in {db.index_calls!r}"
    return matches[0]


class TestGetIndexesCarriesDirection:
    """``get_indexes()`` already exposes direction — guard that it stays."""

    async def test_descending_field_reports_direction(self) -> None:
        defs = [
            d
            for d in DescendingIndexNode.get_indexes()
            if d.get("field") == "context.created_at"
        ]
        assert len(defs) == 1
        assert defs[0]["direction"] == -1
        assert defs[0]["unique"] is False

    async def test_ascending_field_reports_direction(self) -> None:
        defs = [
            d
            for d in AscendingIndexNode.get_indexes()
            if d.get("field") == "context.name"
        ]
        assert len(defs) == 1
        assert defs[0]["direction"] == 1


class TestEnsureIndexesPassesDirection:
    async def test_descending_single_field_passes_list_form(
        self, tmp_path: Any
    ) -> None:
        db = RecordingDB(base_path=str(tmp_path))
        ctx = GraphContext(database=db)

        await ctx.ensure_indexes(DescendingIndexNode)

        _collection, spec, unique, extra = _index_call(db, "context.created_at")
        assert spec == [("context.created_at", -1)]
        assert unique is False
        assert "direction" not in extra

    async def test_descending_unique_single_field_keeps_unique(
        self, tmp_path: Any
    ) -> None:
        db = RecordingDB(base_path=str(tmp_path))
        ctx = GraphContext(database=db)

        await ctx.ensure_indexes(UniqueDescendingIndexNode)

        _collection, spec, unique, _extra = _index_call(db, "context.seq")
        assert spec == [("context.seq", -1)]
        assert unique is True

    async def test_ascending_single_field_still_passes_bare_string(
        self, tmp_path: Any
    ) -> None:
        """Name-stability guard.

        Ascending is the default and covers every index in existing
        deployments. Keep the plain-string call so no backend re-derives a
        different index name for indexes that already exist on disk.
        """
        db = RecordingDB(base_path=str(tmp_path))
        ctx = GraphContext(database=db)

        await ctx.ensure_indexes(AscendingIndexNode)

        _collection, spec, _unique, _extra = _index_call(db, "context.name")
        assert spec == "context.name"

    async def test_compound_index_unchanged(self, tmp_path: Any) -> None:
        db = RecordingDB(base_path=str(tmp_path))
        ctx = GraphContext(database=db)

        await ctx.ensure_indexes(CompoundIndexNode)

        _collection, spec, _unique, extra = _index_call(db, "context.a")
        assert spec == [("context.a", 1), ("context.b", -1)]
        assert extra.get("name") == "idx_test_ab"
