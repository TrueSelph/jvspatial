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
import time
from datetime import datetime, timedelta, timezone
from functools import partial
from typing import Any, Dict, List, Optional, Tuple, Union, cast

from authlib.oauth2.rfc6749 import AuthorizationServer
from authlib.oauth2.rfc6749.errors import InvalidRequestError
from authlib.oauth2.rfc6749.grants import AuthorizationCodeGrant
from authlib.oauth2.rfc6749.grants.refresh_token import RefreshTokenGrant
from authlib.oauth2.rfc6749.requests import BasicOAuth2Payload
from authlib.oauth2.rfc7636 import CodeChallenge
from authlib.oauth2.rfc9068 import JWTBearerTokenGenerator
from joserfc.jwk import KeySet, RSAKey

from jvspatial.api.auth.oauth import keys as keystore
from jvspatial.api.auth.oauth import refresh_store
from jvspatial.api.auth.oauth.bridge import call_async, run_sync_with_async_bridge
from jvspatial.api.auth.oauth.client_adapter import OAuthClientAdapter
from jvspatial.api.auth.oauth.models import AuthorizationCode, OAuthClient
from jvspatial.api.auth.oauth.requests import StarletteOAuth2Request


class RequiredS256CodeChallenge(CodeChallenge):
    """PKCE mandatory for ALL clients (public and confidential), S256 only.

    Authlib's stock ``CodeChallenge(required=True)`` only enforces PKCE when
    ``request.auth_method == "none"`` (public clients).  A confidential client
    authenticated via ``client_secret_post`` or ``client_secret_basic`` can
    silently bypass the challenge.  This subclass overrides
    ``validate_code_challenge`` — the authorize-step hook — so that:

    * a missing ``code_challenge`` is always rejected (regardless of auth method);
    * ``code_challenge_method=plain`` is rejected (S256 only per current best
      practice; plain leaks the verifier to any party that sees the authorize URL).

    The ``validate_code_verifier`` hook (token-step) is inherited unchanged; it
    already rejects a missing verifier when a challenge was stored, and rejects
    a verifier supplied against a code that had no challenge.
    """

    SUPPORTED_CODE_CHALLENGE_METHOD = ["S256"]
    DEFAULT_CODE_CHALLENGE_METHOD = "S256"

    def validate_code_challenge(self, grant, redirect_uri):  # type: ignore[override]
        """Reject missing challenge or non-S256 method at authorize step."""
        challenge = grant.request.payload.data.get("code_challenge")
        method = grant.request.payload.data.get("code_challenge_method")
        if not challenge:
            raise InvalidRequestError("PKCE code_challenge is required")
        if method and method != "S256":
            raise InvalidRequestError("only S256 code_challenge_method is allowed")
        return super().validate_code_challenge(grant, redirect_uri)


#: Authorization codes are single-use and short-lived (RFC 6749 §4.1.2).
DEFAULT_CODE_TTL_SECONDS = 600

#: Refresh token lifetime in days.
DEFAULT_REFRESH_TOKEN_TTL_DAYS = 7


def _generate_refresh_token(**kwargs: Any) -> str:
    """Generate an opaque refresh token string (``rt_`` prefix + 48 url-safe bytes)."""
    import secrets  # stdlib — always available

    return "rt_" + secrets.token_urlsafe(48)


async def _persist_refresh(
    token_str: str,
    user_id: str,
    client_id: str,
    scope: str,
    resource: Optional[str],
    ttl_days: int,
) -> None:
    """Async shim that persists a refresh token via :mod:`refresh_store`.

    ``call_async`` passes only positional args, so all parameters here are
    positional even though ``mint_refresh_token`` is keyword-only.
    """
    await refresh_store.mint_refresh_token(
        token=token_str,
        user_id=user_id,
        client_id=client_id,
        scope=scope,
        resource=resource,
        expires_at=datetime.now(timezone.utc) + timedelta(days=ttl_days),
    )


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


def _intersect_scope(scope: str, permissions: Optional[List[str]]) -> str:
    """Return the intersection of *scope* and *permissions*.

    When *permissions* is ``None`` or empty the original *scope* is returned
    unchanged (back-compat: callers that do not supply ``permissions`` keep
    the full client-allowed scope).  When *permissions* is provided only
    tokens whose name appears in *permissions* are kept.

    Args:
        scope: Space-delimited scope string (already client-filtered).
        permissions: Resource-owner permission list, or ``None``.

    Returns:
        Space-delimited scope string with tokens not in *permissions* removed,
        or the original *scope* when *permissions* is absent.
    """
    if not permissions:  # None / [] => no narrowing (back-compat)
        return scope or ""
    allowed = set(permissions)
    return " ".join(s for s in (scope or "").split() if s in allowed)


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
        """Configure the generator with the *issuer* and audience *resource*.

        Wires :func:`_generate_refresh_token` so that Authlib's
        ``BearerTokenGenerator.generate`` includes a ``refresh_token`` field
        when the client's ``grant_types`` list contains ``refresh_token``.
        """
        super().__init__(issuer=issuer, refresh_token_generator=_generate_refresh_token)
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

    def get_extra_claims(
        self, client: Any, grant_type: str, user: Any, scope: Any
    ) -> Dict[str, Any]:
        """Merge base extra claims with ``nbf`` (Not Before, RFC 7519 §4.1.5).

        ``nbf`` is set to the current epoch second — i.e. the token is valid
        immediately.  Adding it makes the token verifiable by strict validators
        that require ``nbf`` to be present (RFC 9068 recommends it).

        The base :class:`~authlib.oauth2.rfc9068.JWTBearerTokenGenerator`
        ``get_extra_claims`` returns ``{}``; we call super and merge so any
        future upstream additions are preserved.
        """
        base: Dict[str, Any] = super().get_extra_claims(client, grant_type, user, scope)
        base["nbf"] = int(time.time())
        return base

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
        """Persist a single-use authorization code (PKCE challenge included).

        The stored scope is the intersection of the client-allowed requested
        scope (``request.scope``) and the resource-owner's permissions (taken
        from ``request.user["permissions"]`` when present).  When no
        ``permissions`` key is supplied the full client-allowed scope is stored
        unchanged (back-compat with M1b-1 callers that pass only ``{"id": ...}``).

        Because the token generator reads scope from ``authorization_code.get_scope()``
        at token-issue time, narrowing here is sufficient: no further intersection
        is needed in the generator.
        """
        payload_data = request.payload.data
        challenge = payload_data.get("code_challenge") or ""
        method = payload_data.get("code_challenge_method") or "S256"
        client_id = request.client.get_client_id()
        user_id = _grant_user_id(request.user)
        resource = getattr(self.server, "_resource", None)
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=getattr(self.server, "_code_ttl", DEFAULT_CODE_TTL_SECONDS)
        )
        # Extract permissions from grant_user dict (absent => no narrowing).
        permissions: Optional[List[str]] = None
        if isinstance(request.user, dict):
            permissions = request.user.get("permissions") or None
        granted_scope = _intersect_scope(request.scope or "", permissions)
        record = AuthorizationCode(
            code_hash=_sha256(code),
            client_id=client_id,
            user_id=user_id,
            redirect_uri=request.payload.redirect_uri or "",
            code_challenge=challenge,
            code_challenge_method=method,
            scope=granted_scope,
            resource=resource,
            expires_at=expires_at,
        )
        call_async(record.save)

    def query_authorization_code(
        self, code: str, client: Any
    ) -> Optional[StoredAuthCode]:
        """Return the stored, unconsumed, unexpired code for *client* or None.

        READ-ONLY: the code is NOT marked consumed here.  Consuming before
        redirect_uri and PKCE validation would burn the code on any failed
        request, locking out the legitimate client's retry (DoS vector).

        Authlib calls this method first, then validates redirect_uri and the
        PKCE ``code_verifier`` (via the ``after_validate_token_request`` hook),
        and only on the success path calls ``delete_authorization_code``.  The
        single-use point is therefore ``delete_authorization_code``, which runs
        after all validation passes.
        """
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
        """Consume the code so it can never be exchanged again (single-use point).

        Authlib calls this AFTER redirect_uri + PKCE ``code_verifier`` + user
        authentication all pass, and after ``save_token`` completes.  Marking
        consumed here — not in ``query_authorization_code`` — ensures a request
        with a wrong ``code_verifier`` or wrong ``redirect_uri`` does NOT burn
        the code for a legitimate retry.

        Idempotent: if ``consumed`` is already ``True`` (e.g. a concurrent
        success race in a future multi-worker deployment), the save is a no-op
        in effect.

        Note on atomicity: single-use is serialized by the single-process anyio
        bridge, NOT a DB-level compare-and-swap.  Under multi-worker or
        multi-process deployment a conditional-update primitive is required to
        prevent a TOCTOU race between two simultaneous legitimate exchanges of
        the same code (tracked for a later phase).
        """
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
        """Persist the refresh token (hashed) when one was issued.

        Access tokens are stateless RS256 JWTs and require no persistence.
        When a ``refresh_token`` is present in *token* (i.e. the client has
        ``refresh_token`` in its ``grant_types``), the plaintext is stored
        hashed via :func:`refresh_store.mint_refresh_token`.

        ``request.user`` at token-endpoint time is a :class:`_GrantUser`
        produced by :meth:`JvSpatialAuthCodeGrant.authenticate_user`, so
        ``_grant_user_id`` reliably extracts the subject identifier.
        """
        rt = token.get("refresh_token")
        if not rt:
            return
        user_id = _grant_user_id(getattr(request, "user", None))
        client_id: str = ""
        client = getattr(request, "client", None)
        if client is not None:
            client_id = client.get_client_id()
        scope: str = token.get("scope", "")
        call_async(
            _persist_refresh,
            rt,
            user_id,
            client_id,
            scope,
            self._resource,
            DEFAULT_REFRESH_TOKEN_TTL_DAYS,
        )

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


class _RefreshCredential:
    """Adapter over ``OAuthRefreshToken`` for Authlib's ``RefreshTokenGrant``.

    Exposes the interface ``validate_token_request`` reads (authlib 1.7.2):

    * ``check_client(client) -> bool``
    * ``get_scope() -> str``

    ``is_expired`` / ``is_revoked`` are NOT called by the 1.7.2 validate path
    — ``find_active`` already filters on those before this object is built.
    ``authenticate_user`` and ``revoke_old_credential`` receive this same object.
    """

    def __init__(self, rec: Any) -> None:
        """Wrap the persisted ``OAuthRefreshToken`` record."""
        self.record = rec
        # Surface user_id so authenticate_user can build a _GrantUser.
        self.user_id: str = rec.user_id

    # --- interface required by RefreshTokenGrant._validate_request_token ---

    def check_client(self, client: Any) -> bool:
        """True when the record's client_id matches the authenticated client."""
        return self.record.client_id == client.get_client_id()

    def get_scope(self) -> str:
        """Return the scope that was granted when this refresh token was minted."""
        return self.record.scope or ""

    # --- convenience attributes (not called by authlib 1.7.2 validate path) ---

    def is_expired(self) -> bool:
        """``find_active`` already filters expired tokens; always False here."""
        return False

    def is_revoked(self) -> bool:
        """``find_active`` only returns active records; always False here."""
        return not self.record.is_active


class JvSpatialRefreshTokenGrant(RefreshTokenGrant):
    """Refresh-token grant with rotation: old token revoked, new one issued + persisted.

    The ``authenticate_refresh_token`` → ``authenticate_user`` → ``revoke_old_credential``
    lifecycle is driven by Authlib's :class:`RefreshTokenGrant` base class.
    Storage calls bridge to the async ``refresh_store`` via :func:`call_async`.
    """

    TOKEN_ENDPOINT_AUTH_METHODS = [
        "client_secret_basic",
        "client_secret_post",
        "none",
    ]

    #: Issue a new refresh token on every exchange (rotation).
    INCLUDE_NEW_REFRESH_TOKEN = True

    def authenticate_refresh_token(
        self, refresh_token: str
    ) -> Optional[_RefreshCredential]:
        """Look up the active, unexpired token record; return ``None`` on miss/revoke.

        Authlib passes the *plaintext* ``refresh_token`` string from the form.
        :func:`refresh_store.find_active` hashes it internally before querying.
        """
        rec = call_async(refresh_store.find_active, refresh_token)
        if rec is None:
            return None
        return _RefreshCredential(rec)

    def authenticate_user(self, credential: _RefreshCredential) -> _GrantUser:
        """Return the resource owner stored in the credential.

        ``credential`` is the :class:`_RefreshCredential` returned by
        :meth:`authenticate_refresh_token` — carries ``user_id``.
        """
        return _GrantUser(credential.user_id)

    def revoke_old_credential(self, credential: _RefreshCredential) -> None:
        """Revoke the old refresh token record (rotation enforcement).

        Called by Authlib's base class *after* the new token has been saved.
        ``credential`` is the same :class:`_RefreshCredential` object produced
        by :meth:`authenticate_refresh_token`.
        """
        call_async(refresh_store.revoke, credential.record)


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
    server.register_grant(
        JvSpatialAuthCodeGrant, [RequiredS256CodeChallenge(required=True)]
    )
    server.register_grant(JvSpatialRefreshTokenGrant)
    server.register_token_generator(
        "default", JvSpatialJWTTokenGenerator(issuer=issuer, resource=resource)
    )
    return server
