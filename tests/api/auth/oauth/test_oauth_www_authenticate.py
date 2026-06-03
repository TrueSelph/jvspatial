"""RFC 9728 §5.1: 401 responses from a resource server with ``accept_oauth_bearer=True``
must carry ``WWW-Authenticate: Bearer resource_metadata="…"`` so MCP clients can
auto-discover the Authorization Server without out-of-band configuration.

Tests:
  - No Authorization header → 401 with ``WWW-Authenticate`` header (RS bearer on).
  - Invalid/garbage bearer → 401 with ``WWW-Authenticate`` header (RS bearer on).
  - ``accept_oauth_bearer=False`` → 401 without ``WWW-Authenticate`` header.
"""

import tempfile
import uuid

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from jvspatial.api import endpoint
from jvspatial.api.context import set_current_server
from jvspatial.api.server import Server

ISSUER = "https://as.example"
EXPECTED_RESOURCE_METADATA_URL = f"{ISSUER}/.well-known/oauth-protected-resource"
EXPECTED_HEADER_PREFIX = "Bearer "
EXPECTED_HEADER_FRAGMENT = f'resource_metadata="{EXPECTED_RESOURCE_METADATA_URL}"'


@pytest.fixture(autouse=True)
def _allow_insecure_transport(monkeypatch):
    """TestClient uses http://testserver; Authlib requires HTTPS unless gated."""
    monkeypatch.setenv("AUTHLIB_INSECURE_TRANSPORT", "1")


def _make_server(tmp, *, accept_oauth_bearer: bool) -> Server:
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


def _register_whoami2(server: Server) -> None:
    """Register a trivial auth=True route for the 401 surface under test."""

    @endpoint("/whoami2", methods=["GET"], auth=True)
    async def whoami2(request: Request):
        user = request.state.user
        return {"id": getattr(user, "id", None)}

    server.app = None  # force app rebuild to include the new endpoint


# ---------------------------------------------------------------------------
# accept_oauth_bearer=True — header MUST be present on 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_no_bearer_emits_www_authenticate():
    """No Authorization header → 401 with RFC 9728 WWW-Authenticate header."""
    with tempfile.TemporaryDirectory() as tmp:
        server = _make_server(tmp, accept_oauth_bearer=True)
        set_current_server(server)
        _register_whoami2(server)
        with TestClient(server.get_app()) as client:
            r = client.get("/api/whoami2")  # no Authorization header at all
            assert r.status_code == 401, r.text
            www_auth = r.headers.get("www-authenticate", "")
            assert www_auth.startswith(
                EXPECTED_HEADER_PREFIX
            ), f"Expected 'Bearer …' challenge, got: {www_auth!r}"
            assert (
                EXPECTED_HEADER_FRAGMENT in www_auth
            ), f"Expected resource_metadata fragment, got: {www_auth!r}"


@pytest.mark.asyncio
async def test_401_invalid_bearer_emits_www_authenticate():
    """Garbage bearer token → 401 with RFC 9728 WWW-Authenticate header."""
    with tempfile.TemporaryDirectory() as tmp:
        server = _make_server(tmp, accept_oauth_bearer=True)
        set_current_server(server)
        _register_whoami2(server)
        with TestClient(server.get_app()) as client:
            r = client.get(
                "/api/whoami2",
                headers={"Authorization": "Bearer not.a.valid.token"},
            )
            assert r.status_code == 401, r.text
            www_auth = r.headers.get("www-authenticate", "")
            assert www_auth.startswith(
                EXPECTED_HEADER_PREFIX
            ), f"Expected 'Bearer …' challenge, got: {www_auth!r}"
            assert (
                EXPECTED_HEADER_FRAGMENT in www_auth
            ), f"Expected resource_metadata fragment, got: {www_auth!r}"


# ---------------------------------------------------------------------------
# accept_oauth_bearer=False — header must NOT be present on 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_401_no_www_authenticate_when_bearer_off():
    """With accept_oauth_bearer=False, 401 must NOT carry WWW-Authenticate."""
    with tempfile.TemporaryDirectory() as tmp:
        server = _make_server(tmp, accept_oauth_bearer=False)
        set_current_server(server)
        _register_whoami2(server)
        with TestClient(server.get_app()) as client:
            r = client.get("/api/whoami2")  # no Authorization header
            assert r.status_code == 401, r.text
            www_auth = r.headers.get("www-authenticate", "")
            assert (
                www_auth == ""
            ), f"Expected no WWW-Authenticate when bearer off, got: {www_auth!r}"
