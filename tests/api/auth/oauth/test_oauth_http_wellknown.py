"""OAuth HTTP wiring: /.well-known metadata + jwks served at root when enabled."""

import tempfile
import uuid

from fastapi.testclient import TestClient

from jvspatial.api.server import Server


def _server(tmpdir):
    # Flat oauth_* / auth_* kwargs are not mapped into the nested AuthConfig
    # group by ServerConfig (only db_type/db_path are). The verified config
    # path is the nested ``auth=dict(...)`` block, matching tests/api/
    # test_auth_refresh.py.
    return Server(
        title="oauth-test",
        db_type="json",
        db_path=f"{tmpdir}/db_{uuid.uuid4().hex}",
        auth=dict(
            auth_enabled=True,
            jwt_secret="x" * 40,
            jwt_algorithm="HS256",
            oauth_enabled=True,
            oauth_issuer_url="https://as.example",
            oauth_supported_scopes=["mcp"],
        ),
    )


def test_wellknown_metadata_and_jwks_served():
    with tempfile.TemporaryDirectory() as tmp:
        app = _server(tmp).get_app()
        client = TestClient(app)
        md = client.get("/.well-known/oauth-authorization-server")
        assert md.status_code == 200
        body = md.json()
        assert body["issuer"] == "https://as.example"
        assert body["token_endpoint"].endswith("/oauth/token")
        assert "S256" in body["code_challenge_methods_supported"]

        jwks = client.get("/.well-known/jwks.json")
        assert jwks.status_code == 200
        keys = jwks.json()["keys"]
        assert len(keys) >= 1 and keys[0]["kty"] == "RSA" and "d" not in keys[0]


def test_oauth_disabled_no_wellknown():
    with tempfile.TemporaryDirectory() as tmp:
        s = Server(
            title="t",
            db_type="json",
            db_path=f"{tmp}/db_{uuid.uuid4().hex}",
            auth=dict(auth_enabled=True, jwt_secret="x" * 40),  # oauth off
        )
        client = TestClient(s.get_app())
        assert client.get("/.well-known/jwks.json").status_code == 404
