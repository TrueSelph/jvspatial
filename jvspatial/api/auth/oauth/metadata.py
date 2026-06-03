"""RFC 8414 Authorization Server Metadata builder.

Authlib only *validates* AS metadata (``AuthorizationServerMetadata``); it does
not serve it. This builds the document; the route that serves it at
``/.well-known/oauth-authorization-server`` is wired in M1b-3b.
"""

from __future__ import annotations

from typing import Any, Dict, List


def build_as_metadata(
    *,
    issuer: str,
    prefix: str,
    scopes_supported: List[str],
    api_prefix: str = "",
) -> Dict[str, Any]:
    """Build the RFC 8414 AS metadata document for ``issuer``.

    Args:
        issuer: The authorization server issuer URL (no trailing slash).
        prefix: The OAuth route prefix (e.g. ``/oauth``).  OAuth endpoints
            are mounted relative to this within the API prefix.
        scopes_supported: List of supported OAuth scope strings.
        api_prefix: The API mount prefix (e.g. ``/api``).  When non-empty,
            OAuth endpoints are advertised as
            ``{issuer}/{api_prefix}/{prefix}/…``.  Defaults to ``""`` for
            back-compat (``{issuer}/{prefix}/…``).  ``jwks_uri`` and the
            metadata document itself are always served at the root — no API
            prefix is applied to them.
    """
    base = issuer.rstrip("/")
    p = prefix.strip("/")
    api = ("/" + api_prefix.strip("/")) if api_prefix.strip("/") else ""
    ep_base = f"{base}{api}/{p}"
    return {
        "issuer": base,
        "authorization_endpoint": f"{ep_base}/authorize",
        "token_endpoint": f"{ep_base}/token",
        "registration_endpoint": f"{ep_base}/register",
        "revocation_endpoint": f"{ep_base}/revoke",
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
