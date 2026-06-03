"""RFC 8414 Authorization Server Metadata builder.

Authlib only *validates* AS metadata (``AuthorizationServerMetadata``); it does
not serve it. This builds the document; the route that serves it at
``/.well-known/oauth-authorization-server`` is wired in M1b-3b.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_as_metadata(
    *, issuer: str, prefix: str, scopes_supported: List[str]
) -> Dict[str, Any]:
    """Build the RFC 8414 AS metadata document for ``issuer``."""
    base = issuer.rstrip("/")
    p = prefix.strip("/")
    return {
        "issuer": base,
        "authorization_endpoint": f"{base}/{p}/authorize",
        "token_endpoint": f"{base}/{p}/token",
        "registration_endpoint": f"{base}/{p}/register",
        "revocation_endpoint": f"{base}/{p}/revoke",
        "jwks_uri": f"{base}/.well-known/jwks.json",
        "scopes_supported": list(scopes_supported or []),
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": [
            "none",
            "client_secret_basic",
            "client_secret_post",
        ],
    }
