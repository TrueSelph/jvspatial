"""Tests for change-password endpoint."""

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


class TestChangePasswordEndpoint:
    """Test change-password API endpoint."""

    @pytest.mark.asyncio
    async def test_change_password_success(self):
        """Test successful password change via API."""
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True, jwt_secret="test-secret-key"),
            db_type="json",
            db_path=f"./.test_dbs/test_db_change_{test_id}",
        )
        client = TestClient(server.get_app())

        email = f"test_{test_id}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "password123"},
        )
        login_response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert login_response.status_code == 200
        access_token = login_response.json()["access_token"]

        change_response = client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "current_password": "password123",
                "new_password": "newpass456",
            },
        )
        assert change_response.status_code == 200
        assert change_response.json()["message"] == "Password changed successfully"

        # Old password should fail
        old_login = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password123"},
        )
        assert old_login.status_code == 401

        # New password should work
        new_login = client.post(
            "/api/auth/login",
            json={"email": email, "password": "newpass456"},
        )
        assert new_login.status_code == 200

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(self):
        """Test change-password with wrong current password."""
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True, jwt_secret="test-secret-key"),
            db_type="json",
            db_path=f"./.test_dbs/test_db_wrong_{test_id}",
        )
        client = TestClient(server.get_app())

        email = f"test_{test_id}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "password123"},
        )
        login_response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password123"},
        )
        access_token = login_response.json()["access_token"]

        change_response = client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "current_password": "wrongpassword",
                "new_password": "newpass456",
            },
        )
        assert change_response.status_code == 400
        body = change_response.json()
        msg = body.get("message", body.get("detail", ""))
        assert "incorrect" in str(msg).lower()

    @pytest.mark.asyncio
    async def test_change_password_unauthenticated(self):
        """Test change-password without auth returns 403."""
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(auth_enabled=True, jwt_secret="test-secret-key"),
            db_type="json",
            db_path=f"./.test_dbs/test_db_unauth_{test_id}",
        )
        client = TestClient(server.get_app())

        change_response = client.post(
            "/api/auth/change-password",
            json={
                "current_password": "password123",
                "new_password": "newpass456",
            },
        )
        assert change_response.status_code == 403

    @pytest.mark.asyncio
    async def test_change_password_disabled_returns_404(self):
        """Test change-password when disabled returns 404."""
        test_id = uuid.uuid4().hex[:8]
        server = Server(
            title="Test API",
            auth=dict(
                auth_enabled=True,
                jwt_secret="test-secret-key",
                password_change_enabled=False,
            ),
            db_type="json",
            db_path=f"./.test_dbs/test_db_disabled_{test_id}",
        )
        client = TestClient(server.get_app())

        email = f"test_{test_id}@example.com"
        client.post(
            "/api/auth/register",
            json={"email": email, "password": "password123"},
        )
        login_response = client.post(
            "/api/auth/login",
            json={"email": email, "password": "password123"},
        )
        access_token = login_response.json()["access_token"]

        change_response = client.post(
            "/api/auth/change-password",
            headers={"Authorization": f"Bearer {access_token}"},
            json={
                "current_password": "password123",
                "new_password": "newpass456",
            },
        )
        assert change_response.status_code == 404
