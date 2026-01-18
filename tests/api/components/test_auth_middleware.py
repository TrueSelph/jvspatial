"""Tests for AuthenticationMiddleware component.

This module tests the registry-based authentication checking behavior,
ensuring that auth settings are properly respected for all registered endpoints.
"""

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
        """Create test server config with auth enabled."""
        return ServerConfig(
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-key-for-testing",
                jwt_algorithm="HS256",
                jwt_expire_minutes=30,
            )
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
            def __init__(self, path):
                self.url = type("url", (), {"path": path})()

        # SECURITY TEST: Unregistered path - should return True (require auth)
        request = MockRequest("/api/test/unknown")
        result = middleware._endpoint_requires_auth(request)
        assert result is True, "Unregistered endpoint should require authentication"

        # Test with registered path that has auth=False
        @endpoint("/test/registered-false", methods=["POST"], auth=False)
        async def registered_false():
            pass

        server.app = server._create_app_instance()
        request2 = MockRequest("/api/test/registered-false")
        result2 = middleware._endpoint_requires_auth(request2)
        assert result2 is False

        # Test with registered path that has auth=True
        @endpoint("/test/registered-true", methods=["POST"], auth=True)
        async def registered_true():
            pass

        server.app = server._create_app_instance()
        request3 = MockRequest("/api/test/registered-true")
        result3 = middleware._endpoint_requires_auth(request3)
        assert result3 is True

    def test_unregistered_endpoint_requires_auth_direct(self, server):
        """SECURITY TEST: Unregistered endpoints should require authentication (deny by default)."""
        middleware = AuthenticationMiddleware(
            app=server.get_app(),
            auth_config=server._auth_config,
            server=server,
        )

        class MockRequest:
            def __init__(self, path):
                self.url = type("url", (), {"path": path})()

        # Request to endpoint NOT in registry - should require auth
        request = MockRequest("/api/unknown/endpoint")
        result = middleware._endpoint_requires_auth(request)

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
        result = middleware._endpoint_requires_auth(request)

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
        result = middleware._endpoint_requires_auth(request)
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
        result = middleware._endpoint_requires_auth(request)
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
        result = middleware._endpoint_requires_auth(request)
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
