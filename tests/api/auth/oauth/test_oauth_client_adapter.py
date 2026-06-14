"""ClientMixin adapter: wraps an OAuthClient so Authlib can validate it."""

from jvspatial.api.auth.oauth.client_adapter import OAuthClientAdapter
from jvspatial.api.auth.oauth.models import OAuthClient, hash_client_secret


def _client(**kw):
    base = dict(
        client_id="cli_1",
        client_secret_hash=None,
        redirect_uris=["https://c.example/cb"],
        grant_types=["authorization_code", "refresh_token"],
        response_types=["code"],
        scope="mcp read",
        token_endpoint_auth_method="none",
    )
    base.update(kw)
    return OAuthClientAdapter(OAuthClient(**base))


def test_redirect_and_grant_checks():
    a = _client()
    assert a.get_client_id() == "cli_1"
    assert a.check_redirect_uri("https://c.example/cb") is True
    assert a.check_redirect_uri("https://evil.example/cb") is False
    assert a.check_grant_type("authorization_code") is True
    assert a.check_grant_type("client_credentials") is False
    assert a.check_response_type("code") is True
    assert a.get_default_redirect_uri() == "https://c.example/cb"


def test_public_client_auth_method_and_scope_filter():
    a = _client()
    assert a.check_endpoint_auth_method("none", "token") is True
    assert a.check_endpoint_auth_method("client_secret_basic", "token") is False
    assert set(a.get_allowed_scope("mcp write read").split()) == {"mcp", "read"}


def test_confidential_secret_check():
    a = _client(
        client_secret_hash=hash_client_secret("s3cret"),
        token_endpoint_auth_method="client_secret_post",
    )
    assert a.check_client_secret("s3cret") is True
    assert a.check_client_secret("nope") is False
    assert a.check_endpoint_auth_method("client_secret_post", "token") is True
