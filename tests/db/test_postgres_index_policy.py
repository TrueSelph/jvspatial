"""Managed index creation preserves constraints without growing performance DDL."""

import os
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

asyncpg = pytest.importorskip("asyncpg")

from jvspatial.db.postgres import PostgresDB


def test_policy_defaults_and_explicit_override(monkeypatch):
    monkeypatch.delenv("JVSPATIAL_POSTGRES_INDEX_CREATION", raising=False)
    assert PostgresDB().index_creation == "auto"
    monkeypatch.setenv("JVSPATIAL_POSTGRES_INDEX_CREATION", "constraints")
    assert PostgresDB().index_creation == "constraints"
    assert PostgresDB(index_creation="auto").index_creation == "auto"


@pytest.mark.parametrize("value", ["off", "false", "unknown", ""])
def test_invalid_explicit_policy_is_rejected(value):
    with pytest.raises(ValueError, match="index_creation"):
        PostgresDB(index_creation=value)


async def test_performance_declarations_do_not_acquire_connections():
    db = PostgresDB(index_creation="constraints")
    db._bootstrap_collection = AsyncMock()
    db._ensure_pool = AsyncMock()
    await db.create_index("object", "context.description")
    await db.create_index("object", "context.description", fulltext=True, unique=True)
    db._bootstrap_collection.assert_not_awaited()
    db._ensure_pool.assert_not_awaited()
    with pytest.raises(ValueError):
        await db.create_index("unsafe;collection", "context.description")


async def test_vector_storage_can_be_prepared_without_an_automatic_index():
    db = PostgresDB(index_creation="constraints")
    db._bootstrap_collection = AsyncMock()
    conn = AsyncMock()
    pool = MagicMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    db._ensure_pool = AsyncMock(return_value=pool)
    await db.enable_vector_column("node", "embedding", dim=3)
    sql = [call.args[0] for call in conn.execute.await_args_list]
    assert any("ADD COLUMN" in statement for statement in sql)
    assert not any("CREATE INDEX" in statement for statement in sql)
    assert db._vector_columns == {"node": {"embedding": 3}}


@pytest.fixture
async def managed_pg():
    dsn = os.getenv("JVSPATIAL_POSTGRES_TEST_DSN")
    if not dsn:
        pytest.skip("Set JVSPATIAL_POSTGRES_TEST_DSN to a disposable PostgreSQL")
    admin = await asyncpg.connect(dsn)
    schema = "test_index_policy_" + uuid.uuid4().hex
    await admin.execute(f"CREATE SCHEMA {schema}")
    db = PostgresDB(dsn=dsn, schema_name=schema, index_creation="constraints")
    try:
        yield db, admin, schema
    finally:
        await db.close()
        await admin.execute(f"DROP SCHEMA {schema} CASCADE")
        await admin.close()


async def _indexes(admin, schema):
    return await admin.fetch(
        "SELECT indexname, indexdef FROM pg_indexes WHERE schemaname=$1 "
        "ORDER BY indexname",
        schema,
    )


@pytest.mark.asyncio(loop_scope="module")
async def test_new_declarations_do_not_grow_indexes_but_uniqueness_survives(managed_pg):
    db, admin, schema = managed_pg
    await db.save("object", {"id": "a", "entity": "Item", "context": {"key": "same"}})
    baseline = await _indexes(admin, schema)
    assert len(baseline) == 3  # primary key and fixed entity/tenant baseline
    assert not any("USING gin" in row["indexdef"] for row in baseline)
    for i in range(25):
        await db.create_index("object", f"context.field_{i}", entity="Item")
    assert await _indexes(admin, schema) == baseline

    await db.create_index("object", "context.key", entity="Item", unique=True)
    constrained = await _indexes(admin, schema)
    assert len(constrained) == len(baseline) + 1
    assert not any("_sort_" in row["indexname"] for row in constrained)
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.save(
            "object", {"id": "b", "entity": "Item", "context": {"key": "same"}}
        )
    assert await db.get("object", "a") is not None
    assert await db.get("object", "b") is None


@pytest.mark.asyncio(loop_scope="module")
async def test_existing_indexes_remain_and_explicit_provisioning_still_works(
    managed_pg,
):
    db, admin, schema = managed_pg
    provisioner = PostgresDB(dsn=db.dsn, schema_name=schema, index_creation="auto")
    try:
        await provisioner.create_index(
            "object", "context.created_at", entity="Item", partial_by_entity=True
        )
    finally:
        await provisioner.close()
    before = await _indexes(admin, schema)
    assert any("WHERE" in row["indexdef"] for row in before)
    await db.create_index("object", "context.other", entity="Other")
    await db.save("object", {"id": "a", "entity": "Item", "context": {}})
    assert await _indexes(admin, schema) == before


@pytest.mark.asyncio(loop_scope="module")
async def test_failed_unique_provision_does_not_modify_existing_indexes(managed_pg):
    db, admin, schema = managed_pg
    for key in ("a", "b"):
        await db.save(
            "object", {"id": key, "entity": "Item", "context": {"key": "same"}}
        )
    before = await _indexes(admin, schema)
    with pytest.raises(asyncpg.UniqueViolationError):
        await db.create_index("object", "context.key", entity="Item", unique=True)
    assert await _indexes(admin, schema) == before


def test_managed_fingerprints_preserve_physical_semantics():
    from dataclasses import replace

    from jvspatial import IndexSpec

    spec = IndexSpec("a", "owner", "object", ("id ASC NULLS LAST",))
    assert (
        spec.fingerprint
        == replace(spec, logical_id="b", owner="other", keys=("id",)).fingerprint
    )
    assert spec.fingerprint != replace(spec, keys=("id DESC NULLS LAST",)).fingerprint
    assert spec.fingerprint != replace(spec, keys=('id COLLATE "C"',)).fingerprint
    assert len(spec.name.encode()) <= 63
    assert replace(spec, keys=("lower(id)",)).fingerprint != spec.fingerprint
    assert (
        replace(spec, predicate="entity='a b'").fingerprint
        != replace(spec, predicate="entity='ab'").fingerprint
    )


async def test_managed_helpers_never_provision_optional_storage():
    from jvspatial import ManagedSchemaError

    db = PostgresDB(index_creation="managed")
    db._bootstrap_collection = AsyncMock()
    db._ensure_pool = AsyncMock()
    await db.create_index("object", "context.anything")
    await db.create_binary_text_keyset_indexes(
        "node", field="context.title", scope_field="context.track_id", entity="Entry"
    )
    db._ensure_pool.assert_not_awaited()
    with pytest.raises(ManagedSchemaError):
        await db.enable_rls("node")
    db._bootstrap_collection.assert_not_awaited()
