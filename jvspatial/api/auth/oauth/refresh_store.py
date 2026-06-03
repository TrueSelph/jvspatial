"""Async persistence for OAuth refresh tokens (opaque, stored SHA-256 hashed)."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import List, Optional, cast

from jvspatial.api.auth.oauth.models import OAuthRefreshToken


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


async def mint_refresh_token(
    *,
    token: str,
    user_id: str,
    client_id: str,
    scope: str,
    resource: Optional[str],
    expires_at: datetime,
) -> str:
    """Persist a refresh token (hashed); return the plaintext for the caller to emit."""
    rec = OAuthRefreshToken(
        token_hash=_hash(token),
        user_id=user_id,
        client_id=client_id,
        scope=scope or "",
        resource=resource,
        expires_at=expires_at,
        is_active=True,
    )
    await rec.save()
    return token


async def find_active(token: str) -> Optional[OAuthRefreshToken]:
    """Return the active, unexpired record for ``token``, else ``None``."""
    rows = cast(
        List[OAuthRefreshToken],
        await OAuthRefreshToken.find(
            {"context.token_hash": _hash(token), "context.is_active": True}
        ),
    )
    if not rows:
        return None
    rec = rows[0]
    exp = rec.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        return None
    return rec


async def revoke(rec: OAuthRefreshToken) -> None:
    """Mark a refresh token inactive (revocation / rotation)."""
    rec.is_active = False
    await rec.save()
