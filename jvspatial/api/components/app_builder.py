"""App Builder component for creating and configuring FastAPI applications.

This module provides the AppBuilder class that handles the creation and configuration
of FastAPI application instances, following the single responsibility principle.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import FastAPI

from jvspatial.api.config import ServerConfig
from jvspatial.api.constants import LogIcons


class AppBuilder:
    """Component responsible for building and configuring FastAPI applications.

    This class handles the creation of FastAPI instances with proper configuration,
    following the single responsibility principle by focusing solely on app creation.

    Attributes:
        config: Server configuration instance
        _logger: Logger instance for app building operations
    """

    def __init__(self, config: ServerConfig):
        """Initialize the AppBuilder.

        Args:
            config: Server configuration instance
        """
        self.config = config
        self._logger = logging.getLogger(__name__)

    def create_app(self, lifespan: Optional[Any] = None) -> FastAPI:
        """Create a FastAPI application instance.

        Args:
            lifespan: Optional lifespan context manager for startup/shutdown

        Returns:
            Configured FastAPI application instance
        """
        app_kwargs = {
            "title": self.config.title,
            "description": self.config.description,
            "version": self.config.version,
            "docs_url": self.config.docs_url,
            "redoc_url": self.config.redoc_url,
            "debug": self.config.debug,
        }

        # Add lifespan if provided
        if lifespan is not None:
            app_kwargs["lifespan"] = lifespan

        app = FastAPI(**app_kwargs)

        self._logger.info(
            f"{LogIcons.SUCCESS} FastAPI app created: {self.config.title} v{self.config.version}"
        )

        return app

    def configure_openapi_security(
        self, app: FastAPI, has_auth_endpoints: bool = False
    ) -> None:
        """Configure OpenAPI security schemes if auth endpoints exist.

        Args:
            app: FastAPI application instance to configure
            has_auth_endpoints: Whether authenticated endpoints exist
        """
        if not has_auth_endpoints:
            return

        try:
            # Configure OpenAPI security if needed
            from jvspatial.api.auth.openapi_config import configure_openapi_security

            configure_openapi_security(app)
            self._logger.debug(
                f"{LogIcons.SUCCESS} OpenAPI security schemes configured"
            )
        except ImportError as e:
            self._logger.warning(
                f"{LogIcons.WARNING} Could not configure OpenAPI security: {e}"
            )

    def register_core_routes(
        self, app: FastAPI, graph_context: Optional[Any] = None
    ) -> None:
        """Register core routes (health, root).

        Args:
            app: FastAPI application instance to configure
            graph_context: Optional GraphContext for health checks
        """
        from fastapi.responses import JSONResponse

        from jvspatial.core.entities import Root

        # Add default health check endpoint
        @app.get("/health", response_model=None)
        async def health_check() -> Dict[str, Any]:
            """Health check endpoint."""
            try:
                # Test database connectivity through GraphContext
                if graph_context:
                    # Use explicit GraphContext
                    root = await graph_context.get(Root, "n:Root:root")
                    if not root:
                        root = await graph_context.create(Root)
                else:
                    # Use default GraphContext behavior
                    root = await Root.get("n:Root:root")
                    if not root:
                        root = await Root.create()

                return {
                    "status": "healthy",
                    "database": "connected",
                    "root_node": root.id,
                    "service": self.config.title,
                    "version": self.config.version,
                }
            except Exception as e:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "unhealthy",
                        "error": str(e),
                        "service": self.config.title,
                        "version": self.config.version,
                    },
                )

        # Add root endpoint
        @app.get("/")
        async def root_info() -> Dict[str, Any]:
            """Root endpoint with API information."""
            return {
                "service": self.config.title,
                "description": self.config.description,
                "version": self.config.version,
                "docs": self.config.docs_url,
                "health": "/health",
            }

        self._logger.debug(f"{LogIcons.SUCCESS} Core routes registered")


__all__ = ["AppBuilder"]
