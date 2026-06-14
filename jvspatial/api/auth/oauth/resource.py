"""OAuth Resource-Server token verification (RS256 against the local JWKS).

AS and RS are the same jvspatial process; the verifier reads the public signing
keys via the keystore and validates iss/aud/exp/signature. Best-effort: returns
the claims dict on success, ``None`` on any failure (never raises to callers).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, cast

import jwt  # PyJWT

from jvspatial.api.auth.oauth.denylist import is_jti_revoked
from jvspatial.api.auth.oauth.models import OAuthSigningKey

logger = logging.getLogger(__name__)


async def _public_pem_for_kid(kid: Optional[str]) -> Optional[str]:
    rows = cast(
        List[OAuthSigningKey],
        await OAuthSigningKey.find(
            {}
        ),  # all keys (active + rotated, for verify window)
    )
    for k in rows:
        if kid is None or k.kid == kid:
            return k.public_pem
    return None


async def verify_oauth_access_token(
    token: str, *, issuer: str, resource: str
) -> Optional[Dict[str, Any]]:
    """Verify an OAuth RS256 access token; return claims or ``None``.

    Checks signature (JWKS by ``kid``), ``iss`` == issuer, ``aud`` contains
    ``resource`` (audience binding — confused-deputy mitigation), ``exp``, and
    that the token's ``jti`` is not on the revocation denylist (RFC 7009
    access-token revocation).

    ``jti`` is in the ``require`` list because every token the AS issues carries
    one (Authlib's RFC-9068 generator always stamps ``get_jti``, default
    16-char random; jvspatial does not override it). A token without a ``jti``
    is therefore not one we minted and is rejected.

    .. note:: **Hot path.** This adds one indexed denylist lookup
        (:func:`~jvspatial.api.auth.oauth.denylist.is_jti_revoked`,
        ``OAuthRevokedToken.find`` by ``jti``) to every RS validation. The
        denylist is small (only currently-unexpired revoked tokens) and the
        lookup is keyed on ``jti``. A short-TTL in-process cache of revoked
        jtis is a viable future optimization but is deliberately not built
        here — correctness first.

    .. note:: **Per-token only.** This rejects a *specific* revoked token. It
        does not implement "revoke all of a user's/client's tokens"; that
        would need a per-(user, client) ``revoked-after`` watermark since
        stateless jtis cannot be enumerated. Separate future item.
    """
    try:
        header = jwt.get_unverified_header(token)
    except Exception:
        return None
    pub = await _public_pem_for_kid(header.get("kid"))
    if not pub:
        return None
    try:
        claims = jwt.decode(
            token,
            pub,
            algorithms=["RS256"],
            audience=resource,
            issuer=issuer,
            options={"require": ["exp", "iss", "aud", "sub", "jti"]},
        )
    except Exception as exc:
        logger.debug("oauth access token rejected: %s", exc)
        return None
    # RFC 7009: reject tokens whose jti has been explicitly revoked before exp.
    if await is_jti_revoked(claims["jti"]):
        logger.debug("oauth access token rejected: jti %s denylisted", claims["jti"])
        return None
    return claims
