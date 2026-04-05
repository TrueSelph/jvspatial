"""Webhook HMAC: unset / null env; signature_required without secret."""

from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException

from jvspatial.api.integrations.webhooks.middleware import WebhookMiddleware
from jvspatial.api.integrations.webhooks.utils import WebhookConfig


def test_signature_required_without_hmac_secret_raises():
    app = FastAPI()
    mw = WebhookMiddleware(
        app,
        config=WebhookConfig(hmac_secret=None),
        server=MagicMock(),
    )
    with pytest.raises(HTTPException) as exc_info:
        mw._create_processing_config({"signature_required": True, "hmac_secret": None})
    assert exc_info.value.status_code == 500
    assert "JVSPATIAL_WEBHOOK_HMAC_SECRET" in exc_info.value.detail


def test_signature_required_with_endpoint_secret_ok():
    app = FastAPI()
    mw = WebhookMiddleware(
        app,
        config=WebhookConfig(hmac_secret=None),
        server=MagicMock(),
    )
    cfg = mw._create_processing_config(
        {
            "signature_required": True,
            "hmac_secret": "endpoint-specific-hmac-secret-key-32b",
        }
    )
    assert cfg.hmac_secret == "endpoint-specific-hmac-secret-key-32b"
