"""Transaction query methods must retain Postgres semantics and one connection."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("asyncpg")

from jvspatial.db.database import DatabaseError
from jvspatial.db.postgres import PostgresTransaction


def _transaction(connection: Any) -> PostgresTransaction:
    db = MagicMock()
    db.schema_name = "test_schema"
    db._bootstrap_collection = AsyncMock()
    db._record_from_row = lambda row: row["data"]
    db._collections_bootstrapped = set()
    db._collection_bootstrap_locks = {}
    db._pool = None
    db._find_ids_with_connection = AsyncMock(return_value=["n.entry.1"])
    db._count_with_connection = AsyncMock(return_value=1)
    db._find_many_with_connection = AsyncMock(
        return_value={"n.entry.1": {"id": "n.entry.1"}}
    )
    transaction = MagicMock()
    transaction.commit = AsyncMock()
    transaction.rollback = AsyncMock()
    return PostgresTransaction(db, connection, transaction=transaction)


@pytest.mark.asyncio
async def test_read_methods_use_transaction_connection_and_share_query_contract():
    class Connection:
        statements = []

        async def fetch(self, sql, *params):
            self.statements.append((sql, params))
            if sql.startswith("SELECT id FROM"):
                return [{"id": "n.entry.1"}]
            return [{"id": "n.entry.1", "data": {"id": "n.entry.1"}}]

        async def fetchrow(self, sql, *params):
            self.statements.append((sql, params))
            if "COUNT(*)" in sql:
                return {"n": 1}
            return {"data": {"id": "n.entry.1"}}

    conn = Connection()
    tx = _transaction(conn)

    assert await tx.find_one("node", {"id": "n.entry.1"}) == {"id": "n.entry.1"}
    assert await tx.find_ids("node", {}, limit=1, offset=0) == ["n.entry.1"]
    assert await tx.count("node", {"entity": "Entry"}) == 1
    assert await tx.find_many("node", ["n.entry.1", "n.entry.1"]) == {
        "n.entry.1": {"id": "n.entry.1"}
    }
    assert len(conn.statements) == 1
    assert "test_schema." in conn.statements[0][0]
    assert tx._db._bootstrap_collection.await_count == 4
    assert all(
        call.kwargs["connection"] is conn
        for call in tx._db._bootstrap_collection.await_args_list
    )
    assert tx._db._find_ids_with_connection.await_args.kwargs["limit"] == 1
    assert tx._db._count_with_connection.await_args.args[0] is conn
    assert tx._db._find_many_with_connection.await_args.args[0] is conn


@pytest.mark.asyncio
async def test_transaction_serializes_fanout_and_refuses_reads_after_close():
    class Connection:
        active = 0
        maximum = 0

        async def fetchrow(self, *_args, **_kwargs):
            self.active += 1
            self.maximum = max(self.maximum, self.active)
            try:
                await asyncio.sleep(0)
                return {"data": {"id": "same"}}
            finally:
                self.active -= 1

    connection = Connection()
    tx = _transaction(connection)
    results = await asyncio.gather(*(tx.get("object", "same") for _ in range(12)))
    assert results == [{"id": "same"}] * 12
    assert connection.maximum == 1

    await tx.rollback()
    with pytest.raises(DatabaseError, match="no longer active"):
        await tx.get("object", "same")
