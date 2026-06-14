"""Tests for rate limiting middleware and functionality."""

import time
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from jvspatial.api import endpoint
from jvspatial.api.middleware.rate_limit import RateLimitConfig, RateLimitMiddleware
from jvspatial.api.server import Server


@pytest.fixture
def test_app():
    """Create a test FastAPI app."""
    app = FastAPI()
    return app


@pytest.fixture
def rate_limit_config():
    """Create rate limit configuration."""
    return {
        "/api/test": RateLimitConfig(requests=5, window=60),
        "/api/expensive": RateLimitConfig(requests=2, window=30),
    }


@pytest.fixture
def rate_limit_middleware(test_app, rate_limit_config):
    """Create rate limit middleware instance."""
    return RateLimitMiddleware(
        test_app, config=rate_limit_config, default_limit=10, default_window=60
    )


class TestRateLimitMiddleware:
    """Test rate limiting middleware functionality."""

    def test_rate_limit_config_creation(self):
        """Test RateLimitConfig creation."""
        config = RateLimitConfig(requests=10, window=60)
        assert config.requests == 10
        assert config.window == 60
        assert config.identifier is None

    def test_client_identifier_from_ip(self, rate_limit_middleware):
        """Test client identifier generation from IP."""
        request = MagicMock(spec=Request)
        request.client.host = "192.168.1.1"
        request.headers = {"user-agent": "test-agent"}
        request.state = MagicMock()
        request.state.user = None

        identifier = rate_limit_middleware._get_client_identifier(request)
        assert identifier is not None
        assert len(identifier) > 0

    def test_client_identifier_ignores_user_agent(self, rate_limit_middleware):
        """Same IP + different User-Agent -> SAME bucket (no UA-rotation evasion).

        The User-Agent header is attacker-controlled; folding it into the key
        would let an unauthenticated client mint a fresh bucket per request and
        evade the per-IP cap. The identifier must depend on IP only.
        """

        def _req(user_agent: str) -> Request:
            request = MagicMock(spec=Request)
            request.client.host = "192.168.1.1"
            request.headers = {"user-agent": user_agent}
            request.state = MagicMock()
            request.state.user = None
            return request

        id_a = rate_limit_middleware._get_client_identifier(_req("agent-one"))
        id_b = rate_limit_middleware._get_client_identifier(_req("totally-different"))
        id_c = rate_limit_middleware._get_client_identifier(_req(""))

        # Identical IP, three different UAs -> one and the same bucket key.
        assert id_a == id_b == id_c

        # A different IP must still produce a different bucket.
        other = MagicMock(spec=Request)
        other.client.host = "10.0.0.9"
        other.headers = {"user-agent": "agent-one"}
        other.state = MagicMock()
        other.state.user = None
        assert rate_limit_middleware._get_client_identifier(other) != id_a

    def test_client_identifier_from_user(self, rate_limit_middleware):
        """Test client identifier generation from authenticated user."""
        request = MagicMock(spec=Request)
        request.client.host = "192.168.1.1"
        request.headers = {}
        request.state = MagicMock()
        request.state.user = MagicMock()
        request.state.user.id = "user123"

        identifier = rate_limit_middleware._get_client_identifier(request)
        assert identifier.startswith("user:")
        assert "user123" in identifier

    def test_path_matching_exact(self, rate_limit_middleware):
        """Test exact path matching."""
        assert rate_limit_middleware._match_endpoint("/api/test") == "/api/test"
        assert (
            rate_limit_middleware._match_endpoint("/api/expensive") == "/api/expensive"
        )
        assert rate_limit_middleware._match_endpoint("/api/unknown") is None

    def test_path_matching_with_params(self, rate_limit_middleware):
        """Test path matching with parameters."""
        # Add a path with parameters to config
        rate_limit_middleware._limits["/api/users/{user_id}"] = RateLimitConfig(
            requests=10, window=60
        )

        assert (
            rate_limit_middleware._match_endpoint("/api/users/123")
            == "/api/users/{user_id}"
        )
        assert (
            rate_limit_middleware._match_endpoint("/api/users/abc")
            == "/api/users/{user_id}"
        )

    @pytest.mark.asyncio
    async def test_rate_limit_enforcement(self, rate_limit_middleware):
        """Test rate limit enforcement."""
        client_key = "test_client"
        endpoint_key = "/api/test"
        limit = RateLimitConfig(requests=3, window=60)

        # First 3 requests should pass
        assert not await rate_limit_middleware._is_rate_limited(
            client_key, endpoint_key, limit
        )
        assert not await rate_limit_middleware._is_rate_limited(
            client_key, endpoint_key, limit
        )
        assert not await rate_limit_middleware._is_rate_limited(
            client_key, endpoint_key, limit
        )

        # 4th request should be rate limited
        assert await rate_limit_middleware._is_rate_limited(
            client_key, endpoint_key, limit
        )

    @pytest.mark.asyncio
    async def test_rate_limit_window_expiration(self, rate_limit_middleware):
        """Test rate limit window expiration."""
        client_key = "test_client"
        endpoint_key = "/api/test"
        limit = RateLimitConfig(requests=2, window=1)  # 1 second window

        # Make 2 requests
        assert not await rate_limit_middleware._is_rate_limited(
            client_key, endpoint_key, limit
        )
        assert not await rate_limit_middleware._is_rate_limited(
            client_key, endpoint_key, limit
        )

        # 3rd should be limited
        assert await rate_limit_middleware._is_rate_limited(
            client_key, endpoint_key, limit
        )

        # Wait for window to expire
        time.sleep(1.1)

        # Should be able to make requests again
        assert not await rate_limit_middleware._is_rate_limited(
            client_key, endpoint_key, limit
        )

    def test_rate_limit_response(self, rate_limit_middleware):
        """Test rate limit error response."""
        limit = RateLimitConfig(requests=10, window=60)
        response = rate_limit_middleware._rate_limit_response(limit)

        assert response.status_code == 429
        content = response.body.decode()
        assert "rate_limit_exceeded" in content
        assert "10" in content
        assert "60" in content


class TestRateLimitingIntegration:
    """Integration tests for rate limiting with server."""

    @pytest.fixture
    def server(self, request):
        """Create test server with rate limiting enabled."""
        import uuid

        test_id = uuid.uuid4().hex[:8]
        return Server(
            title="Test API",
            db_type="json",
            db_path=f"./.test_dbs/test_db_rate_limit_{test_id}",
            rate_limit=dict(
                rate_limit_enabled=True,
                rate_limit_default_requests=5,
                rate_limit_default_window=60,
            ),
            auth=dict(auth_enabled=False),
        )

    @pytest.fixture
    def client(self, server):
        """Create test client."""
        return TestClient(server.get_app())

    def test_endpoint_with_rate_limit(self, server):
        """Test endpoint with rate limit configuration."""
        from jvspatial.api.context import set_current_server

        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint("/limited", methods=["GET"], rate_limit={"requests": 3, "window": 60})
        async def limited_endpoint():
            return {"message": "success"}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # First 3 requests should succeed
        for _ in range(3):
            response = client.get("/api/limited")
            assert response.status_code == 200

        # 4th request should be rate limited
        response = client.get("/api/limited")
        assert response.status_code == 429
        assert "rate_limit_exceeded" in response.json()["error_code"]

    def test_default_rate_limit(self, server):
        """Test default rate limiting when no endpoint-specific limit is set."""
        from jvspatial.api.context import set_current_server

        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint("/default", methods=["GET"])
        async def default_endpoint():
            return {"message": "success"}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # Make requests up to default limit (5)
        for _ in range(5):
            response = client.get("/api/default")
            assert response.status_code == 200

        # 6th request should be rate limited
        response = client.get("/api/default")
        assert response.status_code == 429

    def test_rate_limit_shared_per_ip_regardless_of_user_agent(self, server):
        """Same IP shares one bucket even when the User-Agent rotates.

        The unauthenticated bucket key is the source IP ONLY — a client cannot
        rotate the User-Agent header to mint fresh buckets and evade the cap.
        Both TestClients connect from the same loopback IP, so they draw down a
        single shared counter.
        """
        from jvspatial.api.context import set_current_server

        # Set server context so endpoints can be registered
        set_current_server(server)

        @endpoint(
            "/per-client", methods=["GET"], rate_limit={"requests": 2, "window": 60}
        )
        async def per_client_endpoint():
            return {"message": "success"}

        # Force app rebuild to include the new endpoint, then create clients
        server.app = None  # Force recreation
        client1 = TestClient(server.get_app())
        client2 = TestClient(server.get_app())

        # Two requests under user-agent "client1" exhaust the cap of 2.
        assert (
            client1.get(
                "/api/per-client", headers={"user-agent": "client1"}
            ).status_code
            == 200
        )
        assert (
            client1.get(
                "/api/per-client", headers={"user-agent": "client1"}
            ).status_code
            == 200
        )

        # A DIFFERENT user-agent from the same IP is NOT a fresh bucket: it is
        # already over the cap and gets 429 (UA-rotation evasion is closed).
        assert (
            client2.get(
                "/api/per-client", headers={"user-agent": "client2"}
            ).status_code
            == 429
        )
        # The original user-agent is likewise still limited.
        assert (
            client1.get(
                "/api/per-client", headers={"user-agent": "client1"}
            ).status_code
            == 429
        )

    def test_rate_limit_options_bypass(self, server):
        """Test that OPTIONS requests bypass rate limiting."""
        from jvspatial.api.context import set_current_server

        # Set server context so endpoints can be registered
        set_current_server(server)

        # Register GET with rate limiting
        @endpoint("/cors", methods=["GET"], rate_limit={"requests": 1, "window": 60})
        async def cors_endpoint():
            return {"message": "success"}

        # Register OPTIONS separately with unique operation_id to avoid duplicate warning
        # Rate limiter skips OPTIONS requests automatically
        @endpoint("/cors", methods=["OPTIONS"], operation_id="cors_options_endpoint")
        async def cors_options_endpoint():
            return {"message": "success"}

        # Force app rebuild to include the new endpoint, then create client
        server.app = None  # Force recreation
        client = TestClient(server.get_app())

        # Make a GET request (uses up the limit)
        response = client.get("/api/cors")
        assert response.status_code == 200

        # OPTIONS should still work (bypasses rate limit)
        response = client.options("/api/cors")
        assert response.status_code in [200, 204]  # OPTIONS can return either

        # Another GET should be rate limited
        response = client.get("/api/cors")
        assert response.status_code == 429
