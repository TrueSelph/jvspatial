"""Tests for forgot-password and reset-password endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient

from jvspatial.api.server import Server
from jvspatial.db.manager import DatabaseManager


@pytest.fixture(autouse=True)
def reset_database_manager():
    """Reset DatabaseManager singleton before each test for isolation."""
    DatabaseManager._instance = None
    yield
    DatabaseManager._instance = None


class TestForgotPasswordEndpoint:
    """Test forgot-password API endpoint."""

    @pytest.mark.asyncio
    async def test_forgot_password_same_response_existing_and_nonexisting(self):
        """Forgot-password returns same message for existing and non-existing email."""
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True, jwt_secret="test-secret-key"),
            db_type="json",
            db_path=f"./.test_dbs/test_db_forgot_{test_id}",
        )
        client = TestClient(server.get_app())

        # Non-existing email
        r1 = client.post(
            "/api/auth/forgot-password",
            json={"email": "nonexistent@example.com"},
        )
        assert r1.status_code == 200
        msg1 = r1.json()["message"]

        # Register a user
        email = f"test_{test_id}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "password123"},
        )

        # Existing email - same message (no enumeration)
        r2 = client.post(
            "/api/auth/forgot-password",
            json={"email": email},
        )
        assert r2.status_code == 200
        msg2 = r2.json()["message"]
        assert msg1 == msg2
        assert "If an account exists" in msg1

    @pytest.mark.asyncio
    async def test_forgot_password_callback_invoked(self):
        """Forgot-password invokes on_password_reset_requested with correct args."""
        test_id = uuid.uuid4().hex[:8]
        callback_args = []

        async def on_reset(email, token, reset_url):
            callback_args.append((email, token, reset_url))

        server = Server(
            title="Test API",
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-key",
                password_reset_base_url="https://app.example.com",
            ),
            db_type="json",
            db_path=f"./.test_dbs/test_db_callback_{test_id}",
            on_password_reset_requested=on_reset,
        )
        client = TestClient(server.get_app())

        email = f"test_{test_id}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "password123"},
        )

        client.post(
            "/api/auth/forgot-password",
            json={"email": email},
        )

        assert len(callback_args) == 1
        cb_email, cb_token, cb_url = callback_args[0]
        assert cb_email == email
        assert len(cb_token) > 20
        assert "https://app.example.com/reset-password?token=" in cb_url
        assert cb_token in cb_url

    @pytest.mark.asyncio
    async def test_forgot_password_inactive_user_no_callback(self):
        """Forgot-password does not send email to inactive users."""
        test_id = uuid.uuid4().hex[:8]
        callback_called = []

        def on_reset(email, token, reset_url):
            callback_called.append(True)

        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True, jwt_secret="test-secret-key"),
            db_type="json",
            db_path=f"./.test_dbs/test_db_inactive_{test_id}",
            on_password_reset_requested=on_reset,
        )
        client = TestClient(server.get_app())

        email = f"test_{test_id}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "password123"},
        )

        # Deactivate user via auth service
        auth_service = server._auth_service
        user = await auth_service._find_user_by_email(email)
        user.is_active = False
        user._graph_context = auth_service.context
        await auth_service.context.save(user)

        # Request reset - should still return success but not call callback
        r = client.post(
            "/api/auth/forgot-password",
            json={"email": email},
        )
        assert r.status_code == 200
        assert len(callback_called) == 0

    @pytest.mark.asyncio
    async def test_forgot_password_disabled_returns_404(self):
        """Forgot-password when disabled returns 404."""
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-key",
                password_reset_enabled=False,
            ),
            db_type="json",
            db_path=f"./.test_dbs/test_db_forgot_disabled_{test_id}",
        )
        client = TestClient(server.get_app())

        r = client.post(
            "/api/auth/forgot-password",
            json={"email": "any@example.com"},
        )
        assert r.status_code == 404


class TestResetPasswordEndpoint:
    """Test reset-password API endpoint."""

    @pytest.mark.asyncio
    async def test_reset_password_success(self):
        """Test successful password reset via API."""
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True, jwt_secret="test-secret-key"),
            db_type="json",
            db_path=f"./.test_dbs/test_db_reset_{test_id}",
        )
        client = TestClient(server.get_app())

        email = f"test_{test_id}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "password123"},
        )

        # Request reset to get token via callback
        reset_token = [None]

        def capture_token(em, token, url):
            reset_token[0] = token

        server_with_cb = Server(
            title="Test API",
            auth=dict(auth_enabled=True, jwt_secret="test-secret-key"),
            db_type="json",
            db_path=f"./.test_dbs/test_db_reset_{test_id}",
            on_password_reset_requested=capture_token,
        )
        client2 = TestClient(server_with_cb.get_app())
        client2.post(
            "/api/auth/forgot-password",
            json={"email": email},
        )
        token = reset_token[0]
        assert token is not None

        # Reset password
        reset_response = client2.post(
            "/api/auth/reset-password",
            json={"token": token, "new_password": "newpass789"},
        )
        assert reset_response.status_code == 200
        assert reset_response.json()["message"] == "Password reset successfully"

        # New password works
        login_response = client2.post(
            "/api/auth/login",
            json={"email": email, "password": "newpass789"},
        )
        assert login_response.status_code == 200

        # Old password fails
        old_login = client2.post(
            "/api/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert old_login.status_code == 401

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(self):
        """Test reset-password with invalid token returns 400."""
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True, jwt_secret="test-secret-key"),
            db_type="json",
            db_path=f"./.test_dbs/test_db_reset_invalid_{test_id}",
        )
        client = TestClient(server.get_app())

        r = client.post(
            "/api/auth/reset-password",
            json={"token": "invalid-token-xyz", "new_password": "newpass789"},
        )
        assert r.status_code == 400
        body = r.json()
        msg = body.get("message", body.get("detail", ""))
        assert "Invalid or expired" in str(msg)

    @pytest.mark.asyncio
    async def test_reset_password_disabled_returns_404(self):
        """Reset-password when disabled returns 404."""
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-key",
                password_reset_enabled=False,
            ),
            db_type="json",
            db_path=f"./.test_dbs/test_db_reset_disabled_{test_id}",
        )
        client = TestClient(server.get_app())

        r = client.post(
            "/api/auth/reset-password",
            json={"token": "any-token", "new_password": "newpass789"},
        )
        assert r.status_code == 404
