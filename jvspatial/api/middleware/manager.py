"""Middleware management service for FastAPI applications.

This module provides centralized middleware configuration and management,
including CORS, webhook middleware, security headers, and custom middleware registration.

Note: Auth middleware is configured by Server (not here) to control ordering:
rate limit -> auth. See server._configure_auth_middleware().
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from jvspatial.api.constants import LogIcons

if TYPE_CHECKING:
    from jvspatial.api.server import Server


# Strict default — applied to application routes.
_DEFAULT_CSP = "default-src 'self'; frame-ancestors 'none'"

# Relaxed CSP for FastAPI's bundled Swagger UI / ReDoc pages. Those pages
# pull swagger-ui-dist + redoc bundles from cdn.jsdelivr.net and a favicon
# from fastapi.tiangolo.com, plus run a small inline bootstrap script. The
# strict default blocks all of that and the docs render blank. Scoped to
# documentation paths only — application routes keep the strict policy.
#
# The single production knob is `JVSPATIAL_DOCS_DISABLED=1` (read at app
# build time in `AppBuilder.create_app`); that flag unpublishes /docs,
# /redoc, and /openapi.json entirely so this CSP never matters in prod.
# When docs ARE published (dev / staging) this relaxation makes Swagger
# UI render — no further env knobs needed.
_DOCS_CSP = (
    "default-src 'self' https://cdn.jsdelivr.net; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: blob: https://cdn.jsdelivr.net https://fastapi.tiangolo.com; "
    "font-src 'self' data: https://cdn.jsdelivr.net; "
    "connect-src 'self' https://cdn.jsdelivr.net; "
    "worker-src 'self' blob:; "
    "object-src 'none'"
)

# Documentation-page path prefixes. Both `/docs` and `/redoc` may carry
# trailing path segments (Swagger's oauth2-redirect, ReDoc assets); match
# exact path or `<prefix>/...`. `/openapi.json` is the JSON spec consumed
# by both UIs — it's CSP-irrelevant on its own but we group it for symmetry.
_DOCS_PATH_PREFIXES = ("/docs", "/redoc", "/openapi.json")


def _is_docs_path(path: str) -> bool:
    """True for FastAPI Swagger / ReDoc / OpenAPI surfaces."""
    return any(path == p or path.startswith(p + "/") for p in _DOCS_PATH_PREFIXES)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware that adds security headers to all responses.

    Headers applied:
    - X-Content-Type-Options: nosniff (MIME sniffing prevention)
    - X-Frame-Options: DENY (clickjacking prevention)
    - Content-Security-Policy: strict on app routes; a relaxed variant
      that permits ``cdn.jsdelivr.net`` is emitted for ``/docs``,
      ``/redoc``, and ``/openapi.json`` so FastAPI's bundled Swagger UI
      and ReDoc pages render. Without this scoped relaxation the docs
      load blank because the strict default blocks the CDN-hosted JS/CSS.
      For production lockdown set ``JVSPATIAL_DOCS_DISABLED=1`` —
      ``AppBuilder.create_app`` then unpublishes the docs surface entirely
      and this CSP never applies (no routes registered).
    - Strict-Transport-Security: max-age=31536000; includeSubDomains (if enabled)

    HSTS is only applied when the server configures hsts_enabled=True
    (off by default in development, on in production).
    """

    def __init__(self, app, hsts_enabled: bool = False):
        super().__init__(app)
        self._hsts_enabled = hsts_enabled

    async def dispatch(self, request, call_next):
        """Process request and add security headers to response."""
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            _DOCS_CSP if _is_docs_path(request.url.path) else _DEFAULT_CSP
        )
        if self._hsts_enabled:
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
        return response


class MiddlewareManager:
    """Service for managing FastAPI middleware configuration.

    This service centralizes all middleware configuration logic, including
    CORS setup, webhook middleware, and custom user-defined middleware.
    It follows the single responsibility principle by focusing solely on
    middleware management.

    Attributes:
        server: Reference to the Server instance
        _custom_middleware: List of custom middleware configurations
        _logger: Logger instance for middleware operations
    """

    def __init__(self, server: "Server") -> None:
        """Initialize the MiddlewareManager.

        Args:
            server: Server instance that owns this middleware manager
        """
        self.server = server
        self._custom_middleware: List[Dict[str, Any]] = []
        self._logger = logging.getLogger(__name__)

    async def add_middleware(self, middleware_type: str, func: Callable) -> None:
        """Register custom middleware for later application.

        Args:
            middleware_type: Type of middleware ("http" or "websocket")
            func: Middleware function to register
        """
        self._custom_middleware.append(
            {"func": func, "middleware_type": middleware_type}
        )
        self._logger.debug(
            f"{LogIcons.REGISTERED} Custom middleware registered: "
            f"{func.__name__} ({middleware_type})"
        )

    def configure_all(self, app: FastAPI) -> None:
        """Configure all middleware on the FastAPI app.

        This orchestrator method applies middleware in the correct order:
        1. Security headers (if enabled)
        2. CORS middleware (if enabled)
        3. Webhook middleware (if webhook endpoints exist)
        4. File storage endpoints (if enabled)
        5. Custom user-defined middleware

        Auth middleware is configured by Server separately (rate limit -> auth).

        Works in both sync and async contexts.

        Args:
            app: FastAPI application instance to configure
        """
        self._configure_security_headers(app)
        self._configure_cors(app)
        self._configure_webhook_middleware(app)
        self._configure_file_storage(app)
        self._configure_custom_middleware(app)

    def _configure_security_headers(self, app: FastAPI) -> None:
        """Add security headers middleware if enabled.

        Sets X-Content-Type-Options, X-Frame-Options, Content-Security-Policy,
        and optionally Strict-Transport-Security headers.

        Args:
            app: FastAPI application instance
        """
        if not self.server.config.security.security_headers_enabled:
            return

        hsts_enabled = getattr(self.server.config.security, "hsts_enabled", False)
        app.add_middleware(SecurityHeadersMiddleware, hsts_enabled=hsts_enabled)
        self._logger.debug(f"{LogIcons.SUCCESS} Security headers middleware configured")

    def _configure_cors(self, app: FastAPI) -> None:
        """Configure CORS middleware if enabled.

        Adds CORS middleware with settings from server configuration,
        allowing cross-origin requests based on configured origins,
        methods, and headers.

        Args:
            app: FastAPI application instance
        """
        if not self.server.config.cors.cors_enabled:
            return

        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.server.config.cors.cors_origins,
            allow_methods=self.server.config.cors.cors_methods,
            allow_headers=self.server.config.cors.cors_headers,
            allow_credentials=True,
        )
        self._logger.debug(
            f"{LogIcons.SUCCESS} CORS middleware configured with "
            f"origins: {self.server.config.cors.cors_origins}"
        )

    def _configure_webhook_middleware(self, app: FastAPI) -> None:
        """Configure webhook middleware if webhook endpoints exist.

        Scans the endpoint registry for webhook-enabled endpoints and
        adds the webhook middleware if any are found. This middleware
        handles webhook payload injection into request context.

        Args:
            app: FastAPI application instance
        """
        has_webhook_endpoints = self._detect_webhook_endpoints()

        if not has_webhook_endpoints:
            # No webhook endpoints - webhook middleware skipped
            return

        try:
            from jvspatial.api.integrations.webhooks.middleware import (
                add_webhook_middleware,
            )

            add_webhook_middleware(app, server=self.server)
            self._logger.info(f"{LogIcons.WEBHOOK} Webhook middleware added to server")
        except ImportError as e:
            self._logger.warning(
                f"{LogIcons.WARNING} Could not add webhook middleware: {e}"
            )

    def _detect_webhook_endpoints(self) -> bool:
        """Detect if any registered endpoints require webhook support.

        Returns:
            True if webhook endpoints are found, False otherwise
        """
        # Check walker endpoints from registry
        registry = self.server._endpoint_registry

        # Check walker endpoints (config-based approach)
        for walker_class in registry._walker_registry.keys():
            endpoint_config = getattr(walker_class, "_jvspatial_endpoint_config", None)
            if endpoint_config and endpoint_config.get("webhook", False):
                return True

        # Check function endpoints from registry (config-based approach)
        for func in registry._function_registry.keys():
            endpoint_config = getattr(func, "_jvspatial_endpoint_config", None)
            if endpoint_config and endpoint_config.get("webhook", False):
                return True

        return False

    def _configure_file_storage(self, app: FastAPI) -> None:
        """Configure file storage endpoints if enabled.

        Registers file storage and proxy endpoints when file storage
        is enabled in the server configuration.

        Args:
            app: FastAPI application instance
        """
        if not self.server.config.file_storage.file_storage_enabled:
            return

        if self.server._file_storage_service is None:
            self._logger.error(f"{LogIcons.ERROR} File storage service not initialized")
            return

        from jvspatial.api.services.file_storage import FileStorageService

        FileStorageService.register_endpoints(app, self.server._file_storage_service)
        self._logger.info(f"{LogIcons.STORAGE} File storage endpoints registered")

    def _configure_custom_middleware(self, app: FastAPI) -> None:
        """Configure user-defined custom middleware.

        Applies all registered custom middleware to the application
        in the order they were registered.

        Args:
            app: FastAPI application instance
        """
        if not self._custom_middleware:
            return

        for middleware_config in self._custom_middleware:
            app.middleware(middleware_config["middleware_type"])(
                middleware_config["func"]
            )
            self._logger.debug(
                f"{LogIcons.SUCCESS} Applied custom middleware: "
                f"{middleware_config['func'].__name__}"
            )

        self._logger.info(
            f"{LogIcons.SUCCESS} Configured {len(self._custom_middleware)} "
            f"custom middleware"
        )
