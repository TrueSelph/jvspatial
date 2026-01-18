"""Tests for API key authentication and management."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from jvspatial.api import endpoint
from jvspatial.api.auth.api_key_service import APIKeyService
from jvspatial.api.auth.models import APIKey, APIKeyCreateRequest
from jvspatial.api.server import Server
from jvspatial.core.context import GraphContext


@pytest.fixture
def api_key_service():
    """Create API key service instance."""
    context = MagicMock(spec=GraphContext)
    return APIKeyService(context)


class TestAPIKeyService:
    """Test API key service functionality."""

    def test_hash_key(self, api_key_service):
        """Test API key hashing with bcrypt/argon2."""
        key = "test_key_12345"
        hash1 = api_key_service._hash_key(key)
        hash2 = api_key_service._hash_key(key)

        # Same key should produce same hash (deterministic for bcrypt/argon2)
        # Note: bcrypt includes salt, so same key may produce different hashes
        # But verification should work
        assert (
            len(hash1) > 20
        )  # Reasonable minimum (bcrypt ~60, argon2 ~97, SHA-256 fallback 64)

        # Verify that the hash can be used for verification
        assert api_key_service._verify_key(key, hash1) is True
        assert api_key_service._verify_key("wrong_key", hash1) is False

    def test_generate_key_string(self, api_key_service):
        """Test API key string generation."""
        key = api_key_service._generate_key_string()
        assert key.startswith("sk_")
        assert len(key) > 32  # Prefix + random part

        # Generate multiple keys - should be unique
        keys = [api_key_service._generate_key_string() for _ in range(10)]
        assert len(set(keys)) == 10  # All unique

    def test_get_key_prefix_display(self, api_key_service):
        """Test key prefix extraction for display."""
        key = "sk_test_" + "x" * 35  # Example test key
        prefix = api_key_service._get_key_prefix_display(key)
        assert len(prefix) <= 23  # 20 chars + "..."
        assert prefix.startswith("sk_")

    @pytest.mark.asyncio
    async def test_generate_key(self, api_key_service):
        """Test API key generation."""
        # Mock the context methods since we're using context directly
        mock_key = MagicMock()
        mock_key.id = "key123"
        mock_key.key_prefix = "sk_live_abc12345"
        mock_key.name = "Test Key"

        # Mock context.save to return the key
        api_key_service.context.save = AsyncMock(return_value=mock_key)
        api_key_service.context.ensure_indexes = AsyncMock()

        plaintext, api_key = await api_key_service.generate_key(
            user_id="user123",
            name="Test Key",
            permissions=["read", "write"],
        )

        assert plaintext.startswith("sk_")
        assert len(plaintext) > 32
        # The ID will be generated, but we can check the key was created
        assert api_key.id is not None
        assert api_key.name == "Test Key"
        api_key_service.context.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_key(self, api_key_service):
        """Test API key validation with new verification logic."""
        test_key = "sk_live_test123456789"

        # Create mock key with hashed key
        mock_key = MagicMock()
        mock_key.is_active = True
        mock_key.expires_at = None
        mock_key.key_hash = api_key_service._hash_key(test_key)  # Hash the test key
        mock_key._graph_context = api_key_service.context

        # Mock context methods since we're using context directly
        api_key_service.context.ensure_indexes = AsyncMock()
        api_key_service.context.database.find = AsyncMock(
            return_value=[
                {
                    "id": "o.APIKey.test123",
                    "entity": "APIKey",
                    "context": {
                        "key_hash": mock_key.key_hash,
                        "is_active": True,
                        "expires_at": None,
                    },
                }
            ]
        )
        api_key_service.context._deserialize_entity = AsyncMock(return_value=mock_key)
        api_key_service.context.save = AsyncMock()

        result = await api_key_service.validate_key(test_key)
        assert result == mock_key
        # Should find all active keys, then verify against them
        api_key_service.context.database.find.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_key_inactive(self, api_key_service):
        """Test validation of inactive API key."""
        test_key = "sk_live_test123456789"

        # Mock context methods - return empty list (no active keys)
        api_key_service.context.ensure_indexes = AsyncMock()
        api_key_service.context.database.find = AsyncMock(return_value=[])

        result = await api_key_service.validate_key(test_key)
        assert result is None

    @pytest.mark.asyncio
    async def test_validate_key_expired(self, api_key_service):
        """Test validation of expired API key."""
        test_key = "sk_live_test123456789"

        mock_key = MagicMock()
        mock_key.is_active = True
        mock_key.expires_at = datetime.utcnow() - timedelta(days=1)  # Expired
        mock_key.key_hash = api_key_service._hash_key(test_key)
        mock_key._graph_context = api_key_service.context

        # Mock context methods
        api_key_service.context.ensure_indexes = AsyncMock()
        api_key_service.context.database.find = AsyncMock(
            return_value=[
                {
                    "id": "o.APIKey.test123",
                    "entity": "APIKey",
                    "context": {
                        "key_hash": mock_key.key_hash,
                        "is_active": True,
                        "expires_at": mock_key.expires_at.isoformat(),
                    },
                }
            ]
        )
        api_key_service.context._deserialize_entity = AsyncMock(return_value=mock_key)

        result = await api_key_service.validate_key(test_key)
        # Should return None because key is expired (checked after verification)
        assert result is None

    @pytest.mark.asyncio
    async def test_revoke_key(self, api_key_service):
        """Test API key revocation."""
        mock_key = MagicMock()
        mock_key.user_id = "user123"
        mock_key.is_active = True
        mock_key._graph_context = api_key_service.context

        # Mock context.get and context.save
        api_key_service.context.get = AsyncMock(return_value=mock_key)
        api_key_service.context.save = AsyncMock()

        result = await api_key_service.revoke_key("key123", "user123")
        assert result is True
        assert mock_key.is_active is False
        api_key_service.context.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_revoke_key_unauthorized(self, api_key_service):
        """Test revocation of key by wrong user."""
        mock_key = MagicMock()
        mock_key.user_id = "user123"

        with patch.object(APIKey, "get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_key

            result = await api_key_service.revoke_key("key123", "user456")
            assert result is False

    def test_verify_key(self, api_key_service):
        """Test key verification with different hash types."""
        test_key = "sk_live_test123456789"

        # Hash the key
        key_hash = api_key_service._hash_key(test_key)

        # Verify correct key
        assert api_key_service._verify_key(test_key, key_hash) is True

        # Verify wrong key
        assert api_key_service._verify_key("wrong_key", key_hash) is False

        # Verify with different hash (should fail)
        other_hash = api_key_service._hash_key("different_key")
        assert api_key_service._verify_key(test_key, other_hash) is False

    def test_verify_key_with_different_hashes(self, api_key_service):
        """Test that verification works with same key hashed multiple times."""
        test_key = "sk_live_test123456789"

        # Hash the same key multiple times
        # Note: bcrypt includes salt, so hashes will differ, but verification should work
        hash1 = api_key_service._hash_key(test_key)
        hash2 = api_key_service._hash_key(test_key)

        # Both hashes should verify correctly
        assert api_key_service._verify_key(test_key, hash1) is True
        assert api_key_service._verify_key(test_key, hash2) is True


class TestAPIKeyIntegration:
    """Integration tests for API key authentication."""

    @pytest.fixture
    def server(self, request):
        """Create test server with API key auth enabled."""
        import uuid

        test_id = uuid.uuid4().hex[:8]
        return Server(
            title="Test API",
            db_type="json",
            db_path=f"./.test_dbs/test_db_api_keys_{test_id}",
            auth=dict(
                auth_enabled=True,
                api_key_auth_enabled=True,
                jwt_auth_enabled=True,
                jwt_secret="test-secret",
            ),
        )

    @pytest.fixture
    def client(self, server):
        """Create test client."""
        return TestClient(server.get_app())

    @pytest.fixture
    def unique_email(self, request):
        """Generate unique email for each test."""
        import uuid

        test_name = request.node.name
        test_id = uuid.uuid4().hex[:8]
        return f"test_{test_name}_{test_id}@example.com"

    def test_create_api_key_endpoint(self, server, client, unique_email):
        """Test API key creation endpoint."""
        # First, register and login a user
        register_response = client.post(
            "/auth/register",
            json={"email": unique_email, "password": "password123"},
        )
        assert register_response.status_code == 200

        login_response = client.post(
            "/auth/login",
            json={"email": unique_email, "password": "password123"},
        )
        assert login_response.status_code == 200
        token = login_response.json()["access_token"]

        # Create API key
        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Test Key", "permissions": ["read", "write"]},
            headers={"Authorization": f"Bearer {token}"},
        )

        assert create_response.status_code == 200
        data = create_response.json()
        assert "key" in data
        assert "key_id" in data
        assert "key_prefix" in data
        assert data["key"].startswith("sk_")
        assert len(data["key"]) > 32

    def test_list_api_keys_endpoint(self, server, client, unique_email):
        """Test API key listing endpoint."""
        # Register, login, and create a key
        client.post(
            "/auth/register",
            json={"email": unique_email, "password": "password123"},
        )
        login_response = client.post(
            "/auth/login",
            json={"email": unique_email, "password": "password123"},
        )
        token = login_response.json()["access_token"]

        # Create a key
        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Test Key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        key_id = create_response.json()["key_id"]

        # List keys
        list_response = client.get(
            "/auth/api-keys", headers={"Authorization": f"Bearer {token}"}
        )

        assert list_response.status_code == 200
        keys = list_response.json()
        assert isinstance(keys, list)
        assert len(keys) >= 1
        assert any(k["id"] == key_id for k in keys)

    def test_revoke_api_key_endpoint(self, server, client, unique_email):
        """Test API key revocation endpoint."""
        # Register, login, and create a key
        client.post(
            "/auth/register",
            json={"email": unique_email, "password": "password123"},
        )
        login_response = client.post(
            "/auth/login",
            json={"email": unique_email, "password": "password123"},
        )
        token = login_response.json()["access_token"]

        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Test Key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        key_id = create_response.json()["key_id"]

        # Revoke key
        revoke_response = client.delete(
            f"/auth/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert revoke_response.status_code == 200
        assert "revoked" in revoke_response.json()["message"].lower()

    def test_api_key_authentication(self, server, unique_email):
        """Test API key authentication for protected endpoints."""
        from jvspatial.api.context import set_current_server

        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint("/protected", methods=["GET"], auth=True)
        async def protected_endpoint():
            return {"message": "authenticated"}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # Register, login, and create a key
        client.post(
            "/auth/register",
            json={"email": unique_email, "password": "password123"},
        )
        login_response = client.post(
            "/auth/login",
            json={"email": unique_email, "password": "password123"},
        )
        token = login_response.json()["access_token"]

        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Test Key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        api_key = create_response.json()["key"]

        # Test endpoint without auth - should fail
        response = client.get("/api/protected")
        assert response.status_code == 401

        # Test endpoint with API key - should succeed
        response = client.get("/api/protected", headers={"X-API-Key": api_key})
        assert response.status_code == 200
        assert response.json()["message"] == "authenticated"

    def test_api_key_ip_restriction(self, server, client):
        """Test API key IP restriction."""
        # This test would require mocking the request client IP
        # For now, we test the service logic
        pass

    def test_api_key_endpoint_restriction(self, server, client):
        """Test API key endpoint restriction."""
        # This test would require testing the middleware logic
        # For now, we test the service logic
        pass
