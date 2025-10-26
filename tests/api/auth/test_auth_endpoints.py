"""
Test suite for authentication endpoints.

This module tests all authentication endpoints including user registration,
login, profile management, API key management, and admin functions.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import Request

from jvspatial.api.auth.endpoints import (
    create_api_key,
    delete_user,
    get_auth_stats,
    get_user_profile,
    list_api_keys,
    list_users,
    login_user,
    logout_user,
    refresh_token,
    register_user,
    revoke_api_key,
    update_user,
    update_user_profile,
)
from jvspatial.api.auth.entities import (
    APIKey,
    InvalidCredentialsError,
    Session,
    User,
    UserNotFoundError,
)


class TestPublicAuthEndpoints:
    """Test public authentication endpoints."""

    @pytest.mark.asyncio
    async def test_register_user_success(self):
        """Test successful user registration."""
        # Mock request data
        from jvspatial.api.auth.endpoints import UserRegistrationRequest

        request_data = UserRegistrationRequest(
            email="new@example.com",
            password="password123",  # pragma: allowlist secret
            confirm_password="password123",  # pragma: allowlist secret
        )

        # Mock that email doesn't exist
        with patch(
            "jvspatial.api.auth.entities.User.find_by_email", new_callable=AsyncMock
        ) as mock_find_email:
            with patch(
                "jvspatial.api.auth.entities.User.create", new_callable=AsyncMock
            ) as mock_create:
                mock_find_email.return_value = None

                mock_user = User(
                    id="user_123",
                    email="new@example.com",
                    password_hash="hashed",  # pragma: allowlist secret
                    created_at=datetime.now().isoformat(),  # Use ISO format string
                )
                mock_create.return_value = mock_user

                result = await register_user(request_data)

                assert result["status"] == "success"
                assert result["message"] == "User registered successfully"
                assert result["user"]["email"] == "new@example.com"
                mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_user_password_mismatch(self):
        """Test user registration with password mismatch."""
        from jvspatial.api.auth.endpoints import UserRegistrationRequest

        request_data = UserRegistrationRequest(
            email="new@example.com",
            password="password123",  # pragma: allowlist secret
            confirm_password="different456",  # pragma: allowlist secret
        )

        result = await register_user(request_data)

        assert result["status"] == "error"
        assert result["error"] == "password_mismatch"
        assert "Passwords do not match" in result["message"]

    @pytest.mark.asyncio
    async def test_register_user_email_taken(self):
        """Test user registration with existing email."""
        from jvspatial.api.auth.endpoints import UserRegistrationRequest

        request_data = UserRegistrationRequest(
            email="existing@example.com",
            password="password123",  # pragma: allowlist secret
            confirm_password="password123",  # pragma: allowlist secret
        )

        existing_user = User(
            email="existing@example.com",
            password_hash="hash",  # pragma: allowlist secret
        )

        with patch(
            "jvspatial.api.auth.entities.User.find_by_email",
            new_callable=AsyncMock,
            return_value=existing_user,
        ):
            result = await register_user(request_data)

            assert result["status"] == "error"
            assert result["error"] == "email_taken"
            assert "Email is already registered" in result["message"]

    @pytest.mark.asyncio
    async def test_login_user_success(self):
        """Test successful user login."""
        from jvspatial.api.auth.endpoints import LoginRequest

        request_data = LoginRequest(
            email="test@example.com",
            password="password123",  # pragma: allowlist secret
            remember_me=False,
        )

        test_user = User(
            id="user_123",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            roles=["user"],
            is_admin=False,
        )

        with patch(
            "jvspatial.api.auth.endpoints.authenticate_user",
            new_callable=AsyncMock,
            return_value=test_user,
        ):
            with patch(
                "jvspatial.api.auth.endpoints.JWTManager.create_access_token",
                return_value="access_token",
            ):
                with patch(
                    "jvspatial.api.auth.endpoints.JWTManager.create_refresh_token",
                    return_value="refresh_token",
                ):
                    with patch(
                        "jvspatial.api.auth.entities.Session.create",
                        new_callable=AsyncMock,
                    ) as mock_create_session:
                        mock_session = Session(
                            session_id="session_123",
                            user_id="user_123",
                            jwt_token="access_token",
                            refresh_token="refresh_token",
                            expires_at=(
                                datetime.now() + timedelta(hours=24)
                            ).isoformat(),  # Use ISO format string
                        )
                        mock_create_session.return_value = mock_session

                        result = await login_user(request_data)

                        assert result["status"] == "success"
                        assert result["access_token"] == "access_token"
                        assert result["refresh_token"] == "refresh_token"
                        assert result["token_type"] == "bearer"
                        assert result["user"]["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_login_user_remember_me(self):
        """Test user login with remember me option."""
        from jvspatial.api.auth.endpoints import LoginRequest

        request_data = LoginRequest(
            email="test@example.com",
            password="password123",  # pragma: allowlist secret
            remember_me=True,
        )

        test_user = User(
            id="user_123",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
        )

        with patch(
            "jvspatial.api.auth.endpoints.authenticate_user", return_value=test_user
        ):
            with patch(
                "jvspatial.api.auth.endpoints.JWTManager.create_access_token",
                return_value="access_token",
            ):
                with patch(
                    "jvspatial.api.auth.endpoints.JWTManager.create_refresh_token",
                    return_value="refresh_token",
                ):
                    with patch(
                        "jvspatial.api.auth.entities.Session.create"
                    ) as mock_create_session:
                        result = await login_user(request_data)

                        # Should have longer expiration (7 days * 3600 seconds)
                        assert result["expires_in"] == 7 * 24 * 3600

                        # Check session creation was called with extended duration
                        call_args = mock_create_session.call_args[1]
                        expires_at = call_args["expires_at"]
                        # Convert to datetime for comparison
                        if isinstance(expires_at, str):
                            expires_at = datetime.fromisoformat(expires_at)
                        time_diff = expires_at - datetime.now()
                        assert time_diff.days >= 6  # About 7 days

    @pytest.mark.asyncio
    async def test_login_user_invalid_credentials(self):
        """Test login with invalid credentials."""
        from jvspatial.api.auth.endpoints import LoginRequest

        request_data = LoginRequest(
            email="test@example.com",
            password="wrongpassword",  # pragma: allowlist secret
        )

        with patch(
            "jvspatial.api.auth.endpoints.authenticate_user",
            side_effect=InvalidCredentialsError(),
        ):
            result = await login_user(request_data)

            assert result["status"] == "error"
            assert result["error"] == "invalid_credentials"
            assert "Invalid email or password" in result["message"]

    @pytest.mark.asyncio
    async def test_refresh_token_success(self):
        """Test successful token refresh."""
        from jvspatial.api.auth.endpoints import TokenRefreshRequest

        request_data = TokenRefreshRequest(refresh_token="valid_refresh_token")

        with patch(
            "jvspatial.api.auth.endpoints.refresh_session",
            return_value=("new_access", "new_refresh"),
        ):
            result = await refresh_token(request_data)

            assert result["status"] == "success"
            assert result["access_token"] == "new_access"
            assert result["refresh_token"] == "new_refresh"
            assert result["token_type"] == "bearer"
            assert result["expires_in"] == 24 * 3600

    @pytest.mark.asyncio
    async def test_refresh_token_failure(self):
        """Test token refresh failure."""
        from jvspatial.api.auth.endpoints import TokenRefreshRequest

        request_data = TokenRefreshRequest(refresh_token="invalid_refresh_token")

        with patch(
            "jvspatial.api.auth.endpoints.refresh_session",
            side_effect=Exception("Token expired"),
        ):
            result = await refresh_token(request_data)

            assert result["status"] == "error"
            assert result["error"] == "refresh_failed"
            assert "Token refresh failed" in result["message"]


class TestAuthenticatedEndpoints:
    """Test authenticated user endpoints."""

    def setup_method(self):
        """Set up test data."""
        self.test_user = User(
            id="user_123",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            roles=["user"],
            permissions=["read_data"],
            is_active=True,
            created_at=datetime.now().isoformat(),  # Use ISO format string
            last_login=(
                datetime.now() - timedelta(days=1)
            ).isoformat(),  # Use ISO format string
            login_count=5,
        )

    @pytest.mark.asyncio
    async def test_logout_user_success(self):
        """Test successful user logout with session revocation."""
        from jvspatial.api.auth.endpoints import LogoutRequest

        request_data = LogoutRequest(revoke_all_sessions=False)

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"Authorization": "Bearer test_token"}

        # Mock database context and session finding
        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch(
                "jvspatial.core.context.get_default_context"
            ) as mock_get_context:
                mock_ctx = MagicMock()
                mock_get_context.return_value = mock_ctx

                # Mock session data
                mock_session_data = [
                    {
                        "session_id": "session_123",
                        "user_id": "user_123",
                        "jwt_token": "test_token",
                        "refresh_token": "refresh_token",
                        "expires_at": (
                            datetime.now() + timedelta(hours=24)
                        ).isoformat(),
                        "is_active": True,
                    }
                ]
                mock_ctx.database.find = AsyncMock(return_value=mock_session_data)

                # Mock the Session.revoke method directly
                with patch(
                    "jvspatial.api.auth.entities.Session.revoke", new_callable=AsyncMock
                ) as mock_revoke:
                    result = await logout_user(request_data, mock_request)

                    assert result["status"] == "success"
                    assert result["message"] == "Logged out successfully"
                    assert result["sessions_revoked"] is False

                    # Verify session was revoked
                    mock_revoke.assert_called_once_with("User logout")

    @pytest.mark.asyncio
    async def test_logout_user_revoke_all(self):
        """Test user logout with revoke all sessions."""
        from jvspatial.api.auth.endpoints import LogoutRequest

        request_data = LogoutRequest(revoke_all_sessions=True)

        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"Authorization": "Bearer test_token"}

        # Mock database context and session finding
        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch(
                "jvspatial.core.context.get_default_context"
            ) as mock_get_context:
                mock_ctx = MagicMock()
                mock_get_context.return_value = mock_ctx

                # Mock session data for current session
                mock_session_data = [
                    {
                        "session_id": "session_123",
                        "user_id": "user_123",
                        "jwt_token": "test_token",
                        "refresh_token": "refresh_token",
                        "expires_at": (
                            datetime.now() + timedelta(hours=24)
                        ).isoformat(),
                        "is_active": True,
                    }
                ]
                mock_ctx.database.find = AsyncMock(return_value=mock_session_data)

                # Mock the Session.revoke method directly
                with patch(
                    "jvspatial.api.auth.entities.Session.revoke", new_callable=AsyncMock
                ) as mock_revoke:
                    result = await logout_user(request_data, mock_request)

                    assert result["status"] == "success"
                    assert result["message"] == "Logged out successfully"
                    assert result["sessions_revoked"] is True

                    # Verify session was revoked
                    mock_revoke.assert_called()

    @pytest.mark.asyncio
    async def test_get_user_profile_success(self):
        """Test getting user profile."""
        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            result = await get_user_profile(mock_request)

            assert result["status"] == "success"
            assert result["message"] == "Profile retrieved successfully"
            assert result["profile"]["email"] == "test@example.com"
            assert result["profile"]["roles"] == ["user"]
            assert result["profile"]["permissions"] == ["read_data"]
            assert result["profile"]["is_active"] is True
            assert result["profile"]["login_count"] == 5

    @pytest.mark.asyncio
    async def test_get_user_profile_no_user(self):
        """Test getting user profile when not authenticated."""
        mock_request = MagicMock(spec=Request)

        with patch("jvspatial.api.auth.endpoints.get_current_user", return_value=None):
            result = await get_user_profile(mock_request)

            assert result["status"] == "error"
            assert result["error"] == "user_not_found"
            assert "User not authenticated" in result["message"]

    @pytest.mark.asyncio
    async def test_update_user_profile_email(self):
        """Test updating user profile email."""
        from jvspatial.api.auth.endpoints import UpdateProfileRequest

        request_data = UpdateProfileRequest(
            email="newemail@example.com",
            current_password="password123",  # pragma: allowlist secret
        )

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch.object(User, "verify_password", return_value=True):
                with patch(
                    "jvspatial.api.auth.entities.User.find_by_email",
                    new_callable=AsyncMock,
                    return_value=None,
                ):
                    with patch.object(
                        User, "save", new_callable=AsyncMock
                    ) as mock_save:
                        result = await update_user_profile(request_data, mock_request)

                        assert result["status"] == "success"
                        assert result["message"] == "Profile updated successfully"
                        assert "email" in result["updates"]
                        assert self.test_user.email == "newemail@example.com"
                        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_profile_password(self):
        """Test updating user profile password."""
        from jvspatial.api.auth.endpoints import UpdateProfileRequest

        request_data = UpdateProfileRequest(
            current_password="oldpassword",  # pragma: allowlist secret
            new_password="newpassword123",  # pragma: allowlist secret
        )

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch.object(User, "verify_password", return_value=True):
                with patch(
                    "jvspatial.api.auth.entities.User.hash_password",
                    return_value="new_hash",
                ):
                    with patch.object(User, "save") as mock_save:
                        result = await update_user_profile(request_data, mock_request)

                        assert result["status"] == "success"
                        assert result["message"] == "Profile updated successfully"
                        assert "password" in result["updates"]
                        assert (
                            self.test_user.password_hash
                            == "new_hash"  # pragma: allowlist secret
                        )
                        mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_profile_wrong_password(self):
        """Test updating profile with wrong current password."""
        from jvspatial.api.auth.endpoints import UpdateProfileRequest

        request_data = UpdateProfileRequest(
            email="newemail@example.com",
            current_password="wrongpassword",  # pragma: allowlist secret
        )

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch.object(User, "verify_password", return_value=False):
                result = await update_user_profile(request_data, mock_request)

                assert result["status"] == "error"
                assert result["error"] == "invalid_password"
                assert "Current password is incorrect" in result["message"]

    @pytest.mark.asyncio
    async def test_update_user_profile_email_taken(self):
        """Test updating profile with already taken email."""
        from jvspatial.api.auth.endpoints import UpdateProfileRequest

        request_data = UpdateProfileRequest(
            email="taken@example.com",
            current_password="password123",  # pragma: allowlist secret
        )

        mock_request = MagicMock(spec=Request)
        existing_user = User(
            id="other_user",
            email="taken@example.com",
            password_hash="hash",  # pragma: allowlist secret
        )

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch.object(User, "verify_password", return_value=True):
                with patch(
                    "jvspatial.api.auth.entities.User.find_by_email",
                    new_callable=AsyncMock,
                    return_value=existing_user,
                ):
                    result = await update_user_profile(request_data, mock_request)

                    assert result["status"] == "error"
                    assert result["error"] == "email_taken"
                    assert "Email is already registered" in result["message"]


class TestAPIKeyEndpoints:
    """Test API key management endpoints."""

    def setup_method(self):
        """Set up test data."""
        self.test_user = User(
            id="user_123",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
        )

        self.test_api_key = APIKey(
            key_id="test_key_123",
            name="Test API Key",
            key_hash="hashed_secret",
            user_id="user_123",
            created_at=datetime.now().isoformat(),
            usage_count=42,
            rate_limit_per_hour=1000,
            is_active=True,
        )

    @pytest.mark.asyncio
    async def test_list_api_keys_success(self):
        """Test listing user's API keys."""
        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch(
                "jvspatial.api.auth.entities.APIKey.find",
                new_callable=AsyncMock,
                return_value=[self.test_api_key],
            ):
                result = await list_api_keys(mock_request)

                assert result["status"] == "success"
                assert result["count"] == 1
                assert len(result["api_keys"]) == 1

                key_data = result["api_keys"][0]
                assert key_data["key_id"] == "test_key_123"
                assert key_data["name"] == "Test API Key"
                assert key_data["usage_count"] == 42
                assert key_data["is_active"] is True

    @pytest.mark.asyncio
    async def test_create_api_key_success(self):
        """Test creating a new API key."""
        from jvspatial.api.auth.endpoints import APIKeyCreateRequest

        request_data = APIKeyCreateRequest(
            name="New API Key",
            expires_days=30,
            allowed_endpoints=["/api/data/*"],
            rate_limit_per_hour=500,
        )

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch(
                "jvspatial.api.auth.entities.APIKey.generate_key_pair",
                return_value=("key_123", "secret_456"),
            ):
                with patch(
                    "jvspatial.api.auth.entities.APIKey.create", new_callable=AsyncMock
                ) as mock_create:
                    mock_api_key = APIKey(
                        key_id="key_123",
                        name="New API Key",
                        key_hash="hashed_secret",
                        user_id="user_123",
                        created_at=datetime.now().isoformat(),
                    )
                    mock_create.return_value = mock_api_key

                    result = await create_api_key(request_data, mock_request)

                    assert result["status"] == "success"
                    assert result["message"] == "API key created successfully"
                    assert result["api_key"]["key_id"] == "key_123"
                    assert (
                        result["api_key"]["secret_key"]
                        == "secret_456"  # pragma: allowlist secret
                    )
                    assert result["api_key"]["name"] == "New API Key"
                    assert "Store the secret key safely" in result["warning"]

    @pytest.mark.asyncio
    async def test_create_api_key_with_expiration(self):
        """Test creating API key with expiration."""
        from jvspatial.api.auth.endpoints import APIKeyCreateRequest

        request_data = APIKeyCreateRequest(name="Expiring Key", expires_days=7)

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch(
                "jvspatial.api.auth.entities.APIKey.generate_key_pair",
                return_value=("key_123", "secret_456"),
            ):
                with patch(
                    "jvspatial.api.auth.entities.APIKey.create", new_callable=AsyncMock
                ) as mock_create:
                    mock_api_key = APIKey(
                        key_id="key_123",
                        name="Expiring Key",
                        key_hash="hashed_secret",
                        user_id="user_123",
                        created_at=datetime.now().isoformat(),
                    )
                    mock_create.return_value = mock_api_key

                    result = await create_api_key(request_data, mock_request)

                    # Check that expiration was calculated
                    call_args = mock_create.call_args[1]
                    expires_at = call_args["expires_at"]
                    assert expires_at is not None
                    # Convert to datetime if it's a string
                    if isinstance(expires_at, str):
                        expires_at = datetime.fromisoformat(expires_at)
                    time_diff = expires_at - datetime.now()
                    assert 6 <= time_diff.days <= 7

    @pytest.mark.asyncio
    async def test_revoke_api_key_success(self):
        """Test revoking an API key."""
        from jvspatial.api.auth.endpoints import APIKeyRevokeRequest

        request_data = APIKeyRevokeRequest(key_id="test_key_123")

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user", return_value=self.test_user
        ):
            with patch(
                "jvspatial.api.auth.entities.APIKey.find_by_key_id",
                new_callable=AsyncMock,
                return_value=self.test_api_key,
            ):
                with patch.object(APIKey, "save", new_callable=AsyncMock) as mock_save:
                    result = await revoke_api_key(request_data, mock_request)

                    assert result["status"] == "success"
                    assert result["message"] == "API key revoked successfully"
                    assert result["revoked_key"]["key_id"] == "test_key_123"
                    assert result["revoked_key"]["name"] == "Test API Key"
                    assert self.test_api_key.is_active is False
                    mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_api_key_not_found(self):
        """Test revoking non-existent API key."""
        from jvspatial.api.auth.endpoints import APIKeyRevokeRequest

        request_data = APIKeyRevokeRequest(key_id="nonexistent_key")

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.test_user,
        ):
            with patch(
                "jvspatial.api.auth.entities.APIKey.find_by_key_id",
                new_callable=AsyncMock,
                return_value=None,
            ):
                result = await revoke_api_key(request_data, mock_request)

                assert result["status"] == "error"
                assert result["error"] == "key_not_found"
                assert "API key not found" in result["message"]

    @pytest.mark.asyncio
    async def test_revoke_api_key_not_owner(self):
        """Test revoking API key that doesn't belong to user."""
        from jvspatial.api.auth.endpoints import APIKeyRevokeRequest

        request_data = APIKeyRevokeRequest(key_id="other_key")

        mock_request = MagicMock(spec=Request)

        # API key belongs to different user
        other_api_key = APIKey(
            key_id="other_key",
            name="Other Key",
            key_hash="hash",
            user_id="other_user_123",
        )

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.test_user,
        ):
            with patch(
                "jvspatial.api.auth.entities.APIKey.find_by_key_id",
                new_callable=AsyncMock,
                return_value=other_api_key,
            ):
                result = await revoke_api_key(request_data, mock_request)

                assert result["status"] == "error"
                assert result["error"] == "unauthorized"
                assert "You can only revoke your own API keys" in result["message"]


class TestAdminEndpoints:
    """Test admin-only endpoints."""

    def setup_method(self):
        """Set up test data."""
        self.admin_user = User(
            id="admin_123",
            email="admin@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_admin=True,
            roles=["admin"],
        )

        self.regular_user = User(
            id="user_123",
            email="user@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_admin=False,
            roles=["user"],
        )

    @pytest.mark.asyncio
    async def test_list_users_success(self):
        """Test listing all users (admin)."""
        from jvspatial.api.auth.endpoints import UserListRequest

        request_data = UserListRequest(page=1, limit=50, active_only=False)

        mock_request = MagicMock(spec=Request)

        users = [self.admin_user, self.regular_user]

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.admin_user,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.find",
                new_callable=AsyncMock,
                return_value=users,
            ):
                with patch(
                    "jvspatial.api.auth.entities.User.count",
                    new_callable=AsyncMock,
                    return_value=2,
                ):
                    result = await list_users(request_data, mock_request)

                    assert result["status"] == "success"
                    assert len(result["users"]) == 2
                    assert result["pagination"]["total"] == 2
                    assert result["pagination"]["pages"] == 1

                    # Check user data
                    admin_data = result["users"][0]
                    assert admin_data["email"] == "admin@example.com"
                    assert admin_data["is_admin"] is True

    @pytest.mark.asyncio
    async def test_list_users_active_only(self):
        """Test listing only active users."""
        from jvspatial.api.auth.endpoints import UserListRequest

        request_data = UserListRequest(page=1, limit=50, active_only=True)

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.admin_user,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.find", new_callable=AsyncMock
            ) as mock_find:
                with patch(
                    "jvspatial.api.auth.entities.User.count",
                    new_callable=AsyncMock,
                    return_value=1,
                ):
                    await list_users(request_data, mock_request)

                    # Check that query included active filter
                    call_args = mock_find.call_args
                    assert call_args[0][0]["context.is_active"] is True

    @pytest.mark.asyncio
    async def test_list_users_pagination(self):
        """Test user list pagination."""
        from jvspatial.api.auth.endpoints import UserListRequest

        request_data = UserListRequest(page=2, limit=1)

        mock_request = MagicMock(spec=Request)
        users = [self.admin_user, self.regular_user]

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.admin_user,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.find",
                new_callable=AsyncMock,
                return_value=users,
            ):  # Return all users
                with patch(
                    "jvspatial.api.auth.entities.User.count",
                    new_callable=AsyncMock,
                    return_value=2,
                ):
                    result = await list_users(request_data, mock_request)

                    # Should only return 1 user (page 2, limit 1)
                    assert len(result["users"]) == 1
                    assert result["pagination"]["page"] == 2
                    assert result["pagination"]["limit"] == 1
                    assert result["pagination"]["total"] == 2
                    assert result["pagination"]["pages"] == 2

    @pytest.mark.asyncio
    async def test_update_user_success(self):
        """Test updating a user (admin)."""
        from jvspatial.api.auth.endpoints import UserUpdateRequest

        request_data = UserUpdateRequest(
            user_id="user_123", is_active=False, roles=["viewer"]
        )

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.admin_user,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.find_by_id",
                new_callable=AsyncMock,
                return_value=self.regular_user,
            ):
                with patch.object(User, "save", new_callable=AsyncMock) as mock_save:
                    result = await update_user(request_data, mock_request)

                    assert result["status"] == "success"
                    assert result["message"] == "User updated successfully"
                    assert result["user_id"] == "user_123"
                    assert "is_active" in result["updates"]
                    assert "roles" in result["updates"]
                    assert result["updated_by"]["admin_email"] == "admin@example.com"

                    # Check user was actually updated
                    assert self.regular_user.is_active is False
                    assert self.regular_user.roles == ["viewer"]
                    mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_user_not_found(self):
        """Test updating non-existent user."""
        from jvspatial.api.auth.endpoints import UserUpdateRequest

        request_data = UserUpdateRequest(user_id="nonexistent_user", is_active=False)

        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.admin_user,
        ):
            with patch("jvspatial.api.auth.entities.User.get", return_value=None):
                result = await update_user(request_data, mock_request)

                assert result["status"] == "error"
                assert result["error"] == "user_not_found"
                assert "User not found" in result["message"]

    @pytest.mark.asyncio
    async def test_get_auth_stats_success(self):
        """Test getting authentication statistics."""
        mock_request = MagicMock(spec=Request)

        users = [self.admin_user, self.regular_user]
        api_keys = [
            APIKey(name="key1", key_id="id1", key_hash="hash1", user_id="user1")
        ]
        sessions = [
            Session(
                session_id="session1",
                user_id="user1",
                jwt_token="jwt1",
                refresh_token="refresh1",
                expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
            )
        ]

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.admin_user,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.find",
                new_callable=AsyncMock,
                return_value=users,
            ):
                with patch(
                    "jvspatial.api.auth.entities.User.count",
                    new_callable=AsyncMock,
                    return_value=2,
                ):
                    with patch(
                        "jvspatial.api.auth.entities.APIKey.find",
                        new_callable=AsyncMock,
                        return_value=api_keys,
                    ):
                        with patch(
                            "jvspatial.api.auth.entities.APIKey.count",
                            new_callable=AsyncMock,
                            return_value=1,
                        ):
                            with patch(
                                "jvspatial.api.auth.entities.Session.find",
                                new_callable=AsyncMock,
                                return_value=sessions,
                            ):
                                with patch(
                                    "jvspatial.api.auth.entities.Session.count",
                                    new_callable=AsyncMock,
                                    return_value=1,
                                ):
                                    result = await get_auth_stats(mock_request)

                                    assert result["status"] == "success"
                                    stats = result["statistics"]
                                    assert stats["total_users"] == 2
                                    assert (
                                        stats["active_users"] == 2
                                    )  # Both users are active by default
                                    assert stats["admin_users"] == 1
                                    assert stats["total_api_keys"] == 1
                                    assert stats["active_api_keys"] == 1
                                    assert stats["active_sessions"] == 1
                                    assert "database_collections" in stats
                                    assert (
                                        result["generated_by"]["admin_email"]
                                        == "admin@example.com"
                                    )

    @pytest.mark.asyncio
    async def test_delete_user_success(self):
        """Test deleting a user (admin)."""
        mock_request = MagicMock(spec=Request)

        # Mock associated data
        user_api_keys = [
            APIKey(name="key", key_id="id", key_hash="hash", user_id="user_123")
        ]
        user_sessions = [
            Session(
                session_id="session",
                user_id="user_123",
                jwt_token="jwt",
                refresh_token="refresh",
                expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
            )
        ]

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.admin_user,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.find_by_id",
                new_callable=AsyncMock,
                return_value=self.regular_user,
            ):
                with patch(
                    "jvspatial.api.auth.entities.APIKey.find",
                    new_callable=AsyncMock,
                    return_value=user_api_keys,
                ):
                    with patch(
                        "jvspatial.api.auth.entities.Session.find",
                        new_callable=AsyncMock,
                        return_value=user_sessions,
                    ):
                        with patch.object(
                            User, "save", new_callable=AsyncMock
                        ) as mock_save_user:
                            with patch.object(
                                User, "delete", new_callable=AsyncMock
                            ) as mock_delete_user:
                                with patch.object(
                                    APIKey, "delete", new_callable=AsyncMock
                                ) as mock_delete_key:
                                    with patch.object(
                                        Session, "delete", new_callable=AsyncMock
                                    ) as mock_delete_session:
                                        result = await delete_user(
                                            "user_123", mock_request
                                        )

                                        assert result["status"] == "success"
                                        assert (
                                            result["message"]
                                            == "User deleted successfully"
                                        )
                                        assert (
                                            result["deleted_user"]["email"]
                                            == "user@example.com"
                                        )
                                        assert (
                                            result["deleted_by"]["admin_email"]
                                            == "admin@example.com"
                                        )
                                        assert (
                                            result["cleanup"]["api_keys_deleted"] == 1
                                        )
                                        assert (
                                            result["cleanup"]["sessions_deleted"] == 1
                                        )

                                        # Check deletions were called
                                        mock_delete_user.assert_called_once()
                                        mock_delete_key.assert_called_once()
                                        mock_delete_session.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_user_self_deletion(self):
        """Test admin trying to delete themselves."""
        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.admin_user,
        ):
            with patch(
                "jvspatial.api.auth.entities.User.find_by_id",
                new_callable=AsyncMock,
                return_value=self.admin_user,
            ):
                result = await delete_user("admin_123", mock_request)

                assert result["status"] == "error"
                assert result["error"] == "self_deletion"
                assert "Cannot delete your own account" in result["message"]

    @pytest.mark.asyncio
    async def test_delete_user_not_found(self):
        """Test deleting non-existent user."""
        mock_request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.endpoints.get_current_user",
            return_value=self.admin_user,
        ):
            with patch("jvspatial.api.auth.entities.User.get", return_value=None):
                result = await delete_user("nonexistent_user", mock_request)

                assert result["status"] == "error"
                assert result["error"] == "user_not_found"
                assert "User not found" in result["message"]
