"""Tests for jvspatial.env.EnvConfig / load_env()."""

import os
from unittest.mock import patch

import pytest

from jvspatial.env import clear_load_env_cache, load_env, resolve_file_storage_root


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


def test_jvspatial_db_path_sets_json_and_sqlite_paths():
    with patch.dict(os.environ, {"JVSPATIAL_DB_PATH": "/data/dbdir"}):
        clear_load_env_cache()
        e = load_env()
        assert e.jsondb_path == "/data/dbdir"
        assert e.db_path == "/data/dbdir"


def test_forbidden_jsondb_path_raises():
    from jvspatial.env_adapter import JvspatialConfigEnvError

    with patch.dict(os.environ, {"JVSPATIAL_JSONDB_PATH": "/x"}):
        clear_load_env_cache()
        with pytest.raises(JvspatialConfigEnvError):
            load_env()


def test_s3_canonical_env_keys():
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_S3_REGION": "eu-west-1",
            "JVSPATIAL_S3_ACCESS_KEY": "ak",
            "JVSPATIAL_S3_SECRET_KEY": "sk",
        },
        clear=True,
    ):
        clear_load_env_cache()
        e = load_env()
        assert e.s3_region_name == "eu-west-1"
        assert e.s3_access_key_id == "ak"
        assert e.s3_secret_access_key == "sk"


def test_resolve_file_storage_root_ignores_legacy_jvspatial_file_storage_root():
    """JVSPATIAL_FILE_STORAGE_ROOT is no longer read (breaking change)."""
    with patch.dict(
        os.environ,
        {"JVSPATIAL_FILE_STORAGE_ROOT": "/legacy_only"},
        clear=True,
    ):
        assert resolve_file_storage_root(serverless=False) == "./.files"


def test_resolve_file_storage_root_merged_fallback():
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_file_storage_root(merged_root="/from_yaml") == "/from_yaml"


def test_resolve_file_storage_root_explicit_serverless_default():
    with patch.dict(os.environ, {}, clear=True):
        assert resolve_file_storage_root(serverless=True) == "/tmp/.files"
        assert resolve_file_storage_root(serverless=False) == "./.files"


def test_load_env_file_storage_root_uses_resolve():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_FILES_ROOT_PATH": "/tmp/jvfiles"},
        clear=True,
    ):
        clear_load_env_cache()
        assert load_env().file_storage_root == "/tmp/jvfiles"


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


def test_log_retention_default_days_unset():
    with patch.dict(os.environ, {}, clear=True):
        clear_load_env_cache()
        assert load_env().log_retention_default_days is None


def test_log_retention_default_days_valid():
    with patch.dict(os.environ, {"JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS": "90"}):
        clear_load_env_cache()
        assert load_env().log_retention_default_days == 90


def test_log_retention_default_days_zero():
    with patch.dict(os.environ, {"JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS": "0"}):
        clear_load_env_cache()
        assert load_env().log_retention_default_days == 0


def test_log_retention_default_days_invalid_or_negative():
    for raw in ("not-int", "-1", "  "):
        with patch.dict(os.environ, {"JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS": raw}):
            clear_load_env_cache()
            assert load_env().log_retention_default_days is None
