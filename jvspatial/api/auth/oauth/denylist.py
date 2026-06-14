"""Access-token ``jti`` denylist for RFC 7009 revocation.

Access tokens are stateless RS256 JWTs; once issued they remain valid until
their ``exp`` regardless of any server-side state. RFC 7009 revocation of an
access token therefore requires the AS/RS to remember which token ids have been
revoked. This module persists those ids as :class:`OAuthRevokedToken` Objects
and exposes the two operations the rest of the OAuth layer needs:

* :func:`revoke_jti` — add a ``jti`` to the denylist (idempotent).
* :func:`is_jti_revoked` — check whether a ``jti`` is currently denylisted.

Rows are **self-expiring**: each carries the revoked token's own ``exp`` as
``expires_at``. Once that moment passes the token is invalid on its ``exp``
claim anyway, so an expired denylist row is treated as not-revoked and is safe
to prune.

.. note::
    Scope is **per-token** revocation (RFC 7009 §2.1): a caller denylists a
    specific token they hold. Revoking *all* of a (user, client)'s outstanding
    tokens at once is a separate future primitive — stateless ``jti`` values
    cannot be enumerated, so mass revocation needs a per-(user, client)
    ``revoked-after`` watermark instead of a per-``jti`` row.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, cast

from jvspatial.api.auth.oauth.models import OAuthRevokedToken


def _aware(dt: datetime) -> datetime:
    """Coerce a possibly naive datetime to a UTC-aware one for comparison."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def revoke_jti(jti: str, expires_at: datetime) -> None:
    """Add *jti* to the denylist until *expires_at* (idempotent on ``jti``).

    *expires_at* should be the revoked token's own ``exp`` so the row
    self-expires alongside the token.

    Calling twice for the same ``jti`` is a no-op (no duplicate row); the
    existing row's ``expires_at`` is left as-is — both reflect the same
    underlying token's ``exp``.
    """
    if not jti:
        return
    existing = cast(
        List[OAuthRevokedToken],
        await OAuthRevokedToken.find({"context.jti": jti}),
    )
    if existing:
        return
    await OAuthRevokedToken(jti=jti, expires_at=expires_at).save()


async def is_jti_revoked(jti: str) -> bool:
    """Return ``True`` when *jti* has a non-expired denylist row.

    An expired row (``expires_at`` in the past) is treated as not-revoked: the
    token it referenced is itself expired by then, so the distinction is moot
    and the verifier rejects it on ``exp`` regardless.
    """
    if not jti:
        return False
    rows = cast(
        List[OAuthRevokedToken],
        await OAuthRevokedToken.find({"context.jti": jti}),
    )
    now = datetime.now(timezone.utc)
    return any(_aware(r.expires_at) > now for r in rows)
