"""DCR is rate-limited (open-registration abuse mitigation, review I-1)."""

import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.server import Server


@pytest.fixture(autouse=True)
def _insecure_transport(monkeypatch):
    monkeypatch.setenv("AUTHLIB_INSECURE_TRANSPORT", "1")


def _client(tmp, cap):
    s = Server(
        title="t",
        db_type="json",
        db_path=f"{tmp}/db_{uuid.uuid4().hex}",
        auth=dict(
            auth_enabled=True,
            jwt_secret="x" * 40,
            oauth_enabled=True,
            oauth_issuer_url="https://as.example",
            oauth_supported_scopes=["mcp"],
            oauth_dcr_rate_limit_per_minute=cap,
        ),
    )
    return TestClient(s.get_app())


def _register(c, i):
    return c.post(
        "/api/oauth/register",
        json={
            "client_name": f"c{i}",
            "redirect_uris": ["https://c.example/cb"],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp",
        },
    )


def test_dcr_rate_limited_after_cap():
    with tempfile.TemporaryDirectory() as tmp:
        c = _client(tmp, cap=3)
        codes = [_register(c, i).status_code for i in range(8)]
        assert any(s == 429 for s in codes), f"expected a 429 within burst, got {codes}"
        # at least the first few succeed
        assert codes[0] in (200, 201)
