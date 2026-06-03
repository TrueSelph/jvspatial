"""End-to-end (in-process) authorization_code + PKCE flow: build server,
register a public client + a user, run /authorize (approve) -> code, exchange
at /token -> RS256 JWT; tampered verifier is rejected."""

import base64
import hashlib
import json
import secrets
import tempfile
import uuid
from urllib.parse import parse_qs, urlparse

import jwt as pyjwt
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
    with tempfile.TemporaryDirectory() as tmpdir:
        database = create_database("json", base_path=f"{tmpdir}/t_{uuid.uuid4().hex}")
        context = GraphContext(database=database)
        set_default_context(context)
        yield context


def _pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    return verifier, challenge


@pytest.mark.asyncio
async def test_authcode_pkce_happy_path_issues_rs256_jwt(temp_context):
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
    verifier, challenge = _pkce()
    authorize_req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/authorize",
        query={
            "response_type": "code",
            "client_id": "cli_pub",
            "redirect_uri": "https://c.example/cb",
            "scope": "mcp",
            "state": "xyz",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        form={},
        headers={},
    )
    resp = await server.async_create_authorization_response(
        authorize_req, grant_user={"id": "u_1"}
    )
    assert resp.status_code in (302, 303)
    location = resp.headers["location"]
    assert location.startswith("https://c.example/cb?")
    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(location).query)["code"][0]
    assert code
    token_req = StarletteOAuth2Request(
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
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    tok_resp = await server.async_create_token_response(token_req)
    assert tok_resp.status_code == 200
    body = tok_resp.body_json
    assert body["token_type"].lower() == "bearer"
    access = body["access_token"]
    key = await keystore.get_active_signing_key()
    decoded = pyjwt.decode(
        access,
        key.public_pem,
        algorithms=["RS256"],
        audience=RESOURCE,
        options={"verify_aud": True},
    )
    assert decoded["iss"] == ISSUER
    assert decoded["sub"] == "u_1"
    assert "mcp" in decoded.get("scope", "")


@pytest.mark.asyncio
async def test_tampered_pkce_verifier_rejected(temp_context):
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code"],
        response_types=["code"],
        scope="mcp",
        token_endpoint_auth_method="none",
    ).save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    _, challenge = _pkce()
    authorize_req = StarletteOAuth2Request(
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
    resp = await server.async_create_authorization_response(
        authorize_req, grant_user={"id": "u_1"}
    )
    from urllib.parse import parse_qs, urlparse

    code = parse_qs(urlparse(resp.headers["location"]).query)["code"][0]
    token_req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/token",
        query={},
        form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://c.example/cb",
            "client_id": "cli_pub",
            "code_verifier": "WRONG-VERIFIER-VALUE-THAT-DOES-NOT-MATCH",
        },
        headers={},
    )
    tok_resp = await server.async_create_token_response(token_req)
    assert tok_resp.status_code in (400, 401)
    assert "access_token" not in (tok_resp.body_json or {})


async def _issue_code(server, challenge):
    authorize_req = StarletteOAuth2Request(
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
    resp = await server.async_create_authorization_response(
        authorize_req, grant_user={"id": "u_1"}
    )
    return parse_qs(urlparse(resp.headers["location"]).query)["code"][0]


def _token_req(code, verifier):
    return StarletteOAuth2Request(
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
        headers={"content-type": "application/x-www-form-urlencoded"},
    )


@pytest.mark.asyncio
async def test_security_self_checks(temp_context):
    key = await keystore.ensure_signing_key()
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
    verifier, challenge = _pkce()

    code = await _issue_code(server, challenge)
    tok_resp = await server.async_create_token_response(_token_req(code, verifier))
    assert tok_resp.status_code == 200
    access = tok_resp.body_json["access_token"]

    # 1) JWT header: alg == RS256, typ == at+jwt, and a kid is stamped.
    header = pyjwt.get_unverified_header(access)
    assert header["alg"] == "RS256"
    assert header.get("typ") == "at+jwt"
    assert header.get("kid") == key.kid

    # 2) Single-use code: re-exchanging the same code MUST fail (no token).
    replay = await server.async_create_token_response(_token_req(code, verifier))
    assert replay.status_code in (400, 401)
    assert "access_token" not in (replay.body_json or {})

    # 3) No client secret or private PEM leaks into any response body.
    body_str = json.dumps(tok_resp.body_json)
    assert "BEGIN PRIVATE KEY" not in body_str
    assert "client_secret" not in body_str
    assert key.private_pem.strip() not in body_str


@pytest.mark.asyncio
async def test_confidential_client_without_pkce_is_rejected(temp_context):
    """A confidential client must NOT be able to skip PKCE at authorize."""
    from jvspatial.api.auth.oauth.models import hash_client_secret

    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_conf",
        client_secret_hash=hash_client_secret("s3cret"),
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code"],
        response_types=["code"],
        scope="mcp",
        token_endpoint_auth_method="client_secret_post",
    ).save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    authorize_req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/authorize",
        query={
            "response_type": "code",
            "client_id": "cli_conf",
            "redirect_uri": "https://c.example/cb",
            "scope": "mcp",
            # NO code_challenge — must be rejected
        },
        form={},
        headers={},
    )
    resp = await server.async_create_authorization_response(
        authorize_req, grant_user={"id": "u_2"}
    )
    # Must NOT issue a code — accepted as redirect-with-error or a 400/401
    if resp.status_code in (302, 303):
        q = parse_qs(urlparse(resp.headers["location"]).query)
        assert "code" not in q, "confidential client bypassed PKCE and got a code"
        assert "error" in q
    else:
        assert resp.status_code in (400, 401)


@pytest.mark.asyncio
async def test_plain_pkce_method_is_rejected(temp_context):
    """code_challenge_method=plain must be rejected (S256 only)."""
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code"],
        response_types=["code"],
        scope="mcp",
        token_endpoint_auth_method="none",
    ).save()
    server = build_authorization_server(issuer=ISSUER, resource=RESOURCE)
    authorize_req = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/authorize",
        query={
            "response_type": "code",
            "client_id": "cli_pub",
            "redirect_uri": "https://c.example/cb",
            "scope": "mcp",
            "code_challenge": "plain-value-plain-value-plain-value-plain-value",
            "code_challenge_method": "plain",
        },
        form={},
        headers={},
    )
    resp = await server.async_create_authorization_response(
        authorize_req, grant_user={"id": "u_1"}
    )
    # Must NOT issue a code — accepted as redirect-with-error or a 400/401
    if resp.status_code in (302, 303):
        q = parse_qs(urlparse(resp.headers["location"]).query)
        assert "code" not in q, "plain PKCE method was accepted but must be rejected"
        assert "error" in q
    else:
        assert resp.status_code in (400, 401)
