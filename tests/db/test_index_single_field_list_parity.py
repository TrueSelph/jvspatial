"""Single-field list-form parity across backends.

``GraphContext.ensure_indexes`` passes a descending single-field index as
``[(field, -1)]`` so Postgres can build a descending B-tree. Every backend
retains canonical annotation-created names while preserving explicit adapter
index declarations. SQL nullable sort companions are direction-specific.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


# ---- SQLite ----------------------------------------------------------------


class TestSQLiteSingleFieldParity:
    @pytest.fixture
    async def sqlite_db(self) -> AsyncIterator[Any]:
        from jvspatial.db.sqlite import SQLiteDB

        with tempfile.TemporaryDirectory() as tmp:
            db = SQLiteDB(db_path=str(Path(tmp) / "parity.db"))
            yield db
            await db.close()

    async def _index_names(self, db: Any) -> List[str]:
        conn = await db._get_connection()
        cursor = await conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' "
            "AND name LIKE 'idx_node_%'"
        )
        return sorted(row[0] for row in await cursor.fetchall())

    async def test_list_form_reuses_string_form_index_name(
        self, sqlite_db: Any
    ) -> None:
        await sqlite_db.create_index("node", "context.created_at")
        from_string = await self._index_names(sqlite_db)

        await sqlite_db.create_index("node", [("context.created_at", -1)])
        after_list = await self._index_names(sqlite_db)

        base_name = "idx_node_context_created_at"
        assert base_name in from_string
        assert base_name in after_list
        assert len([name for name in after_list if "__sort_" not in name]) == 1
        # Nullable ordering needs separate ascending/descending companions.
        assert len(after_list) == len(from_string) + 1
        assert set(from_string).issubset(after_list)
        await sqlite_db.create_index("node", [("context.created_at", -1)])
        assert await self._index_names(sqlite_db) == after_list


# ---- MongoDB ---------------------------------------------------------------


class TestMongoSingleFieldParity:
    @pytest.fixture
    def mongo_pair(self) -> Tuple[Any, Any]:
        from jvspatial.db.mongodb import MongoDB

        with patch("jvspatial.db.mongodb.AsyncIOMotorClient"):
            db = MongoDB(uri="mongodb://localhost:27017/test", db_name="test_db")
            collection = AsyncMock()
            mock_db = MagicMock()
            mock_db.__getitem__.return_value = collection
            db._client = MagicMock()
            db._db = mock_db
            return db, collection

    async def test_explicit_list_form_preserves_declared_direction(
        self, mongo_pair: Tuple[Any, Any]
    ) -> None:
        db, collection = mongo_pair

        await db.create_index("node", "context.created_at")
        string_name = collection.create_index.call_args.kwargs["name"]

        # Fresh index-name cache so the second call is not short-circuited.
        db._created_indexes.clear()
        await db.create_index("node", [("context.created_at", -1)])
        list_name = collection.create_index.call_args.kwargs["name"]

        assert string_name == "context.created_at_1"
        assert list_name == "context.created_at_-1"
        assert collection.create_index.call_args.args[0] == [("context.created_at", -1)]

    async def test_explicit_named_single_field_preserves_direction(self, mongo_pair):
        db, collection = mongo_pair
        await db.create_index(
            "node", [("context.created_at", -1)], name="custom_recent"
        )
        assert collection.create_index.call_args.args[0] == [("context.created_at", -1)]
        assert collection.create_index.call_args.kwargs["name"] == "custom_recent"

    @pytest.mark.parametrize("wrapped", [False, True])
    async def test_annotation_reuses_canonical_single_field_index(self, wrapped):
        from jvspatial import GraphContext, Node
        from jvspatial.core.annotations import attribute
        from jvspatial.db import create_database

        class MongoDirectionNode(Node):
            created_at: str = attribute(default="", indexed=True, index_direction=-1)

        with patch("jvspatial.db.mongodb.AsyncIOMotorClient"):
            db = create_database(
                "mongodb",
                uri="mongodb://localhost:27017/test",
                db_name="test_db",
                cache_get_size=2 if wrapped else 0,
                observe=wrapped,
            )
            inner = db
            while hasattr(inner, "inner"):
                inner = inner.inner
            collection = AsyncMock()
            mock_db = MagicMock()
            mock_db.__getitem__.return_value = collection
            inner._client = MagicMock()
            inner._db = mock_db
            await GraphContext(db).ensure_indexes(MongoDirectionNode)
            calls = [
                call
                for call in collection.create_index.call_args_list
                if call.kwargs["name"] == "context.created_at_1"
            ]
            assert len(calls) == 1
            assert calls[0].args[0] == [("context.created_at", 1)]

    async def test_compound_index_naming_unchanged(
        self, mongo_pair: Tuple[Any, Any]
    ) -> None:
        db, collection = mongo_pair

        await db.create_index("node", [("context.a", 1), ("context.b", -1)])

        assert (
            collection.create_index.call_args.kwargs["name"]
            == "context.a_1_context.b_-1"
        )


# ---- DynamoDB --------------------------------------------------------------


class TestDynamoSingleFieldParity:
    @pytest.fixture
    def dynamo_db(self) -> Any:
        boto3 = pytest.importorskip("aioboto3")  # noqa: F841
        from jvspatial.db.dynamodb import DynamoDB

        db = DynamoDB(table_name="test", region_name="us-east-1")
        return db

    async def _capture_gsi(
        self, db: Any, spec: Any
    ) -> Tuple[str, List[Dict[str, Any]]]:
        captured: Dict[str, Any] = {}

        async def fake_update(
            client: Any,
            table_name: str,
            gsi_name: str,
            attribute_definitions: List[Dict[str, Any]],
            key_schema: List[Dict[str, Any]],
            unique: bool,
            wait_for_active: bool,
        ) -> None:
            captured["gsi_name"] = gsi_name
            captured["key_schema"] = key_schema

        with (
            patch.object(
                db, "_ensure_table_exists", AsyncMock(return_value="test_node")
            ),
            patch.object(db, "_get_client", AsyncMock(return_value=MagicMock())),
            patch.object(db, "_update_table_with_gsi", fake_update),
        ):
            await db.create_index("node", spec)
        return captured["gsi_name"], captured["key_schema"]

    async def test_list_form_matches_string_form(self, dynamo_db: Any) -> None:
        string_name, string_keys = await self._capture_gsi(
            dynamo_db, "context.created_at"
        )

        dynamo_db._indexed_fields.clear()
        dynamo_db._gsi_names.clear()
        list_name, list_keys = await self._capture_gsi(
            dynamo_db, [("context.created_at", -1)]
        )

        assert string_name == "gsi_idx_context_created_at"
        assert list_name == string_name
        assert list_keys == string_keys


# ---- Postgres --------------------------------------------------------------


class TestPostgresIndexOrdering:
    """``PostgresDB.create_index`` must match ``translate_sort``'s ordering.

    ``translate_sort`` emits ``NULLS LAST`` in BOTH directions (SPEC §4.1).
    Postgres' own default is NULLS LAST for ASC but NULLS FIRST for DESC, so
    a bare ``DESC`` index cannot serve ``ORDER BY ... DESC NULLS LAST`` — the
    planner falls back to a seq scan + sort.
    """

    @pytest.fixture
    def pg_db(self) -> Any:
        pytest.importorskip("asyncpg")
        from jvspatial.db.postgres import PostgresDB

        return PostgresDB(dsn="postgresql://nope/none")

    async def _captured_sql(self, db: Any, spec: Any) -> List[str]:
        statements: List[str] = []

        class FakeConn:
            def transaction(self) -> Any:
                return FakeAcquire()

            async def execute(self, sql: str, *args: Any) -> None:
                statements.append(sql)

            async def fetch(self, sql: str, *args: Any) -> List[Any]:
                return []

            async def fetchrow(self, sql: str, *args: Any) -> None:
                return None

            async def fetchval(self, sql: str, *args: Any) -> None:
                return None

        class FakeAcquire:
            async def __aenter__(self) -> FakeConn:
                return FakeConn()

            async def __aexit__(self, *exc: Any) -> None:
                return None

        class FakePool:
            def acquire(self) -> FakeAcquire:
                return FakeAcquire()

        with (
            patch.object(db, "_bootstrap_collection", AsyncMock(return_value=None)),
            patch.object(db, "_ensure_pool", AsyncMock(return_value=FakePool())),
        ):
            await db.create_index("node", spec)
        return statements

    async def test_ascending_index_orders_ascending(self, pg_db: Any) -> None:
        """ASC needs no explicit NULLS clause: it is Postgres' own default."""
        sql = " ".join(await self._captured_sql(pg_db, "context.created_at"))

        assert "ASC" in sql
        assert "DESC" not in sql
        assert "node_context_created_at_idx" in sql

    async def test_descending_index_is_desc_nulls_last(self, pg_db: Any) -> None:
        sql = " ".join(await self._captured_sql(pg_db, [("context.created_at", -1)]))

        assert "DESC NULLS LAST" in sql

    async def test_descending_index_name_matches_ascending(self, pg_db: Any) -> None:
        asc = " ".join(await self._captured_sql(pg_db, "context.created_at"))
        desc = " ".join(await self._captured_sql(pg_db, [("context.created_at", -1)]))

        assert "node_context_created_at_idx" in asc
        assert "node_context_created_at_idx" in desc
