"""``JVSPATIAL_POSTGRES_*`` env keys map onto ServerConfig.database."""

from __future__ import annotations

import pytest

from jvspatial.env_adapter import server_config_overrides_from_env

_POSTGRES_ENV_KEYS = (
    "JVSPATIAL_POSTGRES_DSN",
    "JVSPATIAL_POSTGRES_MIN_POOL_SIZE",
    "JVSPATIAL_POSTGRES_MAX_POOL_SIZE",
    "JVSPATIAL_POSTGRES_POOLER_MODE",
)


@pytest.fixture(autouse=True)
def _clear_postgres_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Host ``.env`` values must not leak into these assertions."""
    for key in _POSTGRES_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_postgres_env_maps_into_database_group(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("JVSPATIAL_DB_TYPE", "postgres")
    monkeypatch.setenv("JVSPATIAL_POSTGRES_DSN", "postgresql://u:p@host:5432/db")
    monkeypatch.setenv("JVSPATIAL_POSTGRES_MIN_POOL_SIZE", "1")
    monkeypatch.setenv("JVSPATIAL_POSTGRES_MAX_POOL_SIZE", "4")
    monkeypatch.setenv("JVSPATIAL_POSTGRES_POOLER_MODE", "transaction")

    db = server_config_overrides_from_env()["database"]

    assert db["db_type"] == "postgres"
    assert db["postgres_dsn"] == "postgresql://u:p@host:5432/db"
    assert db["postgres_min_pool_size"] == 1
    assert db["postgres_max_pool_size"] == 4
    assert db["postgres_pooler_mode"] == "transaction"


def test_postgres_keys_absent_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JVSPATIAL_DB_TYPE", "json")

    db = server_config_overrides_from_env().get("database", {})

    for key in (
        "postgres_dsn",
        "postgres_min_pool_size",
        "postgres_max_pool_size",
        "postgres_pooler_mode",
    ):
        assert key not in db
