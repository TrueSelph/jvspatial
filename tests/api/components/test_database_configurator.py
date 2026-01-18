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
    async def test_initialize_graph_context_mongodb(self):
        """Test GraphContext initialization with MongoDB."""
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
