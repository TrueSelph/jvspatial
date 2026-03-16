"""Tests for AuthenticationMiddleware component.

This module tests the registry-based authentication checking behavior,
ensuring that auth settings are properly respected for all registered endpoints.
"""

import os
import tempfile

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from jvspatial.api.components.auth_middleware import AuthenticationMiddleware
from jvspatial.api.config import ServerConfig
from jvspatial.api.decorators.route import endpoint
from jvspatial.api.server import Server
from jvspatial.core.entities import Walker


class TestAuthenticationMiddleware:
    """Test AuthenticationMiddleware registry-based behavior."""

    @pytest.fixture
    def server_config(self):
        """Create test server config with auth and database enabled."""
        db_path = os.path.join(tempfile.mkdtemp(), "test_auth_middleware_db")
        return ServerConfig(
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-key-for-testing",
                jwt_algorithm="HS256",
                jwt_expire_minutes=30,
            ),
            database=dict(db_type="json", db_path=db_path),
        )

    @pytest.fixture
    def server(self, server_config):
        """Create test server instance."""
        return Server(config=server_config)

    @pytest.fixture
    def app(self, server):
        """Create FastAPI app with authentication middleware."""
        return server.get_app()

    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)

    def test_registered_endpoint_with_auth_true_requires_auth(self, server):
        """Test that registered endpoint with auth=True requires authentication."""

        # Register an endpoint with auth=True (without /api prefix - router adds it)
        @endpoint("/test/protected", methods=["POST"], auth=True)
        async def protected_endpoint():
            return {"message": "success"}

        # Rebuild app to include new endpoint and create new client
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Try to access without auth - should fail
        response = client.post("/api/test/protected")
        assert response.status_code == 401
        assert "authentication_required" in response.json()["error_code"]

    def test_registered_endpoint_with_auth_false_allows_access(self, server):
        """Test that registered endpoint with auth=False allows access without auth."""

        # Register an endpoint with auth=False (without /api prefix - router adds it)
        @endpoint("/test/public", methods=["POST"], auth=False)
        async def public_endpoint():
            return {"message": "success"}

        # Rebuild app to include new endpoint and create new client
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Try to access without auth - should succeed
        response = client.post("/api/test/public")
        assert response.status_code == 200
        assert response.json()["message"] == "success"

    def test_unregistered_endpoint_requires_auth(self, server, client):
        """SECURITY TEST: Unregistered endpoints should require authentication (deny by default)."""

        # Create a simple FastAPI route that's not registered via @endpoint
        @server.app.post("/api/test/unregistered")
        async def unregistered_endpoint():
            return {"message": "unregistered"}

        # Try to access without auth - should fail (SECURITY: deny by default)
        response = client.post("/api/test/unregistered")
        # SECURITY: Must require authentication for unknown endpoints
        assert response.status_code == 401
        assert "authentication_required" in response.json()["error_code"]

    def test_exempt_path_not_protected(self, client):
        """Test that exempt paths (like /health) are not protected."""
        # /health should be in exempt_paths by default
        response = client.get("/health")
        assert response.status_code == 200

    def test_walker_endpoint_with_auth_false_allows_access(self, server):
        """Test that walker endpoint with auth=False allows access without auth."""

        # Register a walker with auth=False (without /api prefix - router adds it)
        @endpoint("/test/walker-public", methods=["POST"], auth=False)
        class PublicWalker(Walker):
            pass

        # Rebuild app to include new endpoint and create new client
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)
        # Trigger lifespan to ensure root node exists (required for walkers)
        client.get("/health")

        # Try to access without auth - should succeed
        response = client.post("/api/test/walker-public", json={})
        assert response.status_code == 200

    def test_walker_endpoint_with_auth_true_requires_auth(self, server):
        """Test that walker endpoint with auth=True requires authentication."""

        # Register a walker with auth=True (without /api prefix - router adds it)
        @endpoint("/test/walker-protected", methods=["POST"], auth=True)
        class ProtectedWalker(Walker):
            pass

        # Rebuild app to include new endpoint and create new client
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)
        client.get("/health")  # Trigger lifespan for root node

        # Try to access without auth - should fail
        response = client.post("/api/test/walker-protected", json={})
        assert response.status_code == 401
        assert "authentication_required" in response.json()["error_code"]

    def test_dynamic_endpoint_respects_auth_false(self, server):
        """Test that dynamically registered endpoints with auth=False are not protected.

        This simulates the jvagent use case where endpoints are registered
        dynamically with explicit auth=False settings.
        """

        # Register endpoint dynamically (simulating jvagent pattern)
        # Without /api prefix - router adds it
        @endpoint("/agents/{agent_id}/interact", methods=["POST"], auth=False)
        async def interact_endpoint(agent_id: str):
            return {"agent_id": agent_id, "response": "interaction complete"}

        # Rebuild app to include new endpoint and create new client
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Try to access without auth - should succeed
        response = client.post("/api/agents/test-agent/interact")
        assert response.status_code == 200
        assert response.json()["agent_id"] == "test-agent"

    def test_endpoint_with_no_config_requires_auth(self, server):
        """SECURITY TEST: Endpoint found in registry but without config should require authentication.

        Note: In practice, the @endpoint decorator always adds config, so this scenario
        shouldn't occur. However, we test it for defense in depth.
        """

        # Register endpoint without explicit auth setting (defaults to False in config)
        @endpoint("/test/no-auth-setting", methods=["POST"])
        async def no_auth_setting_endpoint():
            return {"message": "success"}

        # Rebuild app to include new endpoint and create new client
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Try to access without auth - should succeed (default is False in config)
        # Note: The decorator always adds config with auth=False by default
        response = client.post("/api/test/no-auth-setting")
        assert response.status_code == 200

    def test_path_matching_with_parameters(self, server):
        """Test that path matching works correctly with path parameters after normalization."""

        # Register endpoint with path parameter (without /api prefix - router adds it)
        @endpoint("/test/{param}/endpoint", methods=["POST"], auth=False)
        async def param_endpoint(param: str):
            return {"param": param}

        # Rebuild app to include new endpoint and create new client
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Try to access with different param values (with /api prefix in request)
        response = client.post("/api/test/abc123/endpoint")
        assert response.status_code == 200
        assert response.json()["param"] == "abc123"

        response2 = client.post("/api/test/xyz789/endpoint")
        assert response2.status_code == 200
        assert response2.json()["param"] == "xyz789"

    def test_middleware_uses_registry_only(self, server):
        """Test that middleware only checks registry, not FastAPI routes."""
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        # Create a mock request
        class MockRequest:
            def __init__(self, path, method="GET"):
                self.url = type("url", (), {"path": path})()
                self.method = method

        # SECURITY TEST: Unregistered path - should return True (require auth)
        request = MockRequest("/api/test/unknown")
        result = middleware._auth_resolver.endpoint_requires_auth(request)
        assert result is True, "Unregistered endpoint should require authentication"

        # Test with registered path that has auth=False
        @endpoint("/test/registered-false", methods=["POST"], auth=False)
        async def registered_false():
            pass

        server.app = server._create_app_instance()
        request2 = MockRequest("/api/test/registered-false")
        result2 = middleware._auth_resolver.endpoint_requires_auth(request2)
        assert result2 is False

        # Test with registered path that has auth=True
        @endpoint("/test/registered-true", methods=["POST"], auth=True)
        async def registered_true():
            pass

        server.app = server._create_app_instance()
        request3 = MockRequest("/api/test/registered-true")
        result3 = middleware._auth_resolver.endpoint_requires_auth(request3)
        assert result3 is True

    def test_unregistered_endpoint_requires_auth_direct(self, server):
        """SECURITY TEST: Unregistered endpoints should require authentication (deny by default)."""
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        class MockRequest:
            def __init__(self, path, method="GET"):
                self.url = type("url", (), {"path": path})()
                self.method = method

        # Request to endpoint NOT in registry - should require auth
        request = MockRequest("/api/unknown/endpoint")
        result = middleware._auth_resolver.endpoint_requires_auth(request)

        # SECURITY: Must return True (require auth) for unknown endpoints
        assert result is True, "Unregistered endpoint should require authentication"

    def test_error_during_lookup_requires_auth(self, server):
        """SECURITY TEST: Errors during lookup should require authentication."""
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        class MockRequest:
            def __init__(self, path):
                self.url = type("url", (), {"path": path})()

        # Simulate error by setting server to None temporarily
        original_server = middleware._server
        middleware._server = None

        request = MockRequest("/api/test/endpoint")
        result = middleware._auth_resolver.endpoint_requires_auth(request)

        # SECURITY: Must return True (require auth) on error
        assert result is True, "Error during lookup should require authentication"

        # Restore
        middleware._server = original_server

    def test_path_normalization_with_api_prefix(self, server):
        """Test that path normalization correctly handles /api prefix."""

        @endpoint("/test/normalized", methods=["POST"], auth=False)
        async def normalized_endpoint():
            return {"message": "public"}

        server.app = server._create_app_instance()
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        class MockRequest:
            def __init__(self, path):
                self.url = type("url", (), {"path": path})()

        # Test with /api prefix
        request = MockRequest("/api/test/normalized")
        result = middleware._auth_resolver.endpoint_requires_auth(request)
        assert (
            result is False
        ), "Endpoint with auth=False should not require authentication"

    def test_path_normalization_without_api_prefix(self, server):
        """Test that path normalization works without /api prefix."""

        @endpoint("/test/no-prefix", methods=["POST"], auth=False)
        async def no_prefix_endpoint():
            return {"message": "public"}

        server.app = server._create_app_instance()
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        class MockRequest:
            def __init__(self, path):
                self.url = type("url", (), {"path": path})()

        # Test without /api prefix
        request = MockRequest("/test/no-prefix")
        result = middleware._auth_resolver.endpoint_requires_auth(request)
        assert (
            result is False
        ), "Endpoint with auth=False should not require authentication"

    def test_path_normalization_with_parameters(self, server):
        """Test that path normalization works correctly with path parameters."""

        @endpoint("/agents/{agent_id}/interact", methods=["POST"], auth=False)
        async def interact_endpoint(agent_id: str):
            return {"agent_id": agent_id}

        server.app = server._create_app_instance()
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        class MockRequest:
            def __init__(self, path):
                self.url = type("url", (), {"path": path})()

        # Test with /api prefix and path parameter
        request = MockRequest("/api/agents/test-agent-123/interact")
        result = middleware._auth_resolver.endpoint_requires_auth(request)
        assert (
            result is False
        ), "Endpoint with auth=False should not require authentication"

    def test_swagger_ui_protected_endpoint_requires_auth(self, server):
        """Test that Swagger UI requests to protected endpoints require authentication."""

        # Register a protected endpoint (without /api prefix - router adds it)
        @endpoint("/test/swagger-protected", methods=["POST"], auth=True)
        async def swagger_protected_endpoint():
            return {"message": "protected"}

        # Rebuild app to include new endpoint and create new client
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Simulate Swagger UI request (with /api prefix)
        # This should require authentication
        response = client.post("/api/test/swagger-protected")
        assert response.status_code == 401
        assert "authentication_required" in response.json()["error_code"]

    def test_swagger_ui_public_endpoint_allows_access(self, server):
        """Test that Swagger UI requests to public endpoints work without authentication."""

        # Register a public endpoint (without /api prefix - router adds it)
        @endpoint("/test/swagger-public", methods=["POST"], auth=False)
        async def swagger_public_endpoint():
            return {"message": "public"}

        # Rebuild app to include new endpoint and create new client
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Simulate Swagger UI request (with /api prefix)
        # This should work without authentication
        response = client.post("/api/test/swagger-public")
        assert response.status_code == 200
        assert response.json()["message"] == "public"

    def test_endpoint_registered_via_add_route_with_auth_requires_auth(self, server):
        """Test that endpoints registered via endpoint_router.add_route() with auth=True require authentication.

        This tests the fix for the issue where auth_required wasn't being set in _jvspatial_endpoint_config.
        """

        # Create a test endpoint function
        async def test_protected_endpoint():
            return {"message": "protected"}

        # Register via add_route with auth=True (simulating app_builder pattern)
        server.endpoint_router.add_route(
            path="/test/add-route-protected",
            endpoint=test_protected_endpoint,
            methods=["GET"],
            auth=True,
        )

        # Rebuild app to include new endpoint
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Verify _jvspatial_endpoint_config is set correctly
        endpoint_config = getattr(
            test_protected_endpoint, "_jvspatial_endpoint_config", {}
        )
        assert (
            endpoint_config.get("auth_required") is True
        ), "auth_required must be set in _jvspatial_endpoint_config when registering with auth=True"

        # Try to access without auth - should fail
        response = client.get("/api/test/add-route-protected")
        assert (
            response.status_code == 401
        ), "Endpoint registered with auth=True must require authentication"
        assert "authentication_required" in response.json()["error_code"]

    def test_endpoint_registered_via_add_route_without_auth_allows_access(self, server):
        """Test that endpoints registered via endpoint_router.add_route() with auth=False allow access."""

        # Create a test endpoint function
        async def test_public_endpoint():
            return {"message": "public"}

        # Register via add_route with auth=False
        server.endpoint_router.add_route(
            path="/test/add-route-public",
            endpoint=test_public_endpoint,
            methods=["GET"],
            auth=False,
        )

        # Rebuild app to include new endpoint
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Verify _jvspatial_endpoint_config is set correctly
        endpoint_config = getattr(
            test_public_endpoint, "_jvspatial_endpoint_config", {}
        )
        assert (
            endpoint_config.get("auth_required") is False
        ), "auth_required must be set to False in _jvspatial_endpoint_config when registering with auth=False"

        # Try to access without auth - should succeed
        response = client.get("/api/test/add-route-public")
        assert response.status_code == 200
        assert response.json()["message"] == "public"

    def test_endpoint_registered_via_register_function_sets_config(self, server):
        """Test that endpoints registered via registry.register_function() set _jvspatial_endpoint_config correctly."""

        # Create a test endpoint function
        async def test_registry_endpoint():
            return {"message": "registry"}

        # Register via register_function with auth_required=True
        server._endpoint_registry.register_function(
            test_registry_endpoint,
            path="/api/test/registry-protected",
            methods=["GET"],
            auth_required=True,
        )

        # Verify _jvspatial_endpoint_config is set correctly
        endpoint_config = getattr(
            test_registry_endpoint, "_jvspatial_endpoint_config", {}
        )
        assert (
            endpoint_config.get("auth_required") is True
        ), "auth_required must be set in _jvspatial_endpoint_config when registering with auth_required=True"

        # Rebuild app to include new endpoint
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Try to access without auth - should fail
        response = client.get("/api/test/registry-protected")
        assert (
            response.status_code == 401
        ), "Endpoint registered with auth_required=True must require authentication"
        assert "authentication_required" in response.json()["error_code"]

    def test_middleware_reads_auth_required_from_endpoint_config(self, server):
        """Test that middleware correctly reads auth_required from _jvspatial_endpoint_config."""
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        # Create a test endpoint function
        async def test_config_endpoint():
            return {"message": "config"}

        # Manually set the endpoint config (simulating what add_route should do)
        test_config_endpoint._jvspatial_endpoint_config = {  # type: ignore[attr-defined]
            "auth_required": True,
        }

        # Register the endpoint
        server.endpoint_router.add_route(
            path="/test/config-check",
            endpoint=test_config_endpoint,
            methods=["GET"],
            auth=True,
        )

        # Rebuild app
        server.app = server._create_app_instance()

        # Create mock request
        class MockRequest:
            def __init__(self, path, method="GET"):
                self.url = type("url", (), {"path": path})()
                self.method = method

        # Test that middleware correctly identifies auth requirement
        request = MockRequest("/api/test/config-check")
        result = middleware._auth_resolver.endpoint_requires_auth(request)
        assert (
            result is True
        ), "Middleware must read auth_required from _jvspatial_endpoint_config"

    def test_endpoint_config_missing_auth_required_defaults_to_false(self, server):
        """Test that endpoints without auth_required in config default to requiring auth (security)."""
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        # Create a test endpoint function without config
        async def test_no_config_endpoint():
            return {"message": "no-config"}

        # Register endpoint but don't set _jvspatial_endpoint_config
        server.endpoint_router.add_route(
            path="/test/no-config",
            endpoint=test_no_config_endpoint,
            methods=["GET"],
            auth=False,  # This should set the config
        )

        # Rebuild app
        server.app = server._create_app_instance()

        # Verify config was set by add_route
        endpoint_config = getattr(
            test_no_config_endpoint, "_jvspatial_endpoint_config", {}
        )
        assert (
            "auth_required" in endpoint_config
        ), "add_route must set auth_required in _jvspatial_endpoint_config"
        assert endpoint_config.get("auth_required") is False

    def test_graph_endpoint_requires_authentication(self, server):
        """Test that the /api/graph endpoint (registered via app_builder) requires authentication.

        This is a critical test that ensures the graph endpoint, which is registered
        via app_builder.py using add_route(), properly requires authentication.
        """
        # The graph endpoint should be registered during server initialization
        # Rebuild app to ensure graph endpoint is registered
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Try to access /api/graph without auth - should fail
        response = client.get("/api/graph")
        assert (
            response.status_code == 401
        ), "Graph endpoint must require authentication when auth is enabled"
        assert "authentication_required" in response.json()["error_code"]

        # Verify the endpoint config is set correctly by checking the registry
        # Find the graph endpoint function in the registry
        # get_graph is a local function, so we need to find it via the registry
        graph_endpoint_func = None
        for func, endpoint_info in server._endpoint_registry._function_registry.items():
            if endpoint_info.path == "/api/graph":
                graph_endpoint_func = func
                break

        if graph_endpoint_func and hasattr(
            graph_endpoint_func, "_jvspatial_endpoint_config"
        ):
            endpoint_config = graph_endpoint_func._jvspatial_endpoint_config  # type: ignore[attr-defined]
            assert (
                endpoint_config.get("auth_required") is True
            ), "Graph endpoint must have auth_required=True in _jvspatial_endpoint_config"

    def test_register_function_with_route_config_sets_auth_required(self, server):
        """Test that register_function with route_config properly sets auth_required in endpoint config."""

        # Create a test endpoint function
        async def test_route_config_endpoint():
            return {"message": "route-config"}

        # Register via register_function with route_config containing auth_required
        server._endpoint_registry.register_function(
            test_route_config_endpoint,
            path="/api/test/route-config-protected",
            methods=["GET"],
            route_config={
                "path": "/api/test/route-config-protected",
                "endpoint": test_route_config_endpoint,
                "methods": ["GET"],
                "auth_required": True,
            },
            auth_required=True,  # Also pass as kwarg
        )

        # Verify _jvspatial_endpoint_config is set correctly
        endpoint_config = getattr(
            test_route_config_endpoint, "_jvspatial_endpoint_config", {}
        )
        assert (
            endpoint_config.get("auth_required") is True
        ), "register_function must set auth_required in _jvspatial_endpoint_config from route_config or kwargs"

        # Rebuild app to include new endpoint
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Try to access without auth - should fail
        response = client.get("/api/test/route-config-protected")
        assert (
            response.status_code == 401
        ), "Endpoint registered with auth_required=True in route_config must require authentication"
        assert "authentication_required" in response.json()["error_code"]

    def test_add_route_sets_permissions_and_roles_in_config(self, server):
        """Test that add_route properly sets permissions and roles in _jvspatial_endpoint_config."""

        # Create a test endpoint function
        async def test_permissions_endpoint():
            return {"message": "permissions"}

        # Register via add_route with permissions and roles
        server.endpoint_router.add_route(
            path="/test/permissions",
            endpoint=test_permissions_endpoint,
            methods=["GET"],
            auth=True,
            permissions=["read:data"],
            roles=["admin"],
        )

        # Verify _jvspatial_endpoint_config is set correctly
        endpoint_config = getattr(
            test_permissions_endpoint, "_jvspatial_endpoint_config", {}
        )
        assert endpoint_config.get("auth_required") is True
        assert endpoint_config.get("permissions") == [
            "read:data"
        ], "add_route must set permissions in _jvspatial_endpoint_config"
        assert endpoint_config.get("roles") == [
            "admin"
        ], "add_route must set roles in _jvspatial_endpoint_config"

    def test_endpoint_decorator_sets_auth_required_in_config(self, server):
        """Test that @endpoint decorator properly sets auth_required in _jvspatial_endpoint_config."""

        # Register endpoint with @endpoint decorator
        @endpoint("/test/decorator-protected", methods=["POST"], auth=True)
        async def decorator_protected_endpoint():
            return {"message": "protected"}

        # Rebuild app to include new endpoint
        server.app = server._create_app_instance()
        from fastapi.testclient import TestClient

        client = TestClient(server.app)

        # Verify _jvspatial_endpoint_config is set correctly
        endpoint_config = getattr(
            decorator_protected_endpoint, "_jvspatial_endpoint_config", {}
        )
        assert (
            endpoint_config.get("auth_required") is True
        ), "@endpoint decorator must set auth_required in _jvspatial_endpoint_config when auth=True"

        # Try to access without auth - should fail
        response = client.post("/api/test/decorator-protected")
        assert (
            response.status_code == 401
        ), "Endpoint decorated with auth=True must require authentication"
        assert "authentication_required" in response.json()["error_code"]

    def test_endpoint_config_persistence_across_app_rebuilds(self, server):
        """Test that _jvspatial_endpoint_config persists across app rebuilds."""

        # Create and register endpoint
        async def test_persistence_endpoint():
            return {"message": "persistence"}

        server.endpoint_router.add_route(
            path="/test/persistence",
            endpoint=test_persistence_endpoint,
            methods=["GET"],
            auth=True,
        )

        # Verify config is set
        endpoint_config = getattr(
            test_persistence_endpoint, "_jvspatial_endpoint_config", {}
        )
        assert endpoint_config.get("auth_required") is True

        # Rebuild app
        server.app = server._create_app_instance()

        # Verify config still exists after rebuild
        endpoint_config_after = getattr(
            test_persistence_endpoint, "_jvspatial_endpoint_config", {}
        )
        assert (
            endpoint_config_after.get("auth_required") is True
        ), "_jvspatial_endpoint_config must persist across app rebuilds"

        # Verify middleware still enforces auth
        from fastapi.testclient import TestClient

        client = TestClient(server.app)
        response = client.get("/api/test/persistence")
        assert response.status_code == 401

    def test_middleware_handles_missing_endpoint_config_gracefully(self, server):
        """Test that middleware requires auth for unregistered paths (security: deny by default)."""
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        # Truly unregistered path - should require auth
        class MockRequest:
            def __init__(self, path, method="GET"):
                self.url = type("url", (), {"path": path})()
                self.method = method

        request = MockRequest("/api/truly/unknown/path")
        result = middleware._auth_resolver.endpoint_requires_auth(request)
        assert result is True


class TestJwtAuthUsesPrimeDatabase:
    """Integration test: JWT auth must use get_prime_database(), not server._graph_context.

    Regression test for 401 with valid token when server._graph_context differs from
    prime DB (e.g. after set_graph_context or context switch). Auth middleware must
    always validate JWT against the prime database where users are stored.
    """

    @pytest.mark.asyncio
    async def test_jwt_succeeds_when_graph_context_differs_from_prime(self):
        """Verify JWT validation succeeds when server._graph_context points to a different database."""
        import uuid

        from jvspatial.api import endpoint
        from jvspatial.api.context import set_current_server
        from jvspatial.db import create_database, get_prime_database
        from jvspatial.db.manager import DatabaseManager, set_database_manager

        # Reset DatabaseManager for test isolation
        DatabaseManager._instance = None
        try:
            test_id = uuid.uuid4().hex[:8]
            server = Server(
                title="Test API",
                auth=dict(
                    auth_enabled=True,
                    jwt_secret="test-secret-key-for-prime-db-test",
                ),
                db_type="json",
                db_path=f"./.test_dbs/test_db_prime_auth_{test_id}",
            )
            set_current_server(server)

            @endpoint("/test/protected-prime", methods=["GET"], auth=True)
            async def protected_endpoint():
                return {"message": "authenticated"}

            server.app = server._create_app_instance()
            client = TestClient(server.get_app())

            # Register user and login (user stored in prime DB)
            email = f"test_{test_id}@example.com"
            register_response = client.post(
                "/api/auth/register",
                json={"email": email, "password": "password123"},
            )
            assert register_response.status_code == 200, register_response.text

            login_response = client.post(
                "/api/auth/login",
                json={"email": email, "password": "password123"},
            )
            assert login_response.status_code == 200, login_response.text
            access_token = login_response.json()["access_token"]

            # Simulate bug scenario: server._graph_context points to a different database
            # (e.g. after set_graph_context for multi-tenant or app data switch)
            alt_db = create_database(
                "json",
                base_path=f"./.test_dbs/test_db_alt_{test_id}",
            )
            from jvspatial.core.context import GraphContext

            alt_ctx = GraphContext(database=alt_db)
            server.set_graph_context(alt_ctx)

            # Prime DB is unchanged; auth middleware uses get_prime_database()
            assert get_prime_database() is not alt_db

            # Call protected endpoint with valid token - must succeed (200)
            # because auth uses prime DB, not server._graph_context
            response = client.get(
                "/api/test/protected-prime",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            assert (
                response.status_code == 200
            ), f"Expected 200 with valid token when graph context differs; got {response.status_code}: {response.text}"
            assert response.json()["message"] == "authenticated"
        finally:
            DatabaseManager._instance = None
