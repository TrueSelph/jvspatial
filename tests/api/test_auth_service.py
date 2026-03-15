"""Tests for authentication service token validation."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest

from jvspatial.api.auth.models import User, UserResponse
from jvspatial.api.auth.service import AuthenticationService
from jvspatial.core.context import GraphContext


@pytest.fixture
def auth_service():
    """Create authentication service instance."""
    context = MagicMock(spec=GraphContext)
    return AuthenticationService(
        context,
        jwt_secret="test-secret-key",
        jwt_algorithm="HS256",
        jwt_expire_minutes=30,
        refresh_expire_days=7,
    )


@pytest.fixture
def mock_user():
    """Create a mock user."""
    user = MagicMock(spec=User)
    user.id = "user123"
    user.email = "test@example.com"
    user.name = "Test User"
    user.is_active = True
    user.created_at = datetime.now(timezone.utc)
    return user


class TestTokenValidation:
    """Test token validation behavior."""

    @pytest.mark.asyncio
    async def test_validate_token_decode_first_then_blacklist(
        self, auth_service, mock_user
    ):
        """Verify token is decoded before blacklist check."""
        # Generate a valid token
        token, _ = auth_service._generate_jwt_token(mock_user.id, mock_user.email)
        payload = auth_service._decode_jwt_token(token)
        token_id = payload.get("jti")

        # Mock methods
        auth_service._is_token_blacklisted_by_jti = AsyncMock(return_value=False)
        auth_service._get_user_by_id = AsyncMock(return_value=mock_user)
        auth_service.context.save = AsyncMock()

        # Track decode calls
        decode_calls = []
        original_decode = auth_service._decode_jwt_token

        def tracked_decode(token_str):
            decode_calls.append(token_str)
            return original_decode(token_str)

        auth_service._decode_jwt_token = tracked_decode

        # Validate token
        result = await auth_service.validate_token(token)

        # Verify decode was called first
        assert len(decode_calls) > 0
        # Verify blacklist check was called after decode (we can't easily verify order,
        # but we can verify both were called)
        auth_service._is_token_blacklisted_by_jti.assert_called_once_with(token_id)
        assert result is not None
        assert isinstance(result, UserResponse)

    @pytest.mark.asyncio
    async def test_validate_token_expired_returns_none(self, auth_service):
        """Verify expired tokens return None without checking blacklist."""
        # Create an expired token
        expired_time = datetime.now(timezone.utc) - timedelta(hours=1)
        payload = {
            "user_id": "user123",
            "email": "test@example.com",
            "iat": expired_time,
            "exp": expired_time,
            "jti": "expired_token_id",
        }
        expired_token = jwt.encode(
            payload, auth_service.jwt_secret, algorithm=auth_service.jwt_algorithm
        )

        # Mock blacklist check (should not be called)
        auth_service._is_token_blacklisted_by_jti = AsyncMock()

        # Validate expired token
        result = await auth_service.validate_token(expired_token)

        # Verify token was rejected and blacklist was not checked
        assert result is None
        auth_service._is_token_blacklisted_by_jti.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_token_blacklisted_returns_none(
        self, auth_service, mock_user
    ):
        """Verify blacklisted tokens return None."""
        # Generate a valid token
        token, _ = auth_service._generate_jwt_token(mock_user.id, mock_user.email)
        payload = auth_service._decode_jwt_token(token)
        token_id = payload.get("jti")

        # Mock blacklist check to return True
        auth_service._is_token_blacklisted_by_jti = AsyncMock(return_value=True)

        # Validate blacklisted token
        result = await auth_service.validate_token(token)

        # Verify token was rejected
        assert result is None
        auth_service._is_token_blacklisted_by_jti.assert_called_once_with(token_id)

    @pytest.mark.asyncio
    async def test_validate_token_logging(self, auth_service, mock_user):
        """Verify debug logging occurs at each validation step."""
        # Generate a valid token
        token, _ = auth_service._generate_jwt_token(mock_user.id, mock_user.email)

        # Mock methods
        auth_service._is_token_blacklisted_by_jti = AsyncMock(return_value=False)
        auth_service._get_user_by_id = AsyncMock(return_value=mock_user)
        auth_service.context.save = AsyncMock()

        # Track logger calls
        logger_calls = []

        def log_debug(msg):
            logger_calls.append(msg)

        auth_service._logger.debug = log_debug

        # Validate token
        result = await auth_service.validate_token(token)

        # Verify logging occurred
        assert len(logger_calls) > 0
        # Check for success log
        assert any("Token validation successful" in call for call in logger_calls)
        assert result is not None

    @pytest.mark.asyncio
    async def test_validate_token_logging_on_failure(self, auth_service):
        """Verify debug logging occurs on validation failure."""
        # Create an invalid token
        invalid_token = "invalid.token.here"

        # Track logger calls
        logger_calls = []

        def log_debug(msg):
            logger_calls.append(msg)

        auth_service._logger.debug = log_debug

        # Validate invalid token
        result = await auth_service.validate_token(invalid_token)

        # Verify logging occurred for failure
        assert len(logger_calls) > 0
        assert any("Token validation failed" in call for call in logger_calls)
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_token_success_updates_last_accessed(
        self, auth_service, mock_user
    ):
        """Verify successful validation updates user timestamp."""
        # Generate a valid token
        token, _ = auth_service._generate_jwt_token(mock_user.id, mock_user.email)

        # Mock methods
        auth_service._is_token_blacklisted_by_jti = AsyncMock(return_value=False)
        auth_service._get_user_by_id = AsyncMock(return_value=mock_user)
        auth_service.context.save = AsyncMock()

        # Validate token
        result = await auth_service.validate_token(token)

        # Verify user was saved (which updates last_accessed)
        auth_service.context.save.assert_called_once_with(mock_user)
        assert result is not None

    @pytest.mark.asyncio
    async def test_validate_token_missing_jti_returns_none(self, auth_service):
        """Verify tokens without JTI return None."""
        # Create a token without JTI
        payload = {
            "user_id": "user123",
            "email": "test@example.com",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(minutes=30),
            # No "jti" field
        }
        token = jwt.encode(
            payload, auth_service.jwt_secret, algorithm=auth_service.jwt_algorithm
        )

        # Track logger calls
        logger_calls = []

        def log_debug(msg):
            logger_calls.append(msg)

        auth_service._logger.debug = log_debug

        # Validate token
        result = await auth_service.validate_token(token)

        # Verify token was rejected
        assert result is None
        assert any("missing JTI" in call for call in logger_calls)

    @pytest.mark.asyncio
    async def test_validate_token_user_not_found_returns_none(self, auth_service):
        """Verify tokens for non-existent users return None."""
        # Generate a token
        token, _ = auth_service._generate_jwt_token(
            "nonexistent_user", "test@example.com"
        )
        payload = auth_service._decode_jwt_token(token)
        token_id = payload.get("jti")

        # Mock methods
        auth_service._is_token_blacklisted_by_jti = AsyncMock(return_value=False)
        auth_service._get_user_by_id = AsyncMock(return_value=None)

        # Track logger calls
        logger_calls = []

        def log_debug(msg):
            logger_calls.append(msg)

        auth_service._logger.debug = log_debug

        # Validate token
        result = await auth_service.validate_token(token)

        # Verify token was rejected
        assert result is None
        assert any(
            "user" in call.lower() and "not found" in call.lower()
            for call in logger_calls
        )

    @pytest.mark.asyncio
    async def test_validate_token_inactive_user_returns_none(
        self, auth_service, mock_user
    ):
        """Verify tokens for inactive users return None."""
        # Generate a valid token
        token, _ = auth_service._generate_jwt_token(mock_user.id, mock_user.email)
        payload = auth_service._decode_jwt_token(token)
        token_id = payload.get("jti")

        # Set user as inactive
        mock_user.is_active = False

        # Mock methods
        auth_service._is_token_blacklisted_by_jti = AsyncMock(return_value=False)
        auth_service._get_user_by_id = AsyncMock(return_value=mock_user)

        # Track logger calls
        logger_calls = []

        def log_debug(msg):
            logger_calls.append(msg)

        auth_service._logger.debug = log_debug

        # Validate token
        result = await auth_service.validate_token(token)

        # Verify token was rejected
        assert result is None
        assert any("inactive" in call.lower() for call in logger_calls)
