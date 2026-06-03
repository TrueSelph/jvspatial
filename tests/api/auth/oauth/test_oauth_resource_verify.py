"""RS verifier: accepts a valid AS-issued token; rejects wrong-aud/expired/bad-sig/wrong-iss."""

import tempfile
import time
import uuid

import jwt as pyjwt
import pytest

from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.api.auth.oauth.resource import verify_oauth_access_token
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
