"""
Test suite for webhook decorators.

Tests the new unified decorator API for webhook endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest

from jvspatial.api import endpoint
from jvspatial.api.server import Server
from jvspatial.core.entities import Walker


class TestWebhookEndpointDecorator:
    """Test the @endpoint decorator with webhook=True."""

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
        """Test basic @endpoint decorator with webhook=True."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint("/webhook/basic", webhook=True)
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
        assert config["webhook"] is True

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_custom_methods(self):
        """Test @endpoint with custom HTTP methods and webhook=True."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint("/webhook/custom", methods=["POST", "PUT"], webhook=True)
        async def custom_methods_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = custom_methods_webhook._jvspatial_endpoint_config
        assert config["methods"] == ["POST", "PUT"]
        assert config["path"] == "/webhook/custom"

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_hmac_secret(self):
        """Test @endpoint with HMAC secret and webhook=True."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint(
            "/webhook/hmac",
            webhook=True,
            hmac_secret="secret123",  # pragma: allowlist secret
        )
        async def hmac_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = hmac_webhook._jvspatial_endpoint_config
        assert config["webhook"] is True

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_auth_requirements(self):
        """Test @endpoint with authentication requirements and webhook=True."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint(
            "/webhook/auth",
            webhook=True,
            permissions=["webhook:receive"],
            roles=["webhook_handler"],
            auth=True,
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
        """Test @endpoint with custom webhook configuration."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint(
            "/webhook/custom-config",
            webhook=True,
            hmac_secret="custom_secret",  # pragma: allowlist secret
        )
        async def custom_config_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = custom_config_webhook._jvspatial_endpoint_config
        webhook_config = config["webhook"]
        assert webhook_config is True

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_on_walker_class(self):
        """Test @endpoint decorator on Walker class with webhook=True."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint("/webhook/walker", webhook=True)
        class WebhookWalker(Walker):
            async def process_webhook(self, payload: dict, endpoint):
                return endpoint.response(content={"status": "processed"})

        # Verify endpoint config is set correctly
        assert hasattr(WebhookWalker, "_jvspatial_endpoint_config")
        config = WebhookWalker._jvspatial_endpoint_config
        assert config["path"] == "/webhook/walker"
        assert config["methods"] == ["GET"]
        assert config["webhook"] is True

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_no_server(self):
        """Test webhook endpoint when no server is available."""
        from jvspatial.api.context import set_current_server

        # Ensure no server is set
        set_current_server(None)

        @endpoint("/webhook/no-server", webhook=True)
        async def no_server_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        # Should still set config even without server
        assert hasattr(no_server_webhook, "_jvspatial_endpoint_config")
        config = no_server_webhook._jvspatial_endpoint_config
        assert config["path"] == "/webhook/no-server"
        assert config["webhook"] is True

    async def test_webhook_endpoint_default_values(self):
        """Test webhook endpoint with default configuration values."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint("/webhook/defaults", webhook=True)
        async def default_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = default_webhook._jvspatial_endpoint_config
        webhook_config = config["webhook"]

        # Check default values
        assert webhook_config is True

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_openapi_extra(self):
        """Test webhook endpoint with OpenAPI extra configuration."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint(
            "/webhook/openapi",
            webhook=True,
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
        @endpoint("/webhook/empty", webhook=True, permissions=[], roles=[])
        async def empty_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = empty_webhook._jvspatial_endpoint_config
        assert config["permissions"] == []
        assert config["roles"] == []

        # Test with just hmac_secret
        @endpoint(
            "/webhook/hmac-only",
            webhook=True,
            hmac_secret="test_secret",  # pragma: allowlist secret
        )
        async def hmac_only_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = hmac_only_webhook._jvspatial_endpoint_config
        assert config["webhook"] is True

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_api_key_auth(self):
        """Test @endpoint with webhook_auth='api_key'."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint(
            "/webhook/api-key", methods=["POST"], webhook=True, webhook_auth="api_key"
        )
        async def api_key_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = api_key_webhook._jvspatial_endpoint_config
        assert config["webhook"] is True
        assert config["webhook_auth"] == "api_key"
        assert config["methods"] == ["POST"]

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_with_api_key_path_auth(self):
        """Test @endpoint with webhook_auth='api_key_path'."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint(
            "/webhook/{api_key}/trigger",
            methods=["POST"],
            webhook=True,
            webhook_auth="api_key_path",
        )
        async def api_key_path_webhook(api_key: str, payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = api_key_path_webhook._jvspatial_endpoint_config
        assert config["webhook"] is True
        assert config["webhook_auth"] == "api_key_path"
        assert config["path"] == "/webhook/{api_key}/trigger"

        # Clean up
        set_current_server(None)

    async def test_webhook_endpoint_without_auth(self):
        """Test @endpoint with webhook_auth=False (no API key auth)."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @endpoint(
            "/webhook/no-auth", methods=["POST"], webhook=True, webhook_auth=False
        )
        async def no_auth_webhook(payload: dict, endpoint):
            return endpoint.response(content={"status": "ok"})

        config = no_auth_webhook._jvspatial_endpoint_config
        assert config["webhook"] is True
        assert config["webhook_auth"] is False

        # Clean up
        set_current_server(None)
