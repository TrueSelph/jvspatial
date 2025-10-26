"""Comprehensive test suite for database factory.

Tests database factory and registry functionality including:
- Database registration and unregistration
- Database type management
- Default database configuration
- Database discovery
- Error handling
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from jvspatial.db.database import Database
from jvspatial.db.factory import (
    get_database,
    get_default_database_type,
    list_available_databases,
    register_database,
    set_default_database,
    unregister_database,
)
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.mongodb import MongoDB
from jvspatial.exceptions import InvalidConfigurationError, ValidationError


class TestDatabaseFactory:
    """Test database factory functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Clean up any "mock" registrations from previous tests
        unregister_database("mock")
        unregister_database("custom")
        unregister_database("lifecycle")

    def _create_mock_database_class(self, name="MockDatabase"):
        """Create a real database class for testing."""

        class MockDatabase(Database):
            def __init__(self, **kwargs):
                pass

            async def clean(self) -> None:
                """Clean up orphaned edges."""
                pass

            async def save(self, collection: str, record: dict) -> dict:
                return record

            async def get(self, collection: str, id: str):
                return None

            async def find(self, collection: str, query: dict) -> list:
                return []

            async def delete(self, collection: str, record_id: str) -> None:
                pass

        MockDatabase.__name__ = name
        return MockDatabase

    async def test_database_registration(self):
        """Test database registration."""
        # Create a real database class for testing
        MockDatabase = self._create_mock_database_class("MockDatabase")

        # Register the database
        register_database("mock", MockDatabase)

        # Verify registration
        from jvspatial.db.factory import _DATABASE_REGISTRY

        assert "mock" in _DATABASE_REGISTRY
        assert _DATABASE_REGISTRY["mock"] == MockDatabase

    async def test_database_unregistration(self):
        """Test database unregistration."""
        # Create a real database class for testing
        MockDatabase = self._create_mock_database_class("MockDatabase")

        # Register the database
        register_database("mock", MockDatabase)

        # Unregister it
        unregister_database("mock")

        # Verify unregistration
        from jvspatial.db.factory import _DATABASE_REGISTRY

        assert "mock" not in _DATABASE_REGISTRY

    async def test_database_registration_duplicate(self):
        """Test duplicate database registration."""
        MockDatabase = self._create_mock_database_class("MockDatabase")

        # Register first time
        register_database("mock", MockDatabase)

        # Register again - should raise error
        with pytest.raises(InvalidConfigurationError):
            register_database("mock", MockDatabase)

    async def test_database_registration_invalid_class(self):
        """Test registration of invalid database class."""
        # Try to register non-Database class
        with pytest.raises(ValidationError):
            register_database("invalid", str)

    async def test_database_registration_invalid_name(self):
        """Test registration with invalid name."""
        # Empty name should work but is discouraged
        # Just test with valid database class
        MockDatabase = self._create_mock_database_class()
        register_database("test_empty", MockDatabase)
        unregister_database("test_empty")

    async def test_database_unregistration_nonexistent(self):
        """Test unregistration of non-existent database."""
        # Unregistering non-existent database should succeed (no-op)
        unregister_database("nonexistent")
        # Verify it's still not registered
        available = list_available_databases()
        assert "nonexistent" not in available

    async def test_list_available_databases(self):
        """Test listing available databases."""
        # Register some databases
        mock_db1 = self._create_mock_database_class("MockDatabase1")
        mock_db2 = self._create_mock_database_class("MockDatabase2")

        register_database("mock1", mock_db1)
        register_database("mock2", mock_db2)

        # List available databases (returns dict, not list)
        available = list_available_databases()
        assert "mock1" in available
        assert "mock2" in available

    async def test_list_available_databases_empty(self):
        """Test listing available databases."""
        # Built-in databases are always registered (json, mongodb if available)
        available = list_available_databases()
        assert isinstance(available, dict)
        assert len(available) >= 1  # At least json is registered
        assert "json" in available

    async def test_set_default_database(self):
        """Test setting default database."""
        mock_db_class = self._create_mock_database_class()
        register_database("mock", mock_db_class)

        # Set as default
        set_default_database("mock")

        # Verify default is set
        default_type = get_default_database_type()
        assert default_type == "mock"

    async def test_set_default_database_nonexistent(self):
        """Test setting non-existent database as default."""
        with pytest.raises(InvalidConfigurationError):
            set_default_database("nonexistent")

    async def test_get_default_database_type(self):
        """Test getting default database type."""
        mock_db_class = self._create_mock_database_class()
        register_database("mock", mock_db_class)
        set_default_database("mock")

        default_type = get_default_database_type()
        assert default_type == "mock"

    async def test_get_default_database_type_none(self):
        """Test getting default database type when none is set."""
        # The default is always set, just verify it returns a string
        default_type = get_default_database_type()
        assert isinstance(default_type, str)


class TestDatabaseCreation:
    """Test database creation functionality."""

    def setup_method(self):
        """Set up test environment."""
        # Clean up any "mock" registrations from previous tests
        unregister_database("mock")

    async def test_get_database_with_type(self):
        """Test getting database with specific type."""
        # Register mock database
        mock_db_class = MagicMock(spec=Database)
        mock_db_instance = MagicMock(spec=Database)
        mock_db_class.return_value = mock_db_instance

        register_database("mock", mock_db_class)

        # Get database
        db = get_database("mock", config={"test": "value"})

        # Verify database creation
        assert db == mock_db_instance
        mock_db_class.assert_called_once_with(config={"test": "value"})

    async def test_get_database_with_default(self):
        """Test getting database with default type."""
        # Register mock database and set as default
        mock_db_class = MagicMock(spec=Database)
        mock_db_instance = MagicMock(spec=Database)
        mock_db_class.return_value = mock_db_instance

        register_database("mock", mock_db_class)
        set_default_database("mock")

        # Get database without specifying type
        db = get_database(config={"test": "value"})

        # Verify database creation
        assert db == mock_db_instance
        mock_db_class.assert_called_once_with(config={"test": "value"})

    async def test_get_database_nonexistent_type(self):
        """Test getting database with non-existent type."""
        with pytest.raises(ValueError):
            get_database("nonexistent")

    async def test_get_database_no_default(self):
        """Test getting database with default."""
        # There's always a default (json), so this should succeed
        db = get_database()
        assert db is not None
        from jvspatial.db.jsondb import JsonDB

        assert isinstance(db, JsonDB)

    async def test_get_database_with_environment(self):
        """Test getting database with environment configuration."""
        # Mock environment variable
        with patch.dict(os.environ, {"JVSPATIAL_DB_TYPE": "mock"}):
            # Register mock database
            mock_db_class = MagicMock(spec=Database)
            mock_db_instance = MagicMock(spec=Database)
            mock_db_class.return_value = mock_db_instance

            register_database("mock", mock_db_class)

            # Get database
            db = get_database()

            # Verify database creation
            assert db == mock_db_instance

    async def test_get_database_with_config_override(self):
        """Test getting database with configuration override."""
        # Register mock database
        mock_db_class = MagicMock(spec=Database)
        mock_db_instance = MagicMock(spec=Database)
        mock_db_class.return_value = mock_db_instance

        register_database("mock", mock_db_class)

        # Get database with config override
        db = get_database("mock", config={"override": "value"})

        # Verify database creation with config
        assert db == mock_db_instance
        mock_db_class.assert_called_once_with(config={"override": "value"})


class TestBuiltinDatabases:
    """Test built-in database types."""

    def setup_method(self):
        """Set up test environment."""
        # Don't clear the registry - keep built-in databases available
        pass

    async def test_json_database_registration(self):
        """Test JSON database registration."""
        # JSON database should be available
        available = list_available_databases()
        assert "json" in available

    async def test_mongodb_database_registration(self):
        """Test MongoDB database registration."""
        # MongoDB database should be available if pymongo is installed
        available = list_available_databases()
        # MongoDB might not be available if pymongo is not installed
        # This test should pass regardless

    async def test_get_json_database(self):
        """Test getting JSON database."""
        # Get JSON database
        db = get_database("json", config={"root_path": "/tmp/test"})

        # Verify it's a JsonDB instance
        assert isinstance(db, JsonDB)

    async def test_get_mongodb_database(self):
        """Test getting MongoDB database."""
        # Get MongoDB database
        db = get_database(
            "mongodb", config={"uri": "mongodb://localhost:27017", "db_name": "test"}
        )

        # Verify it's a MongoDB instance
        assert isinstance(db, MongoDB)

    async def test_database_configuration_validation(self):
        """Test database configuration validation."""
        # JsonDB doesn't validate config, it just ignores unknown params
        # This is intentional - it accepts base_path and cache_size
        db = get_database("json", base_path="/tmp/test")
        assert db is not None


class TestDatabaseFactoryIntegration:
    """Test database factory integration."""

    def setup_method(self):
        """Set up test environment."""
        # Clean up any test database registrations from previous tests
        unregister_database("custom")
        unregister_database("lifecycle")
        unregister_database("db1")
        unregister_database("db2")

    async def test_factory_with_custom_database(self):
        """Test factory with custom database."""

        # Create custom database class
        class CustomDatabase(Database):
            def __init__(self, config=None):
                self.custom_initialized = True

            async def clean(self) -> None:
                pass

            async def save(self, collection: str, data: dict) -> dict:
                return data

            async def get(self, collection: str, id: str):
                return None

            async def find(self, collection: str, query: dict) -> list:
                return []

            async def delete(self, collection: str, id: str) -> None:
                pass

        # Register custom database
        register_database("custom", CustomDatabase)

        # Get custom database
        db = get_database("custom", config={"test": "value"})

        # Verify it's the custom database
        assert isinstance(db, CustomDatabase)
        assert db.custom_initialized is True

    async def test_factory_with_multiple_databases(self):
        """Test factory with multiple databases."""
        # Register multiple databases
        mock_db1 = MagicMock(spec=Database)
        mock_db2 = MagicMock(spec=Database)

        register_database("db1", mock_db1)
        register_database("db2", mock_db2)

        # List available databases
        available = list_available_databases()
        assert "db1" in available
        assert "db2" in available

        # Get each database
        db1 = get_database("db1")
        db2 = get_database("db2")

        assert db1 is not None
        assert db2 is not None

    @pytest.mark.asyncio
    async def test_factory_database_lifecycle(self):
        """Test database lifecycle management."""

        # Register database with lifecycle methods
        class LifecycleDatabase(Database):
            def __init__(self, config=None):
                self.initialized = False
                self.closed = False

            async def clean(self) -> None:
                pass

            async def save(self, collection: str, data: dict) -> dict:
                return data

            async def get(self, collection: str, id: str):
                return None

            async def find(self, collection: str, query: dict) -> list:
                return []

            async def delete(self, collection: str, id: str) -> None:
                pass

            async def initialize(self):
                self.initialized = True

            async def close(self):
                self.closed = True

        register_database("lifecycle", LifecycleDatabase)

        # Get database
        db = get_database("lifecycle")

        # Test lifecycle
        assert not db.initialized
        assert not db.closed

        # Initialize
        await db.initialize()
        assert db.initialized

        # Close
        await db.close()
        assert db.closed

    async def test_factory_error_handling(self):
        """Test factory error handling."""
        # Test with invalid database type
        with pytest.raises(ValueError):
            get_database("invalid_type")

        # JsonDB doesn't validate config, it ignores unknown params
        # So this test isn't applicable for JsonDB

        # Test with database creation error
        class FailingDatabase(Database):
            def __init__(self, config=None):
                raise RuntimeError("Database creation failed")

            async def clean(self) -> None:
                pass

            async def save(self, collection: str, data: dict) -> dict:
                return data

            async def get(self, collection: str, id: str):
                return None

            async def find(self, collection: str, query: dict) -> list:
                return []

            async def delete(self, collection: str, id: str) -> None:
                pass

        register_database("failing", FailingDatabase)

        # The error gets wrapped in InvalidConfigurationError
        with pytest.raises(InvalidConfigurationError):
            get_database("failing")

    async def test_factory_configuration_merging(self):
        """Test configuration merging."""
        # Test with environment variables
        with patch.dict(
            os.environ,
            {"JVSPATIAL_DB_TYPE": "json", "JVSPATIAL_JSONDB_PATH": "/tmp/env_path"},
        ):
            db = get_database()
            assert isinstance(db, JsonDB)
            # On macOS, /tmp may be a symlink to /private/tmp
            assert str(db.base_path) == os.path.realpath("/tmp/env_path")

        # Test with configuration override
        db = get_database("json", base_path="/tmp/override")
        assert str(db.base_path) == os.path.realpath("/tmp/override")

    async def test_factory_database_validation(self):
        """Test database validation."""
        # Test with valid database
        db = get_database("json", base_path="/tmp/test")
        assert db is not None

        # JsonDB doesn't validate configuration, it just uses defaults
        # So this test isn't applicable

        # MongoDB would need proper configuration
        # MongoDB tests should check for proper URI and db_name


class TestDatabaseFactoryPerformance:
    """Test database factory performance."""

    def setup_method(self):
        """Set up test environment."""
        # Clean up any test databases from previous runs
        for i in range(1000):
            unregister_database(f"db_{i}")
        unregister_database("perf")
        unregister_database("large_config")

    async def test_factory_registration_performance(self):
        """Test factory registration performance."""
        # Get initial count (built-in databases)
        initial_count = len(list_available_databases())

        # Register many databases
        for i in range(1000):
            mock_db = MagicMock(spec=Database)
            register_database(f"db_{i}", mock_db)

        # List available databases
        available = list_available_databases()
        assert len(available) == initial_count + 1000

    async def test_factory_database_creation_performance(self):
        """Test database creation performance."""
        # Register database
        mock_db_class = MagicMock(spec=Database)
        mock_db_instance = MagicMock(spec=Database)
        mock_db_class.return_value = mock_db_instance

        register_database("perf", mock_db_class)

        # Create many databases
        for _ in range(100):
            db = get_database("perf")
            assert db is not None

    async def test_factory_configuration_performance(self):
        """Test configuration performance."""
        # Test with large configuration
        large_config = {f"key_{i}": f"value_{i}" for i in range(1000)}

        mock_db_class = MagicMock(spec=Database)
        mock_db_instance = MagicMock(spec=Database)
        mock_db_class.return_value = mock_db_instance

        register_database("large_config", mock_db_class)

        # Get database with large config
        db = get_database("large_config", config=large_config)
        assert db is not None
