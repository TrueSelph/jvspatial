"""OAuth 2.1 storage entities stored as jvspatial Objects (no graph edges).

Mirrors the APIKey/RefreshToken pattern in jvspatial/api/auth/models.py.
Secrets are never stored in plaintext: client secrets are SHA-256 hashed
(256-bit secrets => SHA-256 is appropriate; constant-time compare on verify),
matching the APIKey hashing rationale.
"""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timezone
from typing import List, Optional

from pydantic import Field

from jvspatial.core.entities.object import Object


def hash_client_secret(secret: str) -> str:
    """SHA-256 hash of a client secret for storage."""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def verify_client_secret(secret: str, hashed: str) -> bool:
    """Constant-time verify of a client secret against its stored hash."""
    return hmac.compare_digest(hash_client_secret(secret), hashed)


class OAuthClient(Object):
    """A registered OAuth client (RFC 7591 dynamic registration target).

    Public clients (PKCE, no secret) use ``token_endpoint_auth_method="none"``
    and have ``client_secret_hash=None``. Confidential clients store a hash.
    """

    client_id: str = Field(..., description="Public client identifier")
    client_secret_hash: Optional[str] = Field(
        default=None,
        description="SHA-256 hash of client secret (confidential only)",
    )
    client_name: str = Field(default="", description="Human-readable client name")
    redirect_uris: List[str] = Field(
        default_factory=list,
        description="Registered redirect URIs (exact match)",
    )
    grant_types: List[str] = Field(
        default_factory=lambda: ["authorization_code", "refresh_token"],
        description="Allowed grant types",
    )
    response_types: List[str] = Field(
        default_factory=lambda: ["code"],
        description="Allowed response types",
    )
    scope: str = Field(default="", description="Space-delimited allowed scopes")
    token_endpoint_auth_method: str = Field(
        default="none",
        description="none (public/PKCE) | client_secret_post | basic",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Registration timestamp",
    )


class AuthorizationCode(Object):
    """A single-use OAuth authorization code (PKCE).

    Short-lived; consumed on token exchange.
    """

    code_hash: str = Field(..., description="SHA-256 hash of the authorization code")
    client_id: str = Field(..., description="Owning client_id")
    user_id: str = Field(..., description="Authenticated resource-owner user id")
    redirect_uri: str = Field(..., description="Redirect URI used in the request")
    code_challenge: str = Field(..., description="PKCE code challenge")
    code_challenge_method: str = Field(default="S256", description="PKCE method (S256)")
    scope: str = Field(default="", description="Granted scope (space-delimited)")
    resource: Optional[str] = Field(
        default=None,
        description="RFC 8707 resource indicator (audience)",
    )
    expires_at: datetime = Field(..., description="Expiry (short, <= 10 min)")
    consumed: bool = Field(default=False, description="True once exchanged")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )


class OAuthSigningKey(Object):
    """A persisted RS256 signing keypair.

    Active keys sign new tokens; inactive-but-recent keys remain in JWKS for the
    verification window (rotation). Private PEM is stored as-is here; production
    deployments should wrap it (env/KMS) — see plan assumptions.
    """

    kid: str = Field(..., description="Key ID (JWKS 'kid')")
    public_pem: str = Field(..., description="PEM-encoded public key")
    private_pem: str = Field(..., description="PEM-encoded private key")
    algorithm: str = Field(default="RS256", description="Signing algorithm")
    active: bool = Field(default=True, description="Whether this key signs new tokens")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )


class OAuthRevokedToken(Object):
    """A denylisted access-token ``jti`` (RFC 7009 access-token revocation).

    Access tokens are stateless RS256 JWTs that would otherwise remain valid
    until their ``exp``. This row records a single revoked token by its ``jti``
    so the Resource-Server verifier can reject it before expiry.

    Self-expiring: ``expires_at`` mirrors the token's own ``exp`` — once the
    token has naturally expired the verifier rejects it on ``exp`` anyway, so
    there is no value in retaining the denylist row past that point (a cleanup
    job may prune ``expires_at < now`` rows).

    .. note::
        This is **per-token** revocation: a holder revokes a token they
        possess. Revoking *all* of a (user, client)'s outstanding tokens at
        once is a separate, future primitive — it needs a per-(user, client)
        ``revoked-after`` watermark because stateless ``jti`` values cannot be
        enumerated. See the verifier/endpoint docstrings.
    """

    jti: str = Field(..., description="JWT ID of the revoked access token")
    expires_at: datetime = Field(
        ...,
        description="The token's own exp; row self-expires (prune after this)",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Revocation timestamp",
    )


class OAuthRefreshToken(Object):
    """An OAuth refresh token (opaque, stored hashed).

    Distinct from the session-auth ``RefreshToken`` so OAuth carries
    client/scope/resource without disturbing session auth.
    """

    token_hash: str = Field(..., description="SHA-256 hash of the refresh token")
    user_id: str = Field(..., description="Resource-owner user id")
    client_id: str = Field(..., description="Owning client_id")
    scope: str = Field(default="", description="Granted scope (space-delimited)")
    resource: Optional[str] = Field(default=None, description="Audience/resource")
    expires_at: datetime = Field(..., description="Expiry")
    is_active: bool = Field(default=True, description="False once revoked/rotated")
    family_id: str = Field(
        default="",
        description="Rotation family; shared across all rotations of one grant",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
