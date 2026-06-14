"""RFC 8414 AS metadata builder: required fields + validates against Authlib."""

from jvspatial.api.auth.oauth.metadata import build_as_metadata


def test_metadata_required_fields():
    md = build_as_metadata(
        issuer="https://as.example",
        prefix="/oauth",
        scopes_supported=["mcp"],
    )
    assert md["issuer"] == "https://as.example"
    assert md["authorization_endpoint"].endswith("/oauth/authorize")
    assert md["token_endpoint"].endswith("/oauth/token")
    assert md["registration_endpoint"].endswith("/oauth/register")
    assert md["revocation_endpoint"].endswith("/oauth/revoke")
    assert md["jwks_uri"].endswith("/.well-known/jwks.json")
    assert "S256" in md["code_challenge_methods_supported"]
    assert "authorization_code" in md["grant_types_supported"]
    assert "refresh_token" in md["grant_types_supported"]
    assert "code" in md["response_types_supported"]
    from authlib.oauth2.rfc8414 import AuthorizationServerMetadata

    AuthorizationServerMetadata(md).validate()


def test_metadata_with_api_prefix_includes_api_segment():
    """With api_prefix='/api' endpoints must include /api before the oauth segment."""
    md = build_as_metadata(
        issuer="https://as.example",
        prefix="/oauth",
        scopes_supported=["mcp"],
        api_prefix="/api",
    )
    assert md["token_endpoint"] == "https://as.example/api/oauth/token"
    assert md["registration_endpoint"] == "https://as.example/api/oauth/register"
    assert md["revocation_endpoint"] == "https://as.example/api/oauth/revoke"
    assert md["authorization_endpoint"] == "https://as.example/api/oauth/authorize"
    # jwks_uri stays at root — no api prefix
    assert md["jwks_uri"] == "https://as.example/.well-known/jwks.json"
    from authlib.oauth2.rfc8414 import AuthorizationServerMetadata

    AuthorizationServerMetadata(md).validate()


def test_metadata_without_api_prefix_back_compat():
    """Omitting api_prefix (default '') preserves the original /oauth/token shape."""
    md = build_as_metadata(
        issuer="https://as.example",
        prefix="/oauth",
        scopes_supported=["mcp"],
    )
    assert md["token_endpoint"] == "https://as.example/oauth/token"
    assert md["jwks_uri"] == "https://as.example/.well-known/jwks.json"
