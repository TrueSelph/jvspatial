"""Authorization server wiring Authlib's sync OAuth core into jvspatial.

Exposes :func:`build_authorization_server`, returning a server that runs
Authlib's synchronous authorization-code + PKCE grant inside a worker thread
(via the anyio bridge) while its storage hooks reach jvspatial's async
``Object`` layer through :func:`~jvspatial.api.auth.oauth.bridge.call_async`.
Issued access tokens are RS256 RFC-9068 ``at+jwt`` JWTs signed with the active
``OAuthSigningKey``.

The HTTP request/response surface is framework-agnostic: callers build a
:class:`~jvspatial.api.auth.oauth.requests.StarletteOAuth2Request` and receive
an :class:`OAuthHttpResponse`. The async wrappers
(:meth:`JvSpatialAuthorizationServer.async_create_authorization_response` /
:meth:`~JvSpatialAuthorizationServer.async_create_token_response`) are the
public entry points for async route handlers.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from authlib.oauth2.rfc6749 import AuthorizationServer
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant
from authlib.oauth2.rfc6749.requests import BasicOAuth2Payload
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc9068 import JWTBearerTokenGenerator
from joserfc.jwk import KeySet, RSAKey

from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.api.auth.oauth.bridge import call_async, run_sync_with_async_bridge
from jvspatial.api.auth.oauth.client_adapter import OAuthClientAdapter
from jvspatial.api.auth.oauth.models import AuthorizationCode, OAuthClient
from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request

#: Authorization codes are single-use and short-lived (RFC 6749 §4.1.2).
DEFAULT_CODE_TTL_SECONDS = 600


def _sha256(value: str) -> str:
    """Return the hex SHA-256 digest of *value* (authorization-code at-rest)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _ensure_payload(request: StarletteOAuth2Request) -> StarletteOAuth2Request:
    """Attach a combined query+form ``BasicOAuth2Payload`` to *request* once.

    Authlib reads request parameters off ``request.payload`` (combined query and
    form, mirroring Flask's ``request.values``). ``StarletteOAuth2Request`` only
    carries ``args``/``form`` dicts, so build the payload here. Token-endpoint
    client auth (``none``) also reads ``payload.data``, so the form params must
    be present in the payload, not just on ``request.form``.
    """
    if request.payload is None:
        combined: Dict[str, str] = {}
        combined.update(request.args or {})
        combined.update(request.form or {})
        request.payload = BasicOAuth2Payload(combined)
    return request


class OAuthHttpResponse:
    """A framework-agnostic HTTP response produced by ``handle_response``.

    Authlib hands the framework integration a ``(status, body, headers)``
    triple. We normalise headers to a lowercase-keyed dict (so ``location`` is
    reachable regardless of casing) and expose the parsed JSON body via
    :attr:`body_json`.
    """

    def __init__(
        self,
        status_code: int,
        body: Union[dict, str, None],
        headers: Union[List[Tuple[str, str]], Dict[str, str], None],
    ) -> None:
        """Store the status, raw body, and lowercase-keyed header dict."""
        self.status_code = status_code
        self.raw_body = body
        normalized: Dict[str, str] = {}
        items: List[Tuple[str, str]]
        if isinstance(headers, dict):
            items = list(headers.items())
        else:
            items = list(headers or [])
        for key, value in items:
            normalized[key.lower()] = value
        self.headers = normalized

    @property
    def body_json(self) -> Optional[dict]:
        """Return the body as a dict if it is JSON/dict, else ``None``."""
        body = self.raw_body
        if isinstance(body, dict):
            return body
        if isinstance(body, str) and body:
            try:
                parsed = json.loads(body)
            except (TypeError, ValueError):
                return None
            return parsed if isinstance(parsed, dict) else None
        return None


class StoredAuthCode:
    """Adapter exposing a stored :class:`AuthorizationCode` to Authlib's grant.

    Authlib's authorization-code grant and PKCE extension read
    ``get_redirect_uri()`` / ``get_scope()`` plus the ``code_challenge`` /
    ``code_challenge_method`` attributes off the queried code object.
    """

    def __init__(self, record: AuthorizationCode) -> None:
        """Wrap the persisted *record*."""
        self.record = record
        self.code_challenge = record.code_challenge
        self.code_challenge_method = record.code_challenge_method

    def get_redirect_uri(self) -> str:
        """Return the redirect URI the code was issued against."""
        return self.record.redirect_uri

    def get_scope(self) -> str:
        """Return the granted scope (space-delimited)."""
        return self.record.scope or ""

    def get_auth_time(self) -> None:
        """No interactive auth-time is tracked; return ``None`` (OIDC getter)."""
        return None

    def get_nonce(self) -> None:
        """No OIDC nonce is tracked; return ``None`` (OIDC getter)."""
        return None


class _GrantUser:
    """Minimal resource-owner adapter exposing ``get_user_id`` to the token gen.

    The RFC-9068 token generator reads ``user.get_user_id()`` for the ``sub``
    claim. Authorization codes persist only the user id string, so this wraps
    it back into the shape Authlib expects on token exchange.
    """

    def __init__(self, user_id: str) -> None:
        """Store the resource-owner id."""
        self.user_id = user_id

    def get_user_id(self) -> str:
        """Return the resource-owner subject identifier."""
        return self.user_id


def _grant_user_id(grant_user: Any) -> str:
    """Extract a stable user id from the ``grant_user`` Authlib carries.

    ``create_authorization_response`` sets ``request.user`` to whatever the
    caller passed as ``grant_user`` (a ``{"id": ...}`` dict here), so accept
    dicts, objects with ``get_user_id``/``id``, or a bare string.
    """
    if grant_user is None:
        return ""
    if isinstance(grant_user, dict):
        return str(grant_user.get("id") or grant_user.get("sub") or "")
    if hasattr(grant_user, "get_user_id"):
        return str(grant_user.get_user_id())
    if hasattr(grant_user, "id"):
        return str(grant_user.id)
    return str(grant_user)


class JvSpatialJWTTokenGenerator(JWTBearerTokenGenerator):
    """RS256 RFC-9068 token generator backed by the jvspatial signing-key store.

    Runs synchronously inside the threaded grant call, so it reaches the async
    key store through :func:`call_async`. Returns a ``KeySet`` from
    :meth:`get_jwks` so joserfc auto-stamps the active key's ``kid`` into the
    JWT header.
    """

    def __init__(self, issuer: str, resource: str) -> None:
        """Configure the generator with the *issuer* and audience *resource*."""
        super().__init__(issuer=issuer)
        self._resource = resource

    def get_jwks(self) -> KeySet:
        """Return a ``KeySet`` holding the active RS256 private signing key."""
        key = call_async(keystore.get_active_signing_key)
        if key is None:
            raise RuntimeError("No active OAuth signing key available.")
        rsa_key = RSAKey.import_key(
            key.private_pem,
            {"kid": key.kid, "alg": "RS256", "use": "sig"},
        )
        return KeySet([rsa_key])

    def get_audiences(self, client: Any, user: Any, scope: Any) -> str:
        """Return the protected-resource audience for the ``aud`` claim."""
        return self._resource


class JvSpatialAuthCodeGrant(AuthorizationCodeGrant):
    """Authorization-code grant persisting codes via jvspatial ``Object``s.

    Allows public PKCE clients (``none``) in addition to the RFC-6749 secret
    methods, and drives all storage through :func:`call_async`.
    """

    TOKEN_ENDPOINT_AUTH_METHODS = [
        "client_secret_basic",
        "client_secret_post",
        "none",
    ]

    def save_authorization_code(self, code: str, request: Any) -> None:
        """Persist a single-use authorization code (PKCE challenge included)."""
        payload_data = request.payload.data
        challenge = payload_data.get("code_challenge") or ""
        method = payload_data.get("code_challenge_method") or "S256"
        client_id = request.client.get_client_id()
        user_id = _grant_user_id(request.user)
        resource = getattr(self.server, "_resource", None)
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=getattr(self.server, "_code_ttl", DEFAULT_CODE_TTL_SECONDS)
        )
        record = AuthorizationCode(
            code_hash=_sha256(code),
            client_id=client_id,
            user_id=user_id,
            redirect_uri=request.payload.redirect_uri or "",
            code_challenge=challenge,
            code_challenge_method=method,
            scope=request.scope or "",
            resource=resource,
            expires_at=expires_at,
        )
        call_async(record.save)

    def query_authorization_code(
        self, code: str, client: Any
    ) -> Optional[StoredAuthCode]:
        """Return the stored, unconsumed, unexpired code for *client* or None."""
        record = call_async(self._find_code, _sha256(code))
        if record is None or record.consumed:
            return None
        if record.client_id != client.get_client_id():
            return None
        expires_at = record.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return None
        return StoredAuthCode(record)

    def delete_authorization_code(self, authorization_code: StoredAuthCode) -> None:
        """Mark the code consumed so it can never be exchanged twice."""
        call_async(self._consume_code, authorization_code.record)

    def authenticate_user(self, authorization_code: StoredAuthCode) -> _GrantUser:
        """Return the resource owner bound to *authorization_code*."""
        return _GrantUser(authorization_code.record.user_id)

    @staticmethod
    async def _find_code(code_hash: str) -> Optional[AuthorizationCode]:
        """Look up a stored authorization code by its hash (newest match)."""
        matches = cast(
            List[AuthorizationCode],
            await AuthorizationCode.find({"context.code_hash": code_hash}),
        )
        if not matches:
            return None
        return sorted(matches, key=lambda c: c.created_at, reverse=True)[0]

    @staticmethod
    async def _consume_code(record: AuthorizationCode) -> None:
        """Flip ``consumed`` and persist (single-use enforcement)."""
        record.consumed = True
        await record.save()


class JvSpatialAuthorizationServer(AuthorizationServer):
    """``AuthorizationServer`` bound to jvspatial storage and the anyio bridge.

    The framework hooks (:meth:`create_oauth2_request`,
    :meth:`handle_response`, :meth:`query_client`, :meth:`save_token`) run
    synchronously inside the threaded grant call; the async wrappers are the
    coroutine entry points callers ``await``.
    """

    def __init__(self, issuer: str, resource: str, **kwargs: Any) -> None:
        """Configure the server with its *issuer*, audience *resource*, knobs."""
        super().__init__(**kwargs)
        self._issuer = issuer
        self._resource = resource
        self._code_ttl = DEFAULT_CODE_TTL_SECONDS

    def create_oauth2_request(self, request: Any) -> StarletteOAuth2Request:
        """Return the request with its ``payload`` populated.

        Authlib reads parameters off ``request.payload`` (combined query + form,
        mirroring Flask's ``request.values``). The provided
        ``StarletteOAuth2Request`` only carries ``args``/``form`` dicts, so we
        attach a ``BasicOAuth2Payload`` here.
        """
        return _ensure_payload(request)

    def create_json_request(self, request: Any) -> Any:
        """Return the request unchanged (JSON requests are not used here)."""
        return request

    def handle_response(
        self,
        status: int,
        body: Union[dict, str, None],
        headers: Union[List[Tuple[str, str]], Dict[str, str], None],
    ) -> OAuthHttpResponse:
        """Wrap Authlib's ``(status, body, headers)`` into ``OAuthHttpResponse``."""
        return OAuthHttpResponse(status, body, headers)

    def query_client(self, client_id: str) -> Optional[OAuthClientAdapter]:
        """Load a registered client by id, wrapped for Authlib's ``ClientMixin``."""
        client = call_async(self._load_client, client_id)
        return OAuthClientAdapter(client) if client else None

    def save_token(self, token: Any, request: Any) -> None:
        """No-op: access tokens are stateless JWTs (refresh persistence is M1b-2)."""
        return None

    def send_signal(self, name: str, *args: Any, **kwargs: Any) -> None:
        """No-op signal sink (no framework signal system is wired here)."""
        return None

    async def async_create_authorization_response(
        self, req: StarletteOAuth2Request, grant_user: Any
    ) -> OAuthHttpResponse:
        """Run the (sync) authorize flow off-thread and return the response.

        Populates ``req.payload`` up front because ``create_authorization_response``
        only calls ``create_oauth2_request`` for non-``OAuth2Request`` inputs.
        """
        _ensure_payload(req)
        return await run_sync_with_async_bridge(
            partial(self.create_authorization_response, req, grant_user=grant_user)
        )

    async def async_create_token_response(
        self, req: StarletteOAuth2Request
    ) -> OAuthHttpResponse:
        """Run the (sync) token-exchange flow off-thread and return the response."""
        _ensure_payload(req)
        return await run_sync_with_async_bridge(
            partial(self.create_token_response, req)
        )

    @staticmethod
    async def _load_client(client_id: str) -> Optional[OAuthClient]:
        """Fetch the stored :class:`OAuthClient` for *client_id*, or ``None``."""
        matches = cast(
            List[OAuthClient],
            await OAuthClient.find({"context.client_id": client_id}),
        )
        return matches[0] if matches else None


def build_authorization_server(
    issuer: str, resource: str
) -> JvSpatialAuthorizationServer:
    """Build a jvspatial authorization server for the given issuer/resource.

    Registers the authorization-code grant with a *required* PKCE challenge and
    a default RS256 RFC-9068 token generator.

    Args:
        issuer: The ``iss`` claim / authorization-server identifier.
        resource: The protected-resource audience for issued tokens (``aud``).

    Returns:
        A configured :class:`JvSpatialAuthorizationServer`.
    """
    server = JvSpatialAuthorizationServer(
        issuer=issuer,
        resource=resource,
        scopes_supported=None,
    )
    server.register_grant(JvSpatialAuthCodeGrant, [CodeChallenge(required=True)])
    server.register_token_generator(
        "default", JvSpatialJWTTokenGenerator(issuer=issuer, resource=resource)
    )
    return server
