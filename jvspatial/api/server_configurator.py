"""Server configuration logic extracted from Server for maintainability.

Handles exception handlers, error logging context, rate limiting,
auth middleware, and OpenAPI security configuration.
"""

import contextlib
from typing import TYPE_CHECKING, Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from jvspatial.api.components.error_handler import APIErrorHandler
from jvspatial.api.constants import APIRoutes

if TYPE_CHECKING:
    from jvspatial.api.server import Server


class ServerConfigurator:
    """Configures FastAPI app with exception handlers, middleware, and OpenAPI security."""

    def __init__(self, server: "Server") -> None:
        self._server = server

    def configure_all(self, app: FastAPI) -> None:
        """Apply all server configuration to the FastAPI app."""
        self._configure_error_logging_context_middleware(app)
        self._configure_rate_limit_middleware(app)
        self._configure_auth_middleware(app)
        self._configure_exception_handlers(app)

    def _configure_exception_handlers(self, app: FastAPI) -> None:
        """Configure all exception handlers using the unified APIErrorHandler."""
        server = self._server
        for exc_class, handler in server._exception_handlers.items():
            app.add_exception_handler(exc_class, handler)

        from jvspatial.exceptions import JVSpatialAPIException

        @app.exception_handler(JVSpatialAPIException)
        async def jvspatial_exception_handler(
            request: Request, exc: JVSpatialAPIException
        ) -> JSONResponse:
            return await APIErrorHandler.handle_exception(request, exc)

        from fastapi import HTTPException

        @app.exception_handler(HTTPException)
        async def http_exception_handler(
            request: Request, exc: HTTPException
        ) -> JSONResponse:
            return await APIErrorHandler.handle_exception(request, exc)

        @app.exception_handler(Exception)
        async def global_exception_handler(
            request: Request, exc: Exception
        ) -> JSONResponse:
            return await APIErrorHandler.handle_exception(request, exc)

        from jvspatial.api.components.logging_config import LoggingConfigurator

        LoggingConfigurator.configure_exception_logging()

    def _configure_error_logging_context_middleware(self, app: FastAPI) -> None:
        """Configure middleware to clean up error logging context after each request."""
        from starlette.middleware.base import BaseHTTPMiddleware

        class ErrorLoggingContextMiddleware(BaseHTTPMiddleware):
            """Prevents memory leaks and cross-request pollution by clearing context.

            Clears _logged_error_responses after each request. Required because the
            error handler uses contextvars for request-scoped tracking.
            """

            async def dispatch(self, request: Request, call_next):
                from jvspatial.api.components.error_handler import (
                    _logged_error_responses,
                )

                with contextlib.suppress(Exception):
                    _logged_error_responses.set(set())

                try:
                    return await call_next(request)
                finally:
                    with contextlib.suppress(Exception):
                        _logged_error_responses.set(set())

        app.add_middleware(ErrorLoggingContextMiddleware)

    def _configure_rate_limit_middleware(self, app: FastAPI) -> None:
        """Configure rate limiting middleware if rate limiting is enabled."""
        server = self._server
        if not server.config.rate_limit.rate_limit_enabled:
            return

        try:
            from jvspatial.api.middleware.rate_limit import RateLimitMiddleware
            from jvspatial.api.middleware.rate_limit_backend import (
                MemoryRateLimitBackend,
            )

            rate_limits = self._build_rate_limit_config()
            backend = (
                getattr(server.config, "rate_limit_backend", None)
                or MemoryRateLimitBackend()
            )

            app.add_middleware(
                RateLimitMiddleware,
                config=rate_limits,
                default_limit=server.config.rate_limit.rate_limit_default_requests,
                default_window=server.config.rate_limit.rate_limit_default_window,
                backend=backend,
            )

            server._logger.debug(
                f"🔒 Rate limiting enabled: {len(rate_limits)} endpoints configured, "
                f"default {server.config.rate_limit.rate_limit_default_requests} req/"
                f"{server.config.rate_limit.rate_limit_default_window}s"
            )
        except ImportError as e:
            server._logger.warning(f"Could not add rate limiting middleware: {e}")

    def _add_rate_limits_from_registry_items(
        self,
        registry_items: Any,
        rate_limits: Dict[str, Any],
        api_prefix: str,
    ) -> None:
        """Add rate limit config from registry (target_obj, endpoint_info) pairs."""
        from jvspatial.api.middleware.rate_limit import RateLimitConfig

        for target_obj, endpoint_info in registry_items:
            if not endpoint_info or not hasattr(endpoint_info, "path"):
                continue
            path = endpoint_info.path
            endpoint_config = getattr(target_obj, "_jvspatial_endpoint_config", None)
            if not endpoint_config or not endpoint_config.get("rate_limit"):
                continue
            rate_limit_dict = endpoint_config["rate_limit"]
            full_path = (
                f"{api_prefix}{path}" if not path.startswith(api_prefix) else path
            )
            rate_limits[full_path] = RateLimitConfig(
                requests=rate_limit_dict.get("requests", 60),
                window=rate_limit_dict.get("window", 60),
            )

    def _build_rate_limit_config(self) -> Dict[str, Any]:
        """Build rate limit configuration from endpoint registry and decorator configs."""
        from jvspatial.api.middleware.rate_limit import RateLimitConfig

        server = self._server
        rate_limits: Dict[str, RateLimitConfig] = {}
        api_prefix = APIRoutes.PREFIX
        registry = server._endpoint_registry

        self._add_rate_limits_from_registry_items(
            registry._function_registry.items(), rate_limits, api_prefix
        )
        self._add_rate_limits_from_registry_items(
            registry._walker_registry.items(), rate_limits, api_prefix
        )

        for path, override in server.config.rate_limit.rate_limit_overrides.items():
            full_path = (
                f"{api_prefix}{path}" if not path.startswith(api_prefix) else path
            )
            rate_limits[full_path] = RateLimitConfig(
                requests=override.get(
                    "requests", server.config.rate_limit.rate_limit_default_requests
                ),
                window=override.get(
                    "window", server.config.rate_limit.rate_limit_default_window
                ),
            )

        return rate_limits

    def _configure_auth_middleware(self, app: FastAPI) -> None:
        """Configure authentication middleware if authentication is enabled."""
        server = self._server
        if not server.config.auth.auth_enabled or not server._auth_config:
            return

        try:
            from jvspatial.api.components.auth_middleware import (
                AuthenticationMiddleware,
            )

            app.add_middleware(
                AuthenticationMiddleware, auth_config=server._auth_config, server=server
            )
        except ImportError as e:
            server._logger.warning(f"Could not add authentication middleware: {e}")
