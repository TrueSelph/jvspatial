"""RS256 signing-key store: generate/persist/load + JWKS shape + sign/verify
roundtrip with PyJWT."""

import tempfile
import uuid

import jwt
import pytest
from cryptography.fernet import Fernet

from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.api.auth.oauth.models import OAuthSigningKey
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


@pytest.mark.asyncio
async def test_signing_key_encrypted_at_rest(temp_context, monkeypatch):
    monkeypatch.setenv(
        "JVSPATIAL_OAUTH_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    key = await keystore.ensure_signing_key()
    stored = (await OAuthSigningKey.find({}))[0]
    assert stored.private_pem.startswith("fernet:v1:")
    assert "BEGIN PRIVATE KEY" not in stored.private_pem
    assert "BEGIN PRIVATE KEY" in key.private_pem
    assert (await keystore.ensure_signing_key()).private_pem == key.private_pem
    await key.save()
    assert (await OAuthSigningKey.find({}))[0].private_pem.startswith("fernet:v1:")
    assert "private_pem" not in str(await keystore.build_jwks())


@pytest.mark.asyncio
async def test_existing_key_migrates_and_wrong_key_fails_closed(
    temp_context, monkeypatch
):
    monkeypatch.delenv("JVSPATIAL_OAUTH_KEY_ENCRYPTION_KEY", raising=False)
    original = await keystore.ensure_signing_key()
    monkeypatch.setenv(
        "JVSPATIAL_OAUTH_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    migrated = await keystore.ensure_signing_key()
    assert migrated.private_pem == original.private_pem
    assert (await OAuthSigningKey.find({}))[0].private_pem.startswith("fernet:v1:")
    monkeypatch.setenv(
        "JVSPATIAL_OAUTH_KEY_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    with pytest.raises(RuntimeError, match="decryption failed"):
        await keystore.ensure_signing_key()
    monkeypatch.delenv("JVSPATIAL_OAUTH_KEY_ENCRYPTION_KEY")
    with pytest.raises(RuntimeError, match="required"):
        await keystore.ensure_signing_key()
