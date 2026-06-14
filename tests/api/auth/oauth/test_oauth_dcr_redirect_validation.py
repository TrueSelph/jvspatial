"""DCR rejects non-loopback cleartext redirect URIs (OAuth 2.1 BCP)."""

import tempfile
import uuid

import pytest

from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request
from jvspatial.api.auth.oauth.server import build_authorization_server
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database

ISSUER = "https://as.example"
RESOURCE = "https://api.example/mcp"


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as d:
        set_default_context(
            GraphContext(
                database=create_database("json", base_path=f"{d}/t_{uuid.uuid4().hex}")
            )
        )
        yield


async def _register(server, redirect_uris):
    req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/register",
        query={},
        form={},
        headers={"content-type": "application/json"},
    )
    body = {
        "client_name": "c",
        "redirect_uris": redirect_uris,
        "grant_types": ["authorization_code"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "mcp",
    }
    return await server.async_register_client(req, body)


@pytest.mark.asyncio
async def test_https_redirect_accepted(temp_context):
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    resp = await _register(server, ["https://c.example/cb"])
    assert resp.status_code in (200, 201)


@pytest.mark.asyncio
async def test_loopback_http_redirect_accepted(temp_context):
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    resp = await _register(server, ["http://127.0.0.1:8765/cb"])
    assert resp.status_code in (200, 201)


@pytest.mark.asyncio
async def test_cleartext_nonloopback_redirect_rejected(temp_context):
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    resp = await _register(server, ["http://evil.example/cb"])
    assert resp.status_code >= 400
    assert not (resp.body_json or {}).get("client_id")
