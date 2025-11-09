"""Test suite for unified endpoint decorator system.

Tests the simplified @endpoint decorator that replaces multiple endpoint decorators.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI

from jvspatial.api.decorators.route import endpoint
from jvspatial.api.server import Server
from jvspatial.config import Config


class TestEndpointDecorator:
    """Test the unified @endpoint decorator."""

    def setup_method(self):
        """Set up test mocks."""
        self.mock_server = MagicMock(spec=Server)
        self.mock_server._has_auth_endpoints = False

    def test_endpoint_basic(self):
        """Test basic endpoint decorator."""

        @endpoint("/api/test")
        async def test_endpoint():
            return {"message": "test"}

        assert hasattr(test_endpoint, "_jvspatial_endpoint_config")
        config = test_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/test"
        assert config["methods"] == ["GET"]
        assert config["auth_required"] == False

    def test_endpoint_with_methods(self):
        """Test endpoint with specific HTTP methods."""

        @endpoint("/api/users", methods=["GET", "POST"])
        async def users_endpoint():
            return {"users": []}

        config = users_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/users"
        assert config["methods"] == ["GET", "POST"]

    def test_endpoint_with_auth(self):
        """Test endpoint with authentication."""

        @endpoint("/api/admin", auth=True)
        async def admin_endpoint():
            return {"admin": "data"}

        config = admin_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/admin"
        assert config["auth_required"] == True

    def test_endpoint_with_roles(self):
        """Test endpoint with role requirements."""

        @endpoint("/api/super-admin", auth=True, roles=["admin", "super_admin"])
        async def super_admin_endpoint():
            return {"super_admin": "data"}

        config = super_admin_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/super-admin"
        assert config["auth_required"] == True
        assert config["roles"] == ["admin", "super_admin"]

    def test_endpoint_with_permissions(self):
        """Test endpoint with permission requirements."""

        @endpoint("/api/sensitive", auth=True, permissions=["read:sensitive"])
        async def sensitive_endpoint():
            return {"sensitive": "data"}

        config = sensitive_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/sensitive"
        assert config["auth_required"] == True
        assert config["permissions"] == ["read:sensitive"]

    def test_endpoint_webhook(self):
        """Test webhook endpoint."""

        @endpoint("/webhook/data", webhook=True)
        async def webhook_endpoint():
            return {"status": "received"}

        config = webhook_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/webhook/data"
        assert config["webhook"] == True

    def test_endpoint_with_signature_verification(self):
        """Test endpoint with signature verification."""

        @endpoint("/webhook/secure", webhook=True, signature_required=True)
        async def secure_webhook():
            return {"status": "verified"}

        config = secure_webhook._jvspatial_endpoint_config
        assert config["path"] == "/webhook/secure"
        assert config["webhook"] == True
        assert config["signature_required"] == True

    def test_endpoint_with_tags(self):
        """Test endpoint with OpenAPI tags."""

        @endpoint("/api/users", tags=["users", "management"])
        async def users_endpoint():
            return {"users": []}

        config = users_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/users"
        assert config["tags"] == ["users", "management"]

    def test_endpoint_with_summary(self):
        """Test endpoint with OpenAPI summary."""

        @endpoint("/api/users", summary="Get all users")
        async def users_endpoint():
            return {"users": []}

        config = users_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/users"
        assert config["summary"] == "Get all users"

    def test_endpoint_with_description(self):
        """Test endpoint with OpenAPI description."""

        @endpoint("/api/users", description="Retrieve a list of all users")
        async def users_endpoint():
            return {"users": []}

        config = users_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/users"
        assert config["description"] == "Retrieve a list of all users"

    def test_endpoint_with_responses(self):
        """Test endpoint with custom responses."""
        responses = {
            200: {"description": "Success"},
            404: {"description": "Not found"},
            500: {"description": "Server error"},
        }

        @endpoint("/api/users", responses=responses)
        async def users_endpoint():
            return {"users": []}

        config = users_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/users"
        assert config["responses"] == responses

    def test_endpoint_with_deprecated(self):
        """Test deprecated endpoint."""

        @endpoint("/api/old", deprecated=True)
        async def old_endpoint():
            return {"message": "deprecated"}

        config = old_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/old"
        assert config["deprecated"] == True

    def test_endpoint_complex_configuration(self):
        """Test endpoint with complex configuration."""

        @endpoint(
            "/api/complex",
            methods=["GET", "POST"],
            auth=True,
            roles=["admin"],
            permissions=["read:data", "write:data"],
            tags=["complex", "admin"],
            summary="Complex endpoint",
            description="A complex endpoint with multiple configurations",
            responses={
                200: {"description": "Success"},
                403: {"description": "Forbidden"},
            },
            deprecated=False,
        )
        async def complex_endpoint():
            return {"complex": "data"}

        config = complex_endpoint._jvspatial_endpoint_config
        assert config["path"] == "/api/complex"
        assert config["methods"] == ["GET", "POST"]
        assert config["auth_required"] == True
        assert config["roles"] == ["admin"]
        assert config["permissions"] == ["read:data", "write:data"]
        assert config["tags"] == ["complex", "admin"]
        assert config["summary"] == "Complex endpoint"
        assert (
            config["description"] == "A complex endpoint with multiple configurations"
        )
        assert config["deprecated"] == False

    def test_endpoint_class_method(self):
        """Test endpoint decorator on class methods."""

        class TestController:
            @endpoint("/api/controller", methods=["GET"])
            async def get_data(self):
                return {"data": "from controller"}

        controller = TestController()
        config = controller.get_data._jvspatial_endpoint_config
        assert config["path"] == "/api/controller"
        assert config["methods"] == ["GET"]

    def test_endpoint_static_method(self):
        """Test endpoint decorator on static methods."""

        class TestController:
            @staticmethod
            @endpoint("/api/static", methods=["POST"])
            async def static_method():
                return {"static": "data"}

        config = TestController.static_method._jvspatial_endpoint_config
        assert config["path"] == "/api/static"
        assert config["methods"] == ["POST"]

    def test_endpoint_inheritance(self):
        """Test endpoint decorator inheritance."""

        class BaseController:
            @endpoint("/api/base", methods=["GET"])
            async def base_method(self):
                return {"base": "data"}

        class DerivedController(BaseController):
            @endpoint("/api/derived", methods=["POST"])
            async def derived_method(self):
                return {"derived": "data"}

        base = BaseController()
        derived = DerivedController()

        assert hasattr(base.base_method, "_jvspatial_endpoint_config")
        assert hasattr(derived.base_method, "_jvspatial_endpoint_config")
        assert hasattr(derived.derived_method, "_jvspatial_endpoint_config")

        assert base.base_method._jvspatial_endpoint_config["path"] == "/api/base"
        assert (
            derived.derived_method._jvspatial_endpoint_config["path"] == "/api/derived"
        )
