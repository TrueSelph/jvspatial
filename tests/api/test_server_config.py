"""Tests for ServerConfig grouped configuration structure."""

import pytest

from jvspatial.api.config import ServerConfig
from jvspatial.api.config_groups import (
    AuthConfig,
    CORSConfig,
    DatabaseConfig,
    FileStorageConfig,
    ProxyConfig,
    RateLimitConfig,
    WebhookConfig,
)


class TestServerConfigGroups:
    """Test ServerConfig grouped configuration structure."""

    def test_config_groups_initialization(self):
        """Test that config groups are initialized."""
        config = ServerConfig()

        assert isinstance(config.database, DatabaseConfig)
        assert isinstance(config.cors, CORSConfig)
        assert isinstance(config.auth, AuthConfig)
        assert isinstance(config.rate_limit, RateLimitConfig)
        assert isinstance(config.file_storage, FileStorageConfig)
        assert isinstance(config.webhook, WebhookConfig)
        assert isinstance(config.proxy, ProxyConfig)

    def test_config_group_access(self):
        """Test accessing config via groups."""
        config = ServerConfig()

        # Set via group
        config.database.db_type = "sqlite"
        config.database.db_path = "./sqlite_db"

        # Access via group
        assert config.database.db_type == "sqlite"
        assert config.database.db_path == "./sqlite_db"

    def test_config_cors_group(self):
        """Test CORS configuration group."""
        config = ServerConfig()
        config.cors.cors_enabled = True
        config.cors.cors_origins = ["http://localhost:3000"]
        config.cors.cors_methods = ["GET", "POST"]
        config.cors.cors_headers = ["Content-Type"]

        assert config.cors.cors_enabled is True
        assert config.cors.cors_origins == ["http://localhost:3000"]
        assert config.cors.cors_methods == ["GET", "POST"]
        assert config.cors.cors_headers == ["Content-Type"]

    def test_config_auth_group(self):
        """Test Auth configuration group."""
        config = ServerConfig()
        config.auth.auth_enabled = True
        config.auth.jwt_secret = "secret-key"
        config.auth.jwt_algorithm = "HS256"
        config.auth.jwt_expire_minutes = 60
        config.auth.api_key_management_enabled = True
        config.auth.api_key_prefix = "sk_test_"

        assert config.auth.auth_enabled is True
        assert config.auth.jwt_secret == "secret-key"
        assert config.auth.jwt_algorithm == "HS256"
        assert config.auth.jwt_expire_minutes == 60
        assert config.auth.api_key_management_enabled is True
        assert config.auth.api_key_prefix == "sk_test_"

    def test_config_database_group(self):
        """Test Database configuration group."""
        config = ServerConfig()
        config.database.db_type = "dynamodb"
        config.database.db_path = "./dynamo"
        config.database.dynamodb_table_name = "test_table"
        config.database.dynamodb_region = "us-west-2"

        assert config.database.db_type == "dynamodb"
        assert config.database.db_path == "./dynamo"
        assert config.database.dynamodb_table_name == "test_table"
        assert config.database.dynamodb_region == "us-west-2"

    def test_config_rate_limit_group(self):
        """Test RateLimit configuration group."""
        config = ServerConfig()
        config.rate_limit.rate_limit_enabled = True
        config.rate_limit.rate_limit_default_requests = 100
        config.rate_limit.rate_limit_default_window = 120
        config.rate_limit.rate_limit_overrides = {
            "/api/expensive": {"requests": 10, "window": 60}
        }

        assert config.rate_limit.rate_limit_enabled is True
        assert config.rate_limit.rate_limit_default_requests == 100
        assert config.rate_limit.rate_limit_default_window == 120
        assert config.rate_limit.rate_limit_overrides == {
            "/api/expensive": {"requests": 10, "window": 60}
        }

    def test_config_file_storage_group(self):
        """Test FileStorage configuration group."""
        config = ServerConfig()
        config.file_storage.file_storage_enabled = True
        config.file_storage.file_storage_provider = "s3"
        config.file_storage.file_storage_root = "./files"
        config.file_storage.s3_bucket_name = "test-bucket"
        config.file_storage.s3_region = "us-east-1"

        assert config.file_storage.file_storage_enabled is True
        assert config.file_storage.file_storage_provider == "s3"
        assert config.file_storage.file_storage_root == "./files"
        assert config.file_storage.s3_bucket_name == "test-bucket"
        assert config.file_storage.s3_region == "us-east-1"

    def test_config_webhook_group(self):
        """Test Webhook configuration group."""
        config = ServerConfig()
        config.webhook.webhook_api_key_header = "x-webhook-key"
        config.webhook.webhook_api_key_query_param = "webhook_key"
        config.webhook.webhook_https_required = False

        assert config.webhook.webhook_api_key_header == "x-webhook-key"
        assert config.webhook.webhook_api_key_query_param == "webhook_key"
        assert config.webhook.webhook_https_required is False

    def test_config_proxy_group(self):
        """Test Proxy configuration group."""
        config = ServerConfig()
        config.proxy.proxy_enabled = True
        config.proxy.proxy_default_expiration = 7200
        config.proxy.proxy_max_expiration = 86400

        assert config.proxy.proxy_enabled is True
        assert config.proxy.proxy_default_expiration == 7200
        assert config.proxy.proxy_max_expiration == 86400

    def test_config_model_dump(self):
        """Test that model_dump includes grouped configs."""
        config = ServerConfig()
        config.database.db_type = "json"
        config.auth.auth_enabled = True

        dumped = config.model_dump()

        # Should include group fields
        assert "database" in dumped
        assert "auth" in dumped
        assert "cors" in dumped
        assert dumped["database"]["db_type"] == "json"
