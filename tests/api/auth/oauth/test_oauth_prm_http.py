"""RFC 9728 Protected Resource Metadata — HTTP integration tests.

Verifies that:
* ``/.well-known/oauth-protected-resource`` is served when oauth_enabled=True.
* The document shape conforms to RFC 9728.
* The endpoint is absent (404) when oauth_enabled is False.
"""

import tempfile
import uuid

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.server import Server


@pytest.fixture(autouse=True)
def _insecure(monkeypatch):
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


def test_prm_served():
    with tempfile.TemporaryDirectory() as tmp:
        r = TestClient(_app(tmp)).get("/.well-known/oauth-protected-resource")
        assert r.status_code == 200
        b = r.json()
        assert b["resource"] == "https://as.example"
        assert "https://as.example" in b["authorization_servers"]
        assert b["jwks_uri"] == "https://as.example/.well-known/jwks.json"
        assert b["bearer_methods_supported"] == ["header"]
        assert b["scopes_supported"] == ["mcp"]


def test_prm_absent_when_oauth_disabled():
    with tempfile.TemporaryDirectory() as tmp:
        s = Server(
            title="t",
            db_type="json",
            db_path=f"{tmp}/db_{uuid.uuid4().hex}",
            auth=dict(auth_enabled=True, jwt_secret="x" * 40),
        )
        assert (
            TestClient(s.get_app())
            .get("/.well-known/oauth-protected-resource")
            .status_code
            == 404
        )
