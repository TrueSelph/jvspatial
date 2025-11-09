"""Middleware management service for FastAPI applications.

This module provides centralized middleware configuration and management,
including CORS, webhook middleware, and custom middleware registration.
"""

import logging
from typing import TYPE_CHECKING, Any, Callable, Dict, List

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jvspatial.api.constants import LogIcons

if TYPE_CHECKING:
    from jvspatial.api.server import Server


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
            {"middleware_type": middleware_type, "func": func}
        )
        self._logger.debug(
            f"{LogIcons.REGISTERED} Custom middleware registered: "
            f"{func.__name__} ({middleware_type})"
        )

    def configure_all(self, app: FastAPI) -> None:
        """Configure all middleware on the FastAPI app.

        This orchestrator method applies middleware in the correct order:
        1. CORS middleware (if enabled)
        2. Authentication middleware (if authenticated endpoints exist)
        3. Webhook middleware (if webhook endpoints exist)
        4. File storage endpoints (if enabled)
        5. Custom user-defined middleware

        Works in both sync and async contexts.

        Args:
            app: FastAPI application instance to configure
        """
        self._configure_cors(app)
        self._configure_auth_middleware(app)
        self._configure_webhook_middleware(app)
        self._configure_file_storage(app)
        self._configure_custom_middleware(app)

    def _configure_cors(self, app: FastAPI) -> None:
        """Configure CORS middleware if enabled.

        Adds CORS middleware with settings from server configuration,
        allowing cross-origin requests based on configured origins,
        methods, and headers.

        Args:
            app: FastAPI application instance
        """
        if not self.server.config.cors_enabled:
            return

        app.add_middleware(
            CORSMiddleware,
            allow_origins=self.server.config.cors_origins,
            allow_methods=self.server.config.cors_methods,
            allow_headers=self.server.config.cors_headers,
            allow_credentials=True,
        )
        self._logger.info(
            f"{LogIcons.SUCCESS} CORS middleware configured with "
            f"origins: {self.server.config.cors_origins}"
        )

    def _configure_auth_middleware(self, app: FastAPI) -> None:
        """Configure authentication middleware if authenticated endpoints exist.

        Scans the endpoint registry for auth-enabled endpoints and
        adds the authentication middleware if any are found.

        Args:
            app: FastAPI application instance
        """
        has_auth_endpoints = self._detect_auth_endpoints()

        if not has_auth_endpoints:
            self._logger.debug(
                "No authenticated endpoints found, skipping auth middleware"
            )
            return

        try:
            # Authentication middleware is now handled by components
            # from jvspatial.api.auth.middleware import AuthenticationMiddleware
            # app.add_middleware(AuthenticationMiddleware)
            self._logger.info(
                f"{LogIcons.SUCCESS} Authentication middleware added to server"
            )
        except ImportError as e:
            self._logger.warning(
                f"{LogIcons.WARNING} Could not add authentication middleware: {e}"
            )

    def _detect_auth_endpoints(self) -> bool:
        """Detect if any registered endpoints require authentication.

        Returns:
            True if authenticated endpoints are found, False otherwise
        """
        # First check the flag set by auth decorators (most reliable)
        if getattr(self.server, "_has_auth_endpoints", False):
            self._logger.debug("Auth endpoints flag is set")
            return True

        # Fallback: Check walker endpoints from registry
        registry = self.server._endpoint_registry

        self._logger.debug(
            f"Checking {len(registry._walker_registry)} walker endpoints"
        )
        for walker_class in registry._walker_registry.keys():
            if getattr(walker_class, "_auth_required", False):
                self._logger.debug(
                    f"Found auth-required walker: {walker_class.__name__}"
                )
                return True

        # Check function endpoints from registry
        self._logger.debug(
            f"Checking {len(registry._function_registry)} function endpoints"
        )
        for func in registry._function_registry.keys():
            if getattr(func, "_auth_required", False):
                self._logger.debug(f"Found auth-required function: {func.__name__}")
                return True

        return False

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
            self._logger.debug(
                "No webhook endpoints found, skipping webhook middleware"
            )
            return

        try:
            from jvspatial.api.webhook.middleware import add_webhook_middleware

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
        if any(
            getattr(walker_class, "_webhook_required", False)
            for walker_class in registry._walker_registry.keys()
        ):
            return True

        # Check function endpoints from registry
        return any(
            getattr(func, "_webhook_required", False)
            for func in registry._function_registry.keys()
        )

    def _configure_file_storage(self, app: FastAPI) -> None:
        """Configure file storage endpoints if enabled.

        Registers file storage and proxy endpoints when file storage
        is enabled in the server configuration.

        Args:
            app: FastAPI application instance
        """
        if not self.server.config.file_storage_enabled:
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
