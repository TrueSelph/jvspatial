"""Postgres must not push LIMIT when the sort pushdown failed.

``translate_sort`` returns ``None`` for a field path it cannot safely
interpolate (anything outside ``[A-Za-z_][A-Za-z0-9_]*`` per segment). The
ordering then happens in memory — so pushing the LIMIT would hand the
in-memory sort an arbitrary N rows and return "the top N of an arbitrary
subset" instead of the true top N.

``SQLiteDB.find`` and ``DynamoDB.find`` already withhold the LIMIT in this
situation; these cases pin Postgres to the same behavior. Stubbed pool — no
live database required. The DSN-gated end-to-end case lives in
``test_postgres_integration.py``.
"""

from __future__ import annotations

import contextlib
from typing import Any, Dict, List, Optional

import pytest

# PostgresDB imports asyncpg at module load.
pytest.importorskip("asyncpg")

from jvspatial.db.postgres import PostgresDB  # noqa: E402


class _FakeConn:
    """Records every SQL string it is handed and replays canned rows."""

    def __init__(self, rows: List[Dict[str, Any]]) -> None:
        self._rows = rows
        self.queries: List[str] = []
        self.params: List[Any] = []

    async def fetch(self, sql: str, *params: Any) -> List[Dict[str, Any]]:
        self.queries.append(sql)
        self.params.append(params)
        # Mimic a LIMIT the database would have applied itself.
        rows = self._rows
        if " LIMIT " in sql and params:
            rows = rows[: int(params[-1])]
        return [{"data": r} for r in rows]

    async def execute(self, *_args: Any, **_kwargs: Any) -> None:
        return None


def _stub_db(rows: List[Dict[str, Any]]) -> tuple[PostgresDB, _FakeConn]:
    db = PostgresDB(dsn="postgresql://stub/stub")
    conn = _FakeConn(rows)

    class _FakePool:
        @contextlib.asynccontextmanager
        async def acquire(self):  # type: ignore[no-untyped-def]
            yield conn

    async def _ensure_pool() -> Any:
        return _FakePool()

    db._ensure_pool = _ensure_pool  # type: ignore[assignment]
    # Skip DDL; the fake pool has no real table behind it.
    db._collections_bootstrapped.add("interaction")
    return db, conn


def _rows() -> List[Dict[str, Any]]:
    """Deliberately stored in an order that is not the sorted order."""
    return [
        {"id": "old", "context": {"my-field": 1}},
        {"id": "newest", "context": {"my-field": 9}},
        {"id": "mid", "context": {"my-field": 5}},
    ]


@pytest.mark.asyncio
async def test_untranslatable_sort_withholds_limit_pushdown():
    db, conn = _stub_db(_rows())

    # "my-field" contains a hyphen -> _safe_field_path rejects it ->
    # translate_sort returns None.
    out = await db.find("interaction", {}, sort=[("context.my-field", -1)], limit=2)

    assert "LIMIT" not in conn.queries[-1]
    assert "ORDER BY" not in conn.queries[-1]
    # The true top 2, not the first 2 rows the table happened to yield.
    assert [r["id"] for r in out] == ["newest", "mid"]


@pytest.mark.asyncio
async def test_translatable_sort_still_pushes_order_by_and_limit():
    db, conn = _stub_db(_rows())

    await db.find("interaction", {}, sort=[("context.started_at", -1)], limit=2)

    assert "ORDER BY" in conn.queries[-1]
    assert "LIMIT" in conn.queries[-1]


@pytest.mark.asyncio
async def test_no_sort_still_pushes_limit():
    """Without a sort there is no ordering to preserve — keep the pushdown."""
    db, conn = _stub_db(_rows())

    out = await db.find("interaction", {}, limit=2)

    assert "LIMIT" in conn.queries[-1]
    assert len(out) == 2


@pytest.mark.asyncio
async def test_untranslatable_sort_without_limit_is_unaffected():
    db, conn = _stub_db(_rows())

    out = await db.find("interaction", {}, sort=[("context.my-field", 1)])

    assert "LIMIT" not in conn.queries[-1]
    assert [r["id"] for r in out] == ["old", "mid", "newest"]


@pytest.mark.asyncio
async def test_untranslatable_sort_places_missing_values_last_under_limit():
    """The nulls-last contract survives the in-memory limit path."""
    rows = [
        {"id": "hole"},
        {"id": "newest", "context": {"my-field": 9}},
        {"id": "mid", "context": {"my-field": 5}},
    ]
    db, _conn = _stub_db(rows)

    out = await db.find("interaction", {}, sort=[("context.my-field", -1)], limit=2)

    assert [r["id"] for r in out] == ["newest", "mid"]


class _FakeTxConn(_FakeConn):
    async def fetchrow(self, *_args: Any, **_kwargs: Any) -> Optional[Any]:
        return None


@pytest.mark.asyncio
async def test_transaction_find_withholds_limit_pushdown_too():
    """``PostgresTransaction.find`` duplicates the query builder verbatim."""
    from jvspatial.db.postgres import PostgresTransaction

    db, _ = _stub_db(_rows())
    conn = _FakeTxConn(_rows())
    tx = PostgresTransaction(db, conn, transaction=None)

    out = await tx.find("interaction", {}, sort=[("context.my-field", -1)], limit=2)

    assert "LIMIT" not in conn.queries[-1]
    assert [r["id"] for r in out] == ["newest", "mid"]
