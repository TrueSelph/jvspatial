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
            # Configure OpenAPI tags order - ensure "App" appears after "default"
            # Tags are ordered by their appearance in this list
            "openapi_tags": [
                {"name": "default", "description": "Default API endpoints"},
                {"name": "App", "description": "Application-specific endpoints"},
            ],
        }

        # Add lifespan if provided
        if lifespan is not None:
            app_kwargs["lifespan"] = lifespan

        app = FastAPI(**app_kwargs)

        # Override the openapi() method to enforce tag ordering
        # This ensures "App" always appears after "default" in the OpenAPI schema
        from fastapi.openapi.utils import get_openapi

        def custom_openapi() -> Dict[str, Any]:
            """Custom OpenAPI schema generator with enforced tag ordering."""
            if app.openapi_schema:
                return app.openapi_schema

            # Generate the schema using get_openapi directly
            schema = get_openapi(
                title=app.title,
                version=app.version,
                description=app.description,
                routes=app.routes,
            )

            # Enforce tag ordering - ensure "App" appears after "default"
            # Collect all unique tags from the schema
            all_tags = set()
            for path_item in schema.get("paths", {}).values():
                for operation in path_item.values():
                    if isinstance(operation, dict) and "tags" in operation:
                        all_tags.update(operation["tags"])

            # Define tag order - "default" first, then "App", then others alphabetically
            tag_order = ["default", "App"]
            other_tags = sorted([tag for tag in all_tags if tag not in tag_order])
            ordered_tags = tag_order + other_tags

            # Create tag definitions in the correct order
            if "tags" not in schema:
                schema["tags"] = []

            tag_definitions = []
            for tag in ordered_tags:
                tag_def = {"name": tag}
                # Add description if we have it
                if tag == "default":
                    tag_def["description"] = "Default API endpoints"
                elif tag == "App":
                    tag_def["description"] = "Application-specific endpoints"
                tag_definitions.append(tag_def)

            schema["tags"] = tag_definitions

            # Cache the schema
            app.openapi_schema = schema
            return schema

        # Replace the openapi method
        app.openapi = custom_openapi

        self._logger.debug(
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
            # OpenAPI security configured (no log needed)
        except ImportError as e:
            self._logger.warning(
                f"{LogIcons.WARNING} Could not configure OpenAPI security: {e}"
            )

    def register_core_routes(
        self,
        app: FastAPI,
        graph_context: Optional[Any] = None,
        server: Optional[Any] = None,
    ) -> None:
        """Register core routes (health, root).

        Args:
            app: FastAPI application instance to configure
            graph_context: Optional GraphContext for health checks
            server: Optional Server instance for endpoint registration
        """
        from fastapi.responses import JSONResponse

        from jvspatial.core.entities import Root

        # Add default health check endpoint
        @app.get("/health", response_model=None)
        async def health_check() -> Dict[str, Any]:
            """Health check endpoint."""
            try:
                # Test database connectivity - Root.get() always returns singleton
                root = await Root.get()

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
            info = {
                "service": self.config.title,
                "description": self.config.description,
                "version": self.config.version,
                "docs": self.config.docs_url,
                "health": "/health",
            }
            if self.config.graph_endpoint_enabled:
                info["graph"] = "/api/graph"
            return info

        # Add graph visualization endpoint (optional)
        if self.config.graph_endpoint_enabled:
            self._register_graph_endpoint(app, graph_context, server)

        # Core routes registered (no log needed)

    def _register_graph_endpoint(
        self,
        app: FastAPI,
        graph_context: Optional[Any] = None,
        server: Optional[Any] = None,
    ) -> None:
        """Register graph visualization endpoint if enabled.

        Uses the @endpoint decorator and registers with the endpoint registry
        for proper authentication handling.

        Args:
            app: FastAPI application instance
            graph_context: Optional GraphContext for graph generation
            server: Optional Server instance for endpoint registration
        """
        from fastapi import HTTPException, Query
        from fastapi.responses import PlainTextResponse

        from jvspatial.core.context import get_default_context
        from jvspatial.core.graph import export_graph

        # Store graph_context for use in the endpoint function
        # We'll access it via closure
        _graph_context = graph_context

        # Define the endpoint function without the decorator to avoid auto-registration
        # We'll register it manually with explicit tags
        async def get_graph(
            format: str = Query(  # noqa: B008
                default="dot",
                description="Graph format: 'dot' (Graphviz) or 'mermaid'",
                regex="^(dot|mermaid)$",
            ),
            include_attributes: bool = Query(  # noqa: B008
                default=True, description="Include node/edge attributes in labels"
            ),
            rankdir: str = Query(  # noqa: B008
                default="TB",
                description="Graph direction: TB, LR, BT, RL (for DOT) or TB, TD, BT, RL, LR (for Mermaid)",
            ),
            node_shape: str = Query(  # noqa: B008
                default="box",
                description="Node shape for DOT format: box, ellipse, circle, diamond, etc.",
            ),
        ) -> str:
            """Get graph visualization in DOT or Mermaid format.

            This endpoint generates a visual representation of the current application graph
            using the built-in graphing operation. The graph includes all nodes and edges
            in the database.


            **Requires authentication** - This endpoint exposes graph data and requires
            a valid authentication token.


            **Args:**

            - **format**: Output format - `'dot'` for Graphviz or `'mermaid'` for Mermaid diagrams
            - **include_attributes**: Whether to include node/edge attributes in labels
            - **rankdir**: Graph direction:

                - For DOT: `TB` (top-bottom), `LR` (left-right), `BT` (bottom-top), `RL` (right-left)
                - For Mermaid: `TB`, `TD`, `BT`, `RL`, `LR`

            - **node_shape**: Node shape for DOT format (e.g., `box`, `ellipse`, `circle`, `diamond`)


            **Returns:**

            Graph representation string in the requested format


            **Examples:**

            Get Graphviz DOT format:

            ```
            GET /api/graph?format=dot&rankdir=LR
            ```

            Get Mermaid format without attributes:

            ```
            GET /api/graph?format=mermaid&include_attributes=false
            ```

            Get DOT format with custom node shape:

            ```
            GET /api/graph?format=dot&node_shape=ellipse&rankdir=TB
            ```
            """
            try:
                # Use provided graph context or fallback to default
                context = _graph_context
                if not context:
                    context = get_default_context()

                # Generate graph based on format
                if format == "dot":
                    graph_output = await export_graph(
                        context,
                        format="dot",
                        include_attributes=include_attributes,
                        rankdir=rankdir,
                        node_shape=node_shape,
                    )
                else:  # mermaid
                    # Map rankdir to mermaid direction
                    direction = rankdir
                    graph_output = await export_graph(
                        context,
                        format="mermaid",
                        include_attributes=include_attributes,
                        direction=direction,
                    )

                return graph_output

            except Exception as e:
                self._logger.error(f"Graph generation error: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to generate graph: {str(e)}",
                )

        # Manually register the function endpoint with the endpoint registry
        # so the authentication middleware can find it
        # Use explicit tags=["App"] to ensure it only appears under App tag
        if server and hasattr(server, "_endpoint_registry"):
            try:
                from jvspatial.api.endpoints.factory import ParameterModelFactory

                # Create parameter model if function has parameters
                # Use full path for parameter model
                param_model = ParameterModelFactory.create_model(
                    get_graph, path="/api/graph"
                )

                # Wrap function with parameter handling if needed
                if param_model is not None:
                    from jvspatial.api.decorators.route import (
                        _wrap_function_with_params,
                    )

                    wrapped_func = _wrap_function_with_params(
                        get_graph, param_model, ["GET"], path="/api/graph"
                    )
                else:
                    wrapped_func = get_graph

                # Set auth attributes on the function
                get_graph._auth_required = True  # type: ignore[attr-defined]
                wrapped_func._auth_required = True  # type: ignore[attr-defined]

                # Explicitly set tags to only ["App"] - no default tag
                tags = ["App"]

                # Set endpoint config with explicit tags to prevent default tag addition
                if not hasattr(wrapped_func, "_jvspatial_endpoint_config"):
                    wrapped_func._jvspatial_endpoint_config = {}  # type: ignore[attr-defined]
                wrapped_func._jvspatial_endpoint_config["tags"] = tags  # type: ignore[attr-defined]

                # Register with endpoint registry using full path
                server._endpoint_registry.register_function(
                    get_graph,  # Original function
                    "/api/graph",  # Full path for registry
                    methods=["GET"],
                    route_config={
                        "path": "/api/graph",  # Full path
                        "endpoint": wrapped_func,
                        "methods": ["GET"],
                        "auth_required": True,
                        "response_class": PlainTextResponse,
                        "tags": tags,  # Explicitly ["App"] only
                    },
                    auth_required=True,
                    response_class=PlainTextResponse,
                    tags=tags,  # Explicitly ["App"] only
                )

                # Register with endpoint router - path is relative to router prefix (/api)
                # This ensures the endpoint is only registered once with explicit tags
                server.endpoint_router.add_route(
                    path="/graph",  # Relative to /api prefix (becomes /api/graph)
                    endpoint=wrapped_func,
                    methods=["GET"],
                    source_obj=get_graph,
                    auth=True,
                    response_class=PlainTextResponse,
                    tags=tags,  # Explicitly set to only ["App"] - prevents default tag
                )

                # Mark server as having auth endpoints
                server._has_auth_endpoints = True

            except Exception as e:
                self._logger.warning(
                    f"Could not register graph endpoint with registry: {e}"
                )
                # Fallback: register directly with FastAPI and set auth attribute
                # Explicitly set tags to prevent default tag addition
                app.get(
                    "/api/graph",
                    response_class=PlainTextResponse,
                    tags=["App"],  # Explicitly set to only App tag
                )(get_graph)
                get_graph._auth_required = True  # type: ignore[attr-defined]


__all__ = ["AppBuilder"]
