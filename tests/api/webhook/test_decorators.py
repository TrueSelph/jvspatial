"""
Test suite for webhook decorators.

Tests the new unified decorator API for webhook endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest

from jvspatial.api.integrations.webhooks.decorators import webhook_endpoint
from jvspatial.api.server import Server
from jvspatial.core.entities import Walker


class TestWebhookEndpointDecorator:
    """Test the @webhook_endpoint decorator."""

    def setup_method(self):
        """Set up test mocks."""
        self.mock_server = MagicMock(spec=Server)
        self.mock_server._endpoint_registry = MagicMock()
        self.mock_server.endpoint_router = MagicMock()
        self.mock_server.endpoint_router.router = MagicMock()
        self.mock_server._logger = MagicMock()
        self.mock_server._is_running = False
        self.test_user = MagicMock(id="user_123")

    async def test_webhook_endpoint_basic(self):
        """Test basic @webhook_endpoint decorator application."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @webhook_endpoint("/webhook/basic")
        async def basic_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        # Verify endpoint config is set correctly
        assert hasattr(basic_webhook, "_jvspatial_endpoint_config")
        config = basic_webhook._jvspatial_endpoint_config
        assert config["path"] == "/webhook/basic"
        assert config["methods"] == ["GET"]
        assert config["auth_required"] is False
        assert config["permissions"] == []
        assert config["roles"] == []
        assert config["webhook"] is False

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_custom_methods(self):
        """Test @webhook_endpoint with custom HTTP methods."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @webhook_endpoint("/webhook/custom", methods=["POST", "PUT"])
        async def custom_methods_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = custom_methods_webhook._jvspatial_endpoint_config
        assert config["methods"] == ["POST", "PUT"]
        assert config["path"] == "/webhook/custom"

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_hmac_secret(self):
        """Test @webhook_endpoint with HMAC secret."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @webhook_endpoint(
            "/webhook/hmac", hmac_secret="secret123"  # pragma: allowlist secret
        )
        async def hmac_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = hmac_webhook._jvspatial_endpoint_config
        # webhook_endpoint is just an alias for endpoint, so webhook-specific params are ignored
        assert config["webhook"] is False

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_auth_requirements(self):
        """Test @webhook_endpoint with authentication requirements."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @webhook_endpoint(
            "/webhook/auth",
            permissions=["webhook:receive"],
            roles=["webhook_handler"],
            auth_required=True,
        )
        async def auth_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = auth_webhook._jvspatial_endpoint_config
        assert config["auth_required"] is True
        assert config["permissions"] == ["webhook:receive"]
        assert config["roles"] == ["webhook_handler"]

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_custom_webhook_config(self):
        """Test @webhook_endpoint with custom webhook configuration."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @webhook_endpoint(
            "/webhook/custom-config",
            hmac_secret="custom_secret",  # pragma: allowlist secret
        )
        async def custom_config_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = custom_config_webhook._jvspatial_endpoint_config
        webhook_config = config["webhook"]
        # webhook_endpoint is just an alias for endpoint, so webhook-specific params are ignored
        assert webhook_config is False

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_on_walker_class(self):
        """Test @webhook_endpoint decorator on Walker class."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @webhook_endpoint("/webhook/walker")
        class WebhookWalker(Walker):
            async def process_webhook(self, payload: dict, endpoint):
                return endpoint.response(content={"status": "processed"})

        # Verify endpoint config is set correctly
        assert hasattr(WebhookWalker, "_jvspatial_endpoint_config")
        config = WebhookWalker._jvspatial_endpoint_config
        assert config["path"] == "/webhook/walker"
        assert config["methods"] == ["GET"]
        assert config["webhook"] is False

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_no_server(self):
        """Test webhook endpoint when no server is available."""
        from jvspatial.api.context import set_current_server

        # Ensure no server is set
        set_current_server(None)

        @webhook_endpoint("/webhook/no-server")
        async def no_server_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        # Should still set config even without server
        assert hasattr(no_server_webhook, "_jvspatial_endpoint_config")
        config = no_server_webhook._jvspatial_endpoint_config
        assert config["path"] == "/webhook/no-server"
        assert config["webhook"] is not None

    async def test_webhook_endpoint_default_values(self):
        """Test webhook endpoint with default configuration values."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @webhook_endpoint("/webhook/defaults")
        async def default_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = default_webhook._jvspatial_endpoint_config
        webhook_config = config["webhook"]

        # Check default values - webhook_endpoint is just an alias for endpoint
        assert webhook_config is False

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_openapi_extra(self):
        """Test webhook endpoint with OpenAPI extra configuration."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @webhook_endpoint(
            "/webhook/openapi",
            openapi_extra={"tags": ["webhooks"], "summary": "Test webhook"},
        )
        async def openapi_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = openapi_webhook._jvspatial_endpoint_config
        assert config["openapi_extra"] == {
            "tags": ["webhooks"],
            "summary": "Test webhook",
        }

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_edge_cases(self):
        """Test webhook endpoint edge cases."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        # Test with empty permissions and roles
        @webhook_endpoint("/webhook/empty", permissions=[], roles=[])
        async def empty_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = empty_webhook._jvspatial_endpoint_config
        assert config["permissions"] == []
        assert config["roles"] == []

        # Test with just hmac_secret
        @webhook_endpoint(
            "/webhook/hmac-only", hmac_secret="test_secret"  # pragma: allowlist secret
        )
        async def hmac_only_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = hmac_only_webhook._jvspatial_endpoint_config
        # webhook_endpoint is just an alias for endpoint, so webhook-specific params are ignored
        assert config["webhook"] is False

        # Clean up
        set_current_server(None)
