"""Dynamic Client Registration endpoint (RFC 7591).

Implements :class:`JvSpatialClientRegistrationEndpoint`, a subclass of
Authlib's :class:`~authlib.oauth2.rfc7591.ClientRegistrationEndpoint`,
wired into :class:`~jvspatial.api.auth.oauth.server.JvSpatialAuthorizationServer`
via :func:`~jvspatial.api.auth.oauth.server.build_authorization_server`.

**Open registration** — ``authenticate_token`` returns a truthy sentinel so
no initial-access-token is required (MCP zero-config).  Gated deployments can
override this method to check a pre-shared token from the Authorization header.

JSON-body wiring — ``async_register_client`` populates ``request.payload``
with a :class:`~authlib.oauth2.rfc6749.requests.BasicOAuth2Payload` wrapping
the caller-supplied ``json_body`` dict, then dispatches through the anyio
bridge.  The base ``extract_client_metadata`` reads ``request.payload.data``
(the dict), so no request mutation beyond setting ``.payload`` is needed.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from authlib.oauth2.rfc7591 import (
    ClientRegistrationEndpoint,
    InvalidClientMetadataError,
)

from jvspatial.api.auth.oauth.bridge import call_async
from jvspatial.api.auth.oauth.models import OAuthClient, hash_client_secret


def _redirect_uri_allowed(uri: str) -> bool:
    """Return True when *uri* is safe for code delivery (OAuth 2.1 BCP).

    Permitted:
    * Any ``https://`` URI.
    * Loopback ``http://`` URIs: ``127.0.0.1``, ``localhost``, ``[::1]``
      (RFC 8252 §8.3 — native/dev clients that cannot obtain a TLS cert).

    Cleartext ``http://`` URIs to non-loopback hosts are rejected because
    the authorization code travels in the redirect location and is exposed
    to network observers on the cleartext leg.
    """
    p = urlparse(uri)
    if p.scheme == "https":
        return True
    if p.scheme == "http" and p.hostname in ("127.0.0.1", "localhost", "::1"):
        return True
    return False


class JvSpatialClientRegistrationEndpoint(ClientRegistrationEndpoint):
    """RFC 7591 client registration endpoint for jvspatial.

    Three required hooks:

    * :meth:`authenticate_token` — open registration (MCP zero-config);
      returns a truthy sentinel so the base class allows the request.
    * :meth:`get_server_metadata` — returns a minimal AS-metadata dict so
      Authlib can validate the incoming ``token_endpoint_auth_method`` etc.
    * :meth:`save_client` — persists an :class:`~jvspatial.api.auth.oauth.models.OAuthClient`
      via ``call_async``; returns the OAuthClient instance.

    Response body shaping — the base
    :meth:`~authlib.oauth2.rfc7591.ClientRegistrationEndpoint.create_registration_response`
    builds the 201 body from ``client_info + client_metadata`` BEFORE calling
    ``save_client``, so it always includes the generated ``client_secret``.
    We override ``create_registration_response`` to post-process the body and
    strip ``client_secret`` for public clients (``token_endpoint_auth_method
    == "none"``), conforming to RFC 7591 §3.2.1 which says confidential
    clients receive a secret and public clients do not.
    """

    # ------------------------------------------------------------------ #
    # Required hooks                                                       #
    # ------------------------------------------------------------------ #

    def authenticate_token(self, request: Any) -> Any:
        """Allow open registration without an initial-access-token.

        Returns a truthy sentinel (``True``).  The base class rejects the
        request when this returns ``None``/``False``/``0``/``""``.

        To gate registration, inspect ``request.headers.get("Authorization")``
        and return a token object (or truthy value) only when the header
        carries a valid initial-access-token.
        """
        return True  # open DCR — any caller may register

    def get_server_metadata(self) -> Dict[str, Any]:
        """Return the AS metadata dict used to validate registration requests.

        Authlib's :class:`~authlib.oauth2.rfc7591.claims.ClientMetadataClaims`
        cross-checks ``token_endpoint_auth_method`` etc. against the values
        advertised here, so this dict must cover all supported values.

        .. note::
            ``scopes_supported`` is deliberately NOT advertised here. Authlib's
            :meth:`ClientMetadataClaims.get_claims_options` turns an advertised
            ``scopes_supported`` into a *hard* validation
            (``scopes_supported.issuperset(requested)``) that rejects an
            out-of-set scope with ``invalid_client_metadata`` (HTTP 400) inside
            the base ``extract_client_metadata`` — before our filter can run.
            That would defeat the silent-filter contract (drop unsupported
            tokens, keep registering) that this endpoint enforces for
            zero-config MCP clients. The supported-scope ceiling is applied by
            :meth:`extract_client_metadata` (silent intersection) instead.
        """
        return {
            "token_endpoint_auth_methods_supported": [
                "none",
                "client_secret_basic",
                "client_secret_post",
            ],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
            ],
            "response_types_supported": ["code"],
            "code_challenge_methods_supported": ["S256"],
        }

    # ------------------------------------------------------------------ #
    # Redirect-URI security guard (OAuth 2.1 BCP)                        #
    # ------------------------------------------------------------------ #

    def extract_client_metadata(self, request: Any) -> Dict[str, Any]:
        """Validate redirect URIs and filter requested scope before persisting.

        Delegates to the base ``extract_client_metadata`` for all standard
        RFC 7591 metadata validation, then:

        1. Enforces that every registered ``redirect_uri`` is either:

           * an ``https://`` URI (any host), or
           * an ``http://`` loopback URI — ``127.0.0.1``, ``localhost``,
             or ``[::1]`` — permitted for native/dev clients (RFC 8252 §8.3).

           Cleartext ``http://`` URIs to non-loopback hosts are rejected with
           ``invalid_client_metadata`` (HTTP 400) because the authorization
           code is delivered via redirect and is exposed in plaintext to any
           network observer on that leg.

        2. Filters the requested ``scope`` against the authorization server's
           supported scopes WHEN a ceiling is declared
           (``server._supported_scopes`` non-empty). Unsupported tokens are
           silently dropped (RFC 7591 permits the AS to filter rather than
           reject — gentler than a hard 400 for zero-config MCP clients), so a
           client cannot self-register an unsupported / elevated scope. When no
           ceiling is declared (the default), the requested scope is left
           verbatim for back-compat. This is defense-in-depth; the authorize-time
           supported-scope ceiling in
           :meth:`~jvspatial.api.auth.oauth.server.JvSpatialAuthCodeGrant.save_authorization_code`
           is the primary bound on issued-token scope.

        Filtering here (rather than in :meth:`save_client`) keeps a single
        source of truth: the base ``create_registration_response`` builds the
        201 body from this returned metadata, so both the persisted record and
        the echoed ``scope`` reflect the filtered value.

        Raises:
            InvalidClientMetadataError: When any redirect URI fails the check.
        """
        client_metadata = super().extract_client_metadata(request)
        invalid_uris = [
            uri
            for uri in (client_metadata.get("redirect_uris") or [])
            if not _redirect_uri_allowed(uri)
        ]
        if invalid_uris:
            raise InvalidClientMetadataError(
                "redirect_uris must use https (or loopback http for native clients): "
                + ", ".join(invalid_uris)
            )
        supported = list(getattr(self.server, "_supported_scopes", None) or [])
        if supported:
            allowed = set(supported)
            requested = client_metadata.get("scope") or ""
            client_metadata["scope"] = " ".join(
                s for s in requested.split() if s in allowed
            )
        return client_metadata

    def save_client(
        self,
        client_info: Dict[str, Any],
        client_metadata: Dict[str, Any],
        request: Any,
    ) -> "OAuthClient":
        """Persist the registered client.

        Args:
            client_info: Generated identifiers (``client_id``, ``client_secret``,
                ``client_id_issued_at``, ``client_secret_expires_at``).
            client_metadata: Validated client metadata fields from the request
                body (``redirect_uris``, ``grant_types``, etc.).
            request: The DCR HTTP request (payload already validated).

        Returns:
            The persisted :class:`~jvspatial.api.auth.oauth.models.OAuthClient`
            instance (consumed by ``generate_client_registration_info``, which
            returns ``None`` by default).
        """
        auth_method: str = client_metadata.get("token_endpoint_auth_method", "none")
        raw_secret: Optional[str] = client_info.get("client_secret")

        # Public clients (PKCE / auth_method=="none") get no secret stored.
        # Confidential clients store the hash; the plaintext is returned
        # once in the 201 body (RFC 7591 §3.2.1) and then discarded.
        if auth_method == "none" or not raw_secret:
            secret_hash: Optional[str] = None
        else:
            secret_hash = hash_client_secret(raw_secret)

        redirect_uris: List[str] = list(client_metadata.get("redirect_uris") or [])
        grant_types: List[str] = list(
            client_metadata.get("grant_types") or ["authorization_code"]
        )
        response_types: List[str] = list(
            client_metadata.get("response_types") or ["code"]
        )
        scope: str = client_metadata.get("scope") or ""
        client_name: str = client_metadata.get("client_name") or ""

        client = OAuthClient(
            client_id=client_info["client_id"],
            client_secret_hash=secret_hash,
            client_name=client_name,
            redirect_uris=redirect_uris,
            grant_types=grant_types,
            response_types=response_types,
            scope=scope,
            token_endpoint_auth_method=auth_method,
        )
        call_async(client.save)
        return client

    # ------------------------------------------------------------------ #
    # Response shaping — strip secret for public clients                  #
    # ------------------------------------------------------------------ #

    def create_registration_response(self, request: Any):  # type: ignore[override]
        """Strip ``client_secret`` from the 201 body for public clients.

        The base implementation builds the response body from
        ``client_info + client_metadata`` before calling ``save_client``.
        Because ``client_info`` always contains a generated ``client_secret``,
        we post-process the body to remove it when
        ``token_endpoint_auth_method == "none"``.  The base class signature is
        preserved; we delegate to super() and then strip the secret when
        appropriate.
        """
        status, body, headers = super().create_registration_response(request)
        auth_method = body.get("token_endpoint_auth_method", "none")
        if auth_method == "none":
            body = dict(body)
            body.pop("client_secret", None)
            body.pop("client_secret_expires_at", None)
        return status, body, headers
