"""Shared transaction locks admit peers while retaining exclusive ordering."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from tests.db.test_postgres_integration import pg_db as pg_db
from tests.db.test_postgres_transaction_reads import _transaction

pytestmark = pytest.mark.asyncio


@pytest.mark.parametrize("shared", [False, True])
async def test_row_lock_uses_held_connection_without_a_write(shared):
    connection = AsyncMock()
    connection.fetchrow.return_value = {"data": {"id": "record", "entity": "Item"}}
    tx = _transaction(connection)
    assert await tx.lock_record("node", "record", shared=shared) == {
        "id": "record",
        "entity": "Item",
    }
    sql, record_id = connection.fetchrow.await_args.args
    assert record_id == "record"
    assert sql.endswith("FOR SHARE" if shared else "FOR UPDATE")
    connection.execute.assert_not_awaited()
    tx._db._ensure_pool.assert_not_called()
    connection.fetchrow.return_value = None
    assert await tx.lock_record("node", "missing", shared=shared) is None
    await tx.rollback()
    with pytest.raises(Exception, match="no longer active"):
        await tx.lock_record("node", "record", shared=shared)


@pytest.mark.parametrize("shared", [False, True])
async def test_advisory_lock_is_bound_and_transaction_scoped(shared):
    connection = AsyncMock()
    tx = _transaction(connection)
    await tx.advisory_lock("namespace'); SELECT 1;--", "key", shared=shared)
    sql, scope, key = connection.execute.await_args.args
    assert (
        "pg_advisory_xact_lock_shared" in sql
        if shared
        else "pg_advisory_xact_lock(" in sql
    )
    assert "SELECT 1" not in sql
    assert "test_schema" in scope and "namespace" in scope and key == "key"
    connection.fetchrow.assert_not_awaited()


async def test_advisory_scope_retains_the_opening_tenant():
    import json

    from jvspatial.db.postgres import PostgresDB

    database = PostgresDB(dsn="postgresql://unused/unused")
    connection = AsyncMock()
    async with database.tenant("first"):
        tx = _transaction(connection)
    async with database.tenant("second"):
        await tx.advisory_lock("namespace", "key", shared=True)
    assert json.loads(connection.execute.await_args.args[1]) == [
        "test_schema",
        "first",
        "namespace",
    ]


@pytest.mark.parametrize("mode", [None, 0, 1, "shared"])
async def test_lock_modes_are_literal_booleans(mode):
    connection = AsyncMock()
    tx = _transaction(connection)
    with pytest.raises(ValueError):
        await tx.lock_record("node", "record", shared=mode)
    with pytest.raises(ValueError):
        await tx.advisory_lock("scope", "key", shared=mode)
    connection.execute.assert_not_awaited()
    connection.fetchrow.assert_not_awaited()


async def test_unsupported_transactions_refuse_lock_guarantees():
    from jvspatial.db.transaction import MongoDBTransaction

    tx = MongoDBTransaction("test", object(), object())
    with pytest.raises(NotImplementedError):
        await tx.lock_record("node", "record", shared=True)
    with pytest.raises(NotImplementedError):
        await tx.advisory_lock("scope", "key", shared=True)


@pytest.mark.parametrize("kind", ["record", "advisory"])
async def test_shared_peers_block_exclusive_until_both_commit(pg_db, kind):
    await pg_db.save("node", {"id": "record", "entity": "Item"})
    first = await pg_db.begin_transaction()
    second = await pg_db.begin_transaction()
    writer = await pg_db.begin_transaction()

    async def lock(tx, shared):
        if kind == "record":
            return await tx.lock_record("node", "record", shared=shared)
        return await tx.advisory_lock("test", "record", shared=shared)

    pending = None
    try:
        await asyncio.wait_for(lock(first, True), 2)
        await asyncio.wait_for(lock(second, True), 2)
        pending = asyncio.create_task(lock(writer, False))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(pending), 0.1)
        await first.commit()
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(pending), 0.1)
        await second.commit()
        await asyncio.wait_for(pending, 2)
        await writer.commit()
        assert await pg_db.get("node", "record") == {"id": "record", "entity": "Item"}
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        for tx in (writer, second, first):
            await tx.rollback()


@pytest.mark.parametrize("kind", ["record", "advisory"])
async def test_canceled_lock_wait_rolls_back_and_does_not_leak(pg_db, kind):
    from jvspatial.db.transaction import transaction_context

    await pg_db.save("node", {"id": "record", "entity": "Item"})

    async def lock(tx, shared):
        if kind == "record":
            await tx.lock_record("node", "record", shared=shared)
        else:
            await tx.advisory_lock("test", "record", shared=shared)

    holder = await pg_db.begin_transaction()
    await lock(holder, False)
    waiting = asyncio.Event()
    handles = []

    async def canceled_peer():
        async with transaction_context(pg_db) as tx:
            handles.append(tx)
            waiting.set()
            await lock(tx, True)

    peer = asyncio.create_task(canceled_peer())
    try:
        await asyncio.wait_for(waiting.wait(), 2)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(asyncio.shield(peer), 0.1)
        peer.cancel()
        with pytest.raises(asyncio.CancelledError):
            await peer
        assert handles[0].is_rolled_back
        await holder.commit()
        async with transaction_context(pg_db) as fresh:
            await asyncio.wait_for(lock(fresh, False), 2)
    finally:
        if not peer.done():
            peer.cancel()
            await asyncio.gather(peer, return_exceptions=True)
        await holder.rollback()
