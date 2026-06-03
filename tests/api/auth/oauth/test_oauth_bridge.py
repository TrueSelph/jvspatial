"""anyio bridge: a sync function run in a worker thread can call back into
async code; and the Starlette OAuth2Request wrapper exposes args/form dicts."""

import pytest

from jvspatial.api.auth.oauth.bridge import call_async, run_sync_with_async_bridge
from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request


@pytest.mark.asyncio
async def test_bridge_runs_sync_that_calls_async():
    async def _async_double(x):
        return x * 2

    def _sync_work():
        return call_async(_async_double, 21)

    result = await run_sync_with_async_bridge(_sync_work)
    assert result == 42


def test_oauth2_request_wrapper_exposes_args_and_form():
    req = StarletteOAuth2Request(
        method="POST",
        uri="https://as.example/oauth/token?x=1",
        query={"x": "1"},
        form={"grant_type": "authorization_code", "code": "abc"},
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert req.args == {"x": "1"}
    assert req.form["grant_type"] == "authorization_code"
    assert req.form["code"] == "abc"
