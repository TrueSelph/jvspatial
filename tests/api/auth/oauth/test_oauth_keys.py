"""RS256 signing-key store: generate/persist/load + JWKS shape + sign/verify
roundtrip with PyJWT."""

import tempfile
import uuid

import jwt
import pytest

from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        unique_path = f"{tmpdir}/test_{uuid.uuid4().hex}"
        database = create_database("json", base_path=unique_path)
        context = GraphContext(database=database)
        set_default_context(context)
        yield context


@pytest.mark.asyncio
async def test_ensure_signing_key_idempotent(temp_context):
    k1 = await keystore.ensure_signing_key()
    assert k1.kid
    assert "BEGIN PUBLIC KEY" in k1.public_pem
    assert "BEGIN PRIVATE KEY" in k1.private_pem
    assert k1.algorithm == "RS256"
    k2 = await keystore.ensure_signing_key()
    assert k2.kid == k1.kid


@pytest.mark.asyncio
async def test_jwks_contains_active_key(temp_context):
    key = await keystore.ensure_signing_key()
    jwks = await keystore.build_jwks()
    assert "keys" in jwks and len(jwks["keys"]) >= 1
    entry = next(j for j in jwks["keys"] if j["kid"] == key.kid)
    assert entry["kty"] == "RSA"
    assert entry["alg"] == "RS256"
    assert entry["use"] == "sig"
    assert "n" in entry and "e" in entry
    assert "d" not in entry


@pytest.mark.asyncio
async def test_sign_and_verify_roundtrip(temp_context):
    key = await keystore.ensure_signing_key()
    token = jwt.encode(
        {"sub": "u_1", "aud": "https://r.example/api/mcp"},
        key.private_pem,
        algorithm="RS256",
        headers={"kid": key.kid},
    )
    decoded = jwt.decode(
        token,
        key.public_pem,
        algorithms=["RS256"],
        audience="https://r.example/api/mcp",
    )
    assert decoded["sub"] == "u_1"
