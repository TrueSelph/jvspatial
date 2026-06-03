"""OAuth Resource-Server token verification (RS256 against the local JWKS).

AS and RS are the same jvspatial process; the verifier reads the public signing
keys via the keystore and validates iss/aud/exp/signature. Best-effort: returns
the claims dict on success, ``None`` on any failure (never raises to callers).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, cast

import jwt  # PyJWT

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
    ``resource`` (audience binding — confused-deputy mitigation), and ``exp``.
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
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
    except Exception as exc:
        logger.debug("oauth access token rejected: %s", exc)
        return None
    return claims
