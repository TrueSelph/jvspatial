"""Missing sort values land last in both directions, on every backend path.

``finalize_find_results`` sorts descending with ``reverse=True``, which used to
flip the ``None`` flag along with the values and float rows missing the sort
field to the *front*. Both SQL translators emit ``NULLS LAST`` for descending,
so a ``sort`` + ``limit`` "newest N" fetch returned real rows on
SQLite/Postgres/Mongo and a window of holes on the in-memory path.
"""

from __future__ import annotations

import tempfile

import pytest

from jvspatial.db._postgres_translate import translate_sort as pg_translate_sort
from jvspatial.db._sqlite_translate import translate_sort as sqlite_translate_sort
from jvspatial.db.database import finalize_find_results
from jvspatial.db.jsondb import JsonDB


def _rows_with_holes():
    return [
        {"id": "a", "context": {"started_at": "2026-01-03T00:00:00+00:00"}},
        {"id": "missing"},
        {"id": "b", "context": {"started_at": "2026-01-01T00:00:00+00:00"}},
        {"id": "empty", "context": {}},
        {"id": "c", "context": {"started_at": "2026-01-02T00:00:00+00:00"}},
    ]


@pytest.mark.parametrize("direction", [1, -1])
def test_missing_flat_field_sorts_last_in_both_directions(direction):
    rows = [{"id": "a", "v": 1}, {"id": "none"}, {"id": "b", "v": 2}]
    out = finalize_find_results(rows, sort=[("v", direction)])
    assert out[-1]["id"] == "none"


@pytest.mark.parametrize("direction", [1, -1])
def test_missing_dotted_path_sorts_last_in_both_directions(direction):
    out = finalize_find_results(
        _rows_with_holes(), sort=[("context.started_at", direction)]
    )
    assert {r["id"] for r in out[-2:]} == {"missing", "empty"}


def test_newest_n_limit_window_holds_real_rows():
    """The motivating case: descending + limit must not return holes."""
    out = finalize_find_results(
        _rows_with_holes(), sort=[("context.started_at", -1)], limit=2
    )
    assert [r["id"] for r in out] == ["a", "c"]


def test_non_dict_segment_sorts_last_instead_of_raising():
    rows = [
        {"id": "scalar", "context": "not-a-dict"},
        {"id": "ok", "context": {"started_at": "2026-01-01T00:00:00+00:00"}},
    ]
    out = finalize_find_results(rows, sort=[("context.started_at", -1)])
    assert [r["id"] for r in out] == ["ok", "scalar"]


@pytest.mark.parametrize("direction", [1, -1])
def test_sql_translators_agree_on_nulls_last(direction):
    """Pin the contract the in-memory path is now matching."""
    sqlite_frag = sqlite_translate_sort([("v", direction)])
    pg_frag = pg_translate_sort([("v", direction)])

    # SQLite: leading ``IS NULL`` term sorts ASC, so 0 (non-NULL) precedes 1.
    assert sqlite_frag is not None and sqlite_frag.startswith(
        "(json_extract(data, '$.v') IS NULL),"
    )
    assert pg_frag is not None and pg_frag.endswith("NULLS LAST")


@pytest.mark.asyncio
async def test_jsondb_descending_limit_skips_rows_missing_the_field():
    with tempfile.TemporaryDirectory() as tmpdir:
        db = JsonDB(base_path=tmpdir)
        for row in _rows_with_holes():
            await db.save("interaction", row)

        out = await db.find(
            "interaction", {}, sort=[("context.started_at", -1)], limit=2
        )

    assert [r["id"] for r in out] == ["a", "c"]
