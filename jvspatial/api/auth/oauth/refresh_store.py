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
    family_id: str = "",
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
        family_id=family_id,
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


async def find_any(token: str) -> Optional[OAuthRefreshToken]:
    """Return any record for ``token`` regardless of ``is_active`` or expiry.

    Used by reuse detection: a revoked token that is replayed will not appear
    in ``find_active`` but will appear here, revealing the family_id so the
    entire family can be killed.
    """
    rows = cast(
        List[OAuthRefreshToken],
        await OAuthRefreshToken.find({"context.token_hash": _hash(token)}),
    )
    return rows[0] if rows else None


async def revoke_family(family_id: str) -> int:
    """Revoke all tokens that share ``family_id`` (reuse-detection kill-switch).

    Returns the count of records deactivated.
    """
    if not family_id:
        return 0
    rows = cast(
        List[OAuthRefreshToken],
        await OAuthRefreshToken.find({"context.family_id": family_id}),
    )
    count = 0
    for rec in rows:
        if rec.is_active:
            rec.is_active = False
            await rec.save()
            count += 1
    return count


async def revoke(rec: OAuthRefreshToken) -> None:
    """Mark a refresh token inactive (revocation / rotation)."""
    rec.is_active = False
    await rec.save()
