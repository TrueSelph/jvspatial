"""Tests for jvspatial.env live helpers."""

import os
from unittest.mock import patch

from jvspatial.env import (
    env,
    parse_bool,
    parse_optional_nonnegative_int,
    resolve_db_paths,
    resolve_file_storage_root,
)


def test_work_claim_stale_seconds_default():
    with patch.dict(os.environ, {}, clear=True):
        assert (
            env("JVSPATIAL_WORK_CLAIM_STALE_SECONDS", default=600.0, parse=float)
            == 600.0
        )


def test_work_claim_stale_seconds_custom():
    with patch.dict(os.environ, {"JVSPATIAL_WORK_CLAIM_STALE_SECONDS": "42"}):
        assert (
            env("JVSPATIAL_WORK_CLAIM_STALE_SECONDS", default=600.0, parse=float)
            == 42.0
        )


def test_work_claim_stale_seconds_invalid_falls_back():
    with patch.dict(os.environ, {"JVSPATIAL_WORK_CLAIM_STALE_SECONDS": "not-a-float"}):
        assert (
            env("JVSPATIAL_WORK_CLAIM_STALE_SECONDS", default=600.0, parse=float)
            == 600.0
        )


def test_deferred_invoke_disabled_on_values():
    for v in ("true", "1", "yes", "on", "TRUE", " On "):
        with patch.dict(os.environ, {"JVSPATIAL_DEFERRED_INVOKE_DISABLED": v}):
            assert (
                env(
                    "JVSPATIAL_DEFERRED_INVOKE_DISABLED",
                    default=False,
                    parse=parse_bool,
                )
                is True
            )


def test_deferred_invoke_disabled_default():
    with patch.dict(os.environ, {}, clear=True):
        assert (
            env("JVSPATIAL_DEFERRED_INVOKE_DISABLED", default=False, parse=parse_bool)
            is False
        )


def test_deferred_invoke_secret_empty_is_none():
    with patch.dict(os.environ, {}, clear=True):
        assert env("JVSPATIAL_DEFERRED_INVOKE_SECRET") is None
    with patch.dict(os.environ, {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "   "}):
        assert env("JVSPATIAL_DEFERRED_INVOKE_SECRET") is None


def test_deferred_invoke_secret_set():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_DEFERRED_INVOKE_SECRET": "my-secret"},  # pragma: allowlist secret
    ):
        assert env("JVSPATIAL_DEFERRED_INVOKE_SECRET") == "my-secret"


def test_jvspatial_db_path_sets_json_and_sqlite_paths():
    with patch.dict(os.environ, {"JVSPATIAL_DB_PATH": "/data/dbdir"}):
        jsondb_path, sqlite_path = resolve_db_paths(serverless=False)
        assert jsondb_path == "/data/dbdir"
        assert sqlite_path == "/data/dbdir"


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
        assert env("JVSPATIAL_S3_REGION", default="us-east-1") == "eu-west-1"
        assert env("JVSPATIAL_S3_ACCESS_KEY") == "ak"
        assert env("JVSPATIAL_S3_SECRET_KEY") == "sk"


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


def test_file_storage_root_uses_resolve():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_FILES_ROOT_PATH": "/tmp/jvfiles"},
        clear=True,
    ):
        assert resolve_file_storage_root() == "/tmp/jvfiles"


def test_env_reads_live_values():
    with patch.dict(os.environ, {"JVSPATIAL_API_PREFIX": "/v1"}):
        assert env("JVSPATIAL_API_PREFIX", default="/api") == "/v1"
    with patch.dict(os.environ, {"JVSPATIAL_API_PREFIX": "/v2"}):
        assert env("JVSPATIAL_API_PREFIX", default="/api") == "/v2"


def test_log_retention_default_days_unset():
    with patch.dict(os.environ, {}, clear=True):
        assert (
            parse_optional_nonnegative_int(
                os.getenv("JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS")
            )
            is None
        )


def test_log_retention_default_days_valid():
    with patch.dict(os.environ, {"JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS": "90"}):
        assert (
            parse_optional_nonnegative_int(
                os.getenv("JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS")
            )
            == 90
        )


def test_log_retention_default_days_zero():
    with patch.dict(os.environ, {"JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS": "0"}):
        assert (
            parse_optional_nonnegative_int(
                os.getenv("JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS")
            )
            == 0
        )


def test_log_retention_default_days_invalid_or_negative():
    for raw in ("not-int", "-1", "  "):
        with patch.dict(os.environ, {"JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS": raw}):
            assert (
                parse_optional_nonnegative_int(
                    os.getenv("JVSPATIAL_LOG_RETENTION_DEFAULT_DAYS")
                )
                is None
            )
