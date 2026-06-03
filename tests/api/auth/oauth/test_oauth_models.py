"""OAuth storage models: persistence + secret hashing. Uses the json-DB temp
context fixture (mirrors tests/core/test_entity_crud_and_cascade.py)."""

import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from jvspatial.api.auth.oauth.models import (
    AuthorizationCode,
    OAuthClient,
    hash_client_secret,
    verify_client_secret,
)
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


def test_secret_hash_roundtrip():
    secret = "s3cr3t-value"
    hashed = hash_client_secret(secret)
    assert hashed != secret
    assert verify_client_secret(secret, hashed) is True
    assert verify_client_secret("wrong", hashed) is False


@pytest.mark.asyncio
async def test_oauth_client_persist_and_find_by_client_id(temp_context):
    client = OAuthClient(
        client_id="cli_abc123",
        client_secret_hash=hash_client_secret("topsecret"),
        client_name="Claude Code",
        redirect_uris=["http://localhost:8765/callback"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp",
        token_endpoint_auth_method="none",
    )
    await client.save()
    assert client.id is not None

    found = await OAuthClient.find({"context.client_id": "cli_abc123"})
    assert len(found) == 1
    assert found[0].client_name == "Claude Code"
    assert found[0].redirect_uris == ["http://localhost:8765/callback"]
    assert found[0].token_endpoint_auth_method == "none"


@pytest.mark.asyncio
async def test_authorization_code_persist_and_consume(temp_context):
    code = AuthorizationCode(
        code_hash="deadbeef",
        client_id="cli_abc123",
        user_id="u_1",
        redirect_uri="http://localhost:8765/callback",
        code_challenge="abc",
        code_challenge_method="S256",
        scope="mcp",
        resource="https://integral.example.com/api/mcp",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    await code.save()

    found = await AuthorizationCode.find({"context.code_hash": "deadbeef"})
    assert len(found) == 1
    assert found[0].consumed is False
    assert found[0].code_challenge_method == "S256"

    found[0].consumed = True
    await found[0].save()
    reread = await AuthorizationCode.find({"context.code_hash": "deadbeef"})
    assert reread[0].consumed is True
