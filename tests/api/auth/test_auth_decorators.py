"""
Test suite for authentication decorators.

Tests the new unified decorator API for authentication endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest

from jvspatial.api.auth.decorators import admin_endpoint, auth_endpoint
from jvspatial.api.auth.entities import User
from jvspatial.core.entities import Walker


class MockWalker(Walker):
    """Test walker class for decorator testing."""

    pass


class TestWalkerEndpointAuth:
    """Test auth_endpoint decorator functionality with Walker classes."""

    def setup_method(self):
        """Set up test data."""
        self.mock_server = MagicMock()
        self.mock_server.register_walker_class = MagicMock()

    async def test_auth_endpoint_basic(self):
        """Test basic auth endpoint decorator."""
        from jvspatial.api.context import set_current_server

        # Set the mock server as current
        set_current_server(self.mock_server)

        @auth_endpoint("/test/protected")
        class TestAuthWalker(Walker):
            pass

        # Check endpoint config metadata is stored
        assert hasattr(TestAuthWalker, "_endpoint_config")
        config = TestAuthWalker._endpoint_config
        assert config.path == "/test/protected"
        assert config.methods == ["GET"]
        assert config.auth_required is True
        assert config.permissions == []
        assert config.roles == []

        # The decorator just sets config - server registration happens later
        # when the server processes the decorated class

        # Clean up
        set_current_server(None)

    async def test_auth_endpoint_with_permissions(self):
        """Test auth endpoint with permissions on Walker class."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @auth_endpoint(
            "/test/permissions",
            permissions=["read_data", "write_data"],
            methods=["POST"],
        )
        class PermissionWalker(Walker):
            pass

        # Check endpoint config metadata
        assert hasattr(PermissionWalker, "_endpoint_config")
        config = PermissionWalker._endpoint_config
        assert config.auth_required is True
        assert config.permissions == ["read_data", "write_data"]
        assert config.roles == []
        assert config.path == "/test/permissions"
        assert config.methods == ["POST"]

        # Clean up
        set_current_server(None)

    async def test_auth_endpoint_with_roles(self):
        """Test auth endpoint with roles on Walker class."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @auth_endpoint(
            "/test/roles",
            roles=["admin", "user"],
            methods=["PUT"],
        )
        class RoleWalker(Walker):
            pass

        # Check endpoint config metadata
        assert hasattr(RoleWalker, "_endpoint_config")
        config = RoleWalker._endpoint_config
        assert config.auth_required is True
        assert config.permissions == []
        assert config.roles == ["admin", "user"]
        assert config.path == "/test/roles"
        assert config.methods == ["PUT"]

        # Clean up
        set_current_server(None)

    async def test_auth_endpoint_with_both_permissions_and_roles(self):
        """Test auth endpoint with both permissions and roles."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @auth_endpoint(
            "/test/both",
            permissions=["read", "write"],
            roles=["admin"],
            methods=["DELETE"],
        )
        class BothWalker(Walker):
            pass

        # Check endpoint config metadata
        assert hasattr(BothWalker, "_endpoint_config")
        config = BothWalker._endpoint_config
        assert config.auth_required is True
        assert config.permissions == ["read", "write"]
        assert config.roles == ["admin"]
        assert config.path == "/test/both"
        assert config.methods == ["DELETE"]

        # Clean up
        set_current_server(None)

    async def test_admin_endpoint(self):
        """Test admin_endpoint decorator."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @admin_endpoint("/test/admin")
        class AdminWalker(Walker):
            pass

        # Check endpoint config metadata
        assert hasattr(AdminWalker, "_endpoint_config")
        config = AdminWalker._endpoint_config
        assert config.auth_required is True
        assert config.permissions == []
        assert config.roles == ["admin"]
        assert config.path == "/test/admin"
        assert config.methods == ["GET"]

        # Clean up
        set_current_server(None)

    async def test_admin_endpoint_with_custom_methods(self):
        """Test admin_endpoint with custom methods."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @admin_endpoint("/test/admin", methods=["POST", "PUT"])
        class AdminWalker(Walker):
            pass

        # Check endpoint config metadata
        assert hasattr(AdminWalker, "_endpoint_config")
        config = AdminWalker._endpoint_config
        assert config.auth_required is True
        assert config.permissions == []
        assert config.roles == ["admin"]
        assert config.path == "/test/admin"
        assert config.methods == ["POST", "PUT"]

        # Clean up
        set_current_server(None)


class TestFunctionEndpointAuth:
    """Test auth_endpoint decorator functionality with function endpoints."""

    def setup_method(self):
        """Set up test data."""
        self.mock_server = MagicMock()
        self.mock_server.register_function = MagicMock()

    async def test_auth_endpoint_function_basic(self):
        """Test basic auth endpoint decorator on function."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @auth_endpoint("/test/function")
        async def test_function():
            return {"message": "test"}

        # Check endpoint config metadata is stored
        assert hasattr(test_function, "_endpoint_config")
        config = test_function._endpoint_config
        assert config.path == "/test/function"
        assert config.methods == ["GET"]
        assert config.auth_required is True
        assert config.permissions == []
        assert config.roles == []

        # Clean up
        set_current_server(None)

    async def test_auth_endpoint_function_with_permissions(self):
        """Test auth endpoint function with permissions."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @auth_endpoint(
            "/test/function-perms",
            permissions=["read", "write"],
            methods=["POST"],
        )
        async def test_function_with_perms():
            return {"message": "test"}

        # Check endpoint config metadata
        assert hasattr(test_function_with_perms, "_endpoint_config")
        config = test_function_with_perms._endpoint_config
        assert config.path == "/test/function-perms"
        assert config.methods == ["POST"]
        assert config.auth_required is True
        assert config.permissions == ["read", "write"]
        assert config.roles == []

        # Clean up
        set_current_server(None)

    async def test_admin_endpoint_function(self):
        """Test admin_endpoint decorator on function."""
        from jvspatial.api.context import set_current_server

        set_current_server(self.mock_server)

        @admin_endpoint("/test/admin-function")
        async def admin_function():
            return {"message": "admin"}

        # Check endpoint config metadata
        assert hasattr(admin_function, "_endpoint_config")
        config = admin_function._endpoint_config
        assert config.path == "/test/admin-function"
        assert config.methods == ["GET"]
        assert config.auth_required is True
        assert config.permissions == []
        assert config.roles == ["admin"]

        # Clean up
        set_current_server(None)


class TestAuthDecoratorEdgeCases:
    """Test edge cases and error conditions for auth decorators."""

    async def test_auth_endpoint_no_server(self):
        """Test auth endpoint when no server is available."""
        from jvspatial.api.context import set_current_server

        # Ensure no server is set
        set_current_server(None)

        @auth_endpoint("/test/no-server")
        class NoServerWalker(Walker):
            pass

        # Should still set config even without server
        assert hasattr(NoServerWalker, "_endpoint_config")
        config = NoServerWalker._endpoint_config
        assert config.path == "/test/no-server"
        assert config.auth_required is True

    async def test_auth_endpoint_empty_permissions(self):
        """Test auth endpoint with empty permissions list."""
        from jvspatial.api.context import set_current_server

        set_current_server(MagicMock())

        @auth_endpoint("/test/empty", permissions=[])
        class EmptyPermsWalker(Walker):
            pass

        config = EmptyPermsWalker._endpoint_config
        assert config.permissions == []

        # Clean up
        set_current_server(None)

    async def test_auth_endpoint_empty_roles(self):
        """Test auth endpoint with empty roles list."""
        from jvspatial.api.context import set_current_server

        set_current_server(MagicMock())

        @auth_endpoint("/test/empty", roles=[])
        class EmptyRolesWalker(Walker):
            pass

        config = EmptyRolesWalker._endpoint_config
        assert config.roles == []

        # Clean up
        set_current_server(None)

    async def test_auth_endpoint_multiple_methods(self):
        """Test auth endpoint with multiple HTTP methods."""
        from jvspatial.api.context import set_current_server

        set_current_server(MagicMock())

        @auth_endpoint("/test/multi", methods=["GET", "POST", "PUT"])
        class MultiMethodWalker(Walker):
            pass

        config = MultiMethodWalker._endpoint_config
        assert config.methods == ["GET", "POST", "PUT"]

        # Clean up
        set_current_server(None)
