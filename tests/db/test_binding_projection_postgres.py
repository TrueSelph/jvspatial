"""Verify the published binding projection against the native PostgreSQL oracle."""

import asyncio

import pytest

from jvspatial.db._binding_projection_postgres import BindingProjection, install, read
from jvspatial.db.graph_bindings import GraphBindingSummary, LiteralBindingFact
from tests.db.test_graph_binding_summary import seed
from tests.db.test_postgres_integration import pg_db as pg_db

pytestmark = pytest.mark.asyncio
SHAPE = BindingProjection(
    "context.parent_key",
    "Record",
    "Relation",
    "root",
    (
        LiteralBindingFact("context.parent_key", ("root",), "parent_key"),
        LiteralBindingFact("context.state", ("ready", "hold"), "state", required=False),
    ),
)


async def projected(db):
    return await read(db, SHAPE, max_records=100, max_edges=200)


async def verify(db, expected):
    actual = await db.summarize_graph_bindings(
        {"context.parent_key": "root"},
        record_entity=SHAPE.record_entity,
        edge_entity=SHAPE.edge_entity,
        parent_id=SHAPE.parent_id,
        facts=SHAPE.facts,
    )
    assert actual == await projected(db) == expected


async def test_projection_backfill_and_live_updates(pg_db):
    record = await seed(pg_db, context={"parent_key": "root"})
    await install(pg_db, SHAPE)
    await verify(pg_db, GraphBindingSummary(1, 1, 0, 0, True))

    record["context"]["state"] = None
    await pg_db.save("node", record)
    await verify(pg_db, GraphBindingSummary(1, 0, 1, 0, True))

    del record["context"]["state"]
    await pg_db.save("node", record)
    await pg_db.save(
        "edge",
        {"id": "extra", "entity": "Relation", "source": "other", "target": "record"},
    )
    await verify(pg_db, GraphBindingSummary(1, 0, 0, 0, True))
    assert await read(pg_db, SHAPE, max_records=100, max_edges=1) is None

    await pg_db.save(
        "edge",
        {"id": "extra", "entity": "Relation", "source": 42, "target": "record"},
    )
    await verify(pg_db, GraphBindingSummary(1, 0, 0, 1, True))

    await pg_db.delete("edge", "extra")
    record["context"]["parent_key"] = "other"
    await pg_db.save("node", record)
    await verify(pg_db, GraphBindingSummary(0, 0, 0, 0, True))


async def test_projection_gate_rejects_invalidation_and_rls(pg_db):
    await seed(pg_db)
    await install(pg_db, SHAPE)
    schema = pg_db.schema_name
    async with pg_db._acquire_conn() as conn:
        txn = conn.transaction()
        await txn.start()
        await conn.execute(f"TRUNCATE {schema}.edge")
        await txn.rollback()
    await verify(pg_db, GraphBindingSummary(1, 1, 0, 0, True))
    await pg_db.enable_rls("node")
    assert await projected(pg_db) is None
    async with pg_db.tenant("tenant"):
        assert await projected(pg_db) is None
    with pytest.raises(ValueError, match="unfiltered source"):
        await install(pg_db, SHAPE)


async def test_projection_requires_maintenance_triggers(pg_db):
    await seed(pg_db)
    await install(pg_db, SHAPE)
    async with pg_db._acquire_conn() as conn:
        await conn.execute(
            f"ALTER TABLE {pg_db.schema_name}.node "
            "DISABLE TRIGGER jvspatial_binding_maintain_v1"
        )
    assert await projected(pg_db) is None
    async with pg_db._acquire_conn() as conn:
        await conn.execute(
            f"ALTER TABLE {pg_db.schema_name}.node "
            "ENABLE ALWAYS TRIGGER jvspatial_binding_maintain_v1"
        )
    assert await projected(pg_db) is None


async def test_existing_summary_uses_only_matching_published_shape(pg_db, monkeypatch):
    from jvspatial.db import _graph_binding_postgres

    await seed(pg_db)
    await pg_db.install_graph_binding_projection(
        partition_path=SHAPE.partition_path,
        record_entity=SHAPE.record_entity,
        edge_entity=SHAPE.edge_entity,
        parent_id=SHAPE.parent_id,
        facts=SHAPE.facts,
    )
    native = _graph_binding_postgres.summarize
    fallback = []

    async def observe(*args, **kwargs):
        fallback.append(True)
        return await native(*args, **kwargs)

    monkeypatch.setattr(_graph_binding_postgres, "summarize", observe)
    options = {
        "record_entity": SHAPE.record_entity,
        "edge_entity": SHAPE.edge_entity,
        "parent_id": SHAPE.parent_id,
        "facts": SHAPE.facts,
    }
    query = {"$and": [{"entity": "Record"}, {"context.parent_key": "root"}]}
    assert await pg_db.summarize_graph_bindings(
        query, **options
    ) == GraphBindingSummary(1, 1, 0, 0, True)
    assert not fallback

    unsupported = {"context.parent_key": "root", "context.state": "ready"}
    await pg_db.summarize_graph_bindings(unsupported, **options)
    assert fallback == [True]

    async with pg_db._acquire_conn() as conn:
        async with conn.transaction(isolation="repeatable_read"):
            await conn.execute(
                f"UPDATE {pg_db.schema_name}.edge SET data=jsonb_set("
                "data,'{source}',to_jsonb('other'::text)) WHERE id='link'"
            )

    assert await pg_db.summarize_graph_bindings(
        query, **options
    ) == GraphBindingSummary(1, 0, 0, 0, True)
    assert fallback == [True, True]


async def test_projection_serializes_competing_edge_changes(pg_db):
    await seed(pg_db)
    await pg_db.delete("edge", "link")
    await install(pg_db, SHAPE)
    schema = pg_db.schema_name
    insert = (
        f"INSERT INTO {schema}.edge(id,entity,data) VALUES"
        "($1::text,'Relation',jsonb_build_object('id',$1::text,"
        "'entity','Relation','source',$2::text,'target','record'))"
    )
    async with pg_db._acquire_conn() as first, pg_db._acquire_conn() as second:
        write = None
        try:
            async with first.transaction():
                await first.execute(insert, "first", "root")
                write = asyncio.create_task(second.execute(insert, "second", "other"))
                for _ in range(100):
                    if await first.fetchval(
                        "SELECT wait_event='advisory' FROM pg_catalog.pg_stat_activity "
                        "WHERE pid=$1",
                        second.get_server_pid(),
                    ):
                        break
                    await asyncio.sleep(0.02)
                else:
                    pytest.fail("Second writer did not wait for the target")
                assert not write.done()
            await asyncio.wait_for(write, 5)
        finally:
            if write is not None and not write.done():
                write.cancel()
                await asyncio.gather(write, return_exceptions=True)
    await verify(pg_db, GraphBindingSummary(1, 0, 0, 0, True))


async def test_older_repeatable_read_cannot_skip_new_projection(pg_db):
    from asyncpg import SerializationError

    await seed(pg_db)
    async with pg_db._acquire_conn() as old:
        transaction = old.transaction(isolation="repeatable_read")
        await transaction.start()
        try:
            await old.fetchval("SELECT 1")
            await install(pg_db, SHAPE)
            with pytest.raises(SerializationError):
                await old.execute(
                    f"DELETE FROM {pg_db.schema_name}.edge WHERE id='link'"
                )
        finally:
            await transaction.rollback()
    await verify(pg_db, GraphBindingSummary(1, 1, 0, 0, True))


async def test_worker_attaches_without_rebuilding_and_applies_exclusions(
    pg_db, monkeypatch
):
    from jvspatial.db import _graph_binding_postgres
    from jvspatial.db.postgres import PostgresDB

    await seed(pg_db)
    worker = PostgresDB(dsn=pg_db.dsn, schema_name=pg_db.schema_name)
    options = {
        "record_entity": SHAPE.record_entity,
        "edge_entity": SHAPE.edge_entity,
        "parent_id": SHAPE.parent_id,
        "facts": SHAPE.facts,
    }
    try:
        assert not await worker.attach_graph_binding_projection(
            partition_path=SHAPE.partition_path, **options
        )
        await install(pg_db, SHAPE)
        assert await worker.attach_graph_binding_projection(
            partition_path=SHAPE.partition_path, **options
        )

        native = _graph_binding_postgres.summarize

        async def unexpected_native(*args, **kwargs):
            pytest.fail("Supported projected query used the native scan")

        monkeypatch.setattr(_graph_binding_postgres, "summarize", unexpected_native)
        query = {
            "$and": [
                {"context.parent_key": "root"},
                {"id": {"$nin": ["another", "record"]}},
            ]
        }
        assert await worker.summarize_graph_bindings(
            query, **options
        ) == GraphBindingSummary(0, 0, 0, 0, True)
        assert await pg_db.invalidate_graph_binding_projection()
        assert not await pg_db.invalidate_graph_binding_projection()
        monkeypatch.setattr(_graph_binding_postgres, "summarize", native)
        assert await worker.summarize_graph_bindings(
            {"context.parent_key": "root"}, **options
        ) == GraphBindingSummary(1, 1, 0, 0, True)
    finally:
        await worker.close()
