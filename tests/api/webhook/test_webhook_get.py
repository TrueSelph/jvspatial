"""Tests for GET webhook support (verification flows, etc.)."""

import uuid

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from jvspatial.api import endpoint
from jvspatial.api.context import set_current_server
from jvspatial.api.server import Server


class TestWebhookGET:
    """Test GET webhook request handling."""

    @pytest.fixture
    def server(self):
        """Create test server with webhook support."""
        test_id = uuid.uuid4().hex[:8]
        return Server(
            title="Test API",
            db_type="json",
            db_path=f"./.test_dbs/test_db_webhook_get_{test_id}",
            auth=dict(auth_enabled=False),
            webhook=dict(webhook_https_required=False),
        )

    @pytest.fixture
    def client(self, server):
        """Create test client."""
        return TestClient(server.get_app())

    def test_get_webhook_recognized_and_processed(self, server, client):
        """Test GET webhook request is recognized and processed (light path)."""
        set_current_server(server)

        @endpoint("/webhook/verify", methods=["GET"], webhook=True)
        async def verify_webhook(request: Request):
            payload = getattr(request.state, "parsed_payload", None)
            assert payload is not None
            return {"status": "verified", "params": payload}

        server.app = None
        client = TestClient(server.get_app())

        response = client.get(
            "/api/webhook/verify?hub.mode=subscribe&hub.challenge=123"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "verified"
        assert data["params"]["hub.mode"] == "subscribe"
        assert data["params"]["hub.challenge"] == "123"

    def test_get_webhook_parsed_payload_from_query_params(self, server, client):
        """Test GET webhook populates request.state.parsed_payload from query params."""
        set_current_server(server)

        @endpoint("/webhook/params", methods=["GET"], webhook=True)
        async def params_webhook(request: Request):
            payload = getattr(request.state, "parsed_payload", {})
            return {"received": dict(payload)}

        server.app = None
        client = TestClient(server.get_app())

        response = client.get("/api/webhook/params?a=1&b=2&hub.verify_token=secret")

        assert response.status_code == 200
        data = response.json()
        assert data["received"]["a"] == "1"
        assert data["received"]["b"] == "2"
        assert data["received"]["hub.verify_token"] == "secret"

    def test_get_webhook_meta_verification_flow(self, server, client):
        """Test GET webhook with hub.mode, hub.challenge, hub.verify_token (Meta/WhatsApp style)."""
        set_current_server(server)

        @endpoint("/webhook/meta", methods=["GET"], webhook=True)
        async def meta_verify(request: Request):
            payload = getattr(request.state, "parsed_payload", {})
            if (
                payload.get("hub.mode") == "subscribe"
                and payload.get("hub.verify_token") == "my_token"
            ):
                return int(payload.get("hub.challenge", 0))
            raise ValueError("Invalid verification")

        server.app = None
        client = TestClient(server.get_app())

        response = client.get(
            "/api/webhook/meta?hub.mode=subscribe&hub.challenge=456&hub.verify_token=my_token"
        )

        assert response.status_code == 200
        assert response.json() == 456

    def test_post_webhook_behavior_unchanged(self, server, client):
        """Test POST webhook behavior unchanged (regression)."""
        set_current_server(server)

        @endpoint("/webhook/post", methods=["POST"], webhook=True)
        async def post_webhook(request: Request):
            payload = getattr(request.state, "parsed_payload", None)
            return {"status": "received", "body": payload}

        server.app = None
        client = TestClient(server.get_app())

        response = client.post(
            "/api/webhook/post",
            json={"event": "test", "data": {"id": 1}},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "received"
        assert data["body"]["event"] == "test"
        assert data["body"]["data"]["id"] == 1
