"""HTTP routers mounting the OAuth 2.1 authorization server.

:func:`build_oauth_routers` constructs two FastAPI routers, gated by the caller
on :attr:`AuthConfig.oauth_enabled`:

* ``well_known_router`` — mounted at the application ROOT, serving the RFC 8414
  authorization-server metadata and the public JWKS. These are unauthenticated
  discovery documents.
* ``oauth_router`` — mounted under the API prefix at ``oauth_prefix``, serving
  the token, dynamic-client-registration, and revocation endpoints (plus a
  placeholder ``/authorize`` whose consent/session body is completed in a later
  task). These endpoints are client-authenticated (or public), never bearer-gated.

A single :class:`~jvspatial.api.auth.oauth.server.JvSpatialAuthorizationServer`
is built once per call and shared by the handlers via closure. Handlers convert
the Starlette ``Request`` into a
:class:`~jvspatial.api.auth.oauth.requests.StarletteOAuth2Request` and translate
the server's :class:`~jvspatial.api.auth.oauth.server.OAuthHttpResponse` into a
Starlette response via :func:`_to_response`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from jvspatial.api.auth.oauth import keys
from jvspatial.api.auth.oauth.metadata import build_as_metadata
from jvspatial.api.auth.oauth.requests import build_oauth2_request
from jvspatial.api.auth.oauth.server import (
    OAuthHttpResponse,
    build_authorization_server,
)


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


def build_oauth_routers(auth_config: Any) -> tuple[APIRouter, APIRouter]:
    """Build the OAuth ``(oauth_router, well_known_router)`` pair.

    The authorization server is constructed once and captured by the handler
    closures so every request shares the same grant/endpoint registrations and
    signing-key access.

    Args:
        auth_config: The active :class:`~jvspatial.api.auth.config.AuthConfig`
            (``oauth_issuer_url``, ``oauth_prefix``, ``oauth_supported_scopes``).

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
        """RFC 7591 dynamic client registration endpoint."""
        body = await request.json()
        req = await build_oauth2_request(request)
        return _to_response(await server.async_register_client(req, body))

    @oauth_router.post("/revoke")
    async def revoke(request: Request) -> Response:
        """RFC 7009 token revocation endpoint."""
        req = await build_oauth2_request(request)
        return _to_response(await server.async_revoke_token(req))

    @oauth_router.get("/authorize")
    async def authorize() -> HTMLResponse:
        """Placeholder authorize endpoint.

        Consent rendering and session-user permission resolution are completed
        in a later task; this stub keeps the route mounted (and discoverable in
        the AS metadata) without 404-ing.
        """
        return HTMLResponse("<html><body>consent</body></html>")

    return oauth_router, well_known_router


__all__ = ["build_oauth_routers"]
