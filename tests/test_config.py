"""Test suite for unified Config system.

Tests the simplified configuration system that replaces multiple config classes.
"""

import os
from unittest.mock import patch

import pytest

from jvspatial.config import Config, get_config, set_config


class TestConfig:
    """Test unified Config class."""

    def test_config_default_values(self):
        """Test default configuration values."""
        config = Config()

        # Server defaults
        assert config.host == "localhost"
        assert config.port == 8000
        assert config.debug == False

        # Auth defaults
        assert config.jwt_secret == "your-secret-key"  # pragma: allowlist secret
        assert config.jwt_algorithm == "HS256"
        assert config.jwt_expire_minutes == 30

        # Database defaults
        assert config.db_type == "json"
        assert config.db_base_path == ".data"

        # Cache defaults
        assert config.cache_backend == "memory"
        assert config.cache_size == 1000

    def test_config_from_env(self):
        """Test configuration from environment variables."""
        env_vars = {
            "JVSPATIAL_HOST": "0.0.0.0",
            "JVSPATIAL_PORT": "9000",
            "JVSPATIAL_DEBUG": "true",
            "JVSPATIAL_JWT_SECRET_KEY": "test-secret",  # pragma: allowlist secret
            "JVSPATIAL_JWT_EXPIRE_MINUTES": "60",
            "JVSPATIAL_DB_TYPE": "mongodb",
            "JVSPATIAL_CACHE_BACKEND": "redis",
            "JVSPATIAL_CACHE_SIZE": "2000",
        }

        with patch.dict(os.environ, env_vars):
            config = Config.from_env()

            assert config.host == "0.0.0.0"
            assert config.port == 9000
            assert config.debug == True
            assert config.jwt_secret == "test-secret"  # pragma: allowlist secret
            assert config.jwt_expire_minutes == 60
            assert config.db_type == "mongodb"
            assert config.cache_backend == "redis"
            assert config.cache_size == 2000

    def test_config_update(self):
        """Test updating configuration values."""
        config = Config()

        # Update single value
        config.update(host="0.0.0.0")
        assert config.host == "0.0.0.0"

        # Update multiple values
        config.update(port=9000, debug=True)
        assert config.port == 9000
        assert config.debug == True

    def test_config_validation(self):
        """Test configuration validation."""
        # Valid config
        config = Config(host="localhost", port=8000)
        assert config.host == "localhost"
        assert config.port == 8000

        # Invalid port
        with pytest.raises(ValueError):
            Config(port=-1)

        # Invalid host
        with pytest.raises(ValueError):
            Config(host="")

    def test_config_dict_conversion(self):
        """Test converting config to/from dict."""
        config = Config(host="test", port=9000, debug=True)

        # Convert to dict
        config_dict = config.model_dump()
        assert config_dict["host"] == "test"
        assert config_dict["port"] == 9000
        assert config_dict["debug"] == True

        # Create from dict
        new_config = Config(**config_dict)
        assert new_config.host == "test"
        assert new_config.port == 9000
        assert new_config.debug == True

    def test_global_config_functions(self):
        """Test global config functions."""
        # Test get_config
        config = get_config()
        assert isinstance(config, Config)

        # Test set_config
        new_config = Config(host="test", port=9000)
        set_config(new_config)

        retrieved_config = get_config()
        assert retrieved_config.host == "test"
        assert retrieved_config.port == 9000

    def test_config_server_specific(self):
        """Test server-specific configuration."""
        config = Config(
            host="0.0.0.0",
            port=8000,
            debug=True,
            cors_origins=["http://localhost:3000"],
            cors_methods=["GET", "POST"],
            cors_headers=["*"],
        )

        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.debug == True
        assert config.cors_origins == ["http://localhost:3000"]
        assert config.cors_methods == ["GET", "POST"]
        assert config.cors_headers == ["*"]

    def test_config_auth_specific(self):
        """Test authentication-specific configuration."""
        config = Config(
            jwt_secret="super-secret-key",  # pragma: allowlist secret
            jwt_algorithm="HS512",
            jwt_expire_minutes=60,
            jwt_refresh_expire_days=7,
            password_min_length=8,
            password_require_special_chars=True,
        )

        assert config.jwt_secret == "super-secret-key"  # pragma: allowlist secret
        assert config.jwt_algorithm == "HS512"
        assert config.jwt_expire_minutes == 60
        assert config.jwt_refresh_expire_days == 7
        assert config.password_min_length == 8
        assert config.password_require_special_chars == True

    def test_config_database_specific(self):
        """Test database-specific configuration."""
        config = Config(
            db_type="mongodb",
            db_connection_string="mongodb://localhost:27017/test",
            db_base_path="/tmp/data",
            db_pool_size=10,
            db_max_connections=100,
        )

        assert config.db_type == "mongodb"
        assert config.db_connection_string == "mongodb://localhost:27017/test"
        assert config.db_base_path == "/tmp/data"
        assert config.db_pool_size == 10
        assert config.db_max_connections == 100

    def test_config_cache_specific(self):
        """Test cache-specific configuration."""
        config = Config(
            cache_backend="redis",
            cache_size=2000,
            cache_ttl_seconds=3600,
            cache_key_prefix="jvspatial:",
            redis_url="redis://localhost:6379/0",
        )

        assert config.cache_backend == "redis"
        assert config.cache_size == 2000
        assert config.cache_ttl_seconds == 3600
        assert config.cache_key_prefix == "jvspatial:"
        assert config.redis_url == "redis://localhost:6379/0"
