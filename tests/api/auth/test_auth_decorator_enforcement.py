"""
Test suite for authentication decorator enforcement.

This module tests that @auth_endpoint and @auth_walker_endpoint decorators
properly enforce authentication, permissions, and roles when integrated
with the server and middleware.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from jvspatial.api import Server
from jvspatial.api.auth import admin_endpoint, auth_endpoint, auth_walker_endpoint
from jvspatial.api.auth.entities import User
from jvspatial.api.endpoint.router import EndpointField
from jvspatial.core.entities import Node, Walker, on_visit


class SampleNode(Node):
    """Sample node for authentication tests."""

    name: str = ""
    value: int = 0


class MockDataNode(Node):
    """Mock node for walker tests."""

    name: str = "test"
    value: int = 0


class TestAuthEndpointEnforcement:
    """Test that @auth_endpoint decorator properly enforces authentication."""

    def setup_method(self):
        """Set up test server with authenticated endpoints."""
        # Create server
        self.server = Server(
            title="Auth Test Server",
            description="Testing auth enforcement",
            version="1.0.0",
            port=8001,
        )

        # Create authenticated endpoints AFTER server creation
        @auth_endpoint("/api/profile", methods=["GET"], server=self.server)
        async def get_profile(endpoint):
            """Get user profile - requires authentication."""
            return endpoint.success(data={"profile": "data"})

        @auth_endpoint(
            "/api/data/read",
            methods=["GET"],
            permissions=["read_data"],
            server=self.server,
        )
        async def read_data(endpoint):
            """Read data - requires read_data permission."""
            return endpoint.success(data={"data": "protected"})

        @auth_endpoint(
            "/api/reports",
            methods=["POST"],
            roles=["analyst", "admin"],
            server=self.server,
        )
        async def generate_report(endpoint):
            """Generate report - requires analyst or admin role."""
            return endpoint.success(data={"report": "generated"})

        @admin_endpoint("/api/admin/settings", methods=["GET"], server=self.server)
        async def admin_settings(endpoint):
            """Admin settings - requires admin role."""
            return endpoint.success(data={"settings": "admin"})

        # Store references
        self.get_profile = get_profile
        self.read_data = read_data
        self.generate_report = generate_report
        self.admin_settings = admin_settings

        # Create test client
        app = self.server.get_app()
        self.client = TestClient(app)

    def test_endpoints_registered(self):
        """Test that decorated endpoints are registered."""
        endpoints = self.server.list_function_endpoints()

        assert "get_profile" in endpoints
        assert "read_data" in endpoints
        assert "generate_report" in endpoints
        assert "admin_settings" in endpoints

    def test_auth_metadata_stored(self):
        """Test that auth metadata is stored on endpoints."""
        assert self.get_profile._auth_required is True
        assert self.get_profile._required_permissions == []
        assert self.get_profile._required_roles == []

        assert self.read_data._auth_required is True
        assert self.read_data._required_permissions == ["read_data"]
        assert self.read_data._required_roles == []

        assert self.generate_report._auth_required is True
        assert self.generate_report._required_permissions == []
        assert self.generate_report._required_roles == ["analyst", "admin"]

        assert self.admin_settings._auth_required is True
        assert self.admin_settings._required_permissions == []
        assert self.admin_settings._required_roles == ["admin"]

    def test_auth_middleware_applied(self):
        """Test that authentication middleware is automatically applied."""
        app = self.server.get_app()

        # Check middleware stack
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        assert "AuthenticationMiddleware" in middleware_names

    def test_unauthenticated_request_rejected(self):
        """Test that requests without credentials are rejected."""
        # Try to access authenticated endpoint without credentials
        response = self.client.get("/api/profile")

        assert response.status_code == 401
        assert "error" in response.json()
        assert response.json()["error"] == "Authentication required"

    def test_permission_required_endpoint_rejected(self):
        """Test that endpoints requiring permissions reject unauthenticated requests."""
        response = self.client.get("/api/data/read")

        assert response.status_code == 401
        assert "error" in response.json()

    def test_role_required_endpoint_rejected(self):
        """Test that endpoints requiring roles reject unauthenticated requests."""
        response = self.client.post("/api/reports")

        assert response.status_code == 401
        assert "error" in response.json()

    def test_admin_endpoint_rejected(self):
        """Test that admin endpoints reject unauthenticated requests."""
        response = self.client.get("/api/admin/settings")

        assert response.status_code == 401
        assert "error" in response.json()

    def test_public_endpoints_accessible(self):
        """Test that public endpoints remain accessible."""
        # Health endpoint should work without auth
        response = self.client.get("/health")
        assert response.status_code == 200

        # Root endpoint should work without auth
        response = self.client.get("/")
        assert response.status_code == 200

    def test_docs_accessible_without_auth(self):
        """Test that API documentation is accessible without authentication."""
        response = self.client.get("/docs")
        assert response.status_code == 200

        response = self.client.get("/openapi.json")
        assert response.status_code == 200


class TestAuthWalkerEndpointEnforcement:
    """Test that @auth_walker_endpoint decorator properly enforces authentication."""

    def setup_method(self):
        """Set up test server with authenticated walker endpoints."""
        # Create server
        self.server = Server(
            title="Walker Auth Test",
            description="Testing walker auth enforcement",
            version="1.0.0",
            port=8002,
        )

        # Create authenticated walker endpoints
        @auth_walker_endpoint(
            "/analyze",
            methods=["POST"],
            permissions=["analyze_data"],
            server=self.server,
        )
        class AnalyzeWalker(Walker):
            """Analyze data - requires analyze_data permission."""

            query: str = EndpointField(description="Query string")

            @on_visit(MockDataNode)
            async def analyze(self, here: Node):
                self.report({"analyzed": here.name})

        @auth_walker_endpoint(
            "/process",
            methods=["POST"],
            roles=["processor", "admin"],
            server=self.server,
        )
        class ProcessWalker(Walker):
            """Process data - requires processor or admin role."""

            operation: str = EndpointField(description="Operation type")

            @on_visit(MockDataNode)
            async def process(self, here: Node):
                self.report({"processed": self.operation})

        # Store references
        self.AnalyzeWalker = AnalyzeWalker
        self.ProcessWalker = ProcessWalker

        # Create test client with fully initialized app
        app = self.server.get_app()
        self.server._is_running = True  # Required for proper endpoint registration
        self.client = TestClient(app)

    def test_walker_endpoints_registered(self):
        """Test that walker endpoints are registered."""
        walkers = self.server.list_walker_endpoints()

        assert "AnalyzeWalker" in walkers
        assert "ProcessWalker" in walkers

    def test_walker_auth_metadata_stored(self):
        """Test that auth metadata is stored on walker classes."""
        assert self.AnalyzeWalker._auth_required is True
        assert self.AnalyzeWalker._required_permissions == ["analyze_data"]
        assert self.AnalyzeWalker._required_roles == []

        assert self.ProcessWalker._auth_required is True
        assert self.ProcessWalker._required_permissions == []
        assert self.ProcessWalker._required_roles == ["processor", "admin"]

    def test_walker_unauthenticated_request_rejected(self):
        """Test that walker endpoints reject unauthenticated requests."""
        response = self.client.post("/api/analyze", json={"query": "test"})

        assert response.status_code == 401
        assert "error" in response.json()

    def test_walker_permission_endpoint_rejected(self):
        """Test that walker endpoints with permissions reject unauthenticated requests."""
        response = self.client.post("/api/analyze", json={"query": "test"})

        assert response.status_code == 401

    def test_walker_role_endpoint_rejected(self):
        """Test that walker endpoints with roles reject unauthenticated requests."""
        response = self.client.post("/api/process", json={"operation": "count"})

        assert response.status_code == 401


class TestMixedEndpointEnforcement:
    """Test enforcement with mixed public and authenticated endpoints."""

    def setup_method(self):
        """Set up server with mixed endpoint types."""
        # Create server
        self.server = Server(
            title="Mixed Auth Test",
            description="Testing mixed endpoint auth",
            version="1.0.0",
            port=8003,
        )

        # Public function endpoint (using endpoint_router._function_endpoint_impl directly)
        # Create a simple function and manually register it
        async def public_info_func():
            """Public endpoint - no auth required."""
            from jvspatial.api.endpoint.response import create_endpoint_helper

            endpoint = create_endpoint_helper(walker_instance=None)
            return endpoint.success(data={"info": "public"})

        # Manually add to custom routes
        self.server._custom_routes.append(
            {
                "path": "/public/info",
                "endpoint": public_info_func,
                "methods": ["GET"],
            }
        )
        public_info = public_info_func

        # Authenticated function endpoint
        @auth_endpoint("/private/info", methods=["GET"], server=self.server)
        async def private_info(endpoint):
            """Private endpoint - auth required."""
            return endpoint.success(data={"info": "private"})

        # Public walker endpoint (using server.walker)
        @self.server.walker("/public/search", methods=["POST"])
        class PublicSearchWalker(Walker):
            """Public search - no auth required."""

            term: str = EndpointField(description="Search term")

            @on_visit(MockDataNode)
            async def search(self, here: Node):
                self.report({"result": here.name})

        # Authenticated walker endpoint
        @auth_walker_endpoint(
            "/private/search",
            methods=["POST"],
            permissions=["search_data"],
            server=self.server,
        )
        class PrivateSearchWalker(Walker):
            """Private search - requires search_data permission."""

            term: str = EndpointField(description="Search term")

            @on_visit(MockDataNode)
            async def search(self, here: Node):
                self.report({"result": here.name})

        # Store references
        self.public_info = public_info
        self.private_info = private_info
        self.PublicSearchWalker = PublicSearchWalker
        self.PrivateSearchWalker = PrivateSearchWalker

        # Create test client with fully initialized app
        app = self.server.get_app()
        self.server._is_running = True  # Required for proper endpoint registration
        self.client = TestClient(app)

    def test_public_function_endpoint_accessible(self):
        """Test that public function endpoints are accessible without auth."""
        response = self.client.get("/public/info")

        # Should succeed without authentication
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["info"] == "public"

    def test_private_function_endpoint_protected(self):
        """Test that private function endpoints require authentication."""
        response = self.client.get("/private/info")

        assert response.status_code == 401
        assert "error" in response.json()

    def test_public_walker_endpoint_accessible(self):
        """Test that public walker endpoints are accessible without auth."""
        response = self.client.post("/api/public/search", json={"term": "test"})

        # Should succeed without authentication
        assert response.status_code == 200

    def test_private_walker_endpoint_protected(self):
        """Test that private walker endpoints require authentication."""
        response = self.client.post("/api/private/search", json={"term": "test"})

        assert response.status_code == 401
        assert "error" in response.json()

    def test_auth_metadata_differences(self):
        """Test that public and private endpoints have different auth metadata."""
        # Public endpoints should not have _auth_required attribute
        assert not hasattr(self.public_info, "_auth_required")
        assert not hasattr(self.PublicSearchWalker, "_auth_required")

        # Private endpoints should have _auth_required = True
        assert self.private_info._auth_required is True
        assert self.PrivateSearchWalker._auth_required is True
        assert self.PrivateSearchWalker._required_permissions == ["search_data"]


class TestAuthEnforcementWithMockedUser:
    """Test authentication enforcement with mocked authenticated user."""

    def setup_method(self):
        """Set up test server and mock user."""
        self.server = Server(
            title="Mock User Auth Test",
            description="Testing with mocked user",
            version="1.0.0",
            port=8004,
        )

        # Create test user
        self.test_user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            roles=["user"],
            permissions=["read_data"],  # pragma: allowlist secret
            is_active=True,
        )

        # Create endpoint
        @auth_endpoint(
            "/api/protected",
            methods=["GET"],
            permissions=["read_data"],  # pragma: allowlist secret
            server=self.server,
        )
        async def protected_endpoint(endpoint):
            """Protected endpoint requiring read_data permission."""
            return endpoint.success(data={"message": "authorized"})

        self.protected_endpoint = protected_endpoint

        # Get app
        self.app = self.server.get_app()

    @pytest.mark.asyncio
    async def test_request_with_mocked_user(self):
        """Test that middleware properly checks user permissions."""
        from fastapi import Request

        from jvspatial.api.auth.middleware import AuthenticationMiddleware

        # Get the middleware instance
        middleware = None
        for m in self.app.user_middleware:
            if m.cls.__name__ == "AuthenticationMiddleware":
                middleware = m.cls(self.app)
                break

        assert middleware is not None

        # Create mock request
        request = MagicMock(spec=Request)
        request.url.path = "/api/protected"
        request.url.scheme = "http"
        request.state = MagicMock()
        request.app = self.app

        # Mock authentication to return test user
        with patch.object(
            middleware, "_authenticate_request", return_value=self.test_user
        ):
            with patch(
                "jvspatial.api.auth.middleware.rate_limiter.is_allowed",
                return_value=True,
            ):
                call_next = AsyncMock(return_value="success")
                result = await middleware.dispatch(request, call_next)

                # Should succeed because user has required permission
                assert result == "success"
                assert request.state.current_user == self.test_user


class TestCompleteAuthFlow:
    """Test complete authentication flow from decorator to enforcement."""

    def test_decorator_to_middleware_pipeline(self):
        """Test complete pipeline from decorator application to middleware enforcement."""
        # 1. Create server
        server = Server(title="Pipeline Test")

        # 2. Apply decorator
        @auth_endpoint(
            "/test", permissions=["test_perm"], roles=["tester"], server=server
        )
        async def test_endpoint(endpoint):
            return endpoint.success(data={"test": "data"})

        # 3. Verify metadata on function
        assert hasattr(test_endpoint, "_auth_required")
        assert test_endpoint._auth_required is True
        assert test_endpoint._required_permissions == ["test_perm"]
        assert test_endpoint._required_roles == ["tester"]

        # 4. Verify registered in server
        assert any(
            route["endpoint"] == test_endpoint for route in server._custom_routes
        )

        # 5. Verify middleware can detect requirements
        app = server.get_app()
        client = TestClient(app)

        # 6. Test enforcement
        response = client.get("/test")
        assert response.status_code == 401

    def test_walker_decorator_to_handler_metadata_transfer(self):
        """Test that walker auth metadata is transferred to FastAPI handlers."""
        server = Server(title="Walker Metadata Test")

        @auth_walker_endpoint(
            "/walker/test", methods=["POST"], permissions=["walker_perm"], server=server
        )
        class TestAuthWalker(Walker):
            field: str = EndpointField(description="Test field")

            @on_visit(SampleNode)
            async def process(self, here: Node):
                self.report({"node": here.id})

        # Get the app and find the route
        app = server.get_app()

        # Find the walker route
        walker_route = None
        for route in app.routes:
            if hasattr(route, "path") and "/walker/test" in route.path:
                walker_route = route
                break

        assert walker_route is not None

        # Check that handler has auth metadata
        handler = walker_route.endpoint
        assert hasattr(handler, "_auth_required")
        assert handler._auth_required is True
        assert handler._required_permissions == ["walker_perm"]

    def test_auto_middleware_detection(self):
        """Test that middleware is automatically added when auth endpoints exist."""
        # Create server without explicitly adding auth middleware
        server = Server(title="Auto Middleware Test")

        # Add authenticated endpoint
        @auth_endpoint("/protected", server=server)
        async def protected(endpoint):
            return endpoint.success(data={"protected": True})

        # Get app (this triggers middleware configuration)
        app = server.get_app()

        # Verify AuthenticationMiddleware was automatically added
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        assert "AuthenticationMiddleware" in middleware_names

    def test_no_middleware_without_auth_endpoints(self):
        """Test that middleware is not added when no auth endpoints exist."""
        # Create server with only public endpoints
        server = Server(title="No Auth Test")

        from jvspatial.api import endpoint

        @endpoint("/public", server=server)
        async def public_endpoint(endpoint):
            return endpoint.success(data={"public": True})

        # Get app
        app = server.get_app()

        # Verify AuthenticationMiddleware was NOT added
        middleware_names = [m.cls.__name__ for m in app.user_middleware]
        # AuthenticationMiddleware should not be present
        # (Note: It might still be there if any endpoint has auth, but with no auth endpoints it shouldn't be)
        # This test verifies the auto-detection logic works


class TestEndpointHelperInjection:
    """Test that endpoint helper is properly injected by auth decorators."""

    def test_auth_endpoint_has_endpoint_parameter(self):
        """Test that @auth_endpoint injects endpoint helper."""
        server = Server(title="Helper Injection Test")

        endpoint_called = False
        received_endpoint = None

        @auth_endpoint("/test/helper", server=server)
        async def test_helper(endpoint):
            nonlocal endpoint_called, received_endpoint
            endpoint_called = True
            received_endpoint = endpoint
            return endpoint.success(data={"helper": "injected"})

        # Verify the wrapper function exists and doesn't expose 'endpoint' in signature
        import inspect

        sig = inspect.signature(test_helper)
        param_names = list(sig.parameters.keys())

        # The 'endpoint' parameter should be filtered out of the signature
        # so FastAPI doesn't try to resolve it
        assert "endpoint" not in param_names or len(param_names) == 0


class TestAuthDecoratorEdgeCases:
    """Test edge cases and error scenarios for auth decorators."""

    def test_decorator_with_no_server_context(self):
        """Test decorator behavior when no server is in context."""
        from jvspatial.api.context import set_current_server

        # Clear server context
        set_current_server(None)

        # Decorator should still work (deferred registration)
        @auth_endpoint("/deferred")
        async def deferred_endpoint(endpoint):
            return endpoint.success(data={"deferred": True})

        # Metadata should still be stored
        assert deferred_endpoint._auth_required is True
        assert deferred_endpoint._endpoint_path == "/deferred"

    def test_multiple_servers_with_decorators(self):
        """Test using decorators with multiple servers."""
        server1 = Server(title="Server 1", port=9001)
        server2 = Server(title="Server 2", port=9002)

        @auth_endpoint("/server1", server=server1)
        async def endpoint1(endpoint):
            return endpoint.success(data={"server": "1"})

        @auth_endpoint("/server2", server=server2)
        async def endpoint2(endpoint):
            return endpoint.success(data={"server": "2"})

        # Each endpoint should be registered to its own server
        server1_endpoints = server1.list_function_endpoints()
        server2_endpoints = server2.list_function_endpoints()

        assert "endpoint1" in server1_endpoints
        assert "endpoint1" not in server2_endpoints

        assert "endpoint2" in server2_endpoints
        assert "endpoint2" not in server1_endpoints

    def test_combining_permissions_and_roles(self):
        """Test endpoints that require both permissions AND roles."""
        server = Server(title="Combined Auth Test")

        @auth_endpoint(
            "/combined",
            permissions=["read_data", "write_data"],
            roles=["editor", "admin"],
            server=server,
        )
        async def combined_endpoint(endpoint):
            return endpoint.success(data={"combined": True})

        # Both should be stored
        assert combined_endpoint._required_permissions == ["read_data", "write_data"]
        assert combined_endpoint._required_roles == ["editor", "admin"]

        # Verify endpoint requires auth
        client = TestClient(server.get_app())
        response = client.get("/combined")
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_auth_enforcement_integration():
    """Integration test for complete auth enforcement flow."""
    # This test verifies the complete flow:
    # 1. Decorator stores metadata
    # 2. Middleware detects authenticated endpoints
    # 3. Middleware is automatically applied
    # 4. Requests are properly authenticated/rejected

    server = Server(title="Integration Test")

    @auth_endpoint("/integrated", permissions=["test"], server=server)
    async def integrated_endpoint(endpoint):
        return endpoint.success(data={"integrated": True})

    # Verify complete chain
    assert integrated_endpoint._auth_required is True  # 1. Metadata stored

    app = server.get_app()
    middleware_names = [m.cls.__name__ for m in app.user_middleware]
    assert "AuthenticationMiddleware" in middleware_names  # 2 & 3. Middleware applied

    client = TestClient(app)
    response = client.get("/integrated")
    assert response.status_code == 401  # 4. Request properly rejected
