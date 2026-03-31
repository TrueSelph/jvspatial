"""Tests for :class:`~jvspatial.api.config.ServerConfig` and serverless runtime."""

import os
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from jvspatial.api.config import ServerConfig
from jvspatial.runtime.serverless import is_serverless_mode, reset_serverless_mode_cache


class TestServerConfig:
    """Server configuration model."""

    def test_default_values(self) -> None:
        config = ServerConfig()
        assert config.host == "0.0.0.0"
        assert config.port == 8000
        assert config.debug is False
        assert config.auth.jwt_algorithm == "HS256"
        assert config.auth.jwt_expire_minutes == 30

    def test_update_nested(self) -> None:
        config = ServerConfig()
        config.auth.jwt_expire_minutes = 60
        assert config.auth.jwt_expire_minutes == 60

    def test_port_validation(self) -> None:
        with pytest.raises(ValidationError, match="Port must be between"):
            ServerConfig(port=-1)

    def test_host_validation(self) -> None:
        with pytest.raises(ValidationError, match="Host cannot be empty"):
            ServerConfig(host="")

    def test_model_dump_roundtrip(self) -> None:
        config = ServerConfig(host="127.0.0.1", port=9000, debug=True)
        d = config.model_dump()
        restored = ServerConfig(**d)
        assert restored.host == "127.0.0.1"
        assert restored.port == 9000
        assert restored.debug is True


class TestServerlessRuntimeMode:
    """Serverless runtime detection and derived behavior."""

    def test_default_non_serverless_when_unset(self) -> None:
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SERVERLESS_MODE", None)
            os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
            os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
            reset_serverless_mode_cache()
            assert is_serverless_mode() is False

    def test_serverless_override_true(self) -> None:
        for val in ("true", "1", "yes", "True", "TRUE"):
            with patch.dict(os.environ, {"SERVERLESS_MODE": val}):
                reset_serverless_mode_cache()
                assert is_serverless_mode() is True

    def test_serverless_override_false(self) -> None:
        for val in ("false", "0", "no", "False", "FALSE"):
            with patch.dict(
                os.environ, {"SERVERLESS_MODE": val, "AWS_LAMBDA_FUNCTION_NAME": "func"}
            ):
                reset_serverless_mode_cache()
                assert is_serverless_mode() is False

    def test_lambda_auto_detection(self) -> None:
        with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "my-func"}):
            os.environ.pop("SERVERLESS_MODE", None)
            reset_serverless_mode_cache()
            assert is_serverless_mode() is True

    def test_config_override_precedence(self) -> None:
        with patch.dict(os.environ, {"SERVERLESS_MODE": "false"}):
            assert is_serverless_mode(ServerConfig(serverless_mode=True)) is True
            assert is_serverless_mode(ServerConfig(serverless_mode=False)) is False

    def test_current_server_config_used_when_no_explicit_config(self) -> None:
        from unittest.mock import MagicMock

        from jvspatial.api.context import set_current_server

        mock_srv = MagicMock()
        mock_srv.config = ServerConfig(serverless_mode=True)
        with patch.dict(os.environ, {"SERVERLESS_MODE": "false"}):
            os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
            os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
            reset_serverless_mode_cache()
            set_current_server(mock_srv)
            try:
                assert is_serverless_mode() is True
            finally:
                set_current_server(None)
