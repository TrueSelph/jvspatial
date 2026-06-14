"""OAuth over HTTP: DCR persists a client; metadata advertises /api-prefixed URLs."""

import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.server import Server


@pytest.fixture(autouse=True)
def _allow_insecure_transport(monkeypatch):
    """TestClient uses http://testserver; Authlib requires HTTPS unless gated."""
    monkeypatch.setenv("AUTHLIB_INSECURE_TRANSPORT", "1")


def _app(tmp):
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
        ),
    )
    return s.get_app()


def test_metadata_advertises_api_prefixed_endpoints():
    with tempfile.TemporaryDirectory() as tmp:
        c = TestClient(_app(tmp))
        md = c.get("/.well-known/oauth-authorization-server").json()
        assert md["token_endpoint"] == "https://as.example/api/oauth/token"
        assert md["registration_endpoint"] == "https://as.example/api/oauth/register"
        assert md["revocation_endpoint"] == "https://as.example/api/oauth/revoke"
        assert md["authorization_endpoint"] == "https://as.example/api/oauth/authorize"
        assert md["jwks_uri"] == "https://as.example/.well-known/jwks.json"


def test_dcr_over_http_persists_client():
    with tempfile.TemporaryDirectory() as tmp:
        c = TestClient(_app(tmp))
        r = c.post(
            "/api/oauth/register",
            json={
                "client_name": "Claude",
                "redirect_uris": ["https://c.example/cb"],
                "grant_types": ["authorization_code", "refresh_token"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
                "scope": "mcp",
            },
        )
        assert r.status_code in (200, 201), r.text
        assert r.json()["client_id"]
        # https-only redirect guard still applies over HTTP
        bad = c.post(
            "/api/oauth/register",
            json={
                "client_name": "x",
                "redirect_uris": ["http://evil.example/cb"],
                "grant_types": ["authorization_code"],
                "response_types": ["code"],
                "token_endpoint_auth_method": "none",
            },
        )
        assert bad.status_code >= 400
