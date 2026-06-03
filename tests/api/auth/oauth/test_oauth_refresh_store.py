"""OAuthRefreshToken store: mint (hashed) -> lookup by token -> revoke."""

import tempfile
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from jvspatial.api.auth.oauth import refresh_store
from jvspatial.core.context import GraphContext, set_default_context
from jvspatial.db.factory import create_database


@pytest.fixture
def temp_context():
    with tempfile.TemporaryDirectory() as tmpdir:
        database = create_database("json", base_path=f"{tmpdir}/t_{uuid.uuid4().hex}")
        context = GraphContext(database=database)
        set_default_context(context)
        yield context


@pytest.mark.asyncio
async def test_mint_lookup_revoke(temp_context):
    plaintext = await refresh_store.mint_refresh_token(
        token="rt_secret_value",
        user_id="u_1",
        client_id="cli_1",
        scope="mcp",
        resource="https://api.example/mcp",
        expires_at=datetime.now(timezone.utc) + timedelta(days=7),
    )
    assert plaintext == "rt_secret_value"

    found = await refresh_store.find_active("rt_secret_value")
    assert found is not None
    assert found.user_id == "u_1"
    assert found.client_id == "cli_1"
    assert found.is_active is True

    assert await refresh_store.find_active("nope") is None

    await refresh_store.revoke(found)
    assert await refresh_store.find_active("rt_secret_value") is None


@pytest.mark.asyncio
async def test_expired_token_not_active(temp_context):
    await refresh_store.mint_refresh_token(
        token="rt_old",
        user_id="u_1",
        client_id="cli_1",
        scope="mcp",
        resource=None,
        expires_at=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert await refresh_store.find_active("rt_old") is None
