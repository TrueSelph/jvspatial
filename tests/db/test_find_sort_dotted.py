"""Dotted-path sort keys for ``finalize_find_results``.

The SQLite/Postgres sort pushdowns and Mongo's native sort already resolve
dotted field paths. These cases pin the in-memory fallback to the same
behavior so a ``sort=[("context.started_at", -1)]`` spec does not silently
degrade to "every key is ``None``" on backends that sort in Python.
"""

from __future__ import annotations

import tempfile

import pytest

from jvspatial.db.database import finalize_find_results
from jvspatial.db.jsondb import JsonDB


def _rows():
    return [
        {"id": "a", "context": {"started_at": "2026-01-03T00:00:00+00:00"}},
        {"id": "b", "context": {"started_at": "2026-01-01T00:00:00+00:00"}},
        {"id": "c", "context": {"started_at": "2026-01-02T00:00:00+00:00"}},
    ]


def test_finalize_find_sorts_dotted_context_field_desc():
    out = finalize_find_results(_rows(), sort=[("context.started_at", -1)], limit=2)
    assert [r["id"] for r in out] == ["a", "c"]


def test_finalize_find_sorts_dotted_context_field_asc():
    out = finalize_find_results(_rows(), sort=[("context.started_at", 1)])
    assert [r["id"] for r in out] == ["b", "c", "a"]


def test_finalize_find_flat_field_unchanged():
    rows = [{"id": "2"}, {"id": "1"}, {"id": "3"}]
    out = finalize_find_results(rows, sort=[("id", 1)], limit=2)
    assert [r["id"] for r in out] == ["1", "2"]


def test_compound_sort_mixes_flat_and_dotted_keys():
    rows = [
        {"id": "a", "kind": "x", "context": {"n": 2}},
        {"id": "b", "kind": "x", "context": {"n": 1}},
        {"id": "c", "kind": "w", "context": {"n": 9}},
    ]
    out = finalize_find_results(rows, sort=[("kind", 1), ("context.n", -1)])
    assert [r["id"] for r in out] == ["c", "a", "b"]


@pytest.mark.asyncio
async def test_jsondb_find_honors_dotted_sort_with_limit():
    """End-to-end through the JSON backend, which sorts in Python."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = JsonDB(base_path=tmpdir)
        for row in _rows():
            await db.save("interaction", row)

        out = await db.find(
            "interaction", {}, sort=[("context.started_at", -1)], limit=2
        )

    assert [r["id"] for r in out] == ["a", "c"]
