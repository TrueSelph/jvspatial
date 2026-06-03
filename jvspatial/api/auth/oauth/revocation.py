"""Token revocation endpoint (RFC 7009).

Implements :class:`JvSpatialRevocationEndpoint`, a subclass of Authlib's
:class:`~authlib.oauth2.rfc7009.RevocationEndpoint`, wired into
:class:`~jvspatial.api.auth.oauth.server.JvSpatialAuthorizationServer` via
:func:`~jvspatial.api.auth.oauth.server.build_authorization_server`.

**Refresh-token revocation only** — access tokens are stateless RS256 JWTs; a
denial/denylist for them is out of scope for this phase.  Revoking a refresh
token is the meaningful operation: the client can no longer use it to obtain
new access tokens.

**Public client auth** — the default :class:`~authlib.oauth2.rfc6749.TokenEndpoint`
``CLIENT_AUTH_METHODS`` list is ``["client_secret_basic"]``, which would reject
public clients (``token_endpoint_auth_method="none"``).  We override it to
``["none", "client_secret_basic", "client_secret_post"]`` so public PKCE
clients can revoke their own tokens by supplying only ``client_id`` in the
form body (per RFC 7009 §2.1, which defers to the token-endpoint auth rules).
The ``authenticate_none`` method in authlib reads ``client_id`` from
``request.payload.client_id``; :meth:`~jvspatial.api.auth.oauth.server.JvSpatialAuthorizationServer.create_oauth2_request`
populates ``request.payload`` from the combined ``args`` + ``form`` dict, so
this works correctly without any extra wiring.

**``query_token`` signature** — installed authlib 1.7.2 defines
``query_token(self, token_string, token_type_hint)`` (verified against
``.venv/lib/python3.11/site-packages/authlib/oauth2/rfc7009/revocation.py``).
"""

from __future__ import annotations

from typing import Any, Optional

from authlib.oauth2.rfc7009 import RevocationEndpoint

from jvspatial.api.auth.oauth import refresh_store
from jvspatial.api.auth.oauth.bridge import call_async


class _RevocableToken:
    """Minimal adapter exposing ``check_client`` to authlib's revocation flow.

    Authlib's :meth:`~authlib.oauth2.rfc7009.RevocationEndpoint.authenticate_token`
    calls ``token.check_client(client)`` on the value returned by
    :meth:`~JvSpatialRevocationEndpoint.query_token` to ensure the token
    belongs to the presenting client.  ``OAuthRefreshToken`` is a plain
    Pydantic model without that method, so we wrap it here.
    """

    def __init__(self, rec: Any) -> None:
        """Wrap the persisted ``OAuthRefreshToken`` record."""
        self.record = rec

    def check_client(self, client: Any) -> bool:
        """Return ``True`` when ``record.client_id`` matches the authenticated client."""
        return self.record.client_id == client.get_client_id()


class JvSpatialRevocationEndpoint(RevocationEndpoint):
    """RFC 7009 revocation endpoint backed by jvspatial refresh-token storage.

    The two required hooks:

    * :meth:`query_token` — find the ``OAuthRefreshToken`` record for the
      presented token string (or ``None`` if unknown).
    * :meth:`revoke_token` — mark the record inactive via
      :func:`~jvspatial.api.auth.oauth.refresh_store.revoke`.

    **Access tokens are out of scope.** This endpoint only handles refresh
    tokens stored in the ``OAuthRefreshToken`` Object store. Revoking a
    stateless JWT access token would require a denylist (e.g. Redis-backed
    ``jti`` blocklist) — planned for a future phase.
    """

    #: Allow public clients (``token_endpoint_auth_method="none"``) to revoke
    #: their own tokens by supplying only ``client_id`` in the form body.
    #: Confidential clients may also use ``client_secret_basic`` or
    #: ``client_secret_post`` as usual.
    CLIENT_AUTH_METHODS = ["none", "client_secret_basic", "client_secret_post"]

    def query_token(self, token_string: str, token_type_hint: Optional[str]) -> Any:
        """Look up the ``OAuthRefreshToken`` record for *token_string*.

        Uses :func:`~jvspatial.api.auth.oauth.refresh_store.find_any` (no
        ``is_active`` filter) so that an already-revoked token is still
        found and validated against its owning client before being silently
        accepted per RFC 7009 §2.2 ("the server responds with HTTP 200").

        Access tokens (stateless JWTs) are not stored, so they return
        ``None``; per RFC 7009 §2.2 the server MUST respond 200 even when
        the token is unknown, so ``None`` here is safe.

        Args:
            token_string: The plaintext token value from the ``token`` form
                parameter.
            token_type_hint: Optional hint (``"refresh_token"`` /
                ``"access_token"``).  Not used for dispatch because we have
                only one storage backend (refresh tokens only).

        Returns:
            A :class:`_RevocableToken` wrapping the persisted
            :class:`~jvspatial.api.auth.oauth.models.OAuthRefreshToken` record,
            or ``None`` if not found.  The wrapper exposes ``check_client`` as
            required by Authlib's :meth:`authenticate_token`.
        """
        rec = call_async(refresh_store.find_any, token_string)
        return _RevocableToken(rec) if rec is not None else None

    def revoke_token(self, token: Any, request: Any) -> None:
        """Mark the ``OAuthRefreshToken`` *token* record as inactive.

        *token* is the :class:`~jvspatial.api.auth.oauth.models.OAuthRefreshToken`
        record returned by :meth:`query_token` — NOT a string.  Authlib's
        base :meth:`~authlib.oauth2.rfc7009.RevocationEndpoint.create_endpoint_response`
        calls :meth:`query_token` first and passes the result directly here.

        Args:
            token: A :class:`_RevocableToken` wrapping the persisted
                ``OAuthRefreshToken`` record (as returned by
                :meth:`query_token`).
            request: The Authlib OAuth2 request (not used; included for
                signature compatibility).
        """
        call_async(refresh_store.revoke, token.record)
