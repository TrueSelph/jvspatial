"""End-to-end SQLite sort behavior — both the pushdown and the fallback.

``tests/db/test_find_sort_nulls_last.py`` only string-matches the SQL
fragments the translators emit. These cases run a real ``SQLiteDB`` so the
ordering contract in SPEC §4.1 is asserted against actual query results,
through both branches of ``SQLiteDB.find``:

* ``translate_sort`` succeeds  → ORDER BY + LIMIT pushed into SQL
* ``translate_sort`` returns None (unsafe field path) → full match set
  loaded and ordered by ``finalize_find_results``

Both must produce the same ordering.
"""

import pytest

import jvspatial.db.sqlite as sqlite_module
from jvspatial.db.sqlite import SQLiteDB

# A hyphen is outside ``_SAFE_SEGMENT_RE``, so translate_sort refuses the
# path and find() takes the in-memory branch.
PUSHED = "context.started_at"
FALLBACK = "context.started-at"


@pytest.fixture
async def db():
    database = SQLiteDB(db_path=":memory:")
    yield database
    await database.close()


async def _seed(database, field):
    """Three valued records plus two with no value, saved out of order."""
    await database.save("node", {"id": "mid", "context": {field: 2}})
    await database.save("node", {"id": "hole", "context": {}})
    await database.save("node", {"id": "newest", "context": {field: 3}})
    await database.save("node", {"id": "oldest", "context": {field: 1}})
    await database.save("node", {"id": "nulled", "context": {field: None}})


@pytest.mark.parametrize("path", [PUSHED, FALLBACK])
async def test_descending_orders_values_then_missing(db, path):
    await _seed(db, path.split(".", 1)[1])

    out = await db.find("node", {}, sort=[(path, -1)])

    assert [r["id"] for r in out[:3]] == ["newest", "mid", "oldest"]
    assert sorted(r["id"] for r in out[3:]) == ["hole", "nulled"]


@pytest.mark.parametrize("path", [PUSHED, FALLBACK])
async def test_ascending_orders_values_then_missing(db, path):
    await _seed(db, path.split(".", 1)[1])

    out = await db.find("node", {}, sort=[(path, 1)])

    assert [r["id"] for r in out[:3]] == ["oldest", "mid", "newest"]
    assert sorted(r["id"] for r in out[3:]) == ["hole", "nulled"]


@pytest.mark.parametrize("path", [PUSHED, FALLBACK])
async def test_limit_returns_the_true_top_n(db, path):
    """The motivating case — a "newest 2" fetch must not return holes."""
    await _seed(db, path.split(".", 1)[1])

    out = await db.find("node", {}, sort=[(path, -1)], limit=2)

    assert [r["id"] for r in out] == ["newest", "mid"]


async def test_pushdown_and_fallback_agree(db):
    """Same data under both branches produces the same order."""
    await db.save(
        "node",
        {"id": "a", "context": {"started_at": 1, "started-at": 1}},
    )
    await db.save(
        "node",
        {"id": "b", "context": {"started_at": 3, "started-at": 3}},
    )
    await db.save("node", {"id": "c", "context": {}})

    pushed = await db.find("node", {}, sort=[(PUSHED, -1)])
    fallback = await db.find("node", {}, sort=[(FALLBACK, -1)])

    assert [r["id"] for r in pushed] == [r["id"] for r in fallback]
    assert [r["id"] for r in pushed] == ["b", "a", "c"]


async def test_empty_sort_spec_pushes_limit_instead_of_loading_everything(
    db, monkeypatch
):
    """``sort=[]`` must not divert into the untranslatable-sort branch.

    It used to fail the ``sort is None`` guard, so an empty list loaded the
    whole collection and applied the LIMIT in memory. The row count is
    identical either way, so assert the branch: the pushdown path returns
    without consulting ``finalize_find_results`` at all.
    """
    for i in range(5):
        await db.save("node", {"id": str(i), "context": {}})

    calls = []
    real = sqlite_module.finalize_find_results

    def spy(records, **kwargs):
        calls.append(len(records))
        return real(records, **kwargs)

    monkeypatch.setattr(sqlite_module, "finalize_find_results", spy)

    out = await db.find("node", {}, sort=[], limit=2)

    assert len(out) == 2
    assert calls == []  # never fell back to the in-memory path
