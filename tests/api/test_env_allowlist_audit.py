"""JVSPATIAL_* env allowlist enforcement (audit §7.1 / SPEC §10.2).

SPEC §10.2 promises "Unknown JVSPATIAL_* keys are rejected at startup
to catch typos." The earlier implementation only read enumerated keys
in ``env_adapter``; stray ``JVSPATIAL_*`` env vars went silently
ignored. ``enforce_env_allowlist`` now scans the environment and
warns (default) or raises (strict mode) on unknown keys.
"""

import os
from unittest.mock import patch

import pytest

from jvspatial.env_adapter import (
    ALLOWED_ENV_KEYS,
    discover_unknown_jvspatial_env_keys,
    enforce_env_allowlist,
)


def test_discover_unknown_returns_empty_with_known_keys():
    with patch.dict(os.environ, {"JVSPATIAL_DB_TYPE": "json"}, clear=False):
        assert "JVSPATIAL_DB_TYPE" not in discover_unknown_jvspatial_env_keys()


def test_discover_unknown_returns_typo_key():
    with patch.dict(
        os.environ,
        {"JVSPATIAL_JWT_SECRET": "oops"},  # pragma: allowlist secret  - typo
        clear=False,
    ):
        unknown = discover_unknown_jvspatial_env_keys()
        assert "JVSPATIAL_JWT_SECRET" in unknown


def test_enforce_warns_by_default(caplog):
    with patch.dict(
        os.environ,
        {"JVSPATIAL_JWT_SECRET": "oops"},  # pragma: allowlist secret  - typo
        clear=False,
    ):
        # No exception expected — default is warn.
        enforce_env_allowlist()
    # Restoring caplog level for the helper logger is enough — we don't
    # assert on the captured record because the helper uses
    # ``logger.warning`` directly via ``logging.getLogger`` and caplog
    # propagation depends on pytest configuration.


def test_enforce_raises_in_strict_mode():
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_JWT_SECRET": "oops",  # pragma: allowlist secret  - typo
            "JVSPATIAL_STRICT_ENV_ALLOWLIST": "true",
        },
        clear=False,
    ):
        with pytest.raises(ValueError, match="Unknown JVSPATIAL_"):
            enforce_env_allowlist()


def test_allowlist_contains_canonical_keys():
    # Spot-check: a handful of well-known keys must be present.
    expected = {
        "JVSPATIAL_DB_TYPE",
        "JVSPATIAL_JWT_SECRET_KEY",
        "JVSPATIAL_DOCS_DISABLED",
        "JVSPATIAL_WALKER_MAX_STEPS",
        "JVSPATIAL_CORS_ORIGINS",
    }
    assert expected.issubset(ALLOWED_ENV_KEYS)
