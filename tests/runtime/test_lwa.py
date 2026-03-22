"""Tests for Lambda Web Adapter env defaults."""

import os
from unittest.mock import MagicMock, patch

import pytest

from jvspatial.runtime.lwa import apply_aws_lwa_env_defaults
from jvspatial.runtime.serverless import reset_serverless_mode_cache

_LWA_KEYS = (
    "AWS_LWA_PASS_THROUGH_PATH",
    "AWS_LWA_INVOKE_MODE",
    "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED",
)


@pytest.fixture
def _restore_lwa_env():
    saved = {k: os.environ.get(k) for k in _LWA_KEYS}
    yield
    for k in _LWA_KEYS:
        v = saved[k]
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


@pytest.fixture(autouse=True)
def _reset_serverless_cache():
    reset_serverless_mode_cache()
    yield
    reset_serverless_mode_cache()


def test_apply_sets_defaults_serverless_aws(_restore_lwa_env):
    for k in _LWA_KEYS:
        os.environ.pop(k, None)
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "true", "AWS_LAMBDA_FUNCTION_NAME": "fn"},
        clear=False,
    ):
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert os.environ["AWS_LWA_PASS_THROUGH_PATH"] == "/api/_internal/deferred"
        assert os.environ["AWS_LWA_INVOKE_MODE"] == "RESPONSE_STREAM"
        assert os.environ["JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED"] == "true"


def test_apply_does_not_override_existing(_restore_lwa_env):
    with patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "true",
            "AWS_LAMBDA_FUNCTION_NAME": "fn",
            "AWS_LWA_PASS_THROUGH_PATH": "/custom/deferred",
            "AWS_LWA_INVOKE_MODE": "BUFFERED",
            "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED": "false",
        },
        clear=False,
    ):
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert os.environ["AWS_LWA_PASS_THROUGH_PATH"] == "/custom/deferred"
        assert os.environ["AWS_LWA_INVOKE_MODE"] == "BUFFERED"
        assert os.environ["JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED"] == "false"


def test_apply_skips_when_not_serverless(_restore_lwa_env):
    for k in _LWA_KEYS:
        os.environ.pop(k, None)
    with patch.dict(os.environ, {"SERVERLESS_MODE": "false"}, clear=False):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert "AWS_LWA_PASS_THROUGH_PATH" not in os.environ
        assert "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED" not in os.environ


def test_apply_skips_when_serverless_but_not_aws(_restore_lwa_env):
    for k in _LWA_KEYS:
        os.environ.pop(k, None)
    cfg = MagicMock()
    cfg.serverless_mode = True
    with patch.dict(
        os.environ,
        {"FUNCTIONS_WORKER_RUNTIME": "python"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults(cfg)
        assert "AWS_LWA_PASS_THROUGH_PATH" not in os.environ
        assert "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED" not in os.environ
