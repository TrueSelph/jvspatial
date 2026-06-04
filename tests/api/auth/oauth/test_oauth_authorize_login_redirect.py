"""OAuth /authorize login-redirect (M3a): unauthenticated GET → configured SPA.

When ``AuthConfig.oauth_authorize_login_redirect`` is set, an unauthenticated
``GET /oauth/authorize`` 302-redirects the browser to that SPA login URL with
the original OAuth query string appended, instead of returning the legacy 401
JSON. Empty (default) preserves the legacy 401. The redirect target is ONLY the
configured base + the original query — never an attacker-controlled host. The
authenticated GET (consent page) and POST (approve/deny) paths are unchanged.
"""

import base64
import hashlib
import secrets
import tempfile
import uuid
from urllib.parse import urlparse

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.server import Server

ISSUER = "https://as.example"
LOGIN_SPA = "https://app.example.com/oauth/authorize"


def _challenge():
    """Return a valid S256 PKCE challenge (format is validated at the consent step)."""
    verifier = secrets.token_urlsafe(64)
    return (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )


@pytest.fixture(autouse=True)
def _allow_insecure_transport(monkeypatch):
    """TestClient uses http://testserver; Authlib requires HTTPS unless gated."""
    monkeypatch.setenv("AUTHLIB_INSECURE_TRANSPORT", "1")


def _app(tmp, *, login_redirect=""):
    """Build a TestClient app with auth + OAuth enabled over a temp JSON db.

    ``login_redirect`` populates ``oauth_authorize_login_redirect`` (empty by
    default → legacy 401 for the unauthenticated GET).
    """
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
            oauth_authorize_login_redirect=login_redirect,
        ),
    )
    return s.get_app()


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


def _bearer_for_user(c):
    """Register a user (becomes admin via bootstrap) and return its session bearer."""
    email = f"u_{uuid.uuid4().hex}@example.com"
    r = c.post("/api/auth/register", json={"email": email, "password": "password123"})
    assert r.status_code == 200, r.text
    login = c.post("/api/auth/login", json={"email": email, "password": "password123"})
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def _authorize_params(client):
    return {
        "response_type": "code",
        "client_id": client["client_id"],
        "redirect_uri": "https://c.example/cb",
        "scope": "mcp admin",
        "state": "st-redir",
        "code_challenge": _challenge(),
        "code_challenge_method": "S256",
    }


def test_unauth_get_redirects_to_configured_login_spa_with_query():
    """Unauthenticated GET + field SET → 302 to {base}?{original query}."""
    with (
        tempfile.TemporaryDirectory() as tmp,
        TestClient(_app(tmp, login_redirect=LOGIN_SPA)) as c,
    ):
        client = _register_public_client(c)
        params = _authorize_params(client)
        r = c.get("/api/oauth/authorize", params=params, follow_redirects=False)
        assert r.status_code == 302, r.text
        location = r.headers["location"]
        # The target host/path is ONLY the configured base — never request-derived.
        target = urlparse(location)
        base = urlparse(LOGIN_SPA)
        assert (target.scheme, target.netloc, target.path) == (
            base.scheme,
            base.netloc,
            base.path,
        ), location
        # The full original OAuth query string is appended verbatim.
        sent = TestClient(_app(tmp)).build_request(  # query-string builder
            "GET", "/api/oauth/authorize", params=params
        )
        original_query = urlparse(str(sent.url)).query
        assert location == f"{LOGIN_SPA}?{original_query}", location


def test_unauth_get_empty_field_is_legacy_401():
    """Unauthenticated GET + field EMPTY (default) → legacy 401 (no regression)."""
    with tempfile.TemporaryDirectory() as tmp, TestClient(_app(tmp)) as c:
        client = _register_public_client(c)
        r = c.get(
            "/api/oauth/authorize",
            params=_authorize_params(client),
            follow_redirects=False,
        )
        assert r.status_code == 401, r.text
        assert "location" not in {k.lower() for k in r.headers}


def test_authed_get_with_field_set_still_renders_consent_html():
    """Authenticated GET + field SET → consent HTML (200), NOT a redirect.

    The field only affects the unauthenticated case; a valid bearer is unchanged.
    """
    with (
        tempfile.TemporaryDirectory() as tmp,
        TestClient(_app(tmp, login_redirect=LOGIN_SPA)) as c,
    ):
        bearer = _bearer_for_user(c)
        client = _register_public_client(c)
        r = c.get(
            "/api/oauth/authorize",
            params=_authorize_params(client),
            headers={"Authorization": f"Bearer {bearer}"},
            follow_redirects=False,
        )
        assert r.status_code == 200, r.text
        assert "Claude Desktop" in r.text
        assert "location" not in {k.lower() for k in r.headers}


def test_post_authorize_still_requires_auth_even_with_field_set():
    """POST /authorize is unchanged: still requires the session user (401 w/o bearer).

    The login-redirect field affects ONLY the unauthenticated GET — POST never
    redirects to the login SPA.
    """
    with (
        tempfile.TemporaryDirectory() as tmp,
        TestClient(_app(tmp, login_redirect=LOGIN_SPA)) as c,
    ):
        client = _register_public_client(c)
        r = c.post(
            "/api/oauth/authorize",
            data={**_authorize_params(client), "decision": "approve"},
            follow_redirects=False,
        )
        assert r.status_code == 401, r.text
        assert "location" not in {k.lower() for k in r.headers}
