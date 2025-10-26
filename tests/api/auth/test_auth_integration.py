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
    configure_auth,
)
from jvspatial.api.auth.middleware import auth_config
from jvspatial.api.decorators import endpoint
from jvspatial.api.server import Server, ServerConfig
from jvspatial.core import on_visit
from jvspatial.core.entities import Node, Walker


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
            email="test@example.com",
            password_hash=User.hash_password("password123"),
            roles=["user"],
            permissions=["read_data"],
            is_active=True,
            rate_limit_per_hour=50,
        )

        self.admin_user = User(
            id="admin_123",
            email="admin@example.com",
            password_hash=User.hash_password("adminpass"),
            roles=["admin"],
            permissions=["admin_access"],
            is_active=True,
            is_admin=True,
        )

    async def test_server_auth_configuration(self):
        """Test server with authentication middleware configuration."""
        # Create server with auth configuration
        server_config = ServerConfig(title="Test Auth API", debug=True, port=8001)

        server = Server(config=server_config)

        # Add authentication middleware
        app = server.get_app()

        # Verify middleware can be added
        middleware = AuthenticationMiddleware(app)
        assert middleware is not None
        assert "/" in middleware.exempt_paths
        assert "/docs" in middleware.exempt_paths
        assert "/auth/login" in middleware.exempt_paths
        assert "/auth/register" in middleware.exempt_paths

    async def test_auth_endpoint_walker_registration(self):
        """Test auth_endpoint registration with Walker class."""
        server = Server(title="Auth Walker Test")

        @auth_endpoint(
            "/auth/data",
            permissions=["read_data"],
        )
        class AuthDataWalker(Walker):
            query: str = ""

            @on_visit(MockNode)
            async def process_data(self, here):
                self.report({"data": f"Processed: {here.name} - {self.query}"})

        # In the new system, endpoints are not automatically registered
        # Check that the walker has the correct decorator configuration
        assert hasattr(AuthDataWalker, "_endpoint_config")
        config = AuthDataWalker.__dict__["_endpoint_config"]
        assert config.auth_required is True
        assert config.permissions == ["read_data"]

    async def test_auth_endpoint_registration(self):
        """Test authenticated endpoint registration."""
        server = Server(title="Auth Endpoint Test")

        @auth_endpoint(
            "/auth/info",
            roles=["user"],
        )
        async def get_auth_info():
            return {"message": "Authenticated info", "timestamp": datetime.now()}

        # In the new system, endpoints are not automatically registered
        # Check that the function has the correct decorator configuration
        assert hasattr(get_auth_info, "_endpoint_config")
        config = get_auth_info._endpoint_config
        assert config.auth_required is True
        assert config.roles == ["user"]

    async def test_admin_endpoint_registration(self):
        """Test admin endpoint registration."""
        server = Server(title="Admin Test")

        @admin_endpoint("/admin/status")
        async def admin_status():
            return {"admin": True, "status": "ok"}

        # Check admin requirements
        assert hasattr(admin_status, "_endpoint_config")
        config = admin_status._endpoint_config
        assert config.auth_required is True
        assert config.roles == ["admin"]

    @pytest.mark.asyncio
    async def test_complete_auth_flow_with_session_management(self):
        """Test complete authentication flow with session management."""
        from jvspatial.api.auth.endpoints import (
            LoginRequest,
            LogoutRequest,
            UserRegistrationRequest,
        )
        from jvspatial.api.auth.entities import Session, User

        # Test user registration
        register_request = UserRegistrationRequest(
            email="test@example.com",
            password="password123",  # pragma: allowlist secret
            confirm_password="password123",  # pragma: allowlist secret
        )

        with patch(
            "jvspatial.api.auth.entities.User.find_by_email", new_callable=AsyncMock
        ) as mock_find_email:
            with patch(
                "jvspatial.api.auth.entities.User.create", new_callable=AsyncMock
            ) as mock_create:
                mock_find_email.return_value = None

                mock_user = User(
                    id="user_123",
                    email="test@example.com",
                    password_hash="hashed",  # pragma: allowlist secret
                    created_at=datetime.now().isoformat(),
                )
                mock_create.return_value = mock_user

                from jvspatial.api.auth.endpoints import register_user

                result = await register_user(register_request)

                assert result["status"] == "success"
                assert result["user"]["email"] == "test@example.com"

        # Test user login
        login_request = LoginRequest(
            email="test@example.com",
            password="password123",  # pragma: allowlist secret
        )

        with patch(
            "jvspatial.api.auth.endpoints.authenticate_user", new_callable=AsyncMock
        ) as mock_auth:
            with patch(
                "jvspatial.api.auth.endpoints.JWTManager.create_access_token"
            ) as mock_access:
                with patch(
                    "jvspatial.api.auth.endpoints.JWTManager.create_refresh_token"
                ) as mock_refresh:
                    with patch(
                        "jvspatial.api.auth.entities.Session.create",
                        new_callable=AsyncMock,
                    ) as mock_session_create:
                        mock_auth.return_value = mock_user
                        mock_access.return_value = "access_token"
                        mock_refresh.return_value = "refresh_token"

                        mock_session = Session(
                            session_id="session_123",
                            user_id="user_123",
                            jwt_token="access_token",
                            refresh_token="refresh_token",
                            expires_at=(
                                datetime.now() + timedelta(hours=24)
                            ).isoformat(),
                        )
                        mock_session_create.return_value = mock_session

                        from jvspatial.api.auth.endpoints import login_user

                        result = await login_user(login_request)

                        assert result["status"] == "success"
                        assert result["access_token"] == "access_token"
                        assert result["refresh_token"] == "refresh_token"

        # Test user logout with session revocation
        logout_request = LogoutRequest(revoke_all_sessions=False)
        mock_request = MagicMock()
        mock_request.headers = {"Authorization": "Bearer access_token"}

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=mock_user
        ):
            with patch(
                "jvspatial.core.context.get_default_context"
            ) as mock_get_context:
                mock_ctx = MagicMock()
                mock_get_context.return_value = mock_ctx

                mock_session_data = [
                    {
                        "session_id": "session_123",
                        "user_id": "user_123",
                        "jwt_token": "access_token",
                        "refresh_token": "refresh_token",
                        "expires_at": (
                            datetime.now() + timedelta(hours=24)
                        ).isoformat(),
                        "is_active": True,
                    }
                ]
                mock_ctx.database.find = AsyncMock(return_value=mock_session_data)

                with patch(
                    "jvspatial.api.auth.entities.Session.revoke", new_callable=AsyncMock
                ) as mock_revoke:
                    from jvspatial.api.auth.endpoints import logout_user

                    result = await logout_user(logout_request, mock_request)

                    assert result["status"] == "success"
                    assert result["message"] == "Logged out successfully"
                    mock_revoke.assert_called_once_with("User logout")

    @pytest.mark.asyncio
    async def test_authentication_flow_middleware(self):
        """Test authentication flow through middleware."""
        # Create a mock request
        from types import SimpleNamespace

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
        protected_request.state = SimpleNamespace(
            endpoint_auth=True,
            required_roles=[],
            required_permissions=[],
            current_user=self.test_user,  # Pre-set the user to bypass authentication
        )

        with patch(
            "jvspatial.api.auth.middleware.rate_limiter.is_allowed",
            return_value=True,
        ):

            async def call_next_protected(req):
                return "protected_response"

            result = await middleware.dispatch(protected_request, call_next_protected)
            assert result == "protected_response"
            assert protected_request.state.current_user == self.test_user

    @pytest.mark.asyncio
    async def test_authentication_flow_no_user(self):
        """Test authentication flow when no user is authenticated."""
        from types import SimpleNamespace

        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        protected_request = MagicMock()
        protected_request.url.path = "/api/protected"
        protected_request.state = SimpleNamespace(
            endpoint_auth=True, required_roles=[], required_permissions=[]
        )

        # Mock no authentication
        with patch.object(middleware, "_authenticate_jwt", return_value=None):
            with patch.object(middleware, "_authenticate_api_key", return_value=None):
                result = await middleware.dispatch(protected_request, AsyncMock())

                assert isinstance(result, JSONResponse)
                assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_permission_checking_flow(self):
        """Test permission checking in authentication flow."""
        from types import SimpleNamespace

        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        protected_request = MagicMock()
        protected_request.url.path = "/api/admin"
        protected_request.state = SimpleNamespace(
            endpoint_auth=True,
            required_permissions=["admin_access"],
            required_roles=[],
            current_user=self.test_user,
        )

        # User without admin permission
        result = await middleware.dispatch(protected_request, AsyncMock())

        assert isinstance(result, JSONResponse)
        assert result.status_code == 403

        # Create fresh request state for next test
        protected_request.state = SimpleNamespace(
            endpoint_auth=True,
            required_permissions=["admin_access"],
            required_roles=[],
            current_user=self.admin_user,
        )

        # Admin user with permission
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
        from types import SimpleNamespace

        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        protected_request = MagicMock()
        protected_request.url.path = "/api/data"
        protected_request.state = SimpleNamespace(
            endpoint_auth=True, current_user=self.test_user
        )

        # Simulate rate limit exceeded
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
        from types import SimpleNamespace

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
        api_request.state = SimpleNamespace(
            endpoint_auth=True,
            required_roles=[],
            required_permissions=[],
            current_user=self.test_user,
        )

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

    async def test_complete_server_with_auth_endpoints(self):
        """Test complete server setup with authentication endpoints."""
        from jvspatial.api.context import set_current_server

        server = Server(title="Complete Auth Test", debug=True)
        set_current_server(server)  # Ensure this server is current for decorators

        # Add public walker
        @endpoint(
            "/public/data",
        )
        class PublicWalker(Walker):
            query: str = ""

            @on_visit(MockNode)
            async def process(self, here):
                self.report({"public": True})

        # Add authenticated walker
        @auth_endpoint(
            "/auth/data",
            permissions=["read_data"],
        )
        class AuthWalker(Walker):
            query: str = ""

            @on_visit(MockNode)
            async def process(self, here):
                self.report({"authenticated": True})

        # Add admin walker
        @admin_endpoint(
            "/admin/control",
        )
        async def admin_control():
            return {"admin": True, "control": "active"}

        # In the new system, endpoints are not automatically registered
        # Check that the decorator configurations are correct
        assert hasattr(PublicWalker, "_endpoint_config")
        assert hasattr(AuthWalker, "_endpoint_config")
        assert hasattr(admin_control, "_endpoint_config")

        # Check configurations
        public_config = PublicWalker.__dict__["_endpoint_config"]
        auth_config = AuthWalker.__dict__["_endpoint_config"]
        admin_config = admin_control._endpoint_config

        assert public_config.auth_required is False
        assert auth_config.auth_required is True
        assert auth_config.permissions == ["read_data"]
        assert admin_config.auth_required is True
        assert admin_config.roles == ["admin"]

    async def test_auth_configuration_persistence(self):
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

        with patch(
            "jvspatial.api.auth.entities.Session.create", new_callable=AsyncMock
        ) as mock_create:
            session = MagicMock()
            session.session_id = "session_123"
            session.jwt_token = "jwt_token"
            session.refresh_token = "refresh_token"
            mock_create.return_value = session

            result = await create_user_session(self.test_user, mock_request)

            assert result == session
            mock_create.assert_called_once()

    async def test_auth_decorators_integration(self):
        """Test integration between different auth decorators."""
        server = Server(title="Decorator Integration Test")

        # Test different permission levels
        @endpoint(
            "/public",
        )
        class PublicWalker(Walker):
            pass

        @auth_endpoint(
            "/user",
            roles=["user"],
        )
        class UserWalker(Walker):
            pass

        @auth_endpoint(
            "/manager",
            roles=["manager"],
            permissions=["manage_data"],
        )
        class ManagerWalker(Walker):
            pass

        @admin_endpoint(
            "/admin/system",
        )
        async def admin_system():
            return {"system": "admin"}

        # Verify different auth levels
        public_config = PublicWalker.__dict__["_endpoint_config"]
        user_config = UserWalker.__dict__["_endpoint_config"]
        manager_config = ManagerWalker.__dict__["_endpoint_config"]
        admin_config = admin_system._endpoint_config

        assert public_config.auth_required is False  # Public
        assert user_config.auth_required is True
        assert user_config.roles == ["user"]
        assert manager_config.roles == ["manager"]
        assert manager_config.permissions == ["manage_data"]
        assert admin_config.roles == ["admin"]

    async def test_auth_exception_handling(self):
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
        from types import SimpleNamespace

        app = FastAPI()
        middleware = AuthenticationMiddleware(app)

        # Test authentication error response
        protected_request = MagicMock()
        protected_request.url.path = "/api/protected"
        protected_request.state = SimpleNamespace(
            endpoint_auth=True, required_roles=[], required_permissions=[]
        )

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

    async def test_auth_system_components_integration(self):
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
        @auth_endpoint(
            "/integrated/walker",
            permissions=["read_data"],
        )
        class IntegratedWalker(Walker):
            @on_visit(MockNode)
            async def process(self, here):
                self.report({"integrated": True})

        @admin_endpoint(
            "/integrated/admin",
        )
        async def integrated_admin():
            return {"integrated": "admin"}

        # Add middleware
        app = server.get_app()
        middleware = AuthenticationMiddleware(app)

        # Verify complete setup
        walker_config = IntegratedWalker.__dict__["_endpoint_config"]
        admin_config = integrated_admin._endpoint_config
        assert walker_config.auth_required is True
        assert admin_config.auth_required is True
        assert middleware is not None
        assert (
            auth_config.jwt_secret_key
            == "integration-test-secret"  # pragma: allowlist secret
        )

    async def test_auth_entities_integration(self):
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
            expires_at=(datetime.now() + timedelta(hours=24)).isoformat(),
        )

        # Verify relationships
        assert api_key.user_id == self.test_user.id
        assert session.user_id == self.test_user.id
        assert api_key.is_valid() is True
        assert session.is_valid() is True

    def teardown_method(self):
        """Clean up after tests."""
        from jvspatial.api.context import set_current_server

        # Reset auth configuration to defaults
        configure_auth(
            jwt_secret_key="your-secret-key-change-in-production",  # pragma: allowlist secret
            jwt_expiration_hours=24,
            rate_limit_enabled=True,
            default_rate_limit_per_hour=1000,
        )
        set_current_server(None)


class TestAuthSystemScenarios:
    """Test realistic authentication system scenarios."""

    def setup_method(self):
        """Set up realistic test scenario."""
        from jvspatial.api.context import set_current_server

        self.server = Server(title="Auth Scenario Test", debug=True)
        set_current_server(self.server)  # Ensure this server is current for decorators

        # Configure auth for scenario testing
        configure_auth(
            jwt_secret_key="scenario-test-secret-key",  # pragma: allowlist secret
            jwt_expiration_hours=8,
            rate_limit_enabled=True,
            default_rate_limit_per_hour=500,
        )

    async def test_api_documentation_scenario(self):
        """Test API with public documentation but protected endpoints."""

        # Public documentation endpoints (should not require auth)
        @endpoint("/public/docs")
        async def public_docs():
            return {"docs": "public", "version": "1.0"}

        # Protected API endpoints
        @auth_endpoint("/api/v1/data", permissions=["api_access"])
        class APIDataWalker(Walker):
            filter: str = ""
            limit: int = 10

            @on_visit(MockNode)
            async def get_data(self, here):
                self.report({"data": [{"id": 1, "name": here.name}]})

        # Admin management endpoints
        @admin_endpoint("/api/v1/admin/stats")
        async def api_stats():
            return {"requests": 1000, "users": 50, "uptime": "99.9%"}

        # Verify endpoint configuration
        # In the new system, endpoints are not automatically registered
        # Check that the decorator configurations are correct
        assert hasattr(public_docs, "_endpoint_config")
        assert hasattr(APIDataWalker, "_endpoint_config")
        assert hasattr(api_stats, "_endpoint_config")

        public_config = public_docs._endpoint_config
        walker_config = APIDataWalker.__dict__["_endpoint_config"]
        admin_config = api_stats._endpoint_config

        assert public_config.auth_required is False
        assert walker_config.auth_required is True
        assert walker_config.permissions == ["api_access"]
        assert admin_config.auth_required is True
        assert admin_config.roles == ["admin"]

    async def test_multi_tenant_scenario(self):
        """Test multi-tenant application with role-based access."""

        # Tenant admin endpoints
        @auth_endpoint("/tenant/admin", roles=["tenant_admin"])
        class TenantAdminWalker(Walker):
            tenant_id: str = ""
            action: str = ""

            @on_visit(MockNode)
            async def manage_tenant(self, here):
                self.report({"tenant_action": f"{self.action} for {self.tenant_id}"})

        # User data endpoints with tenant isolation
        @auth_endpoint("/tenant/data", permissions=["read_tenant_data"])
        class TenantDataWalker(Walker):
            tenant_id: str = ""

            @on_visit(MockNode)
            async def get_tenant_data(self, here):
                # In real implementation, would filter by tenant
                self.report({"tenant_data": {"tenant": self.tenant_id}})

        # System admin endpoints
        @admin_endpoint("/system/tenants")
        async def manage_tenants():
            return {"tenants": ["tenant1", "tenant2"], "system": "active"}

        # Verify multi-level auth setup
        admin_config = TenantAdminWalker.__dict__["_endpoint_config"]
        data_config = TenantDataWalker.__dict__["_endpoint_config"]
        manage_config = manage_tenants._endpoint_config

        assert admin_config.roles == ["tenant_admin"]
        assert data_config.permissions == ["read_tenant_data"]
        assert manage_config.roles == ["admin"]

    async def test_api_versioning_scenario(self):
        """Test API versioning with different auth requirements."""

        # V1 API - simple auth
        @auth_endpoint("/api/v1/simple", roles=["user"])
        async def v1_simple():
            return {"version": "1.0", "message": "simple auth"}

        # V2 API - enhanced auth with permissions
        @auth_endpoint(
            "/api/v2/enhanced", roles=["user"], permissions=["api_v2_access"]
        )
        class V2EnhancedWalker(Walker):
            feature: str = ""

            @on_visit(MockNode)
            async def v2_feature(self, here):
                self.report(
                    {"version": "2.0", "feature": self.feature, "enhanced": True}
                )

        # V3 API - role-based features
        @auth_endpoint("/api/v3/premium", roles=["premium", "admin"])
        async def v3_premium():
            return {"version": "3.0", "premium": True}

        # Verify versioned auth requirements
        v1_config = v1_simple._endpoint_config
        v2_config = V2EnhancedWalker.__dict__["_endpoint_config"]

        assert v1_config.roles == ["user"]
        assert len(v1_config.permissions) == 0

        assert v2_config.roles == ["user"]
        assert v2_config.permissions == ["api_v2_access"]

        v3_config = v3_premium._endpoint_config
        assert v3_config.roles == ["premium", "admin"]

    async def test_microservice_integration_scenario(self):
        """Test microservice integration with API key authentication."""

        # Service-to-service endpoints (API key auth)
        @auth_endpoint("/internal/sync", permissions=["service_sync"])
        class ServiceSyncWalker(Walker):
            service_name: str = ""
            data_type: str = ""

            @on_visit(MockNode)
            async def sync_data(self, here):
                self.report(
                    {
                        "sync": {
                            "service": self.service_name,
                            "type": self.data_type,
                            "status": "synced",
                        }
                    }
                )

        # Webhook endpoints for external integration
        @auth_endpoint("/webhook/external", permissions=["webhook_access"])
        async def external_webhook():
            return {"webhook": "processed", "timestamp": datetime.now().isoformat()}

        # Health check for services (no auth)
        @endpoint("/internal/health")
        async def service_health():
            return {"status": "healthy", "service": "auth-system"}

        # Verify service integration setup
        sync_config = ServiceSyncWalker.__dict__["_endpoint_config"]
        webhook_config = external_webhook._endpoint_config
        health_config = service_health._endpoint_config

        assert sync_config.permissions == ["service_sync"]
        assert webhook_config.permissions == ["webhook_access"]

        # Health check should not require auth
        assert health_config.auth_required is False

    def teardown_method(self):
        """Clean up scenario test."""
        from jvspatial.api.context import set_current_server

        configure_auth(
            jwt_secret_key="your-secret-key-change-in-production",  # pragma: allowlist secret
            jwt_expiration_hours=24,
            rate_limit_enabled=True,
        )
        set_current_server(None)
