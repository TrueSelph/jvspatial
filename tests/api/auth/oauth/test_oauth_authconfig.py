"""AuthConfig OAuth fields: present, correctly defaulted (all off/empty), and
overridable."""

from jvspatial.api.config_groups import AuthConfig


def test_oauth_defaults_off():
    cfg = AuthConfig()
    assert cfg.oauth_enabled is False
    assert cfg.oauth_prefix == "/oauth"
    assert cfg.oauth_supported_scopes == []
    assert cfg.oauth_dcr_enabled is True
    assert cfg.oauth_access_token_ttl_minutes == 60
    assert cfg.oauth_code_ttl_seconds == 300
    assert cfg.accept_oauth_bearer is False
    assert cfg.oauth_issuer_url == ""
    assert cfg.oauth_authorize_login_redirect == ""


def test_oauth_fields_overridable():
    cfg = AuthConfig(
        oauth_enabled=True,
        oauth_issuer_url="https://app.example.com",
        oauth_supported_scopes=["mcp"],
        accept_oauth_bearer=True,
        oauth_authorize_login_redirect="https://app.example.com/oauth/authorize",
    )
    assert cfg.oauth_enabled is True
    assert cfg.oauth_issuer_url == "https://app.example.com"
    assert cfg.oauth_supported_scopes == ["mcp"]
    assert cfg.accept_oauth_bearer is True
    assert (
        cfg.oauth_authorize_login_redirect == "https://app.example.com/oauth/authorize"
    )
