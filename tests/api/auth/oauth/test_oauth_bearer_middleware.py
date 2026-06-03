"""Resource-server: ``accept_oauth_bearer`` lets OAuth RS256 access tokens
authorize ``@endpoint(auth=True)`` routes alongside session JWTs.

The OAuth branch only runs when the session-JWT ``validate_token`` fails AND
``accept_oauth_bearer`` is on, so the session path is unchanged. We mint a
token with the server's *own* active signing key (the boot lifespan ensures it
in the server's default context, which ``set_default_context`` also records as
the process-wide fallback, so the test reads the same key) and assert it
authorizes a protected route that echoes ``request.state.user``.
"""

import tempfile
import time
import uuid

import jwt as pyjwt
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from jvspatial.api import endpoint
from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.api.context import set_current_server
from jvspatial.api.server import Server

ISSUER = "https://as.example"


@pytest.fixture(autouse=True)
def _allow_insecure_transport(monkeypatch):
    """TestClient uses http://testserver; Authlib requires HTTPS unless gated."""
    monkeypatch.setenv("AUTHLIB_INSECURE_TRANSPORT", "1")


def _make_server(tmp, *, accept_oauth_bearer):
    return Server(
        title="t",
        db_type="json",
        db_path=f"{tmp}/db_{uuid.uuid4().hex}",
        auth=dict(
            auth_enabled=True,
            jwt_secret="x" * 40,
            oauth_enabled=True,
            oauth_issuer_url=ISSUER,
            oauth_supported_scopes=["mcp"],
            accept_oauth_bearer=accept_oauth_bearer,
        ),
    )


def _register_whoami(server):
    """Register a middleware-authenticated route that echoes the principal."""

    @endpoint("/whoami", methods=["GET"], auth=True)
    async def whoami(request: Request):
        user = request.state.user
        return {
            "id": getattr(user, "id", None),
            "permissions": list(getattr(user, "permissions", []) or []),
        }

    server.app = None  # force app rebuild to include the new endpoint


async def _mint_oauth_token(claims):
    """Mint an OAuth RS256 access token with the server's active signing key."""
    key = await keystore.get_active_signing_key()
    assert key is not None, "server boot should have ensured a signing key"
    base = {
        "iss": ISSUER,
        "aud": ISSUER,
        "sub": "u_oauth",
        "scope": "mcp",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "jti": uuid.uuid4().hex,
    }
    base.update(claims)
    return pyjwt.encode(
        base, key.private_pem, algorithm="RS256", headers={"kid": key.kid}
    )


@pytest.mark.asyncio
async def test_oauth_bearer_authorizes_protected_route():
    with tempfile.TemporaryDirectory() as tmp:
        server = _make_server(tmp, accept_oauth_bearer=True)
        set_current_server(server)
        _register_whoami(server)
        with TestClient(server.get_app()) as client:
            # Boot ensures the signing key exists; confirm via JWKS.
            jwks = client.get("/.well-known/jwks.json").json()
            assert jwks["keys"], "JWKS must expose at least one signing key"

            # (a) OAuth token authorizes the protected route as the oauth principal.
            oauth_token = await _mint_oauth_token({})
            r = client.get(
                "/api/whoami",
                headers={"Authorization": f"Bearer {oauth_token}"},
            )
            assert r.status_code == 200, r.text
            assert r.json()["id"] == "u_oauth"
            assert "mcp" in r.json()["permissions"]

            # (b) Session-JWT path still works on the SAME route (unchanged).
            email = f"s{uuid.uuid4().hex[:20]}@example.com"
            client.post(
                "/api/auth/register",
                json={"email": email, "password": "password123"},
            )
            login = client.post(
                "/api/auth/login",
                json={"email": email, "password": "password123"},
            )
            assert login.status_code == 200, login.text
            session_token = login.json()["access_token"]
            session_user_id = login.json()["user"]["id"]
            r2 = client.get(
                "/api/whoami",
                headers={"Authorization": f"Bearer {session_token}"},
            )
            assert r2.status_code == 200, r2.text
            assert r2.json()["id"] == session_user_id

            # (c) OAuth token with the wrong audience -> 401.
            wrong_aud = await _mint_oauth_token({"aud": "https://other.example"})
            r3 = client.get(
                "/api/whoami",
                headers={"Authorization": f"Bearer {wrong_aud}"},
            )
            assert r3.status_code == 401, r3.text


@pytest.mark.asyncio
async def test_oauth_bearer_rejected_when_flag_off():
    with tempfile.TemporaryDirectory() as tmp:
        server = _make_server(tmp, accept_oauth_bearer=False)
        set_current_server(server)
        _register_whoami(server)
        with TestClient(server.get_app()) as client:
            jwks = client.get("/.well-known/jwks.json").json()
            assert jwks["keys"]

            # (d) With accept_oauth_bearer=False, a valid OAuth token -> 401.
            oauth_token = await _mint_oauth_token({})
            r = client.get(
                "/api/whoami",
                headers={"Authorization": f"Bearer {oauth_token}"},
            )
            assert r.status_code == 401, r.text
