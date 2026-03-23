"""Tests for AWS serverless EventBridge env default (Server bootstrap)."""

import os
from unittest.mock import MagicMock, patch

import pytest

from jvspatial.api.constants import APIRoutes
from jvspatial.env import clear_load_env_cache
from jvspatial.runtime.lwa import (
    apply_aws_eventbridge_env_default,
    apply_aws_lwa_env_defaults,
)
from jvspatial.runtime.serverless import reset_serverless_mode_cache

_EB_KEY = "JVSPATIAL_EVENTBRIDGE_SCHEDULER_ENABLED"
_LWA_KEYS = (
    "AWS_LWA_INVOKE_MODE",
    "AWS_LWA_PASS_THROUGH_PATH",
    "JVSPATIAL_LWA_ENV_DEFAULTS",
    "AWS_LWA_PORT",
    "AWS_LAMBDA_EXEC_WRAPPER",
    "JVSPATIAL_API_PREFIX",
)


@pytest.fixture
def _restore_eb_env():
    saved = os.environ.get(_EB_KEY)
    yield
    if saved is None:
        os.environ.pop(_EB_KEY, None)
    else:
        os.environ[_EB_KEY] = saved


@pytest.fixture
def _restore_lwa_env():
    saved = {k: os.environ.get(k) for k in _LWA_KEYS}
    yield
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _aws_serverless_env(**extra: str) -> dict:
    base = {
        "SERVERLESS_MODE": "true",
        "AWS_LAMBDA_FUNCTION_NAME": "fn",
        "AWS_LWA_PORT": "8080",
    }
    base.update(extra)
    return base


@pytest.fixture(autouse=True)
def _reset_serverless_cache():
    reset_serverless_mode_cache()
    yield
    reset_serverless_mode_cache()


def test_apply_sets_eventbridge_default_serverless_aws(_restore_eb_env):
    os.environ.pop(_EB_KEY, None)
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "true", "AWS_LAMBDA_FUNCTION_NAME": "fn"},
        clear=False,
    ):
        reset_serverless_mode_cache()
        apply_aws_eventbridge_env_default()
        assert os.environ[_EB_KEY] == "true"


def test_apply_does_not_override_existing(_restore_eb_env):
    with patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "true",
            "AWS_LAMBDA_FUNCTION_NAME": "fn",
            _EB_KEY: "false",
        },
        clear=False,
    ):
        reset_serverless_mode_cache()
        apply_aws_eventbridge_env_default()
        assert os.environ[_EB_KEY] == "false"


def test_apply_skips_when_not_serverless(_restore_eb_env):
    os.environ.pop(_EB_KEY, None)
    with patch.dict(os.environ, {"SERVERLESS_MODE": "false"}, clear=False):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        reset_serverless_mode_cache()
        apply_aws_eventbridge_env_default()
        assert _EB_KEY not in os.environ


def test_apply_skips_when_serverless_but_not_aws(_restore_eb_env):
    os.environ.pop(_EB_KEY, None)
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
        apply_aws_eventbridge_env_default(cfg)
        assert _EB_KEY not in os.environ


def test_deferred_invoke_full_path_respects_api_prefix(_restore_eb_env):
    with patch.dict(os.environ, {"JVSPATIAL_API_PREFIX": "/v1"}, clear=False):
        clear_load_env_cache()
        assert APIRoutes.deferred_invoke_full_path() == "/v1/_internal/deferred"


def test_lwa_defaults_set_when_aws_serverless_and_port(_restore_lwa_env):
    with patch.dict(os.environ, _aws_serverless_env(), clear=False):
        os.environ.pop("AWS_LWA_INVOKE_MODE", None)
        os.environ.pop("AWS_LWA_PASS_THROUGH_PATH", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert os.environ["AWS_LWA_INVOKE_MODE"] == "RESPONSE_STREAM"
        assert os.environ["AWS_LWA_PASS_THROUGH_PATH"] == "/api/_internal/deferred"


def test_lwa_pass_through_respects_api_prefix(_restore_lwa_env):
    with patch.dict(
        os.environ,
        _aws_serverless_env(JVSPATIAL_API_PREFIX="/v1"),
        clear=False,
    ):
        os.environ.pop("AWS_LWA_INVOKE_MODE", None)
        os.environ.pop("AWS_LWA_PASS_THROUGH_PATH", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert os.environ["AWS_LWA_PASS_THROUGH_PATH"] == "/v1/_internal/deferred"


def test_lwa_defaults_exec_wrapper_bootstrap(_restore_lwa_env):
    with patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "true",
            "AWS_LAMBDA_FUNCTION_NAME": "fn",
            "AWS_LAMBDA_EXEC_WRAPPER": "/opt/bootstrap",
        },
        clear=False,
    ):
        os.environ.pop("AWS_LWA_PORT", None)
        os.environ.pop("AWS_LWA_INVOKE_MODE", None)
        os.environ.pop("AWS_LWA_PASS_THROUGH_PATH", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert os.environ["AWS_LWA_INVOKE_MODE"] == "RESPONSE_STREAM"


def test_lwa_defaults_does_not_override_existing(_restore_lwa_env):
    with patch.dict(
        os.environ,
        _aws_serverless_env(
            AWS_LWA_INVOKE_MODE="BUFFERED",
            AWS_LWA_PASS_THROUGH_PATH="/custom",
        ),
        clear=False,
    ):
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert os.environ["AWS_LWA_INVOKE_MODE"] == "BUFFERED"
        assert os.environ["AWS_LWA_PASS_THROUGH_PATH"] == "/custom"


def test_lwa_defaults_skips_without_lwa_signal(_restore_lwa_env):
    with patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "true",
            "AWS_LAMBDA_FUNCTION_NAME": "fn",
        },
        clear=False,
    ):
        os.environ.pop("AWS_LWA_PORT", None)
        os.environ.pop("AWS_LAMBDA_EXEC_WRAPPER", None)
        os.environ.pop("JVSPATIAL_LWA_ENV_DEFAULTS", None)
        os.environ.pop("AWS_LWA_INVOKE_MODE", None)
        os.environ.pop("AWS_LWA_PASS_THROUGH_PATH", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert "AWS_LWA_INVOKE_MODE" not in os.environ
        assert "AWS_LWA_PASS_THROUGH_PATH" not in os.environ


def test_lwa_defaults_force_via_jvspatial_flag(_restore_lwa_env):
    with patch.dict(
        os.environ,
        {
            "SERVERLESS_MODE": "true",
            "AWS_LAMBDA_FUNCTION_NAME": "fn",
            "JVSPATIAL_LWA_ENV_DEFAULTS": "true",
        },
        clear=False,
    ):
        os.environ.pop("AWS_LWA_PORT", None)
        os.environ.pop("AWS_LAMBDA_EXEC_WRAPPER", None)
        os.environ.pop("AWS_LWA_INVOKE_MODE", None)
        os.environ.pop("AWS_LWA_PASS_THROUGH_PATH", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert os.environ["AWS_LWA_INVOKE_MODE"] == "RESPONSE_STREAM"


def test_lwa_defaults_opt_out_disables(_restore_lwa_env):
    with patch.dict(
        os.environ,
        _aws_serverless_env(JVSPATIAL_LWA_ENV_DEFAULTS="false"),
        clear=False,
    ):
        os.environ.pop("AWS_LWA_INVOKE_MODE", None)
        os.environ.pop("AWS_LWA_PASS_THROUGH_PATH", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert "AWS_LWA_INVOKE_MODE" not in os.environ
        assert "AWS_LWA_PASS_THROUGH_PATH" not in os.environ


def test_lwa_defaults_skips_when_not_serverless(_restore_lwa_env):
    with patch.dict(
        os.environ,
        {"SERVERLESS_MODE": "false", "AWS_LWA_PORT": "8080"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        os.environ.pop("AWS_LWA_INVOKE_MODE", None)
        os.environ.pop("AWS_LWA_PASS_THROUGH_PATH", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults()
        assert "AWS_LWA_INVOKE_MODE" not in os.environ


def test_lwa_defaults_skips_when_not_aws(_restore_lwa_env):
    cfg = MagicMock()
    cfg.serverless_mode = True
    with patch.dict(
        os.environ,
        {"FUNCTIONS_WORKER_RUNTIME": "python", "AWS_LWA_PORT": "8080"},
        clear=False,
    ):
        os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
        os.environ.pop("AWS_LAMBDA_RUNTIME_API", None)
        os.environ.pop("AWS_LWA_INVOKE_MODE", None)
        os.environ.pop("AWS_LWA_PASS_THROUGH_PATH", None)
        reset_serverless_mode_cache()
        apply_aws_lwa_env_defaults(cfg)
        assert "AWS_LWA_INVOKE_MODE" not in os.environ
