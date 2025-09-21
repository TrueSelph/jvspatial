"""
Integration test suite for the authentication system.

This module tests full authentication flows and integration with FastAPI server,
including end-to-end user journeys, middleware integration, and decorator functionality.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from jvspatial.api.auth import (
    APIKey,
    AuthenticationMiddleware,
    Session,
    User,
    admin_endpoint,
    auth_endpoint,
    auth_walker_endpoint,
    configure_auth,
)
from jvspatial.api.auth.middleware import auth_config
from jvspatial.api.server import Server, ServerConfig
from jvspatial.core.entities import Node, Walker, on_visit


class MockNode(Node):
    """Test node for auth integration tests."""

    name: str = "test"
    value: int = 0


class TestAuthIntegration:
    """Integration tests for the complete authentication system."""

    def setup_method(self):
        """Set up test environment."""
        # Reset auth configuration
        configure_auth(
            jwt_secret_key="test-secret-key-for-integration-tests",  # pragma: allowlist secret
            jwt_expiration_hours=24,
            rate_limit_enabled=True,
            default_rate_limit_per_hour=100,
        )

        # Create test users
        self.test_user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            password_hash=User.hash_password("password123"),
            roles=["user"],
            permissions=["read_data"],
            is_active=True,
            rate_limit_per_hour=50,
        )

        self.admin_user = User(
            id="admin_123",
            username="admin",
            email="admin@example.com",
            password_hash=User.hash_password("adminpass"),
            roles=["admin"],
            permissions=["admin_access"],
            is_active=True,
            is_admin=True,
        )

    def test_server_auth_configuration(self):
        """Test server with authentication middleware configuration."""
        # Create server with auth configuration
        server_config = ServerConfig(title="Test Auth API", debug=True, port=8001)

        server = Server(config=server_config)

        # Add authentication middleware
        app = server.get_app()

        # Verify middleware can be added
        middleware = AuthenticationMiddleware(app)
        assert middleware is not None
        assert middleware.exempt_paths == [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/health",
            "/auth/login",
            "/auth/register",
        ]

    def test_auth_walker_endpoint_registration(self):
        """Test authenticated walker endpoint registration."""
        server = Server(title="Auth Walker Test")

        @auth_walker_endpoint("/auth/data", permissions=["read_data"], server=server)
        class AuthDataWalker(Walker):
            query: str = ""

            @on_visit(MockNode)
            async def process_data(self, here):
                self.response["data"] = f"Processed: {here.name} - {self.query}"

        # Check walker is registered with auth requirements
        assert AuthDataWalker in server._registered_walker_classes
        assert hasattr(AuthDataWalker, "_auth_required")
        assert AuthDataWalker._auth_required is True
        assert AuthDataWalker._required_permissions == ["read_data"]

    def test_auth_endpoint_registration(self):
        """Test authenticated endpoint registration."""
        server = Server(title="Auth Endpoint Test")

        @auth_endpoint("/auth/info", roles=["user"], server=server)
        async def get_auth_info():
            return {"message": "Authenticated info", "timestamp": datetime.now()}

        # Check function is registered
        assert get_auth_info in server._function_endpoint_mapping
        assert hasattr(get_auth_info, "_auth_required")
        assert get_auth_info._auth_required is True
        assert get_auth_info._required_roles == ["user"]

    def test_admin_endpoint_registration(self):
        """Test admin endpoint registration."""
        server = Server(title="Admin Test")

        @admin_endpoint("/admin/status")
        async def admin_status():
            return {"admin": True, "status": "ok"}

        # Check admin requirements
        assert hasattr(admin_status, "_auth_required")
        assert admin_status._auth_required is True
        assert admin_status._required_roles == ["admin"]

    @pytest.mark.asyncio
    async def test_authentication_flow_middleware(self):
        """Test authentication flow through middleware."""
        # Create a mock request
        from fastapi import Request

        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        # Test with public path (should bypass)
        public_request = MagicMock(spec=Request)
        public_request.url.path = "/docs"

        async def call_next_public(req):
            return "public_response"

        result = await middleware.dispatch(public_request, call_next_public)
        assert result == "public_response"

        # Test with protected path and valid user
        protected_request = MagicMock(spec=Request)
        protected_request.url.path = "/api/protected"
        protected_request.state = MagicMock()
        protected_request.state.required_roles = []
        protected_request.state.required_permissions = []

        with patch.object(middleware, "_authenticate_jwt", return_value=self.test_user):
            with patch(
                "jvspatial.api.auth.middleware.rate_limiter.is_allowed",
                return_value=True,
            ):

                async def call_next_protected(req):
                    return "protected_response"

                result = await middleware.dispatch(
                    protected_request, call_next_protected
                )
                assert result == "protected_response"
                assert protected_request.state.current_user == self.test_user

    @pytest.mark.asyncio
    async def test_authentication_flow_no_user(self):
        """Test authentication flow when no user is authenticated."""
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        protected_request = MagicMock()
        protected_request.url.path = "/api/protected"
        protected_request.state = MagicMock()
        protected_request.state.required_roles = []
        protected_request.state.required_permissions = []

        # Mock no authentication
        with patch.object(middleware, "_authenticate_jwt", return_value=None):
            with patch.object(middleware, "_authenticate_api_key", return_value=None):
                result = await middleware.dispatch(protected_request, AsyncMock())

                assert isinstance(result, JSONResponse)
                assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_permission_checking_flow(self):
        """Test permission checking in authentication flow."""
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        protected_request = MagicMock()
        protected_request.url.path = "/api/admin"
        protected_request.state = MagicMock()
        protected_request.state.required_permissions = ["admin_access"]
        protected_request.state.required_roles = []

        # User without admin permission
        with patch.object(middleware, "_authenticate_jwt", return_value=self.test_user):
            result = await middleware.dispatch(protected_request, AsyncMock())

            assert isinstance(result, JSONResponse)
            assert result.status_code == 403

        # Admin user with permission
        with patch.object(
            middleware, "_authenticate_jwt", return_value=self.admin_user
        ):
            with patch(
                "jvspatial.api.auth.middleware.rate_limiter.is_allowed",
                return_value=True,
            ):

                async def call_next_admin(req):
                    return "admin_response"

                result = await middleware.dispatch(protected_request, call_next_admin)
                assert result == "admin_response"

    @pytest.mark.asyncio
    async def test_rate_limiting_flow(self):
        """Test rate limiting in authentication flow."""
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        protected_request = MagicMock()
        protected_request.url.path = "/api/data"
        protected_request.state = MagicMock()

        # Simulate rate limit exceeded
        with patch.object(middleware, "_authenticate_jwt", return_value=self.test_user):
            with patch(
                "jvspatial.api.auth.middleware.rate_limiter.is_allowed",
                return_value=False,
            ):
                result = await middleware.dispatch(protected_request, AsyncMock())

                assert isinstance(result, JSONResponse)
                assert result.status_code == 429

    @pytest.mark.asyncio
    async def test_api_key_authentication_flow(self):
        """Test API key authentication flow."""
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        # Create test API key
        test_api_key = APIKey(
            key_id="test_key_123",
            name="Test Key",
            key_hash=APIKey.hash_secret("secret_456"),
            user_id=self.test_user.id,
            is_active=True,
            allowed_endpoints=["/api/data/*"],
        )

        api_request = MagicMock()
        api_request.url.path = "/api/data/list"
        api_request.state = MagicMock()
        api_request.state.required_roles = []
        api_request.state.required_permissions = []
        api_request.headers.get.return_value = "test_key_123:secret_456"
        api_request.query_params.get.return_value = None

        with patch(
            "jvspatial.api.auth.entities.APIKey.find_by_key_id",
            return_value=test_api_key,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.get", return_value=self.test_user
            ):
                with patch(
                    "jvspatial.api.auth.middleware.rate_limiter.is_allowed",
                    return_value=True,
                ):
                    with patch.object(
                        APIKey, "record_usage", new_callable=AsyncMock
                    ) as mock_record:

                        async def call_next_api(req):
                            return "api_response"

                        result = await middleware.dispatch(api_request, call_next_api)
                        assert result == "api_response"
                        assert api_request.state.current_user == self.test_user
                        mock_record.assert_called_once()

    def test_complete_server_with_auth_endpoints(self):
        """Test complete server setup with authentication endpoints."""
        server = Server(title="Complete Auth Test", debug=True)

        # Add public walker
        @server.walker("/public/data")
        class PublicWalker(Walker):
            query: str = ""

            @on_visit(MockNode)
            async def process(self, here):
                self.response["public"] = True

        # Add authenticated walker
        @auth_walker_endpoint("/auth/data", permissions=["read_data"], server=server)
        class AuthWalker(Walker):
            query: str = ""

            @on_visit(MockNode)
            async def process(self, here):
                self.response["authenticated"] = True

        # Add admin walker
        @admin_endpoint("/admin/control", server=server)
        async def admin_control():
            return {"admin": True, "control": "active"}

        # Verify all endpoints are registered
        assert len(server._registered_walker_classes) == 2
        assert PublicWalker in server._registered_walker_classes
        assert AuthWalker in server._registered_walker_classes
        assert admin_control in server._function_endpoint_mapping

    def test_auth_configuration_persistence(self):
        """Test that auth configuration persists across components."""
        # Configure auth settings
        configure_auth(
            jwt_secret_key="persistent-secret",  # pragma: allowlist secret
            jwt_expiration_hours=48,
            rate_limit_enabled=False,
        )

        # Verify configuration is applied
        assert (
            auth_config.jwt_secret_key
            == "persistent-secret"  # pragma: allowlist secret
        )
        assert auth_config.jwt_expiration_hours == 48
        assert auth_config.rate_limit_enabled is False

        # Create JWT manager and verify it uses the config
        from jvspatial.api.auth.middleware import JWTManager

        token = JWTManager.create_access_token(self.test_user)
        assert token is not None

        # Verify token was created with correct secret
        payload = JWTManager.verify_token(token)
        assert payload["sub"] == self.test_user.id

    @pytest.mark.asyncio
    async def test_user_session_lifecycle(self):
        """Test complete user session lifecycle."""
        # Create session
        from jvspatial.api.auth.middleware import JWTManager, create_user_session

        mock_request = MagicMock()
        mock_request.client.host = "127.0.0.1"
        mock_request.headers.get.return_value = "Test Browser"

        with patch("jvspatial.api.auth.entities.Session.create") as mock_create:
            session = MagicMock()
            session.session_id = "session_123"
            session.jwt_token = "jwt_token"
            session.refresh_token = "refresh_token"
            mock_create.return_value = session

            result = await create_user_session(self.test_user, mock_request)

            assert result == session
            mock_create.assert_called_once()

    def test_auth_decorators_integration(self):
        """Test integration between different auth decorators."""
        server = Server(title="Decorator Integration Test")

        # Test different permission levels
        @server.walker("/public")
        class PublicWalker(Walker):
            pass

        @auth_walker_endpoint("/user", roles=["user"], server=server)
        class UserWalker(Walker):
            pass

        @auth_walker_endpoint(
            "/manager", roles=["manager"], permissions=["manage_data"], server=server
        )
        class ManagerWalker(Walker):
            pass

        @admin_endpoint("/admin/system", server=server)
        async def admin_system():
            return {"system": "admin"}

        # Verify different auth levels
        assert not hasattr(PublicWalker, "_auth_required")  # Public
        assert UserWalker._auth_required is True
        assert UserWalker._required_roles == ["user"]
        assert ManagerWalker._required_roles == ["manager"]
        assert ManagerWalker._required_permissions == ["manage_data"]
        assert admin_system._required_roles == ["admin"]

    def test_auth_exception_handling(self):
        """Test authentication exception handling."""
        from jvspatial.api.auth.entities import (
            APIKeyInvalidError,
            AuthenticationError,
            AuthorizationError,
            InvalidCredentialsError,
            SessionExpiredError,
            UserNotFoundError,
        )

        # Test exception hierarchy
        auth_error = AuthenticationError("Auth failed")
        assert isinstance(auth_error, Exception)

        invalid_creds = InvalidCredentialsError("Invalid creds")
        assert isinstance(invalid_creds, AuthenticationError)

        user_not_found = UserNotFoundError("User not found")
        assert isinstance(user_not_found, AuthenticationError)

        session_expired = SessionExpiredError("Session expired")
        assert isinstance(session_expired, AuthenticationError)

        api_key_invalid = APIKeyInvalidError("Invalid API key")
        assert isinstance(api_key_invalid, AuthenticationError)

    @pytest.mark.asyncio
    async def test_middleware_error_responses(self):
        """Test middleware error response formats."""
        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        # Test authentication error response
        protected_request = MagicMock()
        protected_request.url.path = "/api/protected"
        protected_request.state = MagicMock()
        protected_request.state.required_roles = []
        protected_request.state.required_permissions = []

        from jvspatial.api.auth.entities import AuthenticationError

        with patch.object(
            middleware,
            "_authenticate_jwt",
            side_effect=AuthenticationError("Auth error"),
        ):
            result = await middleware.dispatch(protected_request, AsyncMock())

            # Should handle exception gracefully and return 401 JSONResponse
            assert isinstance(result, JSONResponse)
            assert result.status_code == 401

    def test_auth_system_components_integration(self):
        """Test integration between all auth system components."""
        # Verify all components can work together
        server = Server(title="Full Integration Test")

        # Configure authentication
        configure_auth(
            jwt_secret_key="integration-test-secret",  # pragma: allowlist secret
            jwt_expiration_hours=24,
            rate_limit_enabled=True,
        )

        # Create authenticated endpoints
        @auth_walker_endpoint(
            "/integrated/walker", permissions=["read_data"], server=server
        )
        class IntegratedWalker(Walker):
            @on_visit(MockNode)
            async def process(self, here):
                self.response["integrated"] = True

        @admin_endpoint("/integrated/admin", server=server)
        async def integrated_admin():
            return {"integrated": "admin"}

        # Add middleware
        app = server.get_app()
        middleware = AuthenticationMiddleware(app)

        # Verify complete setup
        assert IntegratedWalker._auth_required is True
        assert integrated_admin._auth_required is True
        assert middleware is not None
        assert (
            auth_config.jwt_secret_key
            == "integration-test-secret"  # pragma: allowlist secret
        )

    def test_auth_entities_integration(self):
        """Test integration between auth entities."""
        # Test User-APIKey relationship
        api_key = APIKey(
            name="User API Key",
            key_id="user_key_123",
            key_hash="hashed_secret",
            user_id=self.test_user.id,
            allowed_endpoints=["/api/user/*"],
        )

        # Test User-Session relationship
        session = Session(
            session_id="user_session_123",
            user_id=self.test_user.id,
            jwt_token="jwt_token",
            refresh_token="refresh_token",
            expires_at=datetime.now() + timedelta(hours=24),
        )

        # Verify relationships
        assert api_key.user_id == self.test_user.id
        assert session.user_id == self.test_user.id
        assert api_key.is_valid() is True
        assert session.is_valid() is True

    def teardown_method(self):
        """Clean up after tests."""
        # Reset auth configuration to defaults
        configure_auth(
            jwt_secret_key="your-secret-key-change-in-production",  # pragma: allowlist secret
            jwt_expiration_hours=24,
            rate_limit_enabled=True,
            default_rate_limit_per_hour=1000,
        )


class TestAuthSystemScenarios:
    """Test realistic authentication system scenarios."""

    def setup_method(self):
        """Set up realistic test scenario."""
        self.server = Server(title="Auth Scenario Test", debug=True)

        # Configure auth for scenario testing
        configure_auth(
            jwt_secret_key="scenario-test-secret-key",  # pragma: allowlist secret
            jwt_expiration_hours=8,
            rate_limit_enabled=True,
            default_rate_limit_per_hour=500,
        )

    def test_api_documentation_scenario(self):
        """Test API with public documentation but protected endpoints."""

        # Public documentation endpoints (should not require auth)
        @self.server.route("/public/docs")
        async def public_docs():
            return {"docs": "public", "version": "1.0"}

        # Protected API endpoints
        @auth_walker_endpoint("/api/v1/data", permissions=["api_access"])
        class APIDataWalker(Walker):
            filter: str = ""
            limit: int = 10

            @on_visit(MockNode)
            async def get_data(self, here):
                self.response["data"] = [{"id": 1, "name": here.name}]

        # Admin management endpoints
        @admin_endpoint("/api/v1/admin/stats")
        async def api_stats():
            return {"requests": 1000, "users": 50, "uptime": "99.9%"}

        # Verify endpoint configuration
        public_endpoints = [
            r for r in self.server._custom_routes if "/public/" in r["path"]
        ]
        assert len(public_endpoints) == 1

        assert APIDataWalker._auth_required is True
        assert api_stats._required_roles == ["admin"]

    def test_multi_tenant_scenario(self):
        """Test multi-tenant application with role-based access."""

        # Tenant admin endpoints
        @auth_walker_endpoint("/tenant/admin", roles=["tenant_admin"])
        class TenantAdminWalker(Walker):
            tenant_id: str = ""
            action: str = ""

            @on_visit(MockNode)
            async def manage_tenant(self, here):
                self.response["tenant_action"] = f"{self.action} for {self.tenant_id}"

        # User data endpoints with tenant isolation
        @auth_walker_endpoint("/tenant/data", permissions=["read_tenant_data"])
        class TenantDataWalker(Walker):
            tenant_id: str = ""

            @on_visit(MockNode)
            async def get_tenant_data(self, here):
                # In real implementation, would filter by tenant
                self.response["tenant_data"] = {"tenant": self.tenant_id}

        # System admin endpoints
        @admin_endpoint("/system/tenants")
        async def manage_tenants():
            return {"tenants": ["tenant1", "tenant2"], "system": "active"}

        # Verify multi-level auth setup
        assert TenantAdminWalker._required_roles == ["tenant_admin"]
        assert TenantDataWalker._required_permissions == ["read_tenant_data"]
        assert manage_tenants._required_roles == ["admin"]

    def test_api_versioning_scenario(self):
        """Test API versioning with different auth requirements."""

        # V1 API - simple auth
        @auth_endpoint("/api/v1/simple", roles=["user"])
        async def v1_simple():
            return {"version": "1.0", "message": "simple auth"}

        # V2 API - enhanced auth with permissions
        @auth_walker_endpoint(
            "/api/v2/enhanced", roles=["user"], permissions=["api_v2_access"]
        )
        class V2EnhancedWalker(Walker):
            feature: str = ""

            @on_visit(MockNode)
            async def v2_feature(self, here):
                self.response["version"] = "2.0"
                self.response["feature"] = self.feature
                self.response["enhanced"] = True

        # V3 API - role-based features
        @auth_endpoint("/api/v3/premium", roles=["premium", "admin"])
        async def v3_premium():
            return {"version": "3.0", "premium": True}

        # Verify versioned auth requirements
        assert v1_simple._required_roles == ["user"]
        assert len(v1_simple._required_permissions) == 0

        assert V2EnhancedWalker._required_roles == ["user"]
        assert V2EnhancedWalker._required_permissions == ["api_v2_access"]

        assert v3_premium._required_roles == ["premium", "admin"]

    def test_microservice_integration_scenario(self):
        """Test microservice integration with API key authentication."""

        # Service-to-service endpoints (API key auth)
        @auth_walker_endpoint("/internal/sync", permissions=["service_sync"])
        class ServiceSyncWalker(Walker):
            service_name: str = ""
            data_type: str = ""

            @on_visit(MockNode)
            async def sync_data(self, here):
                self.response["sync"] = {
                    "service": self.service_name,
                    "type": self.data_type,
                    "status": "synced",
                }

        # Webhook endpoints for external integration
        @auth_endpoint("/webhooks/external", permissions=["webhook_access"])
        async def external_webhook():
            return {"webhook": "processed", "timestamp": datetime.now().isoformat()}

        # Health check for services (no auth)
        @self.server.route("/internal/health")
        async def service_health():
            return {"status": "healthy", "service": "auth-system"}

        # Verify service integration setup
        assert ServiceSyncWalker._required_permissions == ["service_sync"]
        assert external_webhook._required_permissions == ["webhook_access"]

        # Health check should not require auth
        health_routes = [
            r for r in self.server._custom_routes if "/health" in r["path"]
        ]
        assert len(health_routes) == 1

    def teardown_method(self):
        """Clean up scenario test."""
        configure_auth(
            jwt_secret_key="your-secret-key-change-in-production",  # pragma: allowlist secret
            jwt_expiration_hours=24,
            rate_limit_enabled=True,
        )
