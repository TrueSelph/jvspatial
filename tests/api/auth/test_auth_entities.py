"""
Test suite for authentication entities.

This module tests the User, APIKey, and Session entities including
password hashing, validation, permissions, and database operations.
"""

import secrets
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.api.auth.entities import (
    APIKey,
    APIKeyInvalidError,
    AuthenticationError,
    AuthorizationError,
    InvalidCredentialsError,
    RateLimitError,
    Session,
    SessionExpiredError,
    User,
    UserNotFoundError,
)


class TestUser:
    """Test User entity functionality."""

    async def test_user_creation(self):
        """Test basic user creation."""
        user = User(
            email="test@example.com",
            password_hash="hashed_password",  # pragma: allowlist secret
            roles=["user"],
            permissions=["read_data"],
        )

        assert user.email == "test@example.com"
        assert user.password_hash == "hashed_password"  # pragma: allowlist secret
        assert user.is_active is True
        assert user.is_verified is False
        assert user.is_admin is False
        assert user.roles == ["user"]
        assert user.permissions == ["read_data"]
        assert user.rate_limit_per_hour == 1000

    async def test_user_collection_name(self):
        """Test user uses correct collection name."""
        user = User(
            username="test",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
        )
        assert user.get_collection_name() == "object"

    async def test_password_hashing(self):
        """Test password hashing functionality."""
        password = "test_password_123"  # pragma: allowlist secret
        hashed = User.hash_password(password)

        # Should be a bcrypt hash
        assert hashed != password
        assert len(hashed) > 50  # BCrypt hashes are long
        assert hashed.startswith("$2b$")  # BCrypt identifier

    async def test_password_verification(self):
        """Test password verification."""
        password = "test_password_123"  # pragma: allowlist secret
        user = User(
            username="test",
            email="test@example.com",
            password_hash=User.hash_password(password),
        )

        # Should verify correct password
        assert user.verify_password(password) is True

        # Should reject incorrect password
        assert user.verify_password("wrong_password") is False

    async def test_permission_checking(self):
        """Test permission checking logic."""
        # Regular user with specific permissions
        user = User(
            username="test",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            permissions=["read_data", "write_data"],
        )

        assert user.has_permission("read_data") is True
        assert user.has_permission("write_data") is True
        assert user.has_permission("delete_data") is False

        # Admin user should have all permissions
        admin_user = User(
            username="admin",
            email="admin@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_admin=True,
        )

        assert admin_user.has_permission("read_data") is True
        assert admin_user.has_permission("any_permission") is True

    async def test_role_checking(self):
        """Test role checking logic."""
        user = User(
            username="test",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            roles=["analyst", "viewer"],
        )

        assert user.has_role("analyst") is True
        assert user.has_role("viewer") is True
        assert user.has_role("admin") is False

        # Admin user should have admin and superuser roles
        admin_user = User(
            username="admin",
            email="admin@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_admin=True,
        )

        assert admin_user.has_role("admin") is True
        assert admin_user.has_role("superuser") is True
        assert admin_user.has_role("analyst") is False

    async def test_region_access_checking(self):
        """Test spatial region access control."""
        # User with specific regions allowed
        user = User(
            username="test",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            allowed_regions=["region_1", "region_2"],
        )

        assert user.can_access_region("region_1") is True
        assert user.can_access_region("region_2") is True
        assert user.can_access_region("region_3") is False

        # Admin user can access all regions
        admin_user = User(
            username="admin",
            email="admin@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_admin=True,
        )

        assert admin_user.can_access_region("any_region") is True

        # User with no region restrictions
        unrestricted_user = User(
            username="unrestricted",
            email="unrestricted@example.com",
            password_hash="hash",  # pragma: allowlist secret
            allowed_regions=[],
        )

        assert unrestricted_user.can_access_region("any_region") is True

    async def test_node_type_access_checking(self):
        """Test node type access control."""
        # User with specific node types allowed
        user = User(
            username="test",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            allowed_node_types=["Document", "Person"],
        )

        assert user.can_access_node_type("Document") is True
        assert user.can_access_node_type("Person") is True
        assert user.can_access_node_type("Location") is False

        # Admin user can access all node types
        admin_user = User(
            email="admin@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_admin=True,
        )

        assert admin_user.can_access_node_type("any_type") is True

    @pytest.mark.asyncio
    async def test_record_login(self):
        """Test login recording functionality."""
        user = User(
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            login_count=5,
        )

        with patch(
            "jvspatial.api.auth.entities.User.save", new_callable=AsyncMock
        ) as mock_save:
            mock_save.return_value = user
            old_count = user.login_count
            await user.record_login()

            # Should increment login count and update last login
            assert user.login_count == old_count + 1
            assert user.last_login is not None
            # last_login is stored as ISO string, not datetime object
            assert isinstance(user.last_login, str)
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_email(self):
        """Test finding user by email."""
        mock_ctx = MagicMock()
        mock_ctx.database.find = AsyncMock(
            return_value=[
                {
                    "id": "user_123",
                    "email": "test@example.com",
                    "password_hash": "hash",  # pragma: allowlist secret
                }
            ]
        )

        with patch("jvspatial.core.context.get_default_context", return_value=mock_ctx):
            user = await User.find_by_email("test@example.com")

            assert user is not None
            assert user.email == "test@example.com"
            mock_ctx.database.find.assert_called_once_with(
                "user", {"email": "test@example.com"}
            )

    @pytest.mark.asyncio
    async def test_find_by_email_not_found(self):
        """Test finding user by email when not found."""
        mock_ctx = MagicMock()
        mock_ctx.database.find = AsyncMock(return_value=[])

        with patch("jvspatial.core.context.get_default_context", return_value=mock_ctx):
            user = await User.find_by_email("nonexistent@example.com")

            assert user is None

    @pytest.mark.asyncio
    async def test_find_by_id(self):
        """Test finding user by ID."""
        mock_ctx = MagicMock()
        mock_ctx.database.find = AsyncMock(
            return_value=[
                {
                    "id": "user_123",
                    "email": "test@example.com",
                    "password_hash": "hash",  # pragma: allowlist secret
                }
            ]
        )

        with patch("jvspatial.core.context.get_default_context", return_value=mock_ctx):
            user = await User.find_by_id("user_123")

            assert user is not None
            assert user.email == "test@example.com"
            mock_ctx.database.find.assert_called_once_with("user", {"id": "user_123"})


class TestAPIKey:
    """Test APIKey entity functionality."""

    async def test_api_key_creation(self):
        """Test basic API key creation."""
        api_key = APIKey(
            name="Test Key",
            key_id="test_key_id",
            key_hash="hashed_secret",
            user_id="user_123",
        )

        assert api_key.name == "Test Key"
        assert api_key.key_id == "test_key_id"
        assert api_key.key_hash == "hashed_secret"
        assert api_key.user_id == "user_123"
        assert api_key.is_active is True
        assert api_key.expires_at is None
        assert api_key.usage_count == 0
        assert api_key.rate_limit_per_hour == 10000

    async def test_api_key_collection_name(self):
        """Test API key uses correct collection name."""
        api_key = APIKey(name="test", key_id="id", key_hash="hash", user_id="user")
        assert api_key.get_collection_name() == "object"

    async def test_generate_key_pair(self):
        """Test API key pair generation."""
        key_id, secret_key = APIKey.generate_key_pair()

        assert key_id is not None
        assert secret_key is not None
        assert len(key_id) > 10  # Should be a reasonable length
        assert len(secret_key) > 20  # Should be longer than key_id
        assert key_id != secret_key

    async def test_hash_secret(self):
        """Test secret key hashing."""
        secret = "my_secret_key"  # pragma: allowlist secret
        hashed = APIKey.hash_secret(secret)

        assert hashed != secret
        assert len(hashed) == 64  # SHA-256 produces 64 character hex string

    async def test_verify_secret(self):
        """Test secret key verification."""
        secret = "my_secret_key"  # pragma: allowlist secret
        api_key = APIKey(
            name="test",
            key_id="id",
            key_hash=APIKey.hash_secret(secret),
            user_id="user",
        )

        assert api_key.verify_secret(secret) is True
        assert api_key.verify_secret("wrong_secret") is False

    async def test_is_valid_active_key(self):
        """Test validity check for active key."""
        api_key = APIKey(
            name="test", key_id="id", key_hash="hash", user_id="user", is_active=True
        )

        assert api_key.is_valid() is True

    async def test_is_valid_inactive_key(self):
        """Test validity check for inactive key."""
        api_key = APIKey(
            name="test", key_id="id", key_hash="hash", user_id="user", is_active=False
        )

        assert api_key.is_valid() is False

    async def test_is_valid_expired_key(self):
        """Test validity check for expired key."""
        api_key = APIKey(
            name="test",
            key_id="id",
            key_hash="hash",
            user_id="user",
            is_active=True,
            expires_at=(
                datetime.now() - timedelta(hours=1)
            ).isoformat(),  # Expired 1 hour ago
        )

        assert api_key.is_valid() is False

    async def test_is_valid_future_expiry(self):
        """Test validity check for key with future expiry."""
        api_key = APIKey(
            name="test",
            key_id="id",
            key_hash="hash",
            user_id="user",
            is_active=True,
            expires_at=(
                datetime.now() + timedelta(hours=1)
            ).isoformat(),  # Expires in 1 hour
        )

        assert api_key.is_valid() is True

    async def test_can_access_endpoint_unrestricted(self):
        """Test endpoint access for unrestricted key."""
        api_key = APIKey(
            name="test",
            key_id="id",
            key_hash="hash",
            user_id="user",
            allowed_endpoints=[],  # No restrictions
        )

        assert api_key.can_access_endpoint("/any/endpoint") is True
        assert api_key.can_access_endpoint("/admin/users") is True

    async def test_can_access_endpoint_restricted(self):
        """Test endpoint access for restricted key."""
        api_key = APIKey(
            name="test",
            key_id="id",
            key_hash="hash",
            user_id="user",
            allowed_endpoints=["/api/data/*", "/api/search"],
        )

        assert api_key.can_access_endpoint("/api/data/list") is True
        assert api_key.can_access_endpoint("/api/data/create") is True
        assert api_key.can_access_endpoint("/api/search") is True
        assert api_key.can_access_endpoint("/admin/users") is False

    async def test_can_perform_operation_unrestricted(self):
        """Test operation checking for unrestricted key."""
        api_key = APIKey(
            name="test",
            key_id="id",
            key_hash="hash",
            user_id="user",
            allowed_operations=[],  # No restrictions
        )

        assert api_key.can_perform_operation("read") is True
        assert api_key.can_perform_operation("write") is True

    async def test_can_perform_operation_restricted(self):
        """Test operation checking for restricted key."""
        api_key = APIKey(
            name="test",
            key_id="id",
            key_hash="hash",
            user_id="user",
            allowed_operations=["read", "search"],
        )

        assert api_key.can_perform_operation("read") is True
        assert api_key.can_perform_operation("search") is True
        assert api_key.can_perform_operation("write") is False

    @pytest.mark.asyncio
    async def test_record_usage(self):
        """Test usage recording functionality."""
        api_key = APIKey(
            name="test", key_id="id", key_hash="hash", user_id="user", usage_count=10
        )

        with patch(
            "jvspatial.api.auth.entities.APIKey.save", new_callable=AsyncMock
        ) as mock_save:
            mock_save.return_value = api_key
            old_count = api_key.usage_count
            await api_key.record_usage("/api/data", "read")

            # Should increment usage count and update last used
            assert api_key.usage_count == old_count + 1
            assert api_key.last_used is not None
            # last_used is stored as ISO string, not datetime object
            assert isinstance(api_key.last_used, str)
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_key_id(self):
        """Test finding API key by key ID."""
        mock_ctx = MagicMock()
        mock_ctx.database.find = AsyncMock(
            return_value=[
                {
                    "id": "apikey_123",
                    "context": {
                        "name": "Test Key",
                        "key_id": "test_key_id",
                        "key_hash": "hash",
                        "user_id": "user_123",
                    },
                }
            ]
        )
        mock_ctx._deserialize_entity = AsyncMock(
            return_value=APIKey(
                name="Test Key",
                key_id="test_key_id",
                key_hash="hash",
                user_id="user_123",
            )
        )

        with patch("jvspatial.core.context.get_default_context", return_value=mock_ctx):
            api_key = await APIKey.find_by_key_id("test_key_id")

            assert api_key is not None
            assert api_key.key_id == "test_key_id"
            mock_ctx.database.find.assert_called_once_with(
                "apikey", {"key_id": "test_key_id"}
            )


class TestSession:
    """Test Session entity functionality."""

    async def test_session_creation(self):
        """Test basic session creation."""
        session = Session(
            session_id="session_123",
            user_id="user_123",
            jwt_token="jwt_token_string",
            refresh_token="refresh_token_string",
            expires_at=(datetime.now() + timedelta(hours=24)).isoformat(),
        )

        assert session.session_id == "session_123"
        assert session.user_id == "user_123"
        assert session.jwt_token == "jwt_token_string"
        assert session.refresh_token == "refresh_token_string"
        assert session.is_active is True
        assert session.revoked_at is None

    async def test_session_revoke(self):
        """Test session revocation."""
        session = Session(
            session_id="session_123",
            user_id="user_123",
            jwt_token="jwt_token_string",
            refresh_token="refresh_token_string",
            expires_at=(
                datetime.now() + timedelta(hours=24)
            ).isoformat(),  # Use ISO format string
        )

        # Test session revocation (save method is called internally by revoke)
        await session.revoke("User logout")

        assert session.is_active is False
        assert session.revoked_at is not None
        assert session.revoked_reason == "User logout"

    async def test_session_collection_name(self):
        """Test session uses correct collection name."""
        session = Session(
            session_id="id",
            user_id="user",
            jwt_token="jwt",
            refresh_token="refresh",
            expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
        )
        assert session.get_collection_name() == "object"

    async def test_create_session_id(self):
        """Test session ID generation."""
        session_id = Session.create_session_id()

        assert session_id is not None
        assert len(session_id) > 20  # Should be a reasonable length

        # Should be unique
        session_id_2 = Session.create_session_id()
        assert session_id != session_id_2

    async def test_is_valid_active_session(self):
        """Test validity check for active session."""
        session = Session(
            session_id="id",
            user_id="user",
            jwt_token="jwt",
            refresh_token="refresh",
            expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
            is_active=True,
        )

        assert session.is_valid() is True

    async def test_is_valid_inactive_session(self):
        """Test validity check for inactive session."""
        session = Session(
            session_id="id",
            user_id="user",
            jwt_token="jwt",
            refresh_token="refresh",
            expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
            is_active=False,
        )

        assert session.is_valid() is False

    async def test_is_valid_revoked_session(self):
        """Test validity check for revoked session."""
        session = Session(
            session_id="id",
            user_id="user",
            jwt_token="jwt",
            refresh_token="refresh",
            expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
            is_active=True,
            revoked_at=(datetime.now() - timedelta(minutes=30)).isoformat(),
        )

        assert session.is_valid() is False

    async def test_is_valid_expired_session(self):
        """Test validity check for expired session."""
        session = Session(
            session_id="id",
            user_id="user",
            jwt_token="jwt",
            refresh_token="refresh",
            expires_at=(
                datetime.now() - timedelta(hours=1)
            ).isoformat(),  # Expired 1 hour ago
            is_active=True,
        )

        assert session.is_valid() is False

    async def test_extend_session(self):
        """Test session extension."""
        session = Session(
            session_id="id",
            user_id="user",
            jwt_token="jwt",
            refresh_token="refresh",
            expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
        )

        old_expires = session.expires_at
        session.extend_session(48)  # Extend by 48 hours

        # Should have extended expiration
        assert session.expires_at > old_expires
        # Convert to datetime for comparison
        if isinstance(session.expires_at, str):
            expires_dt = datetime.fromisoformat(session.expires_at)
        else:
            expires_dt = session.expires_at
        time_diff = expires_dt - datetime.now()
        assert time_diff.total_seconds() > 47 * 3600  # Should be close to 48 hours

        # Should have updated last activity
        assert session.last_activity is not None
        # last_activity is stored as ISO string, not datetime object
        assert isinstance(session.last_activity, str)

    @pytest.mark.asyncio
    async def test_revoke(self):
        """Test session revocation."""
        session = Session(
            session_id="id",
            user_id="user",
            jwt_token="jwt",
            refresh_token="refresh",
            expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
        )

        with patch(
            "jvspatial.api.auth.entities.Session.save", new_callable=AsyncMock
        ) as mock_save:
            mock_save.return_value = session
            await session.revoke("Test revocation")

            assert session.is_active is False
            assert session.revoked_at is not None
            assert session.revoked_reason == "Test revocation"
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_activity(self):
        """Test activity update."""
        session = Session(
            session_id="id",
            user_id="user",
            jwt_token="jwt",
            refresh_token="refresh",
            expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
        )

        with patch(
            "jvspatial.api.auth.entities.Session.save", new_callable=AsyncMock
        ) as mock_save:
            mock_save.return_value = session
            old_activity = session.last_activity
            await session.update_activity()

            assert session.last_activity > old_activity
            mock_save.assert_called_once()

    @pytest.mark.asyncio
    async def test_find_by_session_id(self):
        """Test finding session by session ID."""
        mock_ctx = MagicMock()
        mock_ctx.database.find = AsyncMock(
            return_value=[
                {
                    "id": "session_123",
                    "context": {
                        "session_id": "test_session_id",
                        "user_id": "user_123",
                        "jwt_token": "jwt",
                        "refresh_token": "refresh",
                        "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(),
                    },
                }
            ]
        )
        mock_ctx._deserialize_entity = AsyncMock(
            return_value=Session(
                session_id="test_session_id",
                user_id="user_123",
                jwt_token="jwt",
                refresh_token="refresh",
                expires_at=(datetime.now() + timedelta(hours=1)).isoformat(),
            )
        )

        with patch("jvspatial.core.context.get_default_context", return_value=mock_ctx):
            session = await Session.find_by_session_id("test_session_id")

            assert session is not None
            assert session.session_id == "test_session_id"
            mock_ctx.database.find.assert_called_once_with(
                "session", {"context.session_id": "test_session_id"}
            )


class TestAuthExceptions:
    """Test authentication exception classes."""

    async def test_authentication_error(self):
        """Test AuthenticationError exception."""
        error = AuthenticationError("Test auth error")
        assert str(error) == "Test auth error"
        assert isinstance(error, Exception)

    async def test_authorization_error(self):
        """Test AuthorizationError exception."""
        error = AuthorizationError("Test authz error")
        assert str(error) == "Test authz error"
        assert isinstance(error, Exception)

    async def test_rate_limit_error(self):
        """Test RateLimitError exception."""
        error = RateLimitError("Rate limit exceeded")
        assert str(error) == "Rate limit exceeded"
        assert isinstance(error, Exception)

    async def test_invalid_credentials_error(self):
        """Test InvalidCredentialsError exception."""
        error = InvalidCredentialsError("Invalid creds")
        assert str(error) == "Invalid creds"
        assert isinstance(error, AuthenticationError)

    async def test_user_not_found_error(self):
        """Test UserNotFoundError exception."""
        error = UserNotFoundError("User not found")
        assert str(error) == "User not found"
        assert isinstance(error, AuthenticationError)

    async def test_session_expired_error(self):
        """Test SessionExpiredError exception."""
        error = SessionExpiredError("Session expired")
        assert str(error) == "Session expired"
        assert isinstance(error, AuthenticationError)

    async def test_api_key_invalid_error(self):
        """Test APIKeyInvalidError exception."""
        error = APIKeyInvalidError("Invalid API key")
        assert str(error) == "Invalid API key"
        assert isinstance(error, AuthenticationError)
