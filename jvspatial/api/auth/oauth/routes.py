"""HTTP routers mounting the OAuth 2.1 authorization server.

:func:`build_oauth_routers` constructs two FastAPI routers, gated by the caller
on :attr:`AuthConfig.oauth_enabled`:

* ``well_known_router`` — mounted at the application ROOT, serving the RFC 8414
  authorization-server metadata and the public JWKS. These are unauthenticated
  discovery documents.
* ``oauth_router`` — mounted under the API prefix at ``oauth_prefix``, serving
  the token, dynamic-client-registration, and revocation endpoints. These are
  client-authenticated (or public), never bearer-gated. The ``/authorize``
  endpoint is the exception: its GET (consent page) and POST (approve/deny)
  handlers gate on the *authenticated session user* via ``Depends(get_current_user)``.
  The session user's effective permissions — resolved server-side, NEVER from
  client/request input — are what the authorization server intersects with the
  requested scope, so a token can never carry a scope the resource owner lacks.

A single :class:`~jvspatial.api.auth.oauth.server.JvSpatialAuthorizationServer`
is built once per call and shared by the handlers via closure. Handlers convert
the Starlette ``Request`` into a
:class:`~jvspatial.api.auth.oauth.requests.StarletteOAuth2Request` and translate
the server's :class:`~jvspatial.api.auth.oauth.server.OAuthHttpResponse` into a
Starlette response via :func:`_to_response`.
"""

from __future__ import annotations

from html import escape
from typing import Any, Callable, Optional
from urllib.parse import urlencode, urlparse, urlunparse

from authlib.oauth2 import OAuth2Error
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from jvspatial.api.auth.oauth import keys
from jvspatial.api.auth.oauth.metadata import build_as_metadata
from jvspatial.api.auth.oauth.requests import (
    StarletteOAuth2Request,
    build_oauth2_request,
)
from jvspatial.api.auth.oauth.server import (
    OAuthHttpResponse,
    build_authorization_server,
)
from jvspatial.api.auth.rbac import get_effective_permissions
from jvspatial.api.constants import APIRoutes


def _to_response(holder: OAuthHttpResponse) -> Response:
    """Translate an :class:`OAuthHttpResponse` into a Starlette response.

    When the holder carries a ``location`` header it is a redirect (the
    authorize flow); otherwise it is rendered as JSON. Remaining headers
    (e.g. ``cache-control``, ``pragma``, ``www-authenticate``) are carried
    over onto the response, with ``location`` and ``content-type`` handled by
    the response class itself.

    Args:
        holder: The framework-agnostic response produced by the AS.

    Returns:
        A :class:`RedirectResponse` for redirects, else a :class:`JSONResponse`.
    """
    location = holder.headers.get("location")
    extra_headers = {
        k: v
        for k, v in holder.headers.items()
        if k not in ("location", "content-type", "content-length")
    }
    if location:
        return RedirectResponse(
            url=location,
            status_code=holder.status_code,
            headers=extra_headers or None,
        )
    body = holder.body_json if holder.body_json is not None else {}
    return JSONResponse(
        content=body,
        status_code=holder.status_code,
        headers=extra_headers or None,
    )


#: Authorize-request parameters re-carried through the consent form so the
#: approve POST reconstructs the exact authorization request the GET validated.
_AUTHORIZE_PARAMS = (
    "response_type",
    "client_id",
    "redirect_uri",
    "scope",
    "state",
    "code_challenge",
    "code_challenge_method",
)


def _redirect_with_query(redirect_uri: str, params: dict[str, str]) -> RedirectResponse:
    """Return a 302 to *redirect_uri* with *params* merged into its query string.

    Empty-valued params are dropped so a missing ``state`` is not echoed back as
    ``state=``.
    """
    parts = urlparse(redirect_uri)
    query = urlencode({k: v for k, v in params.items() if v})
    merged = f"{parts.query}&{query}" if parts.query else query
    return RedirectResponse(
        url=urlunparse(parts._replace(query=merged)), status_code=302
    )


def _render_consent_page(
    client_name: str, scopes: list[str], form: dict[str, str]
) -> str:
    """Render the default consent HTML (approve/deny form re-carrying OAuth params).

    The client name and each requested scope are HTML-escaped. The authorize
    request parameters are re-emitted as hidden inputs so the approve/deny POST
    reconstructs the same request; the submit buttons carry ``decision``.
    """
    name = escape(client_name or form.get("client_id", "Unknown client"))
    scope_items = (
        "".join(f"<li><code>{escape(s)}</code></li>" for s in scopes)
        or "<li><em>(no scopes requested)</em></li>"
    )
    hidden = "".join(
        f'<input type="hidden" name="{escape(k)}" value="{escape(v)}">'
        for k, v in form.items()
        if k in _AUTHORIZE_PARAMS and v
    )
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        "<title>Authorize</title></head><body>"
        f"<h1>Authorize {name}</h1>"
        f"<p><strong>{name}</strong> is requesting access with these scopes:</p>"
        f"<ul>{scope_items}</ul>"
        '<form method="post">'
        f"{hidden}"
        '<button type="submit" name="decision" value="approve">Approve</button>'
        '<button type="submit" name="decision" value="deny">Deny</button>'
        "</form></body></html>"
    )


def build_oauth_routers(
    auth_config: Any,
    get_current_user: Optional[Callable[..., Any]] = None,
) -> tuple[APIRouter, APIRouter]:
    """Build the OAuth ``(oauth_router, well_known_router)`` pair.

    The authorization server is constructed once and captured by the handler
    closures so every request shares the same grant/endpoint registrations and
    signing-key access.

    Args:
        auth_config: The active :class:`~jvspatial.api.auth.config.AuthConfig`
            (``oauth_issuer_url``, ``oauth_prefix``, ``oauth_supported_scopes``,
            ``role_permission_mapping``).
        get_current_user: The session-user dependency from the auth configurator.
            Required for the ``/authorize`` consent flow — the GET/POST handlers
            depend on it to resolve the bearer-authenticated resource owner whose
            permissions bound the granted scope. When ``None`` (e.g. a caller
            that does not wire it), ``/authorize`` returns 503.

    Returns:
        ``(oauth_router, well_known_router)`` — the API-prefixed OAuth router and
        the root-mounted discovery router. The caller mounts the OAuth router
        under :attr:`APIRoutes.PREFIX` and the well-known router at root.
    """
    issuer = auth_config.oauth_issuer_url
    # resource defaults to the issuer for now; per-request RFC 8707 resource
    # binding (token audience varies per protected resource) is a later item.
    server = build_authorization_server(issuer=issuer, resource=issuer)

    well_known_router = APIRouter(tags=["OAuth"])

    @well_known_router.get("/.well-known/oauth-authorization-server")
    async def authorization_server_metadata() -> dict:
        """Serve the RFC 8414 authorization-server metadata document."""
        return build_as_metadata(
            issuer=issuer,
            prefix=auth_config.oauth_prefix,
            scopes_supported=list(auth_config.oauth_supported_scopes or []),
            api_prefix=APIRoutes.PREFIX,
        )

    @well_known_router.get("/.well-known/jwks.json")
    async def jwks() -> dict:
        """Serve the public JWKS (RFC 7517).

        Ensures a signing key exists before building the set so the document
        is never empty even if the startup hook has not yet run (e.g. the app
        is exercised without entering its lifespan, as in-process test clients
        do). ``ensure_signing_key`` is idempotent.
        """
        await keys.ensure_signing_key()
        return await keys.build_jwks()

    oauth_router = APIRouter(prefix=auth_config.oauth_prefix, tags=["OAuth"])

    @oauth_router.post("/token")
    async def token(request: Request) -> Response:
        """RFC 6749 token endpoint (authorization_code + refresh_token grants)."""
        req = await build_oauth2_request(request)
        return _to_response(await server.async_create_token_response(req))

    @oauth_router.post("/register")
    async def register(request: Request) -> Response:
        """RFC 7591 dynamic client registration endpoint.

        DCR bodies arrive as JSON (RFC 7591 §3.1), not
        ``application/x-www-form-urlencoded``.  We read the JSON payload first,
        then build a minimal ``StarletteOAuth2Request`` that carries the correct
        method/URI/headers without attempting a second form-body parse on the
        already-consumed stream.
        """
        body = await request.json()
        req = StarletteOAuth2Request(
            method=request.method,
            uri=str(request.url),
            query=dict(request.query_params),
            form={},
            headers=dict(request.headers),
        )
        return _to_response(await server.async_register_client(req, body))

    @oauth_router.post("/revoke")
    async def revoke(request: Request) -> Response:
        """RFC 7009 token revocation endpoint."""
        req = await build_oauth2_request(request)
        return _to_response(await server.async_revoke_token(req))

    if get_current_user is None:
        # No session-user dependency wired — the consent flow cannot resolve the
        # resource owner, so /authorize is unavailable rather than insecure.
        @oauth_router.api_route("/authorize", methods=["GET", "POST"])
        async def authorize_unavailable() -> Response:
            """Return 503 when the consent flow has no session-user dependency."""
            return JSONResponse({"error": "temporarily_unavailable"}, status_code=503)

        return oauth_router, well_known_router

    @oauth_router.get("/authorize", response_class=HTMLResponse)
    async def authorize_get(
        request: Request,
        user: Any = Depends(get_current_user),  # noqa: B008
    ) -> Response:
        """Render the consent page for an authenticated resource owner.

        The bearer-authenticated session user is resolved by ``get_current_user``
        (401 when no/invalid bearer). The request is validated through the AS's
        :meth:`async_get_consent_grant`; on success the validated client name and
        client-filtered scope are rendered into an approve/deny form that
        re-carries the OAuth parameters. A request that fails validation yields a
        400 error page rather than a redirect — the supplied ``redirect_uri`` has
        not been proven to belong to a registered client, so honouring it would
        be an open-redirect (see :func:`_consent_error_response`).

        An optional ``auth_config.oauth_consent_handler`` may override rendering;
        it receives ``(request, client, scopes, form)`` and returns HTML.
        """
        req = await build_oauth2_request(request)
        try:
            grant = await server.async_get_consent_grant(req, end_user={"id": user.id})
        except OAuth2Error as error:
            return _consent_error_response(error)

        client = grant.client.client  # OAuthClientAdapter -> OAuthClient record
        granted_scope = grant.request.scope or req.args.get("scope", "")
        scopes = granted_scope.split()
        form = dict(req.args)

        consent_handler = getattr(auth_config, "oauth_consent_handler", None)
        if consent_handler is not None:
            html = consent_handler(request, client, scopes, form)
            return HTMLResponse(html)
        return HTMLResponse(_render_consent_page(client.client_name, scopes, form))

    @oauth_router.post("/authorize")
    async def authorize_post(
        request: Request,
        user: Any = Depends(get_current_user),  # noqa: B008
    ) -> Response:
        """Complete the consent decision for an authenticated resource owner.

        On *approve* the ``grant_user`` is built ONLY from the server-resolved
        session user: its id, and its effective permissions computed via
        :func:`get_effective_permissions` over the user's roles/permissions and
        the configured ``role_permission_mapping``. The AS intersects the
        requested scope with those permissions (scope ∩ permissions), so the
        issued token can never carry a scope the resource owner lacks — the
        permission set is NEVER read from client or request input.

        On *deny* (or any non-approve decision) the client is redirected back to
        its ``redirect_uri`` with ``error=access_denied`` (RFC 6749 §4.1.2.1),
        carrying ``state`` when present, and no code is issued.
        """
        # Coerce to a str->str dict: the consent form carries only text fields
        # (no file uploads), and StarletteOAuth2Request expects plain strings.
        form = {k: v for k, v in (await request.form()).items() if isinstance(v, str)}
        decision = form.get("decision", "deny")
        redirect_uri = form.get("redirect_uri", "")
        state = form.get("state", "")

        if decision != "approve":
            return _redirect_with_query(
                redirect_uri, {"error": "access_denied", "state": state}
            )

        # TRUST BOUNDARY: permissions come ONLY from the authenticated session
        # user resolved server-side — never from the request/form.
        permissions = sorted(
            get_effective_permissions(
                getattr(user, "roles", None) or [],
                getattr(user, "permissions", None) or [],
                getattr(auth_config, "role_permission_mapping", None) or {},
            )
        )
        grant_user = {"id": user.id, "permissions": permissions}

        req = StarletteOAuth2Request(
            method="POST",
            uri=str(request.url),
            query=dict(request.query_params),
            form=form,
            headers=dict(request.headers),
        )
        return _to_response(
            await server.async_create_authorization_response(req, grant_user=grant_user)
        )

    return oauth_router, well_known_router


def _consent_error_response(error: OAuth2Error) -> Response:
    """Render an authorize-validation failure as a 400 HTML page.

    The supplied ``redirect_uri`` cannot be trusted to belong to a registered
    client (the validation error may itself BE an invalid redirect_uri / unknown
    client), so we do NOT open-redirect: a 400 page describing the error is
    returned. This is the conservative reading of RFC 6749 §4.1.2.1 for the
    validation-failure path.
    """
    description = escape(
        error.get_error_description() or error.error or "invalid_request"
    )
    body = (
        '<!doctype html><html><head><meta charset="utf-8">'
        "<title>Authorization error</title></head><body>"
        f"<h1>Authorization request rejected</h1><p>{description}</p>"
        "</body></html>"
    )
    return HTMLResponse(body, status_code=400)


__all__ = ["build_oauth_routers"]
