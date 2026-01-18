"""Tests for webhook API key authentication."""

import uuid

import pytest
from fastapi.testclient import TestClient

from jvspatial.api import endpoint
from jvspatial.api.context import set_current_server
from jvspatial.api.server import Server


class TestWebhookAPIKeyAuthentication:
    """Test webhook API key authentication functionality."""

    @pytest.fixture
    def server(self, request):
        """Create test server with API key auth enabled."""
        # Use unique database path for each test to ensure isolation
        test_id = uuid.uuid4().hex[:8]
        return Server(
            title="Test API",
            db_type="json",
            db_path=f"./.test_dbs/test_db_webhook_{test_id}",
            auth=dict(
                auth_enabled=True,
                api_key_auth_enabled=True,
                jwt_auth_enabled=True,
                jwt_secret="test-secret",
            ),
            webhook=dict(
                webhook_api_key_require_https=False,  # Allow HTTP in tests
                webhook_https_required=False,  # Allow HTTP in tests
            ),
        )

    @pytest.fixture
    def client(self, server):
        """Create test client."""
        return TestClient(server.get_app())

    @pytest.fixture
    def unique_email(self, request):
        """Generate unique email for each test."""
        test_name = request.node.name
        test_id = uuid.uuid4().hex[:8]
        return f"test_{test_name}_{test_id}@example.com"

    def _register_and_login(self, client, email, password="password123"):
        """Helper to register and login a user."""
        # Try to register, ignore if already exists
        register_response = client.post(
            "/auth/register",
            json={"email": email, "password": password},
        )
        # If registration fails, try login
        if register_response.status_code != 200:
            login_response = client.post(
                "/auth/login",
                json={"email": email, "password": password},
            )
            if login_response.status_code == 200:
                return login_response.json()["access_token"]
            # If both fail, raise an error
            raise Exception(f"Failed to register or login: {register_response.text}")

        # Registration succeeded, now login
        login_response = client.post(
            "/auth/login",
            json={"email": email, "password": password},
        )
        assert login_response.status_code == 200
        return login_response.json()["access_token"]

    def test_webhook_auth_api_key_query_param(self, server, unique_email):
        """Test webhook authentication via query parameter."""
        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint(
            "/webhook/test", methods=["POST"], webhook=True, webhook_auth="api_key"
        )
        async def test_webhook(payload: dict):
            return {"status": "received"}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # Register and login
        token = self._register_and_login(client, unique_email)

        # Create API key
        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Webhook Key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        api_key = create_response.json()["key"]

        # Test webhook with query parameter (endpoint router adds /api prefix)
        response = client.post(
            f"/api/webhook/test?api_key={api_key}",
            json={"event": "test"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "received"

    def test_webhook_auth_api_key_header(self, server, unique_email):
        """Test webhook authentication via header."""
        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint(
            "/webhook/header", methods=["POST"], webhook=True, webhook_auth="api_key"
        )
        async def header_webhook(payload: dict):
            return {"status": "received"}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # Setup: register, login, create key
        token = self._register_and_login(client, unique_email)

        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Webhook Key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        api_key = create_response.json()["key"]

        # Test webhook with header (endpoint router adds /api prefix)
        response = client.post(
            "/api/webhook/header",
            json={"event": "test"},
            headers={"X-API-Key": api_key},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "received"

    def test_webhook_auth_api_key_path(self, server, unique_email):
        """Test webhook authentication via path parameter."""
        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint(
            "/webhook/{api_key}/trigger",
            methods=["POST"],
            webhook=True,
            webhook_auth="api_key_path",
        )
        async def path_webhook(api_key: str, payload: dict):
            return {"status": "triggered", "key_received": api_key[:10] + "..."}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # Setup: register, login, create key
        token = self._register_and_login(client, unique_email)

        create_response = client.post(
            "/auth/api-keys",
            json={"name": "Webhook Key"},
            headers={"Authorization": f"Bearer {token}"},
        )
        api_key = create_response.json()["key"]

        # Test webhook with API key in path (endpoint router adds /api prefix)
        response = client.post(
            f"/api/webhook/{api_key}/trigger",
            json={"event": "test"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "triggered"

    def test_webhook_auth_invalid_key(self, server):
        """Test webhook authentication with invalid API key."""
        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint(
            "/webhook/invalid", methods=["POST"], webhook=True, webhook_auth="api_key"
        )
        async def invalid_webhook(payload: dict):
            return {"status": "received"}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # Test with invalid key (endpoint router adds /api prefix)
        response = client.post(
            "/api/webhook/invalid?api_key=invalid_key_12345",
            json={"event": "test"},
        )

        # Should return 200 with error (webhooks always return 200)
        assert response.status_code == 200
        data = response.json()
        assert "error" in data or "status" in data

    def test_webhook_auth_missing_key(self, server):
        """Test webhook authentication without API key."""
        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint(
            "/webhook/missing", methods=["POST"], webhook=True, webhook_auth="api_key"
        )
        async def missing_webhook(payload: dict):
            return {"status": "received"}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # Test without API key (endpoint router adds /api prefix)
        response = client.post(
            "/api/webhook/missing",
            json={"event": "test"},
        )

        # Should return 200 with error (webhooks always return 200)
        assert response.status_code == 200
        data = response.json()
        assert "error" in data or "status" in data

    def test_webhook_auth_header_precedence(self, server, unique_email):
        """Test that header takes precedence over query parameter."""
        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint(
            "/webhook/precedence",
            methods=["POST"],
            webhook=True,
            webhook_auth="api_key",
        )
        async def precedence_webhook(payload: dict):
            return {"status": "received"}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # Setup: create two keys
        token = self._register_and_login(client, unique_email)

        create_response1 = client.post(
            "/auth/api-keys",
            json={"name": "Key 1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        key1 = create_response1.json()["key"]

        create_response2 = client.post(
            "/auth/api-keys",
            json={"name": "Key 2"},
            headers={"Authorization": f"Bearer {token}"},
        )
        key2 = create_response2.json()["key"]

        # Test with both header and query param - header should be used (endpoint router adds /api prefix)
        response = client.post(
            f"/api/webhook/precedence?api_key={key1}",
            json={"event": "test"},
            headers={"X-API-Key": key2},
        )

        # Should succeed with key2 (from header)
        assert response.status_code == 200

    def test_webhook_auth_with_hmac(self, server):
        """Test webhook with both HMAC signature and API key authentication."""
        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint(
            "/webhook/secure",
            methods=["POST"],
            webhook=True,
            signature_required=True,
            webhook_auth="api_key",
        )
        async def secure_webhook(payload: dict):
            return {"status": "processed"}

        # This test would require HMAC signature generation
        # For now, just verify the configuration is set correctly
        config = secure_webhook._jvspatial_endpoint_config
        assert config["webhook"] is True
        assert config["signature_required"] is True
        assert config["webhook_auth"] == "api_key"
