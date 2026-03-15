"""Tests for refresh token authentication."""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from jvspatial.api import endpoint
from jvspatial.api.auth.models import RefreshToken, TokenRefreshRequest, UserLogin
from jvspatial.api.auth.service import AuthenticationService
from jvspatial.api.server import Server
from jvspatial.core.context import GraphContext
from jvspatial.db.manager import DatabaseManager, set_database_manager


@pytest.fixture(autouse=True)
def reset_database_manager():
    """Reset DatabaseManager singleton before each test for isolation."""
    # Clear the singleton instance
    DatabaseManager._instance = None
    yield
    # Clean up after test
    DatabaseManager._instance = None


@pytest.fixture
def auth_service():
    """Create authentication service instance."""
    context = MagicMock(spec=GraphContext)
    return AuthenticationService(
        context,
        jwt_secret="test-secret-key",
        jwt_expire_minutes=30,
        refresh_expire_days=7,
    )


class TestRefreshTokenGeneration:
    """Test refresh token generation and storage."""

    @pytest.mark.asyncio
    async def test_generate_refresh_token_string(self, auth_service):
        """Test refresh token string generation."""
        token1 = auth_service._generate_refresh_token_string()
        token2 = auth_service._generate_refresh_token_string()

        assert len(token1) > 50  # Should be a long secure token
        assert token1 != token2  # Should be unique

    @pytest.mark.asyncio
    async def test_hash_refresh_token(self, auth_service):
        """Test refresh token hashing."""
        token = "test_refresh_token_12345"
        hash1 = auth_service._hash_refresh_token(token)
        hash2 = auth_service._hash_refresh_token(token)

        # Hash should be reasonable length
        assert len(hash1) > 20

        # Verification should work
        assert auth_service._verify_refresh_token(token, hash1) is True
        assert auth_service._verify_refresh_token("wrong_token", hash1) is False

    @pytest.mark.asyncio
    async def test_generate_and_store_refresh_token(self, auth_service):
        """Test refresh token generation and storage."""
        user_id = "user123"
        access_token_jti = "jti123"

        # Mock context methods
        auth_service.context.save = AsyncMock()
        auth_service.context.ensure_indexes = AsyncMock()

        plaintext_token, expires_at = (
            await auth_service._generate_and_store_refresh_token(
                user_id, access_token_jti
            )
        )

        assert len(plaintext_token) > 50
        assert expires_at > datetime.now(timezone.utc)
        assert (expires_at - datetime.now(timezone.utc)).days <= 7
        auth_service.context.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_login_generates_refresh_token(self, auth_service):
        """Test that login generates refresh token."""
        # Mock user
        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test User"
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.password_hash = auth_service._hash_password("password123")
        mock_user.save = AsyncMock()

        # Mock context methods
        auth_service.context.ensure_indexes = AsyncMock()
        auth_service.context.database.find = AsyncMock(return_value=[])
        auth_service._find_user_by_email = AsyncMock(return_value=mock_user)
        auth_service.context.save = AsyncMock()

        login_data = UserLogin(email="test@example.com", password="password123")
        token_response = await auth_service.login_user(login_data)

        assert token_response.refresh_token is not None
        assert token_response.refresh_expires_in is not None
        assert token_response.refresh_expires_in > 0


class TestRefreshTokenValidation:
    """Test refresh token validation."""

    @pytest.mark.asyncio
    async def test_validate_refresh_token_success(self, auth_service):
        """Test successful refresh token validation."""
        test_token = "test_refresh_token_12345"
        token_hash = auth_service._hash_refresh_token(test_token)

        # Create mock refresh token entity
        mock_refresh_token = MagicMock()
        mock_refresh_token.token_hash = token_hash
        mock_refresh_token.is_active = True
        mock_refresh_token.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        mock_refresh_token.user_id = "user123"
        mock_refresh_token.last_used_at = None
        mock_refresh_token._graph_context = auth_service.context
        mock_refresh_token.save = AsyncMock()

        # Mock context methods
        auth_service.context.ensure_indexes = AsyncMock()
        auth_service.context.database.find = AsyncMock(
            return_value=[{"id": "token123", "token_hash": token_hash}]
        )
        auth_service.context._deserialize_entity = AsyncMock(
            return_value=mock_refresh_token
        )
        auth_service.context.save = AsyncMock()

        result = await auth_service._validate_refresh_token(test_token)

        assert result is not None
        assert result.token_hash == token_hash
        # The code uses context.save(), not refresh_token.save()
        auth_service.context.save.assert_called_once_with(
            mock_refresh_token
        )  # last_used_at should be updated

    @pytest.mark.asyncio
    async def test_validate_refresh_token_expired(self, auth_service):
        """Test validation of expired refresh token."""
        test_token = "test_refresh_token_12345"
        token_hash = auth_service._hash_refresh_token(test_token)

        # Create mock expired refresh token
        mock_refresh_token = MagicMock()
        mock_refresh_token.token_hash = token_hash
        mock_refresh_token.is_active = True
        mock_refresh_token.expires_at = datetime.now(timezone.utc) - timedelta(
            days=1
        )  # Expired
        mock_refresh_token._graph_context = auth_service.context

        # Mock context methods
        auth_service.context.ensure_indexes = AsyncMock()
        auth_service.context.database.find = AsyncMock(
            return_value=[{"id": "token123", "token_hash": token_hash}]
        )
        auth_service.context._deserialize_entity = AsyncMock(
            return_value=mock_refresh_token
        )

        result = await auth_service._validate_refresh_token(test_token)

        assert result is None  # Expired token should not be validated

    @pytest.mark.asyncio
    async def test_validate_refresh_token_inactive(self, auth_service):
        """Test validation of inactive refresh token."""
        test_token = "test_refresh_token_12345"
        token_hash = auth_service._hash_refresh_token(test_token)

        # Create mock inactive refresh token
        mock_refresh_token = MagicMock()
        mock_refresh_token.token_hash = token_hash
        mock_refresh_token.is_active = False  # Inactive
        mock_refresh_token.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        mock_refresh_token._graph_context = auth_service.context

        # Mock context methods - inactive tokens won't be in results
        auth_service.context.ensure_indexes = AsyncMock()
        auth_service.context.database.find = AsyncMock(return_value=[])

        result = await auth_service._validate_refresh_token(test_token)

        assert result is None  # Inactive token should not be validated


class TestRefreshAccessToken:
    """Test access token refresh functionality."""

    @pytest.mark.asyncio
    async def test_refresh_access_token_success(self, auth_service):
        """Test successful access token refresh."""
        test_refresh_token = "test_refresh_token_12345"
        token_hash = auth_service._hash_refresh_token(test_refresh_token)

        # Mock refresh token entity
        mock_refresh_token = MagicMock()
        mock_refresh_token.token_hash = token_hash
        mock_refresh_token.is_active = True
        mock_refresh_token.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        mock_refresh_token.user_id = "user123"
        mock_refresh_token.last_used_at = None
        mock_refresh_token._graph_context = auth_service.context
        mock_refresh_token.save = AsyncMock()

        # Mock user
        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test User"
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)

        # Mock context methods
        auth_service.context.ensure_indexes = AsyncMock()
        auth_service.context.database.find = AsyncMock(
            return_value=[{"id": "token123", "token_hash": token_hash}]
        )
        auth_service.context._deserialize_entity = AsyncMock(
            return_value=mock_refresh_token
        )
        auth_service.context.save = AsyncMock()
        auth_service._get_user_by_id = AsyncMock(return_value=mock_user)

        token_response = await auth_service.refresh_access_token(test_refresh_token)

        assert token_response.access_token is not None
        assert token_response.user.id == "user123"
        # Without rotation, refresh token should not be returned
        assert token_response.refresh_token is None

    @pytest.mark.asyncio
    async def test_refresh_access_token_with_rotation(self, auth_service):
        """Test access token refresh with token rotation enabled."""
        auth_service.refresh_token_rotation = True
        test_refresh_token = "test_refresh_token_12345"
        token_hash = auth_service._hash_refresh_token(test_refresh_token)

        # Mock refresh token entity
        mock_refresh_token = MagicMock()
        mock_refresh_token.token_hash = token_hash
        mock_refresh_token.is_active = True
        mock_refresh_token.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        mock_refresh_token.user_id = "user123"
        mock_refresh_token.last_used_at = None
        mock_refresh_token._graph_context = auth_service.context
        mock_refresh_token.save = AsyncMock()

        # Mock user
        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test User"
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)

        # Mock context methods
        auth_service.context.ensure_indexes = AsyncMock()
        auth_service.context.database.find = AsyncMock(
            return_value=[{"id": "token123", "token_hash": token_hash}]
        )
        auth_service.context._deserialize_entity = AsyncMock(
            return_value=mock_refresh_token
        )
        auth_service.context.save = AsyncMock()
        auth_service._get_user_by_id = AsyncMock(return_value=mock_user)

        token_response = await auth_service.refresh_access_token(test_refresh_token)

        assert token_response.access_token is not None
        assert (
            token_response.refresh_token is not None
        )  # New refresh token with rotation
        assert token_response.refresh_expires_in is not None
        # Old token should be deactivated
        assert mock_refresh_token.is_active is False

    @pytest.mark.asyncio
    async def test_refresh_access_token_invalid(self, auth_service):
        """Test refresh with invalid refresh token."""
        with pytest.raises(ValueError, match="Invalid or expired refresh token"):
            await auth_service.refresh_access_token("invalid_token")


class TestRefreshTokenRevocation:
    """Test refresh token revocation."""

    @pytest.mark.asyncio
    async def test_revoke_refresh_token(self, auth_service):
        """Test revoking a refresh token."""
        test_refresh_token = "test_refresh_token_12345"
        token_hash = auth_service._hash_refresh_token(test_refresh_token)

        # Mock refresh token entity
        mock_refresh_token = MagicMock()
        mock_refresh_token.token_hash = token_hash
        mock_refresh_token.is_active = True
        mock_refresh_token.expires_at = datetime.now(timezone.utc) + timedelta(days=7)
        mock_refresh_token.user_id = "user123"
        mock_refresh_token.access_token_jti = "jti123"
        mock_refresh_token._graph_context = auth_service.context
        mock_refresh_token.save = AsyncMock()

        # Mock context methods
        auth_service.context.ensure_indexes = AsyncMock()
        auth_service.context.database.find = AsyncMock(
            return_value=[{"id": "token123", "token_hash": token_hash}]
        )
        auth_service.context._deserialize_entity = AsyncMock(
            return_value=mock_refresh_token
        )
        auth_service.context.save = AsyncMock()

        result = await auth_service.revoke_refresh_token(test_refresh_token)

        assert result is True
        assert mock_refresh_token.is_active is False
        # The code uses context.save(), not refresh_token.save()
        # Note: save() is called twice - once for refresh token, once for blacklist entry
        # Check that it was called with the refresh token
        auth_service.context.save.assert_any_call(mock_refresh_token)

    @pytest.mark.asyncio
    async def test_revoke_all_user_tokens(self, auth_service):
        """Test revoking all tokens for a user."""
        user_id = "user123"

        # Mock refresh tokens
        mock_token1 = MagicMock()
        mock_token1.is_active = True
        mock_token1.access_token_jti = "jti1"
        mock_token1._graph_context = auth_service.context
        mock_token1.save = AsyncMock()

        mock_token2 = MagicMock()
        mock_token2.is_active = True
        mock_token2.access_token_jti = "jti2"
        mock_token2._graph_context = auth_service.context
        mock_token2.save = AsyncMock()

        # Mock context methods
        auth_service.context.ensure_indexes = AsyncMock()
        auth_service.context.database.find = AsyncMock(
            return_value=[
                {"id": "token1", "user_id": user_id},
                {"id": "token2", "user_id": user_id},
            ]
        )
        auth_service.context._deserialize_entity = AsyncMock(
            side_effect=[mock_token1, mock_token2]
        )
        auth_service.context.save = AsyncMock()
        auth_service.context.delete = AsyncMock()

        revoked_count = await auth_service.revoke_all_user_tokens(user_id)

        assert revoked_count == 2
        assert mock_token1.is_active is False
        assert mock_token2.is_active is False


class TestRefreshTokenEndpoint:
    """Test refresh token API endpoint."""

    @pytest.mark.asyncio
    async def test_refresh_endpoint_success(self):
        """Test successful token refresh via API."""
        # Use unique database path for test isolation
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True),
            db_type="json",
            db_path=f"./.test_dbs/test_db_refresh_{test_id}",
        )
        client = TestClient(server.get_app())

        # Register and login (first user gets admin via bootstrap)
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
        assert login_response.status_code == 200
        login_data = login_response.json()
        assert "refresh_token" in login_data
        refresh_token = login_data["refresh_token"]
        assert (
            refresh_token is not None
        ), f"Refresh token is None in login response: {login_data}"
        assert (
            len(refresh_token) > 0
        ), f"Refresh token is empty in login response: {login_data}"

        # Refresh token
        refresh_response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": refresh_token},
        )
        assert (
            refresh_response.status_code == 200
        ), f"Refresh failed: {refresh_response.status_code} - {refresh_response.text}"
        refresh_data = refresh_response.json()
        assert "access_token" in refresh_data
        assert refresh_data["access_token"] != login_data["access_token"]

    @pytest.mark.asyncio
    async def test_refresh_endpoint_invalid_token(self):
        """Test refresh endpoint with invalid token."""
        # Use unique database path for test isolation
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True),
            db_type="json",
            db_path=f"./.test_dbs/test_db_refresh_invalid_{test_id}",
        )
        client = TestClient(server.get_app())

        refresh_response = client.post(
            "/api/auth/refresh",
            json={"refresh_token": "invalid_token"},
        )
        assert refresh_response.status_code == 401

    @pytest.mark.asyncio
    async def test_revoke_all_endpoint(self):
        """Test revoke all tokens endpoint."""
        # Use unique database path for test isolation
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True),
            db_type="json",
            db_path=f"./.test_dbs/test_db_revoke_{test_id}",
        )
        client = TestClient(server.get_app())

        # Register and login (first user gets admin via bootstrap)
        email = f"test_{test_id}@example.com"
        register_response = client.post(
            "/api/auth/register",
            json={"email": email, "password": "password123"},
        )
        assert (
            register_response.status_code == 200
        ), f"Registration failed: {register_response.text}"

        login_response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        login_data = login_response.json()
        assert (
            "access_token" in login_data
        ), f"Login response missing access_token: {login_data}"
        access_token = login_data["access_token"]

        # Revoke all tokens
        revoke_response = client.post(
            "/api/auth/revoke-all",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert revoke_response.status_code == 200
        revoke_data = revoke_response.json()
        assert "revoked_count" in revoke_data


class TestResilientRefreshTokenGeneration:
    """Test resilient refresh token generation behavior."""

    @pytest.mark.asyncio
    async def test_login_succeeds_when_refresh_token_generation_fails(
        self, auth_service
    ):
        """Verify login succeeds even if refresh token storage fails."""
        # Mock user
        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test User"
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.password_hash = auth_service._hash_password("password123")
        mock_user.save = AsyncMock()
        mock_user._graph_context = auth_service.context

        # Mock context methods
        auth_service._find_user_by_email = AsyncMock(return_value=mock_user)

        # Make refresh token generation fail
        async def failing_refresh_token(*args, **kwargs):
            raise Exception("Database connection failed")

        auth_service._generate_and_store_refresh_token = failing_refresh_token

        # Track logger warnings
        logger_warnings = []

        def log_warning(msg):
            logger_warnings.append(msg)

        auth_service._logger.warning = log_warning

        # Attempt login
        login_data = UserLogin(email="test@example.com", password="password123")
        token_response = await auth_service.login_user(login_data)

        # Verify login succeeded despite refresh token failure
        assert token_response is not None
        assert token_response.access_token is not None
        assert (
            token_response.refresh_token is None
        )  # Should be None when generation fails
        assert token_response.user is not None
        # Verify warning was logged
        assert len(logger_warnings) > 0
        assert any("Failed to generate refresh token" in msg for msg in logger_warnings)

    @pytest.mark.asyncio
    async def test_login_returns_none_refresh_token_on_failure(self, auth_service):
        """Verify refresh_token is None when generation fails."""
        # Mock user
        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test User"
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.password_hash = auth_service._hash_password("password123")
        mock_user.save = AsyncMock()
        mock_user._graph_context = auth_service.context

        # Mock context methods
        auth_service._find_user_by_email = AsyncMock(return_value=mock_user)

        # Make refresh token generation fail
        auth_service._generate_and_store_refresh_token = AsyncMock(
            side_effect=Exception("Storage error")
        )

        # Attempt login
        login_data = UserLogin(email="test@example.com", password="password123")
        token_response = await auth_service.login_user(login_data)

        # Verify refresh_token is None
        assert token_response.refresh_token is None
        assert token_response.refresh_expires_in is None
        # But access token should still be present
        assert token_response.access_token is not None

    @pytest.mark.asyncio
    async def test_login_logs_warning_on_refresh_token_failure(self, auth_service):
        """Verify warning is logged when refresh token fails."""
        # Mock user
        mock_user = MagicMock()
        mock_user.id = "user123"
        mock_user.email = "test@example.com"
        mock_user.name = "Test User"
        mock_user.is_active = True
        mock_user.created_at = datetime.now(timezone.utc)
        mock_user.password_hash = auth_service._hash_password("password123")
        mock_user.save = AsyncMock()
        mock_user._graph_context = auth_service.context

        # Mock context methods
        auth_service._find_user_by_email = AsyncMock(return_value=mock_user)

        # Make refresh token generation fail
        auth_service._generate_and_store_refresh_token = AsyncMock(
            side_effect=Exception("Test error")
        )

        # Track logger warnings
        logger_warnings = []

        def log_warning(msg):
            logger_warnings.append(msg)

        auth_service._logger.warning = log_warning

        # Attempt login
        login_data = UserLogin(email="test@example.com", password="password123")
        await auth_service.login_user(login_data)

        # Verify warning was logged
        assert len(logger_warnings) > 0
        assert any("Failed to generate refresh token" in msg for msg in logger_warnings)
        assert any(
            "Login will proceed without refresh token" in msg for msg in logger_warnings
        )

    @pytest.mark.asyncio
    async def test_ensure_indexes_called_before_saving_refresh_token(
        self, auth_service
    ):
        """Verify ensure_indexes is called before saving refresh token."""
        from jvspatial.api.auth.models import RefreshToken

        # Track ensure_indexes calls
        ensure_calls = []

        async def tracked_ensure_indexes(model):
            ensure_calls.append(model)
            return None

        auth_service.context.ensure_indexes = tracked_ensure_indexes
        auth_service.context.save = AsyncMock()

        # Generate refresh token directly to test ensure_indexes
        await auth_service._generate_and_store_refresh_token("user123", "jti123")

        # Verify ensure_indexes was called with RefreshToken
        assert len(ensure_calls) > 0
        assert RefreshToken in ensure_calls or any(
            "RefreshToken" in str(call) or call == RefreshToken for call in ensure_calls
        )
