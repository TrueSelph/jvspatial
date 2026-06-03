"""RFC 7009 revocation: revoking a refresh token makes it unusable."""

import base64
import hashlib
import secrets
import tempfile
import uuid
from urllib.parse import parse_qs, urlparse

import pytest

from jvspatial.api.auth.oauth import keys as keystore
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
async def test_revoke_refresh_token(temp_context):
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp",
        token_endpoint_auth_method="none",
    ).save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    a = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/authorize",
        query={
            "response_type": "code",
            "client_id": "cli_pub",
            "redirect_uri": "https://c.example/cb",
            "scope": "mcp",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        form={},
        headers={},
    )
    code = parse_qs(
        urlparse(
            (
                await server.async_create_authorization_response(
                    a, grant_user={"id": "u_1"}
                )
            ).headers["location"]
        ).query
    )["code"][0]
    t = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/token",
        query={},
        form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://c.example/cb",
            "client_id": "cli_pub",
            "code_verifier": verifier,
        },
        headers={},
    )
    rt = (await server.async_create_token_response(t)).body_json["refresh_token"]

    rev = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/revoke",
        query={},
        form={"token": rt, "token_type_hint": "refresh_token", "client_id": "cli_pub"},
        headers={},
    )
    rev_resp = await server.async_revoke_token(rev)
    assert rev_resp.status_code == 200

    # revoked refresh can't be exchanged
    use = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/token",
        query={},
        form={
            "grant_type": "refresh_token",
            "refresh_token": rt,
            "client_id": "cli_pub",
        },
        headers={},
    )
    used = await server.async_create_token_response(use)
    assert used.status_code in (400, 401)
