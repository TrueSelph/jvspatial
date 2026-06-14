"""OAuth 2.1 refresh reuse detection: replaying a rotated (revoked) refresh
token revokes the whole family, killing the attacker-or-victim live token."""

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


async def _issue_first_refresh(server):
    await OAuthClient(
        client_id="cli_pub",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp",
        token_endpoint_auth_method="none",
    ).save()
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
    r = await server.async_create_authorization_response(a, grant_user={"id": "u_1"})
    code = parse_qs(urlparse(r.headers["location"]).query)["code"][0]
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
    return (await server.async_create_token_response(t)).body_json["refresh_token"]


def _refresh_req(rt):
    return StarletteOAuth2Request(
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


@pytest.mark.asyncio
async def test_replay_of_rotated_token_revokes_family(temp_context):
    await keystore.ensure_signing_key()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    rt1 = await _issue_first_refresh(server)
    rt2 = (await server.async_create_token_response(_refresh_req(rt1))).body_json[
        "refresh_token"
    ]
    assert rt2 and rt2 != rt1
    # attacker replays the rotated rt1 -> rejected AND family killed
    replay = await server.async_create_token_response(_refresh_req(rt1))
    assert replay.status_code in (400, 401)
    # rt2 (same family) is now dead too
    after = await server.async_create_token_response(_refresh_req(rt2))
    assert after.status_code in (400, 401)
    assert "access_token" not in (after.body_json or {})
