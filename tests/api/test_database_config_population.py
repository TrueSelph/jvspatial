"""DatabaseConfig accepts its fields by name, not only by env alias.

Aliased fields on a pydantic v2 model are settable *only* by their alias
unless the model opts into ``populate_by_name``. ``DatabaseConfig`` did not,
so every ``dynamodb_*`` (and later ``postgres_*``) value passed by field name
-- by ``server_config_overrides_from_env`` and by embedding hosts building a
``DatabaseConfig`` directly -- was silently dropped. Nothing raised; the
backend simply fell back to reading env itself, which masked it.

``AuthConfig`` already sets ``populate_by_name``; these tests pin the same
contract for ``DatabaseConfig``.
"""

from __future__ import annotations

import pytest

from jvspatial.api.config_groups import DatabaseConfig

_ALIASED_FIELDS = [
    ("dynamodb_table_name", "JVSPATIAL_DYNAMODB_TABLE_NAME", "my-table"),
    ("dynamodb_region", "JVSPATIAL_DYNAMODB_REGION", "eu-west-1"),
    ("dynamodb_endpoint_url", "JVSPATIAL_DYNAMODB_ENDPOINT_URL", "http://localhost"),
    ("dynamodb_access_key_id", "AWS_ACCESS_KEY_ID", "AKIAEXAMPLE"),
    ("dynamodb_secret_access_key", "AWS_SECRET_ACCESS_KEY", "secret"),
    ("postgres_dsn", "JVSPATIAL_POSTGRES_DSN", "postgresql://u:p@h:5432/db"),
    ("postgres_pooler_mode", "JVSPATIAL_POSTGRES_POOLER_MODE", "transaction"),
]


@pytest.mark.parametrize("field,alias,value", _ALIASED_FIELDS)
def test_field_name_population(field: str, alias: str, value: str) -> None:
    assert getattr(DatabaseConfig(**{field: value}), field) == value


@pytest.mark.parametrize("field,alias,value", _ALIASED_FIELDS)
def test_alias_population_still_works(field: str, alias: str, value: str) -> None:
    """The env alias path must keep working — it is how env overrides land."""
    assert getattr(DatabaseConfig(**{alias: value}), field) == value


@pytest.mark.parametrize(
    "field,value",
    [("postgres_min_pool_size", 2), ("postgres_max_pool_size", 20)],
)
def test_integer_fields_populate_by_name(field: str, value: int) -> None:
    assert getattr(DatabaseConfig(**{field: value}), field) == value


def test_env_adapter_output_lands_on_the_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """The dict built from env must actually populate the model.

    ``server_config_overrides_from_env`` keys its database group by field
    name, so this is the path that was quietly inert.
    """
    from jvspatial.env_adapter import server_config_overrides_from_env

    monkeypatch.setenv("JVSPATIAL_DB_TYPE", "postgres")
    monkeypatch.setenv("JVSPATIAL_POSTGRES_DSN", "postgresql://u:p@h:5432/db")
    monkeypatch.setenv("JVSPATIAL_POSTGRES_MAX_POOL_SIZE", "7")

    db = DatabaseConfig(**server_config_overrides_from_env()["database"])

    assert db.db_type == "postgres"
    assert db.postgres_dsn == "postgresql://u:p@h:5432/db"
    assert db.postgres_max_pool_size == 7


def test_unaliased_fields_unaffected() -> None:
    db = DatabaseConfig(db_type="json", db_path="./jvdb")
    assert (db.db_type, db.db_path) == ("json", "./jvdb")
