"""Token revocation endpoint (RFC 7009).

Implements :class:`JvSpatialRevocationEndpoint`, a subclass of Authlib's
:class:`~authlib.oauth2.rfc7009.RevocationEndpoint`, wired into
:class:`~jvspatial.api.auth.oauth.server.JvSpatialAuthorizationServer` via
:func:`~jvspatial.api.auth.oauth.server.build_authorization_server`.

Handles **both** token types:

* **Refresh tokens** — opaque, stored hashed as ``OAuthRefreshToken``.
  Revoking marks the record inactive so it can no longer be exchanged.
* **Access tokens** — stateless RS256 JWTs. They cannot be "deleted"; instead
  the token's ``jti`` is added to the :mod:`~jvspatial.api.auth.oauth.denylist`
  so the Resource-Server verifier rejects it before its natural ``exp``.

**Per-token revocation (RFC 7009 §2.1).** The caller must *present* the token
they want revoked and authenticate as its owning client. Both conditions are
enforced before anything is denylisted (see :meth:`authenticate_token` →
``check_client``), so a caller can only revoke a token they actually hold —
there is no "denylist an arbitrary jti" DoS surface. Mass revocation of *all*
of a (user, client)'s tokens at once is a separate future primitive (it needs a
per-(user, client) ``revoked-after`` watermark; stateless jtis can't be
enumerated) and is intentionally **not** implemented here.

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

from datetime import datetime, timezone
from typing import Any, Optional

from authlib.oauth2.rfc7009 import RevocationEndpoint

from jvspatial.api.auth.oauth import denylist, refresh_store
from jvspatial.api.auth.oauth.bridge import call_async
from jvspatial.api.auth.oauth.resource import verify_oauth_access_token


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


class _RevocableAccessToken:
    """Adapter over the validated claims of a JWT access token.

    Returned by :meth:`~JvSpatialRevocationEndpoint.query_token` when the
    presented token is a JWT access token rather than a stored refresh token.
    Carries the ``jti`` and ``exp`` needed to denylist it and the ``client_id``
    claim used to enforce RFC 7009's "issued to this client" check.
    """

    def __init__(self, claims: dict) -> None:
        """Wrap verified JWT *claims* (``jti``, ``exp``, ``client_id``)."""
        self.claims = claims

    def check_client(self, client: Any) -> bool:
        """Return ``True`` when the token's ``client_id`` claim matches *client*.

        RFC 9068 access tokens carry the issuing ``client_id`` claim, so a
        caller can only revoke a token that was issued to the client they have
        authenticated as.
        """
        return self.claims.get("client_id") == client.get_client_id()


class JvSpatialRevocationEndpoint(RevocationEndpoint):
    """RFC 7009 revocation endpoint backed by jvspatial token storage.

    The two required hooks:

    * :meth:`query_token` — resolve the presented token to a revocable object:
      an ``OAuthRefreshToken`` record (refresh tokens) or a
      :class:`_RevocableAccessToken` (validated JWT access tokens).
    * :meth:`revoke_token` — mark a refresh record inactive via
      :func:`~jvspatial.api.auth.oauth.refresh_store.revoke`, or denylist a JWT
      access token's ``jti`` via
      :func:`~jvspatial.api.auth.oauth.denylist.revoke_jti`.
    """

    #: Allow public clients (``token_endpoint_auth_method="none"``) to revoke
    #: their own tokens by supplying only ``client_id`` in the form body.
    #: Confidential clients may also use ``client_secret_basic`` or
    #: ``client_secret_post`` as usual.
    CLIENT_AUTH_METHODS = ["none", "client_secret_basic", "client_secret_post"]

    def query_token(self, token_string: str, token_type_hint: Optional[str]) -> Any:
        """Resolve *token_string* to a revocable token object (or ``None``).

        Resolution order:

        1. **Refresh token** — :func:`~jvspatial.api.auth.oauth.refresh_store.find_any`
           (no ``is_active`` filter) so an already-revoked token is still found
           and validated against its owning client per RFC 7009 §2.2. Skipped
           when ``token_type_hint == "access_token"``.
        2. **Access token (JWT)** — if not a refresh token (or the hint says
           ``access_token``), validate the token as a JWT via
           :func:`~jvspatial.api.auth.oauth.resource.verify_oauth_access_token`
           (signature / ``iss`` / ``aud`` / ``exp``). On success return a
           :class:`_RevocableAccessToken` carrying ``jti``/``exp``/``client_id``.

        Anything that matches neither returns ``None``; per RFC 7009 §2.2 the
        server MUST respond 200 even for an unknown token, so ``None`` is safe.

        Args:
            token_string: The plaintext token value from the ``token`` form
                parameter.
            token_type_hint: Optional hint (``"refresh_token"`` /
                ``"access_token"``). Used to skip the refresh lookup when the
                caller explicitly says ``access_token``.

        Returns:
            A :class:`_RevocableToken` (refresh), a :class:`_RevocableAccessToken`
            (JWT access token), or ``None``. The wrapper exposes ``check_client``
            as required by Authlib's :meth:`authenticate_token`.
        """
        if token_type_hint != "access_token":
            rec = call_async(refresh_store.find_any, token_string)
            if rec is not None:
                return _RevocableToken(rec)

        # Not a known refresh token (or the caller hinted access_token): try to
        # validate it as a JWT access token. verify_* returns None on any
        # failure (bad sig/iss/aud/expired/missing jti/already denylisted).
        issuer = self.server._issuer
        resource = self.server._resource

        async def _verify() -> Optional[dict]:
            return await verify_oauth_access_token(
                token_string, issuer=issuer, resource=resource
            )

        claims = call_async(_verify)
        if claims and claims.get("jti"):
            return _RevocableAccessToken(claims)
        return None

    def revoke_token(self, token: Any, request: Any) -> None:
        """Revoke *token* — either a refresh record or a JWT access token.

        *token* is the object returned by :meth:`query_token` (NOT a string);
        Authlib's base
        :meth:`~authlib.oauth2.rfc7009.RevocationEndpoint.create_endpoint_response`
        calls :meth:`query_token` first and passes the result directly here.

        * :class:`_RevocableToken` (refresh) → mark the
          ``OAuthRefreshToken`` record inactive.
        * :class:`_RevocableAccessToken` (JWT) → add its ``jti`` to the
          denylist until the token's own ``exp`` (self-expiring row).

        Args:
            token: The revocable object from :meth:`query_token`.
            request: The Authlib OAuth2 request (unused; signature compat).
        """
        if isinstance(token, _RevocableAccessToken):
            exp = datetime.fromtimestamp(int(token.claims["exp"]), tz=timezone.utc)
            call_async(denylist.revoke_jti, token.claims["jti"], exp)
            return
        call_async(refresh_store.revoke, token.record)
