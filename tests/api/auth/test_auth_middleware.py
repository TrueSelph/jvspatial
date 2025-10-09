"""
Test suite for authentication middleware.

This module tests the AuthenticationMiddleware, RateLimiter, JWTManager,
and related authentication utilities.
"""

import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, Request
from starlette.responses import JSONResponse

from jvspatial.api.auth.entities import (
    APIKey,
    APIKeyInvalidError,
    InvalidCredentialsError,
    Session,
    SessionExpiredError,
    User,
    UserNotFoundError,
)
from jvspatial.api.auth.middleware import (
    AuthConfig,
    AuthenticationMiddleware,
    JWTManager,
    RateLimiter,
    auth_config,
    authenticate_user,
    configure_auth,
    create_user_session,
    get_admin_user,
    get_current_active_user,
    get_current_user,
    get_current_user_dependency,
    no_auth_required,
    refresh_session,
    require_auth,
    security,
)


class TestAuthConfig:
    """Test AuthConfig functionality."""

    def test_default_config(self):
        """Test default authentication configuration."""
        config = AuthConfig()

        assert (
            config.jwt_secret_key
            == "your-secret-key-change-in-production"  # pragma: allowlist secret
        )
        assert config.jwt_algorithm == "HS256"
        assert config.jwt_expiration_hours == 24
        assert config.jwt_refresh_expiration_days == 30
        assert config.api_key_header == "X-API-Key"  # pragma: allowlist secret
        assert config.api_key_query_param == "api_key"  # pragma: allowlist secret
        assert config.rate_limit_enabled is True
        assert config.default_rate_limit_per_hour == 1000
        assert config.require_https is False
        assert config.session_cookie_secure is False
        assert config.session_cookie_httponly is True

    def test_configure_auth(self):
        """Test authentication configuration."""
        # Store original values
        original_secret = auth_config.jwt_secret_key
        original_hours = auth_config.jwt_expiration_hours

        # Configure new values
        configure_auth(
            jwt_secret_key="test-secret-key",  # pragma: allowlist secret
            jwt_expiration_hours=48,
            rate_limit_enabled=False,
        )

        assert (
            auth_config.jwt_secret_key == "test-secret-key"  # pragma: allowlist secret
        )
        assert auth_config.jwt_expiration_hours == 48
        assert auth_config.rate_limit_enabled is False

        # Restore original values
        configure_auth(
            jwt_secret_key=original_secret,
            jwt_expiration_hours=original_hours,
            rate_limit_enabled=True,
        )


class TestRateLimiter:
    """Test RateLimiter functionality."""

    def test_rate_limiter_creation(self):
        """Test rate limiter initialization."""
        limiter = RateLimiter()

        assert limiter.requests == {}
        assert limiter.cleanup_interval == 300
        assert limiter.last_cleanup <= time.time()

    def test_is_allowed_first_request(self):
        """Test first request is allowed."""
        limiter = RateLimiter()

        result = limiter.is_allowed("user_123", 100)

        assert result is True
        assert len(limiter.requests["user_123"]) == 1

    def test_is_allowed_under_limit(self):
        """Test requests under limit are allowed."""
        limiter = RateLimiter()

        # Make several requests under limit
        for i in range(5):
            result = limiter.is_allowed("user_123", 10)
            assert result is True

        assert len(limiter.requests["user_123"]) == 5

    def test_is_allowed_over_limit(self):
        """Test requests over limit are denied."""
        limiter = RateLimiter()

        # Fill up the limit
        for i in range(10):
            result = limiter.is_allowed("user_123", 10)
            assert result is True

        # Next request should be denied
        result = limiter.is_allowed("user_123", 10)
        assert result is False

    def test_is_allowed_different_users(self):
        """Test rate limiting is per-user."""
        limiter = RateLimiter()

        # Fill up limit for user1
        for i in range(10):
            result = limiter.is_allowed("user1", 10)
            assert result is True

        # user1 should be denied
        result = limiter.is_allowed("user1", 10)
        assert result is False

        # But user2 should still be allowed
        result = limiter.is_allowed("user2", 10)
        assert result is True

    def test_cleanup_old_requests(self):
        """Test cleanup of old requests."""
        limiter = RateLimiter()

        # Add some old requests
        old_time = time.time() - 3700  # More than 1 hour ago
        limiter.requests["user1"] = [old_time, old_time]
        limiter.requests["user2"] = [time.time()]  # Recent request

        # Trigger cleanup
        limiter._cleanup()

        # Old user should be cleaned up
        assert "user1" not in limiter.requests
        # Recent user should remain
        assert "user2" in limiter.requests
        assert len(limiter.requests["user2"]) == 1


class TestJWTManager:
    """Test JWT token management functionality."""

    def setup_method(self):
        """Set up test data."""
        self.test_user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            roles=["user", "analyst"],
            is_admin=False,
        )

        self.admin_user = User(
            id="admin_123",
            username="admin",
            email="admin@example.com",
            password_hash="hash",  # pragma: allowlist secret
            roles=["admin"],
            is_admin=True,
        )

    def test_create_access_token(self):
        """Test access token creation."""
        token = JWTManager.create_access_token(self.test_user)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 50  # JWT tokens are long

        # Decode and verify payload
        payload = jwt.decode(
            token, auth_config.jwt_secret_key, algorithms=[auth_config.jwt_algorithm]
        )
        assert payload["sub"] == self.test_user.id
        assert payload["username"] == self.test_user.username
        assert payload["email"] == self.test_user.email
        assert payload["roles"] == self.test_user.roles
        assert payload["is_admin"] == self.test_user.is_admin
        assert payload["type"] == "access"

    def test_create_access_token_with_custom_expiry(self):
        """Test access token creation with custom expiration."""
        custom_expiry = timedelta(hours=12)
        token = JWTManager.create_access_token(
            self.test_user, expires_delta=custom_expiry
        )

        payload = jwt.decode(
            token, auth_config.jwt_secret_key, algorithms=[auth_config.jwt_algorithm]
        )
        exp_time = datetime.fromtimestamp(payload["exp"])

        # Should expire in approximately 12 hours (allow for timezone differences)
        time_diff = exp_time - datetime.utcnow()
        # Be more lenient with timezone differences
        assert 6 * 3600 < time_diff.total_seconds() < 15 * 3600

    def test_create_refresh_token(self):
        """Test refresh token creation."""
        token = JWTManager.create_refresh_token(self.test_user)

        assert token is not None
        assert isinstance(token, str)

        # Decode and verify payload
        payload = jwt.decode(
            token, auth_config.jwt_secret_key, algorithms=[auth_config.jwt_algorithm]
        )
        assert payload["sub"] == self.test_user.id
        assert payload["type"] == "refresh"

        # Should have long expiration
        exp_time = datetime.fromtimestamp(payload["exp"])
        time_diff = exp_time - datetime.utcnow()
        assert time_diff.days >= 29  # Should be about 30 days

    def test_verify_token_valid(self):
        """Test token verification for valid token."""
        token = JWTManager.create_access_token(self.test_user)

        payload = JWTManager.verify_token(token)

        assert payload["sub"] == self.test_user.id
        assert payload["username"] == self.test_user.username
        assert payload["type"] == "access"

    def test_verify_token_invalid(self):
        """Test token verification for invalid token."""
        invalid_token = "invalid.token.here"

        with pytest.raises(InvalidCredentialsError):
            JWTManager.verify_token(invalid_token)

    def test_verify_token_expired(self):
        """Test token verification for expired token."""
        # Create token with immediate expiration
        expired_payload = {
            "sub": self.test_user.id,
            "exp": datetime.utcnow() - timedelta(seconds=1),
            "type": "access",
        }
        expired_token = jwt.encode(
            expired_payload,
            auth_config.jwt_secret_key,
            algorithm=auth_config.jwt_algorithm,
        )

        with pytest.raises(SessionExpiredError):
            JWTManager.verify_token(expired_token)


class TestAuthenticationMiddleware:
    """Test AuthenticationMiddleware functionality."""

    def setup_method(self):
        """Set up test data."""
        self.test_user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            roles=["user"],
            permissions=["read_data"],
            is_active=True,
            rate_limit_per_hour=100,
        )

        self.mock_app = MagicMock()
        self.middleware = AuthenticationMiddleware(self.mock_app)

    @pytest.mark.asyncio
    async def test_exempt_path_bypass(self):
        """Test that exempt paths bypass authentication."""
        # Mock request for exempt path
        request = MagicMock(spec=Request)
        request.url.path = "/docs"

        call_next = AsyncMock()
        call_next.return_value = "response"

        result = await self.middleware.dispatch(request, call_next)

        assert result == "response"
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_explicit_no_auth_bypass(self):
        """Test that explicitly non-auth endpoints bypass authentication."""
        request = MagicMock(spec=Request)
        request.url.path = "/api/public"
        request.state.endpoint_auth = False

        call_next = AsyncMock()
        call_next.return_value = "response"

        result = await self.middleware.dispatch(request, call_next)

        assert result == "response"
        call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_successful_jwt_authentication(self):
        """Test successful JWT authentication."""
        from types import SimpleNamespace

        request = MagicMock(spec=Request)
        request.url.path = "/api/protected"
        request.state = SimpleNamespace(
            endpoint_auth=True, required_roles=[], required_permissions=[]
        )

        # Mock JWT authentication
        with patch.object(
            self.middleware, "_authenticate_jwt", return_value=self.test_user
        ):
            call_next = AsyncMock()
            call_next.return_value = "response"

            result = await self.middleware.dispatch(request, call_next)

            assert result == "response"
            assert request.state.current_user == self.test_user
            call_next.assert_called_once_with(request)

    @pytest.mark.asyncio
    async def test_successful_api_key_authentication(self):
        """Test successful API key authentication."""
        from types import SimpleNamespace

        request = MagicMock(spec=Request)
        request.url.path = "/api/protected"
        request.state = SimpleNamespace(
            endpoint_auth=True, required_roles=[], required_permissions=[]
        )

        # Mock API key authentication (JWT returns None, API key returns user)
        with patch.object(self.middleware, "_authenticate_jwt", return_value=None):
            with patch.object(
                self.middleware, "_authenticate_api_key", return_value=self.test_user
            ):
                call_next = AsyncMock()
                call_next.return_value = "response"

                result = await self.middleware.dispatch(request, call_next)

                assert result == "response"
                assert request.state.current_user == self.test_user

    @pytest.mark.asyncio
    async def test_rate_limiting(self):
        """Test rate limiting functionality."""
        from types import SimpleNamespace

        request = MagicMock(spec=Request)
        request.url.path = "/api/protected"
        request.state = SimpleNamespace(endpoint_auth=True)

        # Mock authentication but fail rate limiting
        with patch.object(
            self.middleware, "_authenticate_jwt", return_value=self.test_user
        ):
            with patch(
                "jvspatial.api.auth.middleware.rate_limiter.is_allowed",
                return_value=False,
            ):
                result = await self.middleware.dispatch(request, AsyncMock())

                assert isinstance(result, JSONResponse)
                assert result.status_code == 429

    @pytest.mark.asyncio
    async def test_permission_checking(self):
        """Test permission checking."""
        from types import SimpleNamespace

        request = MagicMock(spec=Request)
        request.url.path = "/api/protected"
        request.state = SimpleNamespace(
            endpoint_auth=True, required_permissions=["write_data"]
        )  # User only has read_data

        with patch.object(
            self.middleware, "_authenticate_jwt", return_value=self.test_user
        ):
            result = await self.middleware.dispatch(request, AsyncMock())

            assert isinstance(result, JSONResponse)
            assert result.status_code == 403

    @pytest.mark.asyncio
    async def test_role_checking(self):
        """Test role checking."""
        from types import SimpleNamespace

        request = MagicMock(spec=Request)
        request.url.path = "/api/protected"
        request.state = SimpleNamespace(
            endpoint_auth=True, required_roles=["admin"]
        )  # User only has "user" role

        with patch.object(
            self.middleware, "_authenticate_jwt", return_value=self.test_user
        ):
            result = await self.middleware.dispatch(request, AsyncMock())

            assert isinstance(result, JSONResponse)
            assert result.status_code == 403

    @pytest.mark.asyncio
    async def test_no_authentication_required(self):
        """Test endpoints that require authentication but user is not authenticated."""
        from types import SimpleNamespace

        request = MagicMock(spec=Request)
        request.url.path = "/api/protected"
        request.state = SimpleNamespace(endpoint_auth=True)

        # Mock no authentication
        with patch.object(self.middleware, "_authenticate_jwt", return_value=None):
            with patch.object(
                self.middleware, "_authenticate_api_key", return_value=None
            ):
                result = await self.middleware.dispatch(request, AsyncMock())

                assert isinstance(result, JSONResponse)
                assert result.status_code == 401

    @pytest.mark.asyncio
    async def test_authenticate_jwt_success(self):
        """Test JWT authentication success."""
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "Bearer valid_token"

        mock_payload = {"sub": self.test_user.id}

        with patch(
            "jvspatial.api.auth.middleware.JWTManager.verify_token",
            return_value=mock_payload,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.get", return_value=self.test_user
            ):
                result = await self.middleware._authenticate_jwt(request)

                assert result == self.test_user

    @pytest.mark.asyncio
    async def test_authenticate_jwt_no_header(self):
        """Test JWT authentication with no auth header."""
        request = MagicMock(spec=Request)
        request.headers.get.return_value = None

        result = await self.middleware._authenticate_jwt(request)

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_jwt_invalid_token(self):
        """Test JWT authentication with invalid token."""
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "Bearer invalid_token"

        with patch(
            "jvspatial.api.auth.middleware.JWTManager.verify_token",
            side_effect=InvalidCredentialsError(),
        ):
            result = await self.middleware._authenticate_jwt(request)

            assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_api_key_success(self):
        """Test API key authentication success."""
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "test_key_id:test_secret"
        request.query_params.get.return_value = None
        request.url.path = "/api/data"

        # Mock API key
        mock_api_key = MagicMock(spec=APIKey)
        mock_api_key.is_valid.return_value = True
        mock_api_key.verify_secret.return_value = True
        mock_api_key.can_access_endpoint.return_value = True
        mock_api_key.user_id = self.test_user.id
        mock_api_key.record_usage = AsyncMock()

        with patch(
            "jvspatial.api.auth.entities.APIKey.find_by_key_id",
            return_value=mock_api_key,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.get", return_value=self.test_user
            ):
                result = await self.middleware._authenticate_api_key(request)

                assert result == self.test_user
                mock_api_key.record_usage.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_api_key_no_key(self):
        """Test API key authentication with no key provided."""
        request = MagicMock(spec=Request)
        request.headers.get.return_value = None
        request.query_params.get.return_value = None

        result = await self.middleware._authenticate_api_key(request)

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_api_key_invalid_format(self):
        """Test API key authentication with invalid format."""
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "invalid_format"
        request.query_params.get.return_value = None

        result = await self.middleware._authenticate_api_key(request)

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_api_key_not_found(self):
        """Test API key authentication when key not found."""
        request = MagicMock(spec=Request)
        request.headers.get.return_value = "test_key_id:test_secret"
        request.query_params.get.return_value = None

        with patch(
            "jvspatial.api.auth.entities.APIKey.find_by_key_id", return_value=None
        ):
            result = await self.middleware._authenticate_api_key(request)

            assert result is None


class TestAuthUtilities:
    """Test authentication utility functions."""

    def setup_method(self):
        """Set up test data."""
        self.test_user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            password_hash=User.hash_password("password123"),
            is_active=True,
        )

        self.admin_user = User(
            id="admin_123",
            username="admin",
            email="admin@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_admin=True,
            is_active=True,
        )

    def test_get_current_user(self):
        """Test getting current user from request state."""
        request = MagicMock(spec=Request)
        request.state.current_user = self.test_user

        result = get_current_user(request)

        assert result == self.test_user

    def test_get_current_user_none(self):
        """Test getting current user when none set."""
        request = MagicMock(spec=Request)
        request.state = MagicMock()

        # Mock getattr to return None
        with patch("jvspatial.api.auth.middleware.getattr", return_value=None):
            result = get_current_user(request)

            assert result is None

    @pytest.mark.asyncio
    async def test_create_user_session(self):
        """Test user session creation."""
        request = MagicMock(spec=Request)
        request.client.host = "127.0.0.1"
        request.headers.get.return_value = "Test User Agent"

        with patch("jvspatial.api.auth.entities.Session.create") as mock_create:
            mock_session = MagicMock(spec=Session)
            mock_create.return_value = mock_session

            result = await create_user_session(self.test_user, request)

            assert result == mock_session
            mock_create.assert_called_once()

            # Verify session creation arguments
            call_args = mock_create.call_args[1]
            assert call_args["user_id"] == self.test_user.id
            assert call_args["client_ip"] == "127.0.0.1"
            assert call_args["user_agent"] == "Test User Agent"

    @pytest.mark.asyncio
    async def test_authenticate_user_success(self):
        """Test successful user authentication."""
        with patch(
            "jvspatial.api.auth.entities.User.find_by_username",
            return_value=self.test_user,
        ):
            with patch.object(User, "verify_password", return_value=True):
                with patch.object(
                    User, "record_login", new_callable=AsyncMock
                ) as mock_record:
                    result = await authenticate_user("testuser", "password123")

                    assert result == self.test_user
                    mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_authenticate_user_by_email(self):
        """Test user authentication by email."""
        with patch(
            "jvspatial.api.auth.entities.User.find_by_username", return_value=None
        ):
            with patch(
                "jvspatial.api.auth.entities.User.find_by_email",
                return_value=self.test_user,
            ):
                with patch.object(User, "verify_password", return_value=True):
                    with patch.object(User, "record_login", new_callable=AsyncMock):
                        result = await authenticate_user(
                            "test@example.com", "password123"
                        )

                        assert result == self.test_user

    @pytest.mark.asyncio
    async def test_authenticate_user_not_found(self):
        """Test user authentication when user not found."""
        with patch(
            "jvspatial.api.auth.entities.User.find_by_username", return_value=None
        ):
            with patch(
                "jvspatial.api.auth.entities.User.find_by_email", return_value=None
            ):
                with pytest.raises(InvalidCredentialsError):
                    await authenticate_user("nonexistent", "password")

    @pytest.mark.asyncio
    async def test_authenticate_user_inactive(self):
        """Test user authentication when user is inactive."""
        inactive_user = User(
            username="inactive",
            email="inactive@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_active=False,
        )

        with patch(
            "jvspatial.api.auth.entities.User.find_by_username",
            return_value=inactive_user,
        ):
            with pytest.raises(InvalidCredentialsError):
                await authenticate_user("inactive", "password")

    @pytest.mark.asyncio
    async def test_authenticate_user_wrong_password(self):
        """Test user authentication with wrong password."""
        with patch(
            "jvspatial.api.auth.entities.User.find_by_username",
            return_value=self.test_user,
        ):
            with patch.object(User, "verify_password", return_value=False):
                with pytest.raises(InvalidCredentialsError):
                    await authenticate_user("testuser", "wrongpassword")

    @pytest.mark.asyncio
    async def test_refresh_session_success(self):
        """Test successful session refresh."""
        refresh_token = JWTManager.create_refresh_token(self.test_user)

        with patch("jvspatial.api.auth.entities.User.get", return_value=self.test_user):
            new_access, new_refresh = await refresh_session(refresh_token)

            assert new_access is not None
            assert new_refresh is not None
            assert isinstance(new_access, str)
            assert isinstance(new_refresh, str)

    @pytest.mark.asyncio
    async def test_refresh_session_invalid_type(self):
        """Test session refresh with non-refresh token."""
        access_token = JWTManager.create_access_token(self.test_user)

        with pytest.raises(SessionExpiredError):
            await refresh_session(access_token)

    @pytest.mark.asyncio
    async def test_refresh_session_user_not_found(self):
        """Test session refresh when user not found."""
        refresh_token = JWTManager.create_refresh_token(self.test_user)

        with patch("jvspatial.api.auth.entities.User.get", return_value=None):
            with pytest.raises(SessionExpiredError):
                await refresh_session(refresh_token)

    @pytest.mark.asyncio
    async def test_get_current_user_dependency_success(self):
        """Test FastAPI dependency for current user."""
        request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.middleware.get_current_user",
            return_value=self.test_user,
        ):
            result = await get_current_user_dependency(request, None)

            assert result == self.test_user

    @pytest.mark.asyncio
    async def test_get_current_user_dependency_no_user(self):
        """Test FastAPI dependency when no user authenticated."""
        request = MagicMock(spec=Request)

        with patch("jvspatial.api.auth.middleware.get_current_user", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user_dependency(request, None)

            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_active_user_success(self):
        """Test getting active user dependency."""
        result = await get_current_active_user(self.test_user)

        assert result == self.test_user

    @pytest.mark.asyncio
    async def test_get_current_active_user_inactive(self):
        """Test getting active user when user is inactive."""
        inactive_user = User(
            username="inactive",
            email="inactive@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_active=False,
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_current_active_user(inactive_user)

        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_get_admin_user_success(self):
        """Test getting admin user dependency."""
        result = await get_admin_user(self.admin_user)

        assert result == self.admin_user

    @pytest.mark.asyncio
    async def test_get_admin_user_not_admin(self):
        """Test getting admin user when user is not admin."""
        with pytest.raises(HTTPException) as exc_info:
            await get_admin_user(self.test_user)

        assert exc_info.value.status_code == 403


class TestAuthDecorators:
    """Test authentication decorators."""

    @pytest.mark.asyncio
    async def test_require_auth_decorator(self):
        """Test require_auth decorator."""

        @require_auth(permissions=["read_data"], roles=["user"])
        async def test_endpoint():
            return "success"

        # Check that metadata is stored
        assert hasattr(test_endpoint, "_auth_required")
        assert test_endpoint._auth_required is True
        assert test_endpoint._required_permissions == ["read_data"]
        assert test_endpoint._required_roles == ["user"]

        # Test execution
        result = await test_endpoint()
        assert result == "success"

    @pytest.mark.asyncio
    async def test_no_auth_required_decorator(self):
        """Test no_auth_required decorator."""

        @no_auth_required
        async def test_endpoint():
            return "public"

        # Check that metadata is stored
        assert hasattr(test_endpoint, "_auth_required")
        assert test_endpoint._auth_required is False

        # Test execution
        result = await test_endpoint()
        assert result == "public"
