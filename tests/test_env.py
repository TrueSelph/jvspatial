"""Tests for jvspatial.env.EnvConfig / load_env()."""

import os
from unittest.mock import patch

import pytest

from jvspatial.env import clear_load_env_cache, load_env


@pytest.fixture(autouse=True)
def _reset_load_env_cache():
    clear_load_env_cache()
    yield
    clear_load_env_cache()


def test_work_claim_stale_seconds_default():
    with patch.dict(os.environ, {}, clear=True):
        clear_load_env_cache()
        assert load_env().work_claim_stale_seconds == 600.0


def test_work_claim_stale_seconds_custom():
    with patch.dict(os.environ, {"JVSPATIAL_WORK_CLAIM_STALE_SECONDS": "42"}):
        clear_load_env_cache()
        assert load_env().work_claim_stale_seconds == 42.0


def test_work_claim_stale_seconds_invalid_falls_back():
    with patch.dict(os.environ, {"JVSPATIAL_WORK_CLAIM_STALE_SECONDS": "not-a-float"}):
        clear_load_env_cache()
        assert load_env().work_claim_stale_seconds == 600.0


def test_deferred_invoke_disabled_on_values():
    for v in ("true", "1", "yes", "on", "TRUE", " On "):
        with patch.dict(os.environ, {"JVSPATIAL_DEFERRED_INVOKE_DISABLED": v}):
            clear_load_env_cache()
            assert load_env().deferred_invoke_disabled is True


def test_deferred_invoke_disabled_default():
    with patch.dict(os.environ, {}, clear=True):
        clear_load_env_cache()
        assert load_env().deferred_invoke_disabled is False


def test_deferred_invoke_secret_empty_is_none():
    with patch.dict(os.environ, {}, clear=True):
        clear_load_env_cache()
        assert load_env().deferred_invoke_secret is None
    with patch.dict(os.environ, {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "   "}):
        clear_load_env_cache()
        assert load_env().deferred_invoke_secret is None


def test_deferred_invoke_secret_set():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "my-secret"},  # pragma: allowlist secret
    ):
        clear_load_env_cache()
        assert load_env().deferred_invoke_secret == "my-secret"


def test_sqlite_path_over_db_path():
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_DB_PATH": "/from/db_path.db",
            "JVSPATIAL_SQLITE_PATH": "/from/sqlite_path.db",
        },
    ):
        clear_load_env_cache()
        assert load_env().db_path == "/from/sqlite_path.db"


def test_s3_legacy_env_aliases():
    with patch.dict(
        os.environ,
        {},
        clear=True,
    ):
        clear_load_env_cache()
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_S3_REGION": "eu-west-1",
            "JVSPATIAL_S3_ACCESS_KEY": "ak",
            "JVSPATIAL_S3_SECRET_KEY": "sk",
        },
    ):
        clear_load_env_cache()
        e = load_env()
        assert e.s3_region_name == "eu-west-1"
        assert e.s3_access_key_id == "ak"
        assert e.s3_secret_access_key == "sk"


def test_load_env_is_cached_until_cleared():
    clear_load_env_cache()
    with patch.dict(os.environ, {"JVSPATIAL_API_PREFIX": "/v1"}):
        clear_load_env_cache()
        assert load_env().api_prefix == "/v1"
        assert load_env().api_prefix == "/v1"
    clear_load_env_cache()
    with patch.dict(os.environ, {"JVSPATIAL_API_PREFIX": "/v2"}):
        clear_load_env_cache()
        assert load_env().api_prefix == "/v2"
