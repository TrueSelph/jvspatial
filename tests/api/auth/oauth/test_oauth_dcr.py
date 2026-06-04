"""DCR: a client self-registers; an OAuthClient is persisted; public (PKCE)
client gets no secret."""

import tempfile
import uuid

import pytest

from jvspatial.api.auth.oauth.models import OAuthClient
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


@pytest.mark.asyncio
async def test_dcr_registers_public_client(temp_context):
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/register",
        query={},
        form={},  # DCR body is JSON, not form — see note
        headers={"content-type": "application/json"},
    )
    # JSON body carried explicitly for the registration endpoint:
    body = {
        "client_name": "Claude Code",
        "redirect_uris": ["https://c.example/cb"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "mcp",
    }
    resp = await server.async_register_client(req, body)
    assert resp.status_code in (200, 201)
    out = resp.body_json
    assert out["client_id"]
    assert out.get("token_endpoint_auth_method") == "none"
    # persisted
    rows = await OAuthClient.find({"context.client_id": out["client_id"]})
    assert len(rows) == 1
    assert rows[0].redirect_uris == ["https://c.example/cb"]
    # public client: no secret returned/stored
    assert not out.get("client_secret")
    assert rows[0].client_secret_hash is None


@pytest.mark.asyncio
async def test_dcr_filters_requested_scope_against_supported(temp_context):
    """A client requesting an unsupported scope has it silently dropped.

    With ``supported_scopes=["mcp"]`` declared on the AS, a registration body
    asking for ``"mcp admin"`` is filtered down to ``"mcp"`` (defense-in-depth:
    a client cannot self-register an elevated scope the AS does not support).
    RFC 7591 permits the AS to filter rather than reject.
    """
    server = build_authorization_server(
        issuer=ISSUER, resource=RESOURCE, supported_scopes=["mcp"]
    )
    req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/register",
        query={},
        form={},
        headers={"content-type": "application/json"},
    )
    body = {
        "client_name": "Greedy Client",
        "redirect_uris": ["https://c.example/cb"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "mcp admin",
    }
    resp = await server.async_register_client(req, body)
    assert resp.status_code in (200, 201)
    out = resp.body_json
    # "admin" is dropped; only the supported "mcp" survives.
    assert out.get("scope") == "mcp"
    rows = await OAuthClient.find({"context.client_id": out["client_id"]})
    assert len(rows) == 1
    assert rows[0].scope == "mcp"


@pytest.mark.asyncio
async def test_dcr_no_supported_scopes_keeps_requested_verbatim(temp_context):
    """Back-compat: with no supported-scope ceiling, the request is verbatim.

    An AS built without ``supported_scopes`` (the default) declares no ceiling,
    so a requested ``"mcp admin"`` is persisted and returned unchanged — no
    behaviour change for callers that do not constrain supported scopes.
    """
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/register",
        query={},
        form={},
        headers={"content-type": "application/json"},
    )
    body = {
        "client_name": "Unconstrained Client",
        "redirect_uris": ["https://c.example/cb"],
        "grant_types": ["authorization_code", "refresh_token"],
        "response_types": ["code"],
        "token_endpoint_auth_method": "none",
        "scope": "mcp admin",
    }
    resp = await server.async_register_client(req, body)
    assert resp.status_code in (200, 201)
    out = resp.body_json
    assert out.get("scope") == "mcp admin"
    rows = await OAuthClient.find({"context.client_id": out["client_id"]})
    assert len(rows) == 1
    assert rows[0].scope == "mcp admin"
