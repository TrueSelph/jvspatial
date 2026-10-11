"""Webhook HTTPS env keys → ServerConfig.webhook via env adapter."""

import os
from unittest.mock import patch

from jvspatial.api.config import ServerConfig
from jvspatial.env_adapter import deep_merge, server_config_overrides_from_env


def test_webhook_api_key_require_https_from_env():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_WEBHOOK_API_KEY_REQUIRE_HTTPS": "false"},
        clear=False,
    ):
        overrides = server_config_overrides_from_env()
    assert overrides["webhook"]["webhook_api_key_require_https"] is False

    merged = deep_merge(ServerConfig().model_dump(), overrides)
    config = ServerConfig(**merged)
    assert config.webhook.webhook_api_key_require_https is False


def test_webhook_https_required_from_env():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_WEBHOOK_HTTPS_REQUIRED": "false"},
        clear=False,
    ):
        overrides = server_config_overrides_from_env()
    assert overrides["webhook"]["webhook_https_required"] is False

    merged = deep_merge(ServerConfig().model_dump(), overrides)
    config = ServerConfig(**merged)
    assert config.webhook.webhook_https_required is False
