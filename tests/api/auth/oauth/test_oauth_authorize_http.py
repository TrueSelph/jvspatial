"""OAuth /authorize over HTTP: consent page + session-user permission resolution.

Exercises the trust boundary end-to-end through ``TestClient``:

* unauthenticated ``GET /authorize`` is rejected (401, no bearer);
* an authenticated session user (with ``mcp`` but NOT ``admin``) drives the
  consent → approve → code → token exchange, and the issued access token's
  scope is the intersection of the client-requested scope (``mcp admin``) and
  the *session user's* effective permissions (``mcp``) — ``admin`` is filtered
  because the session user lacks it. The permissions come ONLY from the
  server-resolved session user, never from request input;
* deny redirects with ``error=access_denied`` and issues no code.
"""

import base64
import hashlib
import secrets
import tempfile
import uuid
from urllib.parse import parse_qs, urlparse

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient

from jvspatial.api.server import Server

ISSUER = "https://as.example"


@pytest.fixture(autouse=True)
def _allow_insecure_transport(monkeypatch):
    """TestClient uses http://testserver; Authlib requires HTTPS unless gated."""
    monkeypatch.setenv("AUTHLIB_INSECURE_TRANSPORT", "1")


def _app(tmp):
    """Build a TestClient app with auth + OAuth enabled over a temp JSON db."""
    s = Server(
        title="t",
        db_type="json",
        db_path=f"{tmp}/db_{uuid.uuid4().hex}",
        auth=dict(
            auth_enabled=True,
            jwt_secret="x" * 40,
            oauth_enabled=True,
            oauth_issuer_url=ISSUER,
            oauth_supported_scopes=["mcp", "admin"],
        ),
    )
    return s.get_app()


def _pkce():
    """Return a (verifier, S256-challenge) PKCE pair."""
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


def _bearer_for_mcp_user(c):
    """Create a non-admin user with the ``mcp`` permission; return (bearer, user_id).

    The first registered user becomes admin via the bootstrap rule, so we use
    that admin's bearer to mint a SECOND user with ``roles=["user"]`` and a
    direct ``mcp`` permission (so its effective permissions are exactly
    ``{"mcp"}`` — notably NOT ``admin``). We then log in as that second user to
    obtain its session bearer.
    """
    admin_email = f"admin_{uuid.uuid4().hex}@example.com"
    r = c.post(
        "/api/auth/register",
        json={"email": admin_email, "password": "password123"},
    )
    assert r.status_code == 200, r.text
    admin_login = c.post(
        "/api/auth/login",
        json={"email": admin_email, "password": "password123"},
    )
    assert admin_login.status_code == 200, admin_login.text
    admin_bearer = admin_login.json()["access_token"]

    user_email = f"user_{uuid.uuid4().hex}@example.com"
    created = c.post(
        "/api/auth/admin/users",
        headers={"Authorization": f"Bearer {admin_bearer}"},
        json={
            "email": user_email,
            "password": "password123",
            "roles": ["user"],
            "permissions": ["mcp"],
        },
    )
    assert created.status_code == 200, created.text
    user_body = created.json()
    user_id = user_body["id"]
    # effective permissions are mcp only — admin must be absent
    assert "mcp" in user_body["permissions"]
    assert "admin" not in user_body["permissions"]

    user_login = c.post(
        "/api/auth/login",
        json={"email": user_email, "password": "password123"},
    )
    assert user_login.status_code == 200, user_login.text
    return user_login.json()["access_token"], user_id


def _register_public_client(c, scope="mcp admin"):
    """DCR-register a public PKCE client with an https redirect; return its dict."""
    r = c.post(
        "/api/oauth/register",
        json={
            "client_name": "Claude Desktop",
            "redirect_uris": ["https://c.example/cb"],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": scope,
        },
    )
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_authorize_get_unauthenticated_is_401():
    """``GET /authorize`` without a bearer is rejected by the route dependency."""
    with tempfile.TemporaryDirectory() as tmp, TestClient(_app(tmp)) as c:
        client = _register_public_client(c)
        _, challenge = _pkce()
        r = c.get(
            "/api/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": client["client_id"],
                "redirect_uri": "https://c.example/cb",
                "scope": "mcp admin",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        assert r.status_code == 401, r.text


def test_authorize_full_flow_intersects_scope_with_session_permissions():
    """Approve flow issues a code whose token scope is session-permission limited."""
    with tempfile.TemporaryDirectory() as tmp, TestClient(_app(tmp)) as c:
        bearer, user_id = _bearer_for_mcp_user(c)
        client = _register_public_client(c, scope="mcp admin")
        verifier, challenge = _pkce()
        params = {
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://c.example/cb",
            "scope": "mcp admin",
            "state": "st-123",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }

        # GET consent page (authenticated) -> 200 HTML showing client + scopes.
        consent = c.get(
            "/api/oauth/authorize",
            params=params,
            headers={"Authorization": f"Bearer {bearer}"},
        )
        assert consent.status_code == 200, consent.text
        html = consent.text
        assert "Claude Desktop" in html
        assert "mcp" in html
        assert "admin" in html

        # POST approve (authenticated) -> 302 to redirect_uri with ?code=
        approved = c.post(
            "/api/oauth/authorize",
            data={**params, "decision": "approve"},
            headers={"Authorization": f"Bearer {bearer}"},
            follow_redirects=False,
        )
        assert approved.status_code in (302, 303), approved.text
        location = approved.headers["location"]
        assert location.startswith("https://c.example/cb?")
        q = parse_qs(urlparse(location).query)
        assert "code" in q, location
        assert q.get("state") == ["st-123"]
        code = q["code"][0]

        # Exchange the code at /token with the PKCE verifier -> access_token.
        tok = c.post(
            "/api/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": "https://c.example/cb",
                "client_id": client["client_id"],
                "code_verifier": verifier,
            },
        )
        assert tok.status_code == 200, tok.text
        access = tok.json()["access_token"]

        # Decode and assert the TRUST BOUNDARY: sub is the session user and the
        # scope is intersected with the session user's permissions (mcp, not
        # admin). Verify against the public key served at the JWKS endpoint.
        jwks = c.get("/.well-known/jwks.json").json()
        header = pyjwt.get_unverified_header(access)
        jwk = next(k for k in jwks["keys"] if k["kid"] == header["kid"])
        public_key = pyjwt.algorithms.RSAAlgorithm.from_jwk(jwk)
        decoded = pyjwt.decode(
            access,
            public_key,
            algorithms=["RS256"],
            audience=ISSUER,
        )
        assert decoded["sub"] == user_id
        granted = set(decoded.get("scope", "").split())
        assert "mcp" in granted
        assert "admin" not in granted


def test_authorize_deny_redirects_with_error_and_no_code():
    """Deny redirects to redirect_uri with error=access_denied and issues no code."""
    with tempfile.TemporaryDirectory() as tmp, TestClient(_app(tmp)) as c:
        bearer, _ = _bearer_for_mcp_user(c)
        client = _register_public_client(c, scope="mcp admin")
        _, challenge = _pkce()
        params = {
            "response_type": "code",
            "client_id": client["client_id"],
            "redirect_uri": "https://c.example/cb",
            "scope": "mcp admin",
            "state": "st-deny",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        denied = c.post(
            "/api/oauth/authorize",
            data={**params, "decision": "deny"},
            headers={"Authorization": f"Bearer {bearer}"},
            follow_redirects=False,
        )
        assert denied.status_code in (302, 303), denied.text
        location = denied.headers["location"]
        q = parse_qs(urlparse(location).query)
        assert q.get("error") == ["access_denied"], location
        assert "code" not in q
        assert q.get("state") == ["st-deny"]
