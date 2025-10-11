"""
Test suite for authentication decorators.

This module tests the auth decorators including auth_walker_endpoint, auth_endpoint,
admin decorators, and authentication/authorization checking functionality.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from jvspatial.api.auth.decorators import (
    AuthAwareEndpointProcessor,
    admin_endpoint,
    admin_walker_endpoint,
    auth_endpoint,
    auth_walker_endpoint,
    authenticated_endpoint,
    authenticated_walker_endpoint,
    require_admin,
    require_authenticated_user,
    require_permissions,
    require_roles,
)
from jvspatial.api.auth.entities import User
from jvspatial.core.entities import Walker


class MockWalker(Walker):
    """Test walker class for decorator testing."""

    pass


class TestAuthWalkerEndpoint:
    """Test auth_walker_endpoint decorator functionality."""

    def setup_method(self):
        """Set up test data."""
        self.mock_server = MagicMock()
        self.mock_server.register_walker_class = MagicMock()

    def test_auth_walker_endpoint_basic(self):
        """Test basic auth walker endpoint decorator."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @auth_walker_endpoint("/test/protected")
            class TestAuthWalker(Walker):
                pass

            # Check metadata is stored
            assert hasattr(TestAuthWalker, "_auth_required")
            assert TestAuthWalker._auth_required is True
            assert TestAuthWalker._required_permissions == []
            assert TestAuthWalker._required_roles == []
            assert TestAuthWalker._endpoint_path == "/test/protected"

            # Check server registration was called (with openapi_extra parameter)
            self.mock_server.register_walker_class.assert_called_once()
            call_args = self.mock_server.register_walker_class.call_args
            assert call_args[0][0] == TestAuthWalker
            assert call_args[0][1] == "/test/protected"
            assert call_args[0][2] == ["GET", "POST"]
            # Check that openapi_extra was passed
            assert "openapi_extra" in call_args[1]

    def test_auth_walker_endpoint_with_permissions(self):
        """Test auth walker endpoint with permissions."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @auth_walker_endpoint(
                "/test/permissions",
                permissions=["read_data", "write_data"],
                methods=["POST"],
            )
            class PermissionWalker(Walker):
                pass

            # Check metadata
            assert PermissionWalker._auth_required is True
            assert PermissionWalker._required_permissions == ["read_data", "write_data"]
            assert PermissionWalker._required_roles == []

            # Check registration (with openapi_extra parameter)
            self.mock_server.register_walker_class.assert_called_once()
            call_args = self.mock_server.register_walker_class.call_args
            assert call_args[0][0] == PermissionWalker
            assert call_args[0][1] == "/test/permissions"
            assert call_args[0][2] == ["POST"]

    def test_auth_walker_endpoint_with_roles(self):
        """Test auth walker endpoint with roles."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @auth_walker_endpoint("/test/roles", roles=["analyst", "admin"])
            class RoleWalker(Walker):
                pass

            # Check metadata
            assert RoleWalker._auth_required is True
            assert RoleWalker._required_permissions == []
            assert RoleWalker._required_roles == ["analyst", "admin"]

    def test_auth_walker_endpoint_with_custom_server(self):
        """Test auth walker endpoint with custom server."""
        custom_server = MagicMock()
        custom_server.register_walker_class = MagicMock()

        @auth_walker_endpoint("/test/custom", server=custom_server)
        class CustomServerWalker(Walker):
            pass

        # Should use custom server, not default
        custom_server.register_walker_class.assert_called_once()

    def test_auth_walker_endpoint_no_server(self):
        """Test auth walker endpoint when no server available."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server", return_value=None
        ):
            # With deferred registration, no exception should be raised during decoration
            @auth_walker_endpoint("/test/walker")
            class NoServerWalker(Walker):
                async def test_func(self):
                    return {"message": "authenticated"}

            # Check that metadata is still stored
            assert NoServerWalker._auth_required is True
            assert NoServerWalker._endpoint_path == "/test/walker"

    def test_authenticated_walker_endpoint_alias(self):
        """Test that authenticated_walker_endpoint is an alias."""
        assert authenticated_walker_endpoint == auth_walker_endpoint


class TestAuthEndpoint:
    """Test auth_endpoint decorator functionality."""

    def setup_method(self):
        """Set up test data."""
        self.mock_server = MagicMock()
        self.mock_server.register_function_endpoint = MagicMock()
        self.mock_server._custom_routes = []
        self.mock_server._endpoint_registry = MagicMock()
        self.mock_server._endpoint_registry.register_function = MagicMock()

    def test_auth_endpoint_basic(self):
        """Test basic auth endpoint decorator."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @auth_endpoint("/test/function")
            async def test_function():
                return {"message": "authenticated"}

            # Check metadata is stored on wrapper
            assert hasattr(test_function, "_auth_required")
            assert test_function._auth_required is True
            assert test_function._required_permissions == []
            assert test_function._required_roles == []
            assert test_function._endpoint_path == "/test/function"

            # With new registration approach, check the custom routes
            assert len(self.mock_server._custom_routes) > 0
            assert any(
                route["path"] == "/test/function"
                for route in self.mock_server._custom_routes
            )

    def test_auth_endpoint_with_permissions(self):
        """Test auth endpoint with permissions."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @auth_endpoint(
                "/test/perms", permissions=["admin_access"], methods=["PUT", "DELETE"]
            )
            async def admin_function():
                return {"message": "admin only"}

            # Check metadata
            assert admin_function._auth_required is True
            assert admin_function._required_permissions == ["admin_access"]
            assert admin_function._required_roles == []

    def test_auth_endpoint_with_roles(self):
        """Test auth endpoint with roles."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @auth_endpoint("/test/roles", roles=["manager", "admin"])
            async def role_function():
                return {"message": "manager or admin"}

            # Check metadata
            assert role_function._auth_required is True
            assert role_function._required_permissions == []
            assert role_function._required_roles == ["manager", "admin"]

    def test_auth_endpoint_no_server(self):
        """Test auth endpoint when no server available."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server", return_value=None
        ):
            # With deferred registration, no exception should be raised during decoration
            @auth_endpoint("/test/function")
            async def test_function():
                return {"message": "authenticated"}

            # Check that metadata is still stored
            assert test_function._auth_required is True
            assert test_function._endpoint_path == "/test/function"

    def test_authenticated_endpoint_alias(self):
        """Test that authenticated_endpoint is an alias."""
        assert authenticated_endpoint == auth_endpoint


class TestAdminDecorators:
    """Test admin-specific decorators."""

    def setup_method(self):
        """Set up test data."""
        self.mock_server = MagicMock()
        self.mock_server.register_walker_class = MagicMock()
        self.mock_server.register_function_endpoint = MagicMock()
        self.mock_server._custom_routes = []
        self.mock_server._endpoint_registry = MagicMock()
        self.mock_server._endpoint_registry.register_function = MagicMock()

    def test_admin_walker_endpoint(self):
        """Test admin walker endpoint decorator."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @admin_walker_endpoint("/admin/data")
            class AdminWalker(Walker):
                pass

            # Should have admin role requirement
            assert AdminWalker._auth_required is True
            assert AdminWalker._required_permissions == []
            assert AdminWalker._required_roles == ["admin"]

            # Check registration (with openapi_extra parameter)
            self.mock_server.register_walker_class.assert_called_once()
            call_args = self.mock_server.register_walker_class.call_args
            assert call_args[0][0] == AdminWalker
            assert call_args[0][1] == "/admin/data"
            assert call_args[0][2] == ["GET", "POST"]

    def test_admin_walker_endpoint_with_methods(self):
        """Test admin walker endpoint with custom methods."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @admin_walker_endpoint("/admin/users", methods=["PUT", "DELETE"])
            class AdminUserWalker(Walker):
                pass

            # Check registration with custom methods (with openapi_extra parameter)
            self.mock_server.register_walker_class.assert_called_once()
            call_args = self.mock_server.register_walker_class.call_args
            assert call_args[0][0] == AdminUserWalker
            assert call_args[0][1] == "/admin/users"
            assert call_args[0][2] == ["PUT", "DELETE"]

    def test_admin_endpoint(self):
        """Test admin endpoint decorator."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @admin_endpoint("/admin/settings")
            async def admin_settings():
                return {"settings": "admin_only"}

            # Should have admin role requirement
            assert admin_settings._auth_required is True
            assert admin_settings._required_permissions == []
            assert admin_settings._required_roles == ["admin"]

    def test_admin_endpoint_with_methods(self):
        """Test admin endpoint with custom methods."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @admin_endpoint("/admin/config", methods=["POST", "PUT"])
            async def admin_config():
                return {"config": "updated"}

            # Check that route was added to custom routes
            assert len(self.mock_server._custom_routes) > 0
            assert any(
                route["path"] == "/admin/config" and route["methods"] == ["POST", "PUT"]
                for route in self.mock_server._custom_routes
            )


class TestAuthAwareEndpointProcessor:
    """Test AuthAwareEndpointProcessor functionality."""

    def test_extract_auth_requirements_with_auth(self):
        """Test extracting auth requirements from authenticated endpoint."""
        # Mock function with auth requirements
        mock_func = MagicMock()
        mock_func._auth_required = True
        mock_func._required_permissions = ["read_data", "write_data"]
        mock_func._required_roles = ["user", "admin"]
        mock_func._endpoint_path = "/api/protected"

        with patch("jvspatial.api.auth.decorators.getattr") as mock_getattr:
            # Set up getattr to return our mock values
            def getattr_side_effect(obj, name, default):
                return getattr(mock_func, name, default)

            mock_getattr.side_effect = getattr_side_effect

            result = AuthAwareEndpointProcessor.extract_auth_requirements(mock_func)

            assert result["auth_required"] is True
            assert result["required_permissions"] == ["read_data", "write_data"]
            assert result["required_roles"] == ["user", "admin"]
            assert result["endpoint_path"] == "/api/protected"

    def test_extract_auth_requirements_defaults(self):
        """Test extracting auth requirements with defaults."""
        mock_func = MagicMock()

        # Remove all auth attributes to test defaults
        for attr in [
            "_auth_required",
            "_required_permissions",
            "_required_roles",
            "_endpoint_path",
        ]:
            if hasattr(mock_func, attr):
                delattr(mock_func, attr)

        result = AuthAwareEndpointProcessor.extract_auth_requirements(mock_func)

        assert result["auth_required"] is True  # Default is True
        assert result["required_permissions"] == []
        assert result["required_roles"] == []
        assert result["endpoint_path"] == ""

    def test_check_walker_auth_no_auth_required(self):
        """Test walker auth check when no auth required."""
        # Mock walker class with no auth requirement
        mock_walker = MagicMock()
        mock_walker._auth_required = False

        with patch("jvspatial.api.auth.decorators.getattr", return_value=False):
            is_authorized, error = AuthAwareEndpointProcessor.check_walker_auth(
                mock_walker, None
            )

            assert is_authorized is True
            assert error is None

    def test_check_walker_auth_no_user(self):
        """Test walker auth check when no user provided."""
        mock_walker = MagicMock()

        with patch("jvspatial.api.auth.decorators.getattr", return_value=True):
            is_authorized, error = AuthAwareEndpointProcessor.check_walker_auth(
                mock_walker, None
            )

            assert is_authorized is False
            assert error == "Authentication required"

    def test_check_walker_auth_inactive_user(self):
        """Test walker auth check with inactive user."""
        mock_walker = MagicMock()
        mock_user = MagicMock(spec=User)
        mock_user.is_active = False

        with patch("jvspatial.api.auth.decorators.getattr", return_value=True):
            is_authorized, error = AuthAwareEndpointProcessor.check_walker_auth(
                mock_walker, mock_user
            )

            assert is_authorized is False
            assert error == "User account is inactive"

    def test_check_walker_auth_missing_permissions(self):
        """Test walker auth check with missing permissions."""
        mock_walker = MagicMock()
        mock_user = MagicMock(spec=User)
        mock_user.is_active = True
        mock_user.has_permission.return_value = False

        def getattr_side_effect(obj, name, default):
            if name == "_auth_required":
                return True
            elif name == "_required_permissions":
                return ["admin_access"]
            elif name == "_required_roles":
                return []
            return default

        with patch(
            "jvspatial.api.auth.decorators.getattr", side_effect=getattr_side_effect
        ):
            is_authorized, error = AuthAwareEndpointProcessor.check_walker_auth(
                mock_walker, mock_user
            )

            assert is_authorized is False
            assert "Missing required permission: admin_access" in error

    def test_check_walker_auth_missing_roles(self):
        """Test walker auth check with missing roles."""
        mock_walker = MagicMock()
        mock_user = MagicMock(spec=User)
        mock_user.is_active = True
        mock_user.has_role.return_value = False

        def getattr_side_effect(obj, name, default):
            if name == "_auth_required":
                return True
            elif name == "_required_permissions":
                return []
            elif name == "_required_roles":
                return ["admin", "manager"]
            return default

        with patch(
            "jvspatial.api.auth.decorators.getattr", side_effect=getattr_side_effect
        ):
            is_authorized, error = AuthAwareEndpointProcessor.check_walker_auth(
                mock_walker, mock_user
            )

            assert is_authorized is False
            assert "Missing required role: admin, manager" in error

    def test_check_walker_auth_success(self):
        """Test successful walker auth check."""
        mock_walker = MagicMock()
        mock_user = MagicMock(spec=User)
        mock_user.is_active = True
        mock_user.has_permission.return_value = True
        mock_user.has_role.return_value = True

        def getattr_side_effect(obj, name, default):
            if name == "_auth_required":
                return True
            elif name == "_required_permissions":
                return ["read_data"]
            elif name == "_required_roles":
                return ["user"]
            return default

        with patch(
            "jvspatial.api.auth.decorators.getattr", side_effect=getattr_side_effect
        ):
            is_authorized, error = AuthAwareEndpointProcessor.check_walker_auth(
                mock_walker, mock_user
            )

            assert is_authorized is True
            assert error is None


class TestUtilityFunctions:
    """Test authentication utility functions."""

    def setup_method(self):
        """Set up test data."""
        self.test_user = User(
            id="user_123",
            username="testuser",
            email="test@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_active=True,
            is_admin=False,
            roles=["user"],
            permissions=["read_data"],
        )

        self.admin_user = User(
            id="admin_123",
            username="admin",
            email="admin@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_active=True,
            is_admin=True,
            roles=["admin"],
            permissions=["admin_access"],
        )

    @pytest.mark.asyncio
    async def test_require_authenticated_user_success(self):
        """Test require_authenticated_user with valid user."""
        request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.middleware.get_current_user",
            return_value=self.test_user,
        ):
            result = await require_authenticated_user(request)
            assert result == self.test_user

    @pytest.mark.asyncio
    async def test_require_authenticated_user_no_user(self):
        """Test require_authenticated_user with no user."""
        request = MagicMock(spec=Request)

        with patch("jvspatial.api.auth.middleware.get_current_user", return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await require_authenticated_user(request)

            assert exc_info.value.status_code == 401
            assert "Authentication required" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_require_authenticated_user_inactive(self):
        """Test require_authenticated_user with inactive user."""
        request = MagicMock(spec=Request)
        inactive_user = User(
            username="inactive",
            email="inactive@example.com",
            password_hash="hash",  # pragma: allowlist secret
            is_active=False,
        )

        with patch(
            "jvspatial.api.auth.middleware.get_current_user", return_value=inactive_user
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_authenticated_user(request)

            assert exc_info.value.status_code == 403
            assert "User account is inactive" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_require_permissions_success(self):
        """Test require_permissions with valid permissions."""
        request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.decorators.require_authenticated_user",
            return_value=self.test_user,
        ):
            with patch.object(User, "has_permission", return_value=True):
                result = await require_permissions(request, ["read_data"])
                assert result == self.test_user

    @pytest.mark.asyncio
    async def test_require_permissions_missing(self):
        """Test require_permissions with missing permissions."""
        request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.decorators.require_authenticated_user",
            return_value=self.test_user,
        ):
            with patch.object(User, "has_permission", return_value=False):
                with pytest.raises(HTTPException) as exc_info:
                    await require_permissions(request, ["admin_access"])

                assert exc_info.value.status_code == 403
                assert "Missing required permission" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_require_roles_success(self):
        """Test require_roles with valid roles."""
        request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.decorators.require_authenticated_user",
            return_value=self.test_user,
        ):
            with patch.object(User, "has_role", return_value=True):
                result = await require_roles(request, ["admin", "manager"])
                assert result == self.test_user
                assert result == self.test_user

    @pytest.mark.asyncio
    async def test_require_roles_missing(self):
        """Test require_roles with missing roles."""
        request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.decorators.require_authenticated_user",
            return_value=self.test_user,
        ):
            with patch.object(User, "has_role", return_value=False):
                with pytest.raises(HTTPException) as exc_info:
                    await require_roles(request, ["admin"])

                assert exc_info.value.status_code == 403
                assert "Missing required role" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_require_admin_success(self):
        """Test require_admin with admin user."""
        request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.decorators.require_authenticated_user",
            return_value=self.admin_user,
        ):
            result = await require_admin(request)

            assert result == self.admin_user

    @pytest.mark.asyncio
    async def test_require_admin_not_admin(self):
        """Test require_admin with non-admin user."""
        request = MagicMock(spec=Request)

        with patch(
            "jvspatial.api.auth.decorators.require_authenticated_user",
            return_value=self.test_user,
        ):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin(request)

            assert exc_info.value.status_code == 403
            assert "Admin access required" in str(exc_info.value.detail)


class TestDecoratorIntegration:
    """Test integration scenarios for auth decorators."""

    def setup_method(self):
        """Set up test data."""
        self.mock_server = MagicMock()
        self.mock_server.register_walker_class = MagicMock()
        self.mock_server.register_function_endpoint = MagicMock()

    def test_multiple_decorators_on_walker(self):
        """Test multiple auth-related decorators on a walker."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            @auth_walker_endpoint(
                "/complex/walker",
                methods=["POST", "PUT"],
                permissions=["read_data", "write_data"],
                roles=["analyst", "admin"],
            )
            class ComplexWalker(Walker):
                """Walker with complex auth requirements."""

                pass

            # Check all metadata is properly set
            assert ComplexWalker._auth_required is True
            assert ComplexWalker._required_permissions == ["read_data", "write_data"]
            assert ComplexWalker._required_roles == ["analyst", "admin"]
            assert ComplexWalker._endpoint_path == "/complex/walker"

            # Check server registration (with openapi_extra parameter)
            self.mock_server.register_walker_class.assert_called_once()
            call_args = self.mock_server.register_walker_class.call_args
            assert call_args[0][0] == ComplexWalker
            assert call_args[0][1] == "/complex/walker"
            assert call_args[0][2] == ["POST", "PUT"]

    def test_nested_decorator_functionality(self):
        """Test that decorators work properly when combined."""
        with patch(
            "jvspatial.api.auth.decorators.get_current_server",
            return_value=self.mock_server,
        ):

            # Define a complex endpoint with multiple requirements
            @auth_endpoint(
                "/api/complex",
                methods=["GET", "POST", "PUT"],
                permissions=["create_data", "update_data"],
                roles=["editor", "admin"],
            )
            async def complex_endpoint(request: Request):
                # This would normally use the utility functions
                user = await require_authenticated_user(request)
                await require_permissions(request, ["create_data", "update_data"])
                await require_roles(request, ["editor", "admin"])
                return {"message": "Complex operation successful"}

            # Check metadata
            assert complex_endpoint._auth_required is True
            assert complex_endpoint._required_permissions == [
                "create_data",
                "update_data",
            ]
            assert complex_endpoint._required_roles == ["editor", "admin"]

    def test_decorator_error_handling(self):
        """Test error handling in decorators."""
        # Test with no default server and no explicit server
        with patch(
            "jvspatial.api.auth.decorators.get_current_server", return_value=None
        ):

            # With deferred registration, decorators should not raise errors during decoration
            @auth_walker_endpoint("/test/error")
            class ErrorWalker(Walker):
                pass

            assert ErrorWalker._auth_required is True

            @auth_endpoint("/test/error")
            async def error_function():
                pass

            assert error_function._auth_required is True
