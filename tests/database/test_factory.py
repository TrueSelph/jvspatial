"""
Tests for database factory and configuration.
"""

import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from jvspatial.db.database import Database
from jvspatial.db.factory import get_database
from jvspatial.db.jsondb import JsonDB
from jvspatial.db.mongodb import MongoDB


class TestDatabaseFactory:
    """Test database factory functionality"""

    def setup_method(self):
        """Reset environment variables before each test"""
        # Store original environment
        self.original_env = {}
        env_vars = [
            "JVSPATIAL_DB_TYPE",
            "JVSPATIAL_JSONDB_PATH",
            "JVSPATIAL_MONGODB_URI",
            "JVSPATIAL_MONGODB_DB_NAME",
        ]
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Restore environment variables after each test"""
        # Restore original environment
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

    def test_default_database_type(self):
        """Test factory returns JsonDB by default"""
        db = get_database()

        assert isinstance(db, JsonDB)
        assert db.base_path.name == "jvdb"

    def test_explicit_json_database(self):
        """Test factory returns JsonDB when explicitly configured"""
        os.environ["JVSPATIAL_DB_TYPE"] = "json"

        db = get_database()

        assert isinstance(db, JsonDB)

    def test_json_database_with_custom_path(self):
        """Test JsonDB with custom path configuration"""
        custom_path = "/tmp/test_jsondb"
        os.environ["JVSPATIAL_DB_TYPE"] = "json"
        os.environ["JVSPATIAL_JSONDB_PATH"] = custom_path

        db = get_database()

        assert isinstance(db, JsonDB)
        assert db.base_path.samefile(custom_path)

    def test_mongodb_database(self):
        """Test factory returns MongoDB when configured"""
        os.environ["JVSPATIAL_DB_TYPE"] = "mongodb"

        # Mock MongoDB to avoid actual connection
        with patch("jvspatial.db.factory.MongoDB") as mock_mongodb:
            mock_instance = MagicMock(spec=MongoDB)
            mock_mongodb.return_value = mock_instance

            db = get_database()

            # Should create MongoDB instance
            mock_mongodb.assert_called_once()
            assert db == mock_instance

    def test_unsupported_database_type(self):
        """Test factory raises error for unsupported database type"""
        os.environ["JVSPATIAL_DB_TYPE"] = "unsupported_db"

        with pytest.raises(
            ValueError, match="Unsupported database type: unsupported_db"
        ):
            get_database()

    def test_case_insensitive_database_type(self):
        """Test that database type matching is case sensitive"""
        os.environ["JVSPATIAL_DB_TYPE"] = "JSON"  # uppercase

        with pytest.raises(ValueError, match="Unsupported database type: JSON"):
            get_database()

    def test_empty_database_type(self):
        """Test factory with empty database type raises error"""
        os.environ["JVSPATIAL_DB_TYPE"] = ""

        with pytest.raises(ValueError, match="Unsupported database type:"):
            get_database()


class TestJsonDBConfiguration:
    """Test JsonDB specific configuration"""

    def setup_method(self):
        """Reset environment variables"""
        self.original_env = {}
        env_vars = ["JVSPATIAL_DB_TYPE", "JVSPATIAL_JSONDB_PATH"]
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Restore environment variables"""
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

    def test_default_jsondb_path(self):
        """Test default JsonDB path"""
        os.environ["JVSPATIAL_DB_TYPE"] = "json"

        db = get_database()

        assert isinstance(db, JsonDB)
        assert db.base_path.name == "jvdb"

    def test_custom_jsondb_path_absolute(self):
        """Test JsonDB with custom absolute path"""
        temp_dir = tempfile.mkdtemp()
        try:
            os.environ["JVSPATIAL_DB_TYPE"] = "json"
            os.environ["JVSPATIAL_JSONDB_PATH"] = temp_dir

            db = get_database()

            assert isinstance(db, JsonDB)
            assert db.base_path.samefile(temp_dir)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_custom_jsondb_path_relative(self):
        """Test JsonDB with custom relative path"""
        os.environ["JVSPATIAL_DB_TYPE"] = "json"
        os.environ["JVSPATIAL_JSONDB_PATH"] = "custom/jvdb/path"

        db = get_database()

        assert isinstance(db, JsonDB)
        assert str(db.base_path).endswith("custom/jvdb/path")


class TestMongoDBConfiguration:
    """Test MongoDB specific configuration"""

    def setup_method(self):
        """Reset environment variables"""
        self.original_env = {}
        env_vars = [
            "JVSPATIAL_DB_TYPE",
            "JVSPATIAL_MONGODB_URI",
            "JVSPATIAL_MONGODB_DB_NAME",
        ]
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Restore environment variables"""
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

    def test_mongodb_basic_configuration(self):
        """Test basic MongoDB configuration"""
        os.environ["JVSPATIAL_DB_TYPE"] = "mongodb"

        with patch("jvspatial.db.factory.MongoDB") as mock_mongodb:
            mock_instance = MagicMock(spec=MongoDB)
            mock_mongodb.return_value = mock_instance

            db = get_database()

            mock_mongodb.assert_called_once()
            assert db == mock_instance


class TestFactoryErrorHandling:
    """Test error handling in factory"""

    def setup_method(self):
        """Reset environment variables"""
        self.original_env = {}
        env_vars = ["JVSPATIAL_DB_TYPE"]
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Restore environment variables"""
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

    def test_invalid_database_type_error_message(self):
        """Test specific error message for invalid database type"""
        invalid_type = "redis"
        os.environ["JVSPATIAL_DB_TYPE"] = invalid_type

        with pytest.raises(ValueError) as exc_info:
            get_database()

        assert f"Unsupported database type: {invalid_type}" in str(exc_info.value)

    def test_mongodb_import_failure_handling(self):
        """Test handling of MongoDB import failure"""
        os.environ["JVSPATIAL_DB_TYPE"] = "mongodb"

        # Mock a failed import
        with patch(
            "jvspatial.db.factory.MongoDB",
            side_effect=ImportError("MongoDB not available"),
        ):
            with pytest.raises(ImportError, match="MongoDB not available"):
                get_database()


class TestFactoryIntegration:
    """Test factory integration with actual database instances"""

    def setup_method(self):
        """Reset environment variables"""
        self.original_env = {}
        env_vars = ["JVSPATIAL_DB_TYPE", "JVSPATIAL_JSONDB_PATH"]
        for var in env_vars:
            self.original_env[var] = os.environ.get(var)
            if var in os.environ:
                del os.environ[var]

    def teardown_method(self):
        """Restore environment variables"""
        for var, value in self.original_env.items():
            if value is not None:
                os.environ[var] = value
            elif var in os.environ:
                del os.environ[var]

    def test_jsondb_instance_functionality(self):
        """Test that factory-created JsonDB instance works"""
        temp_dir = tempfile.mkdtemp()
        try:
            os.environ["JVSPATIAL_DB_TYPE"] = "json"
            os.environ["JVSPATIAL_JSONDB_PATH"] = temp_dir

            db = get_database()

            # Test basic functionality
            assert isinstance(db, JsonDB)
            assert hasattr(db, "save")
            assert hasattr(db, "get")
            assert hasattr(db, "delete")
            assert hasattr(db, "find")

            # Test that it's properly configured
            assert db.base_path.samefile(temp_dir)

        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    def test_multiple_factory_calls_same_configuration(self):
        """Test multiple factory calls with same configuration"""
        os.environ["JVSPATIAL_DB_TYPE"] = "json"

        db1 = get_database()
        db2 = get_database()

        # Should create separate instances
        assert isinstance(db1, JsonDB)
        assert isinstance(db2, JsonDB)
        assert db1 is not db2  # Different instances
        assert str(db1.base_path) == str(db2.base_path)  # Same configuration
