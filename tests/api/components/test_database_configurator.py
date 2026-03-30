"""Tests for DatabaseConfigurator component."""

from unittest.mock import MagicMock, patch

import pytest

from jvspatial.api.components.database_configurator import DatabaseConfigurator
from jvspatial.api.config import ServerConfig


class TestDatabaseConfigurator:
    """Test DatabaseConfigurator functionality."""

    @pytest.fixture
    def config(self):
        """Create test server config."""
        config = ServerConfig()
        config.database.db_type = "json"
        config.database.db_path = "./test_db"
        return config

    @pytest.fixture
    def configurator(self, config):
        """Create DatabaseConfigurator instance."""
        return DatabaseConfigurator(config)

    def test_initialization(self, configurator, config):
        """Test configurator initialization."""
        assert configurator.config == config

    @pytest.mark.asyncio
    async def test_initialize_graph_context_json(self, configurator):
        """Test GraphContext initialization with JSON database."""
        with patch(
            "jvspatial.api.components.database_configurator.create_database"
        ) as mock_create:
            mock_db = MagicMock()
            mock_create.return_value = mock_db

            with patch(
                "jvspatial.api.components.database_configurator.get_database_manager"
            ) as mock_get_manager:
                mock_manager = MagicMock()
                mock_manager.get_current_database.return_value = mock_db
                mock_get_manager.side_effect = RuntimeError()  # Manager doesn't exist

                with patch(
                    "jvspatial.api.components.database_configurator.set_database_manager"
                ):
                    with patch(
                        "jvspatial.api.components.database_configurator.GraphContext"
                    ) as mock_context:
                        mock_ctx_instance = MagicMock()
                        mock_context.return_value = mock_ctx_instance

                        with patch(
                            "jvspatial.api.components.database_configurator.set_default_context"
                        ):
                            result = configurator.initialize_graph_context()

                            assert result == mock_ctx_instance
                            mock_create.assert_called_once_with(
                                db_type="json",
                                base_path="./test_db",
                            )

    @pytest.mark.asyncio
    async def test_initialize_graph_context_mongodb(self, monkeypatch):
        """Test GraphContext initialization with MongoDB (config only; env unset)."""
        monkeypatch.delenv("JVSPATIAL_MONGODB_URI", raising=False)
        monkeypatch.delenv("JVSPATIAL_MONGODB_DB_NAME", raising=False)
        config = ServerConfig()
        config.database.db_type = "mongodb"
        config.database.db_connection_string = "mongodb://localhost:27017"
        config.database.db_database_name = "testdb"
        configurator = DatabaseConfigurator(config)

        with patch(
            "jvspatial.api.components.database_configurator.create_database"
        ) as mock_create:
            mock_db = MagicMock()
            mock_create.return_value = mock_db

            with patch(
                "jvspatial.api.components.database_configurator.get_database_manager"
            ) as mock_get_manager:
                mock_manager = MagicMock()
                mock_manager.get_current_database.return_value = mock_db
                mock_get_manager.side_effect = RuntimeError()

                with patch(
                    "jvspatial.api.components.database_configurator.set_database_manager"
                ):
                    with patch(
                        "jvspatial.api.components.database_configurator.GraphContext"
                    ) as mock_context:
                        mock_ctx_instance = MagicMock()
                        mock_context.return_value = mock_ctx_instance

                        with patch(
                            "jvspatial.api.components.database_configurator.set_default_context"
                        ):
                            result = configurator.initialize_graph_context()

                            assert result == mock_ctx_instance
                            mock_create.assert_called_once_with(
                                db_type="mongodb",
                                uri="mongodb://localhost:27017",
                                db_name="testdb",
                            )

    def test_resolve_mongodb_env_uri_overrides_config(self, monkeypatch):
        """JVSPATIAL_MONGODB_URI wins over database.db_connection_string."""
        monkeypatch.setenv("JVSPATIAL_MONGODB_URI", "mongodb://env-host:27017")
        monkeypatch.delenv("JVSPATIAL_MONGODB_DB_NAME", raising=False)
        config = ServerConfig()
        config.database.db_type = "mongodb"
        config.database.db_connection_string = "mongodb://config-host:27017"
        config.database.db_database_name = "configdb"
        configurator = DatabaseConfigurator(config)
        uri, db_name = configurator._resolve_mongodb_connection()
        assert uri == "mongodb://env-host:27017"
        assert db_name == "configdb"

    def test_resolve_mongodb_config_only_when_env_absent(self, monkeypatch):
        """When Mongo env vars are absent, use Server config and defaults."""
        monkeypatch.delenv("JVSPATIAL_MONGODB_URI", raising=False)
        monkeypatch.delenv("JVSPATIAL_MONGODB_DB_NAME", raising=False)
        config = ServerConfig()
        config.database.db_connection_string = "mongodb://cfg:27017"
        config.database.db_database_name = "cfgdb"
        configurator = DatabaseConfigurator(config)
        uri, db_name = configurator._resolve_mongodb_connection()
        assert uri == "mongodb://cfg:27017"
        assert db_name == "cfgdb"

    def test_resolve_mongodb_empty_config_uses_localhost_jvdb(self, monkeypatch):
        monkeypatch.delenv("JVSPATIAL_MONGODB_URI", raising=False)
        monkeypatch.delenv("JVSPATIAL_MONGODB_DB_NAME", raising=False)
        config = ServerConfig()
        configurator = DatabaseConfigurator(config)
        uri, db_name = configurator._resolve_mongodb_connection()
        assert uri == "mongodb://localhost:27017"
        assert db_name == "jvdb"

    def test_resolve_mongodb_db_name_from_env_uri_from_config(self, monkeypatch):
        """JVSPATIAL_MONGODB_DB_NAME set without URI uses config URI."""
        monkeypatch.delenv("JVSPATIAL_MONGODB_URI", raising=False)
        monkeypatch.setenv("JVSPATIAL_MONGODB_DB_NAME", "from_env")
        config = ServerConfig()
        config.database.db_connection_string = "mongodb://only-config:27017"
        config.database.db_database_name = "ignored_when_env_set"
        configurator = DatabaseConfigurator(config)
        uri, db_name = configurator._resolve_mongodb_connection()
        assert uri == "mongodb://only-config:27017"
        assert db_name == "from_env"

    def test_resolve_mongodb_empty_env_uri_falls_back_to_config(self, monkeypatch):
        monkeypatch.setenv("JVSPATIAL_MONGODB_URI", "   ")
        monkeypatch.delenv("JVSPATIAL_MONGODB_DB_NAME", raising=False)
        config = ServerConfig()
        config.database.db_connection_string = "mongodb://fallback:27017"
        configurator = DatabaseConfigurator(config)
        uri, db_name = configurator._resolve_mongodb_connection()
        assert uri == "mongodb://fallback:27017"
        assert db_name == "jvdb"

    @pytest.mark.asyncio
    async def test_initialize_graph_context_mongodb_env_overrides(self, monkeypatch):
        """Integration: create_database receives env URI when both env and config set."""
        monkeypatch.setenv("JVSPATIAL_MONGODB_URI", "mongodb://lambda:27017")
        monkeypatch.setenv("JVSPATIAL_MONGODB_DB_NAME", "lambdadb")
        config = ServerConfig()
        config.database.db_type = "mongodb"
        config.database.db_connection_string = "mongodb://yaml:27017"
        config.database.db_database_name = "yamldb"
        configurator = DatabaseConfigurator(config)

        with patch(
            "jvspatial.api.components.database_configurator.create_database"
        ) as mock_create:
            mock_db = MagicMock()
            mock_create.return_value = mock_db

            with patch(
                "jvspatial.api.components.database_configurator.get_database_manager"
            ) as mock_get_manager:
                mock_manager = MagicMock()
                mock_manager.get_current_database.return_value = mock_db
                mock_get_manager.side_effect = RuntimeError()

                with patch(
                    "jvspatial.api.components.database_configurator.set_database_manager"
                ):
                    with patch(
                        "jvspatial.api.components.database_configurator.GraphContext"
                    ) as mock_context:
                        mock_ctx_instance = MagicMock()
                        mock_context.return_value = mock_ctx_instance

                        with patch(
                            "jvspatial.api.components.database_configurator.set_default_context"
                        ):
                            configurator.initialize_graph_context()

                            mock_create.assert_called_once_with(
                                db_type="mongodb",
                                uri="mongodb://lambda:27017",
                                db_name="lambdadb",
                            )

    @pytest.mark.asyncio
    async def test_initialize_graph_context_dynamodb(self):
        """Test GraphContext initialization with DynamoDB."""
        config = ServerConfig()
        config.database.db_type = "dynamodb"
        config.database.dynamodb_table_name = "test_table"
        config.database.dynamodb_region = "us-west-2"
        configurator = DatabaseConfigurator(config)

        with patch(
            "jvspatial.api.components.database_configurator.create_database"
        ) as mock_create:
            mock_db = MagicMock()
            mock_create.return_value = mock_db

            with patch(
                "jvspatial.api.components.database_configurator.get_database_manager"
            ) as mock_get_manager:
                mock_manager = MagicMock()
                mock_manager.get_current_database.return_value = mock_db
                mock_get_manager.side_effect = RuntimeError()

                with patch(
                    "jvspatial.api.components.database_configurator.set_database_manager"
                ):
                    with patch(
                        "jvspatial.api.components.database_configurator.GraphContext"
                    ) as mock_context:
                        mock_ctx_instance = MagicMock()
                        mock_context.return_value = mock_ctx_instance

                        with patch(
                            "jvspatial.api.components.database_configurator.set_default_context"
                        ):
                            result = configurator.initialize_graph_context()

                            assert result == mock_ctx_instance
                            mock_create.assert_called_once_with(
                                db_type="dynamodb",
                                table_name="test_table",
                                region_name="us-west-2",
                                endpoint_url=None,
                                aws_access_key_id=None,
                                aws_secret_access_key=None,
                            )

    @pytest.mark.asyncio
    async def test_initialize_graph_context_no_db_type(self, configurator):
        """Test that None is returned when db_type is not set."""
        configurator.config.database.db_type = None
        result = configurator.initialize_graph_context()
        assert result is None

    @pytest.mark.asyncio
    async def test_initialize_graph_context_invalid_type(self, configurator):
        """Test error handling for invalid database type."""
        configurator.config.database.db_type = "invalid_type"

        with pytest.raises(ValueError, match="Unsupported database type"):
            configurator.initialize_graph_context()

    @pytest.mark.asyncio
    async def test_initialize_graph_context_s3_path_error(self, configurator):
        """Test error when S3 path is used with file-based database."""
        configurator.config.database.db_type = "json"
        configurator.config.database.db_path = "s3://bucket/path"

        with pytest.raises(ValueError, match="JSON database does not support S3 paths"):
            configurator.initialize_graph_context()

    @pytest.mark.asyncio
    async def test_db_path_resolve_app_resolves_relative_path(self, configurator):
        """Test that db_path_resolve='app' resolves relative db_path against app base dir."""
        configurator.config.database.db_path_resolve = "app"
        configurator.config.database.db_path = "track75_db"

        with patch.object(
            configurator, "_get_app_base_dir", return_value="/opt/backend"
        ):
            with patch(
                "jvspatial.api.components.database_configurator.create_database"
            ) as mock_create:
                mock_db = MagicMock()
                mock_create.return_value = mock_db

                with patch(
                    "jvspatial.api.components.database_configurator.get_database_manager"
                ) as mock_get_manager:
                    mock_get_manager.side_effect = RuntimeError()

                    with patch(
                        "jvspatial.api.components.database_configurator.set_database_manager"
                    ):
                        with patch(
                            "jvspatial.api.components.database_configurator.GraphContext"
                        ) as mock_context:
                            mock_ctx_instance = MagicMock()
                            mock_context.return_value = mock_ctx_instance

                            with patch(
                                "jvspatial.api.components.database_configurator.set_default_context"
                            ):
                                configurator.initialize_graph_context()

                                mock_create.assert_called_once_with(
                                    db_type="json",
                                    base_path="/opt/backend/track75_db",
                                )

    def test_resolve_db_path_absolute_unchanged(self, configurator):
        """Test that absolute paths are not modified."""
        configurator.config.database.db_path_resolve = "app"
        result = configurator._resolve_db_path("/absolute/path/to/db")
        assert result == "/absolute/path/to/db"

    def test_resolve_db_path_no_resolve_mode_unchanged(self, configurator):
        """Test that relative path is unchanged when db_path_resolve is not set."""
        result = configurator._resolve_db_path("relative/path")
        assert result == "relative/path"
