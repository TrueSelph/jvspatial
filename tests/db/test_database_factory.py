"""Test suite for database factory.

Tests the simplified database creation functionality and custom database registration.
"""

import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from jvspatial.db.database import Database
from jvspatial.db.factory import (
    create_database,
    create_default_database,
    list_database_types,
    register_database_type,
    unregister_database_type,
)
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.mongodb import MongoDB

try:
    from jvspatial.db.sqlite import SQLiteDB

    HAS_SQLITE = True
except ImportError:  # pragma: no cover - exercised when aiosqlite missing
    SQLiteDB = None  # type: ignore[misc]
    HAS_SQLITE = False


class TestDatabaseFactory:
    """Test database factory functions."""

    def test_create_database_json(self):
        """Test creating JSON database."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db = create_database("json", base_path=temp_dir)
            assert isinstance(db, JsonDB)
            assert db.base_path.resolve() == Path(temp_dir).resolve()

    def test_create_database_mongodb(self):
        """Test creating MongoDB database."""
        with patch("jvspatial.db.mongodb.AsyncIOMotorClient"):
            db = create_database("mongodb", uri="mongodb://localhost:27017/test")
            assert isinstance(db, MongoDB)

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite is required for SQLite tests")
    async def test_create_database_sqlite(self):
        """Test creating SQLite database."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "test.db"
            db = create_database("sqlite", db_path=db_path)
            try:
                assert isinstance(db, SQLiteDB)
                # Compare resolved paths for consistency (handles Path objects and strings)
                assert db.db_path.resolve() == db_path.resolve()
            finally:
                if hasattr(db, "close"):
                    await db.close()

    def test_create_database_invalid_type(self):
        """Test error handling for invalid database type."""
        with pytest.raises(ValueError) as exc_info:
            create_database("invalid_type")

        assert "Unsupported database type" in str(exc_info.value)
        assert "invalid_type" in str(exc_info.value)

    def test_create_database_default_json(self):
        """Test default database creation defaults to JSON."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"JVSPATIAL_DB_TYPE": "json"}):
                db = create_default_database()
                assert isinstance(db, JsonDB)

    def test_create_database_default_mongodb(self):
        """Test default database creation with MongoDB."""
        from jvspatial.db.manager import DatabaseManager

        # Save current instance
        original_instance = DatabaseManager._instance

        try:
            # Reset singleton to force re-initialization
            DatabaseManager._instance = None

            with patch("jvspatial.db.mongodb.AsyncIOMotorClient"):
                with patch.dict(os.environ, {"JVSPATIAL_DB_TYPE": "mongodb"}):
                    db = create_default_database()
                    assert isinstance(db, MongoDB)
        finally:
            # Restore original instance
            DatabaseManager._instance = original_instance

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite is required for SQLite tests")
    async def test_create_database_default_sqlite(self):
        """Test default database creation with SQLite."""
        from jvspatial.db.manager import DatabaseManager

        original_instance = DatabaseManager._instance
        db: Optional[SQLiteDB] = None

        try:
            DatabaseManager._instance = None

            with tempfile.TemporaryDirectory() as temp_dir:
                db_path = str(Path(temp_dir) / "prime.db")
                with patch.dict(
                    os.environ,
                    {
                        "JVSPATIAL_DB_TYPE": "sqlite",
                        "JVSPATIAL_SQLITE_PATH": db_path,
                    },
                    clear=False,
                ):
                    database = create_default_database()
                    assert isinstance(database, SQLiteDB)
                    db = database
                    # Compare resolved paths for consistency
                    assert db.db_path.resolve() == Path(db_path).resolve()
        finally:
            if db is not None and hasattr(db, "close"):
                await db.close()
            DatabaseManager._instance = original_instance

    def test_create_database_json_with_config(self):
        """Test creating JSON database with configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {"base_path": temp_dir, "create_dirs": True, "pretty_print": True}
            db = create_database("json", **config)
            assert isinstance(db, JsonDB)
            assert db.base_path.resolve() == Path(temp_dir).resolve()

    def test_create_database_mongodb_with_config(self):
        """Test creating MongoDB database with configuration."""
        with patch("jvspatial.db.mongodb.AsyncIOMotorClient"):
            config = {"uri": "mongodb://localhost:27017/test", "db_name": "test_db"}
            db = create_database("mongodb", **config)
            assert isinstance(db, MongoDB)

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite is required for SQLite tests")
    async def test_create_database_sqlite_with_config(self):
        """Test creating SQLite database with configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "configured.db"
            db = create_database(
                "sqlite",
                db_path=db_path,
                timeout=1.5,
                journal_mode="DELETE",
                synchronous="OFF",
            )
            try:
                assert isinstance(db, SQLiteDB)
                # Compare resolved paths for consistency
                assert db.db_path.resolve() == db_path.resolve()
                assert db.timeout == 1.5
                assert db.journal_mode == "DELETE"
                assert db.synchronous == "OFF"
            finally:
                if hasattr(db, "close"):
                    await db.close()

    @pytest.mark.asyncio
    async def test_database_integration(self):
        """Test database integration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db = create_database("json", base_path=temp_dir)

            # Test basic operations
            data = {"id": "test-id", "name": "test", "value": 123}
            await db.save("test_collection", data)
            result = await db.get("test_collection", "test-id")
            assert result["name"] == "test"
            assert result["value"] == 123

            # Test find
            results = await db.find("test_collection", {"name": "test"})
            assert len(results) == 1
            assert results[0]["name"] == "test"

            # Test delete
            await db.delete("test_collection", "test-id")
            result = await db.get("test_collection", "test-id")
            assert result is None

    @pytest.mark.asyncio
    @pytest.mark.skipif(not HAS_SQLITE, reason="aiosqlite is required for SQLite tests")
    async def test_sqlite_database_integration(self):
        """Test SQLite database CRUD integration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "integration.db"
            db = create_database("sqlite", db_path=db_path)

            try:
                data = {"id": "item-1", "name": "Widget", "quantity": 10}
                await db.save("inventory", data)

                retrieved = await db.get("inventory", "item-1")
                assert retrieved is not None
                assert retrieved["name"] == "Widget"

                matches = await db.find("inventory", {"name": "Widget"})
                assert len(matches) == 1
                assert matches[0]["quantity"] == 10

                # Ensure count helper works (calls find internally)
                count = await db.count("inventory", {"name": "Widget"})
                assert count == 1

                await db.delete("inventory", "item-1")
                assert await db.get("inventory", "item-1") is None
            finally:
                if hasattr(db, "close"):
                    await db.close()


class TestCustomDatabaseRegistration:
    """Test custom database registration functionality."""

    class CustomTestDatabase(Database):
        """Test custom database implementation."""

        __test__ = False  # Prevent pytest from collecting as test class

        def __init__(self, test_param: str = "default", **kwargs: Any):
            """Initialize test database."""
            self.test_param = test_param
            self._data: Dict[str, Dict[str, Dict[str, Any]]] = {}

        async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
            """Save a record."""
            if "id" not in data:
                raise ValueError("Record must have an 'id' field")
            if collection not in self._data:
                self._data[collection] = {}
            self._data[collection][data["id"]] = data.copy()
            return data

        async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
            """Get a record."""
            if collection not in self._data:
                return None
            return self._data[collection].get(id)

        async def delete(self, collection: str, id: str) -> None:
            """Delete a record."""
            if collection in self._data:
                self._data[collection].pop(id, None)

        async def find(
            self, collection: str, query: Dict[str, Any]
        ) -> List[Dict[str, Any]]:
            """Find records."""
            if collection not in self._data:
                return []
            if not query:
                return list(self._data[collection].values())
            results = []
            for record in self._data[collection].values():
                if all(record.get(k) == v for k, v in query.items()):
                    results.append(record)
            return results

    def test_register_database_type(self):
        """Test registering a custom database type."""

        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        # Cleanup in case of previous test failure
        try:
            unregister_database_type("test_custom")
        except ValueError:
            pass

        # Register custom database
        register_database_type("test_custom", create_test_db)

        # Verify it's registered
        types = list_database_types()
        assert "test_custom" in types
        assert "Custom database" in types["test_custom"]

        # Cleanup
        unregister_database_type("test_custom")

    def test_create_custom_database(self):
        """Test creating a custom database via factory."""

        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        # Cleanup in case of previous test failure
        try:
            unregister_database_type("test_custom")
        except ValueError:
            pass

        # Register and create
        register_database_type("test_custom", create_test_db)
        db = create_database("test_custom", test_param="custom_value")

        assert isinstance(db, TestCustomDatabaseRegistration.CustomTestDatabase)
        assert db.test_param == "custom_value"

        # Cleanup
        unregister_database_type("test_custom")

    def test_create_custom_database_with_kwargs(self):
        """Test creating custom database with additional kwargs."""

        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        # Cleanup in case of previous test failure
        try:
            unregister_database_type("test_custom")
        except ValueError:
            pass

        register_database_type("test_custom", create_test_db)
        db = create_database(
            "test_custom", test_param="test_value", extra_param="ignored"
        )

        assert isinstance(db, TestCustomDatabaseRegistration.CustomTestDatabase)
        assert db.test_param == "test_value"

        # Cleanup
        unregister_database_type("test_custom")

    def test_register_duplicate_type(self):
        """Test error when registering duplicate database type."""

        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        # Cleanup in case of previous test failure
        try:
            unregister_database_type("test_duplicate")
        except ValueError:
            pass

        register_database_type("test_duplicate", create_test_db)

        # Try to register again
        with pytest.raises(ValueError) as exc_info:
            register_database_type("test_duplicate", create_test_db)

        assert "already registered" in str(exc_info.value).lower()

        # Cleanup
        unregister_database_type("test_duplicate")

    def test_register_builtin_type_fails(self):
        """Test that registering built-in types fails."""

        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        # Try to register "json" (built-in)
        with pytest.raises(ValueError) as exc_info:
            register_database_type("json", create_test_db)

        assert "built-in" in str(exc_info.value).lower()

        # Try to register "mongodb" (built-in)
        with pytest.raises(ValueError) as exc_info:
            register_database_type("mongodb", create_test_db)

        assert "built-in" in str(exc_info.value).lower()

        # Try to register "sqlite" (built-in)
        with pytest.raises(ValueError) as exc_info:
            register_database_type("sqlite", create_test_db)

        assert "built-in" in str(exc_info.value).lower()

    def test_unregister_database_type(self):
        """Test unregistering a custom database type."""

        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        # Register then unregister
        register_database_type("test_unregister", create_test_db)
        assert "test_unregister" in list_database_types()

        unregister_database_type("test_unregister")
        assert "test_unregister" not in list_database_types()

    def test_unregister_nonexistent_type(self):
        """Test error when unregistering non-existent type."""
        with pytest.raises(ValueError) as exc_info:
            unregister_database_type("nonexistent_type")

        assert "not registered" in str(exc_info.value).lower()

    def test_unregister_builtin_type_fails(self):
        """Test that unregistering built-in types fails."""
        with pytest.raises(ValueError) as exc_info:
            unregister_database_type("json")

        assert "built-in" in str(exc_info.value).lower()

        with pytest.raises(ValueError) as exc_info:
            unregister_database_type("mongodb")

        assert "built-in" in str(exc_info.value).lower()

        with pytest.raises(ValueError) as exc_info:
            unregister_database_type("sqlite")

        assert "built-in" in str(exc_info.value).lower()

    def test_list_database_types(self):
        """Test listing all database types."""
        types = list_database_types()

        # Should include built-in types
        assert "json" in types
        assert "mongodb" in types
        assert "sqlite" in types
        assert "json" in str(types["json"]).lower()
        assert "mongodb" in str(types["mongodb"]).lower()
        if HAS_SQLITE:
            assert "built-in" in types["sqlite"].lower()
        else:  # pragma: no cover - requires uninstalling aiosqlite
            assert "requires aiosqlite" in types["sqlite"].lower()

        # Register custom type and verify it appears
        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        register_database_type("test_list", create_test_db)
        types = list_database_types()
        assert "test_list" in types

        # Cleanup
        unregister_database_type("test_list")

    def test_create_unregistered_type_fails(self):
        """Test that creating unregistered custom type fails."""
        with pytest.raises(ValueError) as exc_info:
            create_database("unregistered_custom")

        assert "Unsupported database type" in str(exc_info.value)
        assert "unregistered_custom" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_custom_database_integration(self):
        """Test custom database with full CRUD operations."""

        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        register_database_type("test_integration", create_test_db)

        try:
            db = create_database("test_integration")

            # Test save
            data = {"id": "test-1", "name": "test", "value": 42}
            saved = await db.save("test_collection", data)
            assert saved["id"] == "test-1"

            # Test get
            retrieved = await db.get("test_collection", "test-1")
            assert retrieved is not None
            assert retrieved["name"] == "test"
            assert retrieved["value"] == 42

            # Test find
            results = await db.find("test_collection", {"name": "test"})
            assert len(results) == 1
            assert results[0]["id"] == "test-1"

            # Test find with empty query
            all_results = await db.find("test_collection", {})
            assert len(all_results) == 1

            # Test delete
            await db.delete("test_collection", "test-1")
            retrieved = await db.get("test_collection", "test-1")
            assert retrieved is None

        finally:
            unregister_database_type("test_integration")

    def test_custom_database_with_multi_database_management(self):
        """Test custom database with multi-database management."""

        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        register_database_type("test_multi", create_test_db)

        try:
            from jvspatial.db import get_database_manager

            # Create and register with manager
            db = create_database("test_multi", register=True, name="test_multi_db")
            manager = get_database_manager()

            # Verify it's registered
            databases = manager.list_databases()
            assert "test_multi_db" in databases

            # Switch to it
            manager.set_current_database("test_multi_db")
            current = manager.get_current_database()
            assert isinstance(
                current, TestCustomDatabaseRegistration.CustomTestDatabase
            )

        finally:
            unregister_database_type("test_multi")
            # Cleanup manager registration
            try:
                from jvspatial.db import unregister_database

                unregister_database("test_multi_db")
            except ValueError:
                pass  # Already unregistered

    def test_custom_database_with_graph_context(self):
        """Test custom database with GraphContext."""

        def create_test_db(
            **kwargs: Any,
        ) -> TestCustomDatabaseRegistration.CustomTestDatabase:
            return TestCustomDatabaseRegistration.CustomTestDatabase(**kwargs)

        register_database_type("test_context", create_test_db)

        try:
            from jvspatial.core.context import GraphContext

            db = create_database("test_context")
            ctx = GraphContext(database=db)

            # Verify context uses custom database
            assert ctx.database is db
            assert isinstance(
                ctx.database, TestCustomDatabaseRegistration.CustomTestDatabase
            )

        finally:
            unregister_database_type("test_context")
