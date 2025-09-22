"""
Test suite for webhook endpoint decorators.

This module tests the @webhook_endpoint decorator, ensuring it properly
configures authentication metadata, handles path patterns with route and
auth_token parameters, and registers endpoints with the server when available.
"""

from typing import List
from unittest.mock import MagicMock, patch

import pytest

from jvspatial.api.auth.decorators import webhook_endpoint
from jvspatial.api.server import Server
from jvspatial.core.entities import Walker


class TestWebhookEndpointDecorator:
    """Test the @webhook_endpoint decorator."""

    def setup_method(self):
        """Set up test mocks."""
        self.mock_server = MagicMock(spec=Server)
        self.mock_server._custom_routes = MagicMock()
        self.test_user = MagicMock(id="user_123")

    def test_webhook_endpoint_basic(self):
        """Test basic @webhook_endpoint decorator application."""

        @webhook_endpoint("/webhook/basic")
        async def basic_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        # Verify metadata is set correctly
        assert hasattr(basic_webhook, "_webhook_required")
        assert basic_webhook._webhook_required is True
        assert basic_webhook._auth_required is False  # No permissions/roles specified
        assert basic_webhook._required_permissions == []
        assert basic_webhook._required_roles == []
        assert basic_webhook._endpoint_path == "/webhook/basic"
        assert basic_webhook._endpoint_methods == ["POST"]

        # Verify webhook-specific metadata
        assert basic_webhook._hmac_secret is None
        assert basic_webhook._idempotency_key_field == "X-Idempotency-Key"
        assert basic_webhook._idempotency_ttl_hours == 24
        assert basic_webhook._async_processing is False
        assert basic_webhook._path_key_auth is False

        # Verify route config for registration
        assert hasattr(basic_webhook, "_route_config")
        route_config = basic_webhook._route_config
        assert route_config["path"] == "/webhook/basic"
        assert route_config["methods"] == ["POST"]

    def test_webhook_endpoint_with_custom_methods(self):
        """Test @webhook_endpoint with custom HTTP methods."""

        @webhook_endpoint("/webhook/custom", methods=["POST", "PUT"])
        async def custom_methods_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        assert custom_methods_webhook._endpoint_methods == ["POST", "PUT"]
        assert custom_methods_webhook._route_config["methods"] == ["POST", "PUT"]

    def test_webhook_endpoint_with_permissions(self):
        """Test @webhook_endpoint with required permissions."""

        @webhook_endpoint(
            "/webhook/secure",
            permissions=["process_webhooks", "read_events"],
            hmac_secret="test-secret",  # pragma: allowlist secret
        )
        async def secure_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "secure"})

        assert secure_webhook._required_permissions == [
            "process_webhooks",
            "read_events",
        ]
        assert (
            secure_webhook._auth_required is True
        )  # Should be True when permissions specified
        assert secure_webhook._hmac_secret == "test-secret"  # pragma: allowlist secret

    def test_webhook_endpoint_path_based_auth(self):
        """Test @webhook_endpoint with path-based authentication."""

        @webhook_endpoint(
            "/webhook/stripe/{key}",
            path_key_auth=True,
            hmac_secret="stripe-secret",  # pragma: allowlist secret
        )
        async def stripe_webhook(raw_body: bytes, content_type: str, endpoint):
            return endpoint.response(content={"status": "received"})

        # Verify path-based auth metadata
        assert stripe_webhook._path_key_auth is True
        assert (
            stripe_webhook._hmac_secret == "stripe-secret"  # pragma: allowlist secret
        )
        assert stripe_webhook._endpoint_path == "/webhook/stripe/{key}"

    def test_webhook_endpoint_path_key_validation(self):
        """Test that path_key_auth requires {key} parameter."""
        with pytest.raises(ValueError, match=r"must include \{key\} parameter"):

            @webhook_endpoint("/webhook/invalid", path_key_auth=True)
            async def invalid_webhook(payload: dict, endpoint):
                return endpoint.response()

    def test_webhook_endpoint_with_roles(self):
        """Test @webhook_endpoint with required roles."""

        @webhook_endpoint(
            "/webhook/admin/{route}/{auth_token}", roles=["admin", "webhook_manager"]
        )
        async def admin_webhook(request):
            return {"status": "admin"}

        assert admin_webhook._required_roles == ["admin", "webhook_manager"]

    def test_webhook_endpoint_server_registration(self):
        """Test server registration when server is available."""
        with patch(
            "jvspatial.api.auth.decorators.get_default_server",
            return_value=self.mock_server,
        ):

            @webhook_endpoint("/webhook/register/{auth_token}")
            async def register_webhook(request):
                return {"status": "registered"}

            # Verify server registration was attempted
            self.mock_server._custom_routes.append.assert_called_once()
            # Note: Actual registration happens via _custom_routes in server startup

    def test_webhook_endpoint_no_server_deferred(self):
        """Test decorator works without server (deferred registration)."""
        with patch(
            "jvspatial.api.auth.decorators.get_default_server", return_value=None
        ):

            @webhook_endpoint("/webhook/deferred/{auth_token}")
            async def deferred_webhook(request):
                return {"status": "deferred"}

            # Should not raise error, metadata still set
            assert (
                deferred_webhook._auth_required is False
            )  # No permissions/roles provided
            assert deferred_webhook._endpoint_path == "/webhook/deferred/{auth_token}"

    def test_webhook_endpoint_path_pattern(self):
        """Test that the decorator uses the correct path pattern with route and auth_token."""

        @webhook_endpoint("/webhook/{route}/{auth_token}")
        async def dynamic_route_webhook(request):
            return {"status": "dynamic"}

        # The path should include both route and auth_token parameters
        assert dynamic_route_webhook._endpoint_path == "/webhook/{route}/{auth_token}"

    def test_webhook_endpoint_custom_server(self):
        """Test @webhook_endpoint with explicit server parameter."""
        custom_server = MagicMock(spec=Server)
        custom_server._custom_routes = []

        @webhook_endpoint("/webhook/custom_server/{auth_token}", server=custom_server)
        async def custom_server_webhook(request):
            return {"status": "custom"}

        # Should use custom server for registration
        assert len(custom_server._custom_routes) > 0
        assert any(
            route["path"] == "/webhook/custom_server/{auth_token}"
            for route in custom_server._custom_routes
        )

    @pytest.mark.asyncio
    async def test_webhook_endpoint_function_execution(self):
        """Test that decorated webhook functions execute normally."""
        mock_request = MagicMock()
        mock_request.state.current_user = self.test_user  # Mock auth already done

        @webhook_endpoint("/webhook/execute/{auth_token}")
        async def execute_webhook(request):
            user = request.state.current_user
            return {"user_id": user.id, "status": "executed"}

        # Execute the function
        result = await execute_webhook(mock_request)
        assert result["user_id"] == "user_123"
        assert result["status"] == "executed"

    def test_webhook_endpoint_metadata_extraction(self):
        """Test extraction of auth metadata from decorated endpoint."""
        from jvspatial.api.auth.decorators import AuthAwareEndpointProcessor

        @webhook_endpoint(
            "/webhook/metadata/{route}/{auth_token}",
            permissions=["webhook_access"],
            roles=["operator"],
        )
        async def metadata_webhook(request):
            return {"status": "metadata"}

        # Extract requirements
        requirements = AuthAwareEndpointProcessor.extract_auth_requirements(
            metadata_webhook
        )

        assert requirements["auth_required"] is True
        assert requirements["required_permissions"] == ["webhook_access"]
        assert requirements["required_roles"] == ["operator"]
        assert requirements["endpoint_path"] == "/webhook/metadata/{route}/{auth_token}"

    def test_webhook_endpoint_no_auth_required_variant(self):
        """Test variant without authentication (no permissions/roles)."""

        # Test that webhook_endpoint works without permissions/roles (auth_required=False)
        @webhook_endpoint("/webhook/noauth/{auth_token}")
        async def noauth_webhook(request):
            return {"status": "no auth"}

        # Should have auth_required=False when no permissions/roles specified
        assert noauth_webhook._auth_required is False
        assert noauth_webhook._required_permissions == []
        assert noauth_webhook._required_roles == []

    def test_webhook_endpoint_walker_integration(self):
        """Test @webhook_endpoint with a walker class (if applicable)."""
        # Note: webhook_endpoint is for functions, not walkers, but test compatibility

        with pytest.raises(TypeError):
            # Should not work with classes (walker_endpoint would be used)
            @webhook_endpoint("/webhook/walker/{auth_token}")
            class WalkerWebhook(Walker):
                pass

        # Verify it's function-only
        assert True  # Decorator expects function, not class


# Note: Additional integration tests with full server setup would go in test_endpoints.py
