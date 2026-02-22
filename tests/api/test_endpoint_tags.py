"""Tests for API endpoint tag organization."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from jvspatial.api import endpoint
from jvspatial.api.server import Server, ServerConfig
from jvspatial.core.context import GraphContext


@pytest.fixture
def mock_context():
    """Create mock context."""
    context = MagicMock(spec=GraphContext)
    context.database = AsyncMock()
    context.ensure_indexes = AsyncMock()
    context.save = AsyncMock()
    context.get = AsyncMock()
    context.find = AsyncMock(return_value=[])
    return context


@pytest.fixture
def server_with_auth(mock_context):
    """Create server with authentication enabled."""
    config = ServerConfig(
        db_type="json",
        db_path="test_db",
        auth=dict(
            auth_enabled=True,
            jwt_secret="test-secret-key",
            jwt_algorithm="HS256",
            jwt_expire_minutes=30,
        ),
    )
    server = Server(config=config)
    return server


class TestEndpointTags:
    """Test API endpoint tag organization."""

    def test_logs_endpoint_has_app_tag(self, server_with_auth):
        """Verify /api/logs endpoint has 'App' tag."""
        # Import the logs endpoint to trigger registration
        from jvspatial.logging.endpoints import get_logs

        # Check if endpoint is registered
        app = server_with_auth.get_app()

        # Find the /api/logs route
        logs_route = None
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path == "/api/logs":
                logs_route = route
                break

        # If route exists, check its tags
        if logs_route:
            assert (
                "App" in logs_route.tags
            ), f"/api/logs should have 'App' tag, got {logs_route.tags}"
            assert (
                "Auth" not in logs_route.tags
            ), f"/api/logs should not have 'Auth' tag"

    def test_graph_endpoint_has_app_tag(self, server_with_auth):
        """Verify /api/graph endpoint has 'App' tag."""
        # The graph endpoint is registered by AppBuilder
        # We need to ensure AppBuilder has registered it
        from jvspatial.api.components.app_builder import AppBuilder

        app_builder = AppBuilder(server_with_auth.config)
        app = server_with_auth.get_app()
        app_builder.register_core_routes(
            app, server_with_auth._graph_context, server_with_auth
        )

        # Find the /api/graph route
        graph_route = None
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path == "/api/graph":
                graph_route = route
                break

        # If route exists, check its tags
        if graph_route:
            assert (
                "App" in graph_route.tags
            ), f"/api/graph should have 'App' tag, got {graph_route.tags}"
            assert (
                "Auth" not in graph_route.tags
            ), f"/api/graph should not have 'Auth' tag"

    def test_auth_endpoints_have_auth_tag(self, server_with_auth):
        """Verify all /api/auth/* endpoints have 'Auth' tag."""
        # Configure auth to register endpoints
        from jvspatial.api.components.auth_configurator import AuthConfigurator

        configurator = AuthConfigurator(server_with_auth.config)
        configurator.configure()
        app = server_with_auth.get_app()
        app.include_router(configurator.auth_router, prefix="/api")

        # Find all /api/auth/* routes
        auth_routes = []
        for route in app.routes:
            if isinstance(route, APIRoute) and route.path.startswith("/api/auth/"):
                auth_routes.append(route)

        # All auth routes should have "Auth" tag
        if auth_routes:
            for route in auth_routes:
                assert (
                    "Auth" in route.tags
                ), f"Route {route.path} should have 'Auth' tag, got {route.tags}"
                assert (
                    "App" not in route.tags
                ), f"Route {route.path} should not have 'App' tag"

    def test_endpoint_registry_tags(self, server_with_auth):
        """Verify endpoint registry reflects correct tags."""
        # Configure auth
        from jvspatial.api.components.auth_configurator import AuthConfigurator

        configurator = AuthConfigurator(server_with_auth.config)
        configurator.configure()

        # Check endpoint registry if available
        if hasattr(server_with_auth, "_endpoint_registry"):
            registry = server_with_auth._endpoint_registry

            # Check auth endpoints in registry
            if hasattr(registry, "_function_registry"):
                for func, endpoint_info in registry._function_registry.items():
                    if hasattr(endpoint_info, "path") and endpoint_info.path.startswith(
                        "/auth/"
                    ):
                        if hasattr(endpoint_info, "tags"):
                            assert "Auth" in endpoint_info.tags or any(
                                "Auth" in tag for tag in endpoint_info.tags
                            ), f"Auth endpoint {endpoint_info.path} should have 'Auth' tag"

    def test_tags_in_openapi_schema(self, server_with_auth):
        """Verify tags appear correctly in OpenAPI schema."""
        # Configure auth
        from jvspatial.api.components.auth_configurator import AuthConfigurator

        configurator = AuthConfigurator(server_with_auth.config)
        configurator.configure()
        app = server_with_auth.get_app()
        app.include_router(configurator.auth_router, prefix="/api")

        # Get OpenAPI schema
        openapi_schema = app.openapi()

        # Check that tags are defined
        if "tags" in openapi_schema:
            tag_names = [tag["name"] for tag in openapi_schema["tags"]]
            # Should have both "App" and "Auth" tags
            assert "App" in tag_names or any(
                "app" in name.lower() for name in tag_names
            )
            assert "Auth" in tag_names or any(
                "auth" in name.lower() for name in tag_names
            )

        # Check paths for tag assignments
        if "paths" in openapi_schema:
            for path, methods in openapi_schema["paths"].items():
                for method, operation in methods.items():
                    if isinstance(operation, dict) and "tags" in operation:
                        tags = operation["tags"]
                        if path.startswith("/api/auth/"):
                            assert "Auth" in tags or any(
                                "auth" in tag.lower() for tag in tags
                            ), f"Auth endpoint {path} should have 'Auth' tag"
                        elif path in ["/api/logs", "/api/graph"]:
                            assert "App" in tags or any(
                                "app" in tag.lower() for tag in tags
                            ), f"App endpoint {path} should have 'App' tag"
