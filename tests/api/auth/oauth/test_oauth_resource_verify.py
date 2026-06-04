"""RS verifier: accepts a valid AS-issued token; rejects wrong-aud/expired/bad-sig/wrong-iss.

Also covers the ``jti`` denylist (RFC 7009 access-token revocation): a token that
has been denylisted via :func:`~jvspatial.api.auth.oauth.denylist.revoke_jti`
verifies as ``None`` even though its signature/claims are otherwise valid.
"""

import base64
import hashlib
import secrets
import tempfile
import time
import uuid
from urllib.parse import parse_qs, urlparse

import jwt as pyjwt
import pytest

from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.api.auth.oauth.denylist import revoke_jti
from jvspatial.api.auth.oauth.models import OAuthClient
from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request
from jvspatial.api.auth.oauth.resource import verify_oauth_access_token
from jvspatial.api.auth.oauth.server import build_authorization_server
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database

ISSUER = "https://as.example"
RESOURCE = "https://as.example"


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as d:
        set_default_context(
            GraphContext(
                database=create_database("json", base_path=f"{d}/t_{uuid.uuid4().hex}")
            )
        )
        yield


async def _mint(claims):
    key = await keystore.ensure_signing_key()
    base = {
        "iss": ISSUER,
        "aud": RESOURCE,
        "sub": "u_1",
        "scope": "mcp",
        "iat": int(time.time()),
        "exp": int(time.time()) + 300,
        "jti": uuid.uuid4().hex,
    }
    base.update(claims)
    return pyjwt.encode(
        base, key.private_pem, algorithm="RS256", headers={"kid": key.kid}
    )


@pytest.mark.asyncio
async def test_valid_token_accepted(temp_context):
    tok = await _mint({})
    claims = await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE)
    assert claims is not None and claims["sub"] == "u_1" and "mcp" in claims["scope"]


@pytest.mark.asyncio
async def test_wrong_audience_rejected(temp_context):
    tok = await _mint({"aud": "https://other.example"})
    assert (
        await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE) is None
    )


@pytest.mark.asyncio
async def test_expired_rejected(temp_context):
    tok = await _mint({"exp": int(time.time()) - 10})
    assert (
        await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE) is None
    )


@pytest.mark.asyncio
async def test_wrong_issuer_rejected(temp_context):
    tok = await _mint({"iss": "https://evil.example"})
    assert (
        await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE) is None
    )


@pytest.mark.asyncio
async def test_bad_signature_rejected(temp_context):
    await keystore.ensure_signing_key()
    # token signed by a DIFFERENT key
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    pk = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = pk.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    import time as _t

    forged = pyjwt.encode(
        {
            "iss": ISSUER,
            "aud": RESOURCE,
            "sub": "u_x",
            "scope": "mcp",
            "exp": int(_t.time()) + 300,
        },
        pem,
        algorithm="RS256",
        headers={"kid": "nope"},
    )
    assert (
        await verify_oauth_access_token(forged, issuer=ISSUER, resource=RESOURCE)
        is None
    )


# --- jti denylist (RFC 7009 access-token revocation) -----------------------


async def _mint_via_flow(client_id: str = "cli_pub") -> str:
    """Mint an access token through the real authorization-code + token flow.

    Returns the plaintext ``access_token``. This exercises
    :class:`~jvspatial.api.auth.oauth.server.JvSpatialJWTTokenGenerator` so the
    token carries whatever claims the generator stamps (notably ``jti``).
    """
    await keystore.ensure_signing_key()
    await OAuthClient(
        client_id=client_id,
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
    return (await server.async_create_token_response(t)).body_json["access_token"]


@pytest.mark.asyncio
async def test_issued_token_carries_jti(temp_context):
    """Gates the ``require=["jti"]`` change: every issued token MUST carry jti.

    Decode a token minted by the real flow (no signature verification needed
    for this assertion) and confirm the ``jti`` claim is present and non-empty.
    """
    tok = await _mint_via_flow()
    claims = pyjwt.decode(tok, options={"verify_signature": False})
    assert claims.get("jti"), "issued access token is missing a jti claim"
    # client_id is also present (used by the revoke endpoint's check_client).
    assert claims.get("client_id") == "cli_pub"


@pytest.mark.asyncio
async def test_denylisted_token_rejected(temp_context):
    """A valid token verifies; after ``revoke_jti`` it verifies as ``None``."""
    tok = await _mint_via_flow()
    claims = await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE)
    assert claims is not None
    jti = claims["jti"]

    # denylist this token's jti until its own exp (self-expiring row)
    from datetime import datetime, timezone

    exp = datetime.fromtimestamp(claims["exp"], tz=timezone.utc)
    await revoke_jti(jti, exp)

    assert (
        await verify_oauth_access_token(tok, issuer=ISSUER, resource=RESOURCE) is None
    )


@pytest.mark.asyncio
async def test_other_token_unaffected_by_denylist(temp_context):
    """Denylisting one token's jti does not reject a different token."""
    tok_a = await _mint_via_flow(client_id="cli_a")
    tok_b = await _mint_via_flow(client_id="cli_b")
    claims_a = await verify_oauth_access_token(tok_a, issuer=ISSUER, resource=RESOURCE)
    assert claims_a is not None

    from datetime import datetime, timezone

    exp = datetime.fromtimestamp(claims_a["exp"], tz=timezone.utc)
    await revoke_jti(claims_a["jti"], exp)

    # the OTHER token is still valid
    assert (
        await verify_oauth_access_token(tok_b, issuer=ISSUER, resource=RESOURCE)
        is not None
    )


@pytest.mark.asyncio
async def test_revoke_jti_idempotent(temp_context):
    """Calling ``revoke_jti`` twice for the same jti does not error or duplicate."""
    from datetime import datetime, timedelta, timezone

    from jvspatial.api.auth.oauth.denylist import is_jti_revoked
    from jvspatial.api.auth.oauth.models import OAuthRevokedToken

    jti = uuid.uuid4().hex
    exp = datetime.now(timezone.utc) + timedelta(minutes=5)
    await revoke_jti(jti, exp)
    await revoke_jti(jti, exp)
    assert await is_jti_revoked(jti) is True
    rows = await OAuthRevokedToken.find({"context.jti": jti})
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_expired_denylist_row_not_revoked(temp_context):
    """A denylist row whose expiry has passed is treated as not-revoked."""
    from datetime import datetime, timedelta, timezone

    from jvspatial.api.auth.oauth.denylist import is_jti_revoked

    jti = uuid.uuid4().hex
    past = datetime.now(timezone.utc) - timedelta(seconds=10)
    await revoke_jti(jti, past)
    assert await is_jti_revoked(jti) is False
