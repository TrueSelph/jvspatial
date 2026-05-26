"""CORS wildcard warning + EXPOSE_ERROR_DETAILS prod guard.

Audit §4.10 / §4.12 / SPEC §15.4-§15.5.
"""

import logging
import os
from unittest.mock import patch

from jvspatial.api.components.error_handler import _expose_error_details_to_clients
from jvspatial.api.config_groups import CORSConfig


def test_wildcard_origin_emits_warning(caplog):
    caplog.set_level(logging.WARNING, logger="jvspatial.api.config_groups")
    CORSConfig(cors_origins=["*"])
    assert any(
        "wildcard origins detected" in record.getMessage() for record in caplog.records
    )


def test_wildcard_with_opt_in_silences_warning(caplog):
    caplog.set_level(logging.WARNING, logger="jvspatial.api.config_groups")
    CORSConfig(cors_origins=["*"], cors_allow_wildcard=True)
    assert not any(
        "wildcard origins detected" in record.getMessage() for record in caplog.records
    )


def test_disabled_cors_does_not_warn(caplog):
    caplog.set_level(logging.WARNING, logger="jvspatial.api.config_groups")
    CORSConfig(cors_enabled=False, cors_origins=["*"])
    assert not any(
        "wildcard origins detected" in record.getMessage() for record in caplog.records
    )


def test_expose_error_details_suppressed_in_production():
    """Production-marked runtime ignores JVSPATIAL_EXPOSE_ERROR_DETAILS."""
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_EXPOSE_ERROR_DETAILS": "true",
            "JVSPATIAL_ENVIRONMENT": "production",
        },
        clear=False,
    ):
        # Reset the once-per-process flag so the warning re-arms.
        if hasattr(_expose_error_details_to_clients, "_warned"):
            delattr(_expose_error_details_to_clients, "_warned")
        assert _expose_error_details_to_clients() is False


def test_expose_error_details_honored_outside_production():
    with patch.dict(
        os.environ,
        {
            "JVSPATIAL_EXPOSE_ERROR_DETAILS": "true",
            "JVSPATIAL_ENVIRONMENT": "development",
        },
        clear=False,
    ):
        assert _expose_error_details_to_clients() is True
