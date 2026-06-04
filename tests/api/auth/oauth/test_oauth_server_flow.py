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
async def test_authcode_flow_issues_persisted_refresh_token(temp_context):
    import base64
    import hashlib
    import secrets
    from urllib.parse import parse_qs, urlparse

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
    body = (await server.async_create_token_response(t)).body_json
    assert body.get("refresh_token")
    from jvspatial.api.auth.oauth import refresh_store

    assert await refresh_store.find_active(body["refresh_token"]) is not None


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


@pytest.mark.asyncio
async def test_refresh_token_rotation_and_revocation(temp_context):
    import base64
    import hashlib
    import secrets
    from urllib.parse import parse_qs, urlparse

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
    first = (await server.async_create_token_response(t)).body_json
    rt1 = first["refresh_token"]

    t2 = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/token",
        query={},
        form={
            "grant_type": "refresh_token",
            "refresh_token": rt1,
            "client_id": "cli_pub",
        },
        headers={},
    )
    second = (await server.async_create_token_response(t2)).body_json
    assert second.get("access_token")
    rt2 = second.get("refresh_token")
    assert rt2 and rt2 != rt1  # rotated

    t3 = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/token",
        query={},
        form={
            "grant_type": "refresh_token",
            "refresh_token": rt1,
            "client_id": "cli_pub",
        },
        headers={},
    )
    resp3 = await server.async_create_token_response(t3)
    assert resp3.status_code in (400, 401)
    assert "access_token" not in (resp3.body_json or {})


@pytest.mark.asyncio
async def test_scope_intersected_with_user_permissions_and_nbf(temp_context):
    import base64
    import hashlib
    import secrets
    from urllib.parse import parse_qs, urlparse

    import jwt as pyjwt

    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code"],
        response_types=["code"],
        scope="mcp admin",
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
            "scope": "mcp admin",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        form={},
        headers={},
    )
    # user only has 'mcp' permission, not 'admin'
    r = await server.async_create_authorization_response(
        a, grant_user={"id": "u_1", "permissions": ["mcp"]}
    )
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
    body = (await server.async_create_token_response(t)).body_json
    key = await keystore.get_active_signing_key()
    decoded = pyjwt.decode(
        body["access_token"], key.public_pem, algorithms=["RS256"], audience=RESOURCE
    )
    granted = set(decoded.get("scope", "").split())
    assert "mcp" in granted and "admin" not in granted  # admin filtered (user lacks it)
    assert "nbf" in decoded


@pytest.mark.asyncio
async def test_failed_verifier_does_not_burn_code_for_retry(temp_context):
    """A wrong code_verifier must NOT consume the code; a correct retry succeeds."""
    import base64
    import hashlib
    import secrets
    from urllib.parse import parse_qs, urlparse

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

    # 1) wrong verifier -> rejected, but code NOT burned
    bad = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/token",
        query={},
        form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://c.example/cb",
            "client_id": "cli_pub",
            "code_verifier": "WRONG",
        },
        headers={},
    )
    bad_resp = await server.async_create_token_response(bad)
    assert bad_resp.status_code in (400, 401)

    # 2) correct verifier on the SAME code -> succeeds (no lockout)
    good = StarletteOAuth2Request(
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
    good_resp = await server.async_create_token_response(good)
    assert good_resp.status_code == 200
    assert good_resp.body_json.get("access_token")


@pytest.mark.asyncio
async def test_scope_unfiltered_when_no_permissions_provided(temp_context):
    """Back-compat: grant_user without 'permissions' => scope not narrowed (M1b-1 callers)."""
    import base64
    import hashlib
    import secrets
    from urllib.parse import parse_qs, urlparse

    import jwt as pyjwt

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
    body = (await server.async_create_token_response(t)).body_json
    key = await keystore.get_active_signing_key()
    decoded = pyjwt.decode(
        body["access_token"], key.public_pem, algorithms=["RS256"], audience=RESOURCE
    )
    assert "mcp" in decoded.get("scope", "")


async def _granted_scope(
    *,
    client_scope: str,
    requested_scope: str,
    grant_user: dict,
    supported_scopes=None,
) -> set:
    """Run authorize -> token and return the granted scope set from the JWT.

    Builds a fresh public PKCE client and authorization server (optionally with
    a ``supported_scopes`` ceiling), approves the request as *grant_user*, then
    exchanges the code and decodes the issued RS256 access token's ``scope``.
    """
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id="cli_pub",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code"],
        response_types=["code"],
        scope=client_scope,
        token_endpoint_auth_method="none",
    ).save()
    server = build_authorization_server(
        issuer=ISSUER, resource=RESOURCE, supported_scopes=supported_scopes
    )
    verifier, challenge = _pkce()
    a = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/authorize",
        query={
            "response_type": "code",
            "client_id": "cli_pub",
            "redirect_uri": "https://c.example/cb",
            "scope": requested_scope,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        },
        form={},
        headers={},
    )
    r = await server.async_create_authorization_response(a, grant_user=grant_user)
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
    body = (await server.async_create_token_response(t)).body_json
    key = await keystore.get_active_signing_key()
    decoded = pyjwt.decode(
        body["access_token"], key.public_pem, algorithms=["RS256"], audience=RESOURCE
    )
    return set(decoded.get("scope", "").split())


@pytest.mark.asyncio
async def test_scope_empty_permissions_grants_nothing(temp_context):
    """Footgun fix: a present-but-empty 'permissions' list narrows to nothing.

    Previously ``permissions=[]`` was collapsed to ``None`` and the full
    requested scope was granted. Now an explicit empty permission set means the
    resource owner authorizes no scopes.
    """
    granted = await _granted_scope(
        client_scope="mcp",
        requested_scope="mcp",
        grant_user={"id": "u_1", "permissions": []},
    )
    assert granted == set()


@pytest.mark.asyncio
async def test_scope_supported_ceiling(temp_context):
    """A non-empty ``supported_scopes`` ceilings the granted scope.

    The user is permitted ``mcp admin`` and requests ``mcp admin``, but the
    server only supports ``mcp`` — so ``admin`` is ceiling'd out. With no
    ceiling declared the permission-intersected scope passes through unchanged.
    """
    ceilinged = await _granted_scope(
        client_scope="mcp admin",
        requested_scope="mcp admin",
        grant_user={"id": "u_1", "permissions": ["mcp", "admin"]},
        supported_scopes=["mcp"],
    )
    assert ceilinged == {"mcp"}

    uncapped = await _granted_scope(
        client_scope="mcp admin",
        requested_scope="mcp admin",
        grant_user={"id": "u_1", "permissions": ["mcp", "admin"]},
        supported_scopes=[],
    )
    assert uncapped == {"mcp", "admin"}


@pytest.mark.asyncio
async def test_admin_wildcard_ceilinged_to_supported(temp_context):
    """Wildcard admin permission grants all requested scope, bounded by support.

    A user whose permissions are ``["*"]`` matches every requested scope (fixes
    the inverted-admin footgun where a literal ``*`` matched nothing), but the
    ``supported_scopes`` ceiling still bounds the result — so requesting
    ``mcp admin`` against supported ``["mcp"]`` yields exactly ``mcp``.
    """
    granted = await _granted_scope(
        client_scope="mcp admin",
        requested_scope="mcp admin",
        grant_user={"id": "u_1", "permissions": ["*"]},
        supported_scopes=["mcp"],
    )
    assert granted == {"mcp"}


@pytest.mark.asyncio
async def test_concurrent_code_exchange_only_one_succeeds(temp_context):
    """Two concurrent consumes of the same code: exactly one wins.

    Drives the single-use point (``_consume_code``) directly as a
    compare-and-swap. The first consume matches ``consumed=False`` and flips
    it to ``True``; the second consume of the *same* record sees the row
    already consumed, loses the CAS, and raises the same ``InvalidGrantError``
    a replayed/consumed code produces at the token endpoint — so no second
    token can ever be issued.

    Backend note: the test suite runs on the JSON adapter, whose
    ``find_one_and_update`` is the best-effort read-modify-write base path
    (not a true atomic CAS — that guarantee is for the postgres/mongo
    adapters, which issue ``SELECT ... FOR UPDATE`` / native ``findOneAndUpdate``).
    The assertion here pins the *logical* contract that holds on every
    backend: once the row reads ``consumed=True``, a second consume rejects.
    """
    from authlib.oauth2.rfc6749.errors import InvalidGrantError

    from jvspatial.api.auth.oauth.models import AuthorizationCode
    from jvspatial.api.auth.oauth.server import JvSpatialAuthCodeGrant, _sha256

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
    code = await _issue_code(server, challenge)

    # Look up the persisted, still-unconsumed code record.
    record = await JvSpatialAuthCodeGrant._find_code(_sha256(code))
    assert record is not None and record.consumed is False

    # First consume wins the CAS (consumed flips False -> True).
    await JvSpatialAuthCodeGrant._consume_code(record)
    refreshed = await AuthorizationCode.get(record.id)
    assert refreshed is not None and refreshed.consumed is True

    # Second consume of the same record loses the CAS (already consumed) and
    # rejects with the consumed-code error path — no token, no double-spend.
    with pytest.raises(InvalidGrantError):
        await JvSpatialAuthCodeGrant._consume_code(refreshed)

    # And a full token exchange after the code is consumed still rejects.
    verifier_mismatch = StarletteOAuth2Request(
        method="POST",
        uri=f"{ISSUER}/oauth/token",
        query={},
        form={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": "https://c.example/cb",
            "client_id": "cli_pub",
            "code_verifier": "anything",
        },
        headers={},
    )
    replay = await server.async_create_token_response(verifier_mismatch)
    assert replay.status_code in (400, 401)
    assert "access_token" not in (replay.body_json or {})


@pytest.mark.asyncio
async def test_full_exchange_issues_exactly_one_token_after_cas(temp_context):
    """Regression guard: the happy single exchange still issues one token.

    Confirms the CAS consume does not break the normal authorize -> token
    path: a single valid exchange returns 200 with an access token, and an
    immediate replay of the same code is rejected (single-use preserved).
    """
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
    verifier, challenge = _pkce()
    code = await _issue_code(server, challenge)

    first = await server.async_create_token_response(_token_req(code, verifier))
    assert first.status_code == 200
    assert first.body_json.get("access_token")

    replay = await server.async_create_token_response(_token_req(code, verifier))
    assert replay.status_code in (400, 401)
    assert "access_token" not in (replay.body_json or {})
