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


async def _authorize_and_token(server, client_id="cli_pub"):
    """Run authorize+token through *server*; return the token response body."""
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
            "client_id": client_id,
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
            "client_id": client_id,
            "code_verifier": verifier,
        },
        headers={},
    )
    return (await server.async_create_token_response(t)).body_json


@pytest.mark.asyncio
async def test_revoke_access_token_denylists_jti(temp_context):
    """RFC 7009 access-token path: revoke endpoint denylists the token's jti.

    Presenting a valid access token (with the owning client's auth) returns 200
    and renders the token invalid at the resource server (``verify`` -> None),
    while a DIFFERENT client's token is unaffected.
    """
    from jvspatial.api.auth.oauth.resource import verify_oauth_access_token

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
    at = (await _authorize_and_token(server))["access_token"]

    # token is valid at the RS before revocation
    assert (
        await verify_oauth_access_token(at, issuer=ISSUER, resource=RESOURCE)
        is not None
    )

    rev = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/revoke",
        query={},
        form={"token": at, "token_type_hint": "access_token", "client_id": "cli_pub"},
        headers={},
    )
    rev_resp = await server.async_revoke_token(rev)
    assert rev_resp.status_code == 200

    # token is now denylisted -> RS verification returns None
    assert await verify_oauth_access_token(at, issuer=ISSUER, resource=RESOURCE) is None


@pytest.mark.asyncio
async def test_revoke_access_token_without_hint(temp_context):
    """Access-token denylisting works even with NO token_type_hint supplied.

    The endpoint must fall back to JWT decoding when the token is not found in
    the refresh store (RFC 7009 allows omitting the hint).
    """
    from jvspatial.api.auth.oauth.resource import verify_oauth_access_token

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
    at = (await _authorize_and_token(server))["access_token"]

    rev = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/revoke",
        query={},
        form={"token": at, "client_id": "cli_pub"},  # no token_type_hint
        headers={},
    )
    rev_resp = await server.async_revoke_token(rev)
    assert rev_resp.status_code == 200
    assert await verify_oauth_access_token(at, issuer=ISSUER, resource=RESOURCE) is None


@pytest.mark.asyncio
async def test_revoke_access_token_wrong_client_rejected(temp_context):
    """A client cannot denylist an access token issued to a DIFFERENT client.

    RFC 7009 §2.1: revoke only proceeds when ``check_client`` passes. A
    mismatching ``client_id`` yields invalid_grant (400) and the token stays
    valid at the RS.
    """
    from jvspatial.api.auth.oauth.resource import verify_oauth_access_token

    await keystore.ensure_signing_key()
    for cid in ("cli_owner", "cli_attacker"):
        await OAuthClient(
            client_id=cid,
            client_secret_hash=None,
            redirect_uris=["https://c.example/cb"],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            scope="mcp",
            token_endpoint_auth_method="none",
        ).save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    at = (await _authorize_and_token(server, client_id="cli_owner"))["access_token"]

    # attacker presents the owner's token under its own client_id
    rev = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/revoke",
        query={},
        form={
            "token": at,
            "token_type_hint": "access_token",
            "client_id": "cli_attacker",
        },
        headers={},
    )
    rev_resp = await server.async_revoke_token(rev)
    # invalid_grant -> 400; the token MUST remain valid
    assert rev_resp.status_code == 400
    assert (
        await verify_oauth_access_token(at, issuer=ISSUER, resource=RESOURCE)
        is not None
    )
