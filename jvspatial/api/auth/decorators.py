"""Enhanced decorators with authentication support for jvspatial.

This module extends the existing @walker_endpoint and @endpoint decorators
to support authentication requirements, permissions, and roles.
"""

import inspect
import warnings
from typing import Any, Callable, List, Optional, Tuple, Type, Union, cast

from fastapi import HTTPException, Request

from jvspatial.api.context import get_current_server
from jvspatial.api.response import create_endpoint_helper
from jvspatial.core.entities import Walker

from .openapi_config import (
    ensure_server_has_security_config,
    get_endpoint_security_requirements,
)


def _auth_walker_endpoint(
    path: str,
    *,
    methods: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    server=None,
) -> Callable[[Type[Walker]], Type[Walker]]:
    """Internal authenticated walker endpoint handler (use @auth_endpoint instead).

    This is an internal implementation detail. Use the unified @auth_endpoint decorator
    for both Walker classes and functions.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods allowed (defaults to ["GET", "POST"])
        permissions: List of required permissions (all must be present)
        roles: List of required roles (user must have at least one)
        server: Server instance to register with (uses default if None)

    Returns:
        Decorator function
    """
    if methods is None:
        methods = ["GET", "POST"]

    def decorator(walker_class: Type[Walker]) -> Type[Walker]:
        # Store authentication metadata on the walker class
        walker_class._auth_required = True
        walker_class._required_permissions = permissions or []
        walker_class._required_roles = roles or []
        walker_class._endpoint_path = path
        walker_class._endpoint_methods = methods
        walker_class._endpoint_server = server

        # Try to register with server if available, but don't fail if not
        try:
            target_server = server or get_current_server()
            if target_server:
                # Configure OpenAPI security schemes (automatic on first use)
                ensure_server_has_security_config(target_server)

                # Get security requirements for OpenAPI spec
                security_requirements = get_endpoint_security_requirements(
                    permissions, roles
                )

                # Mark that this server has auth endpoints
                target_server._has_auth_endpoints = True

                # Register the walker with the server, including OpenAPI security
                target_server.register_walker_class(
                    walker_class,
                    path,
                    methods,
                    openapi_extra={"security": security_requirements},
                )
        except (RuntimeError, AttributeError):
            # Server not available during decoration (e.g., during test collection)
            # Registration will be deferred
            pass

        return walker_class

    return decorator


def auth_endpoint(
    path: str,
    *,
    methods: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    server=None,
) -> Callable[
    [Union[Type[Walker], Callable[..., Any]]], Union[Type[Walker], Callable[..., Any]]
]:
    """Unified authenticated endpoint decorator for both walkers and functions.

    Automatically detects whether decorating a Walker class or function.
    Requires authentication with optional permission and role-based access control.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (default: ["POST"] for walkers, ["GET"] for functions)
        permissions: List of required permissions (all must be present)
        roles: List of required roles (user must have at least one)
        server: Server instance to register with (uses default if None)

    Returns:
        Decorator function that works with both Walker classes and functions

    Examples:
        # Auth function endpoint (auto-detected)
        @auth_endpoint("/admin/users", methods=["GET"], roles=["admin"])
        async def manage_users(endpoint):
            return endpoint.success(data={"users": []})

        # Auth Walker endpoint (auto-detected)
        @auth_endpoint("/protected/data", permissions=["read_data"])
        class ProtectedDataWalker(Walker):
            pass
    """

    def decorator(
        target: Union[Type[Walker], Callable[..., Any]]
    ) -> Union[Type[Walker], Callable[..., Any]]:
        # Detect if target is a Walker class
        if inspect.isclass(target):
            try:
                if issubclass(target, Walker):
                    # Handle as authenticated Walker endpoint
                    default_methods = methods or ["POST"]
                    return _auth_walker_endpoint(
                        path,
                        methods=default_methods,
                        permissions=permissions,
                        roles=roles,
                        server=server,
                    )(target)
                else:
                    raise TypeError(
                        f"@auth_endpoint can only decorate Walker classes or functions. "
                        f"{target.__name__} is a class but not a Walker subclass. "
                        f"Did you mean to use a function instead?"
                    )
            except TypeError:
                # issubclass raises TypeError if target is not a class
                raise TypeError(
                    f"@auth_endpoint can only decorate Walker classes or functions. "
                    f"{target.__name__} is a class but not a Walker subclass. "
                    f"Did you mean to use a function instead?"
                )
        else:
            # Handle as authenticated function endpoint
            default_methods = methods or ["GET"]
            func = target
            # Get the original function signature
            sig = inspect.signature(func)
            params = list(sig.parameters.values())

            # Check if function expects 'endpoint' parameter
            has_endpoint_param = any(p.name == "endpoint" for p in params)

            # Filter out 'endpoint' parameter for signature (we'll inject it if needed)
            filtered_params = [p for p in params if p.name != "endpoint"]

            # Create wrapper that accepts both positional and keyword arguments
            async def auth_wrapper(*args: Any, **kwargs_inner: Any) -> Any:
                # Only inject endpoint helper if function expects it
                if has_endpoint_param:
                    endpoint_helper = create_endpoint_helper(walker_instance=None)
                    kwargs_inner["endpoint"] = endpoint_helper

                # Call original function with positional and keyword arguments
                if inspect.iscoroutinefunction(func):
                    return await func(*args, **kwargs_inner)
                else:
                    return func(*args, **kwargs_inner)

            # Apply the filtered signature to the wrapper
            auth_wrapper.__signature__ = sig.replace(parameters=filtered_params)  # type: ignore[attr-defined]
            auth_wrapper.__name__ = func.__name__
            auth_wrapper.__doc__ = func.__doc__
            auth_wrapper.__module__ = func.__module__

            # Store authentication metadata on the wrapper
            auth_wrapper._auth_required = True  # type: ignore[attr-defined]
            auth_wrapper._required_permissions = permissions or []  # type: ignore[attr-defined]
            auth_wrapper._required_roles = roles or []  # type: ignore[attr-defined]
            auth_wrapper._endpoint_path = path  # type: ignore[attr-defined]
            auth_wrapper._endpoint_methods = default_methods  # type: ignore[attr-defined]
            auth_wrapper._endpoint_server = server  # type: ignore[attr-defined]

            # Get security requirements for OpenAPI spec
            security_requirements = get_endpoint_security_requirements(
                permissions, roles
            )

            # Store registration data for deferred registration
            auth_wrapper._route_config = {  # type: ignore[attr-defined]
                "path": path,
                "endpoint": auth_wrapper,
                "methods": default_methods,
                "openapi_extra": {"security": security_requirements},
            }

            # Try to register with server if available, but don't fail if not
            try:
                target_server = server or get_current_server()
                if target_server:
                    # Mark that this server has auth endpoints
                    target_server._has_auth_endpoints = True

                    # Configure OpenAPI security schemes (automatic on first use)
                    ensure_server_has_security_config(target_server)

                    # Register with endpoint registry
                    if hasattr(target_server, "_endpoint_registry"):
                        target_server._endpoint_registry.register_function(
                            auth_wrapper,
                            path,
                            default_methods,
                            route_config=auth_wrapper._route_config,  # type: ignore[attr-defined]
                        )

                    # Register with the unified endpoint router
                    target_server.endpoint_router.router.add_api_route(
                        path=path,
                        endpoint=auth_wrapper,
                        methods=default_methods,
                        openapi_extra={"security": security_requirements},
                    )

                    target_server._logger.info(
                        f"{'🔄' if target_server._is_running else '📝'} "
                        f"{'Dynamically registered' if target_server._is_running else 'Registered'} "
                        f"auth function endpoint: {func.__name__} at {path}"
                    )
            except (RuntimeError, AttributeError):
                # Server not available during decoration (e.g., during test collection)
                # Registration will be deferred
                pass

            return cast(Callable[..., Any], auth_wrapper)

    return decorator


# Webhook decorators have been moved to jvspatial.api.webhook.decorators
# This is a backward-compatibility shim. Remove in future versions.
def webhook_endpoint(
    *args: Any, **kwargs: Any
) -> Union[Type[Walker], Callable[..., Any]]:
    """Deprecated: Import webhook_endpoint from jvspatial.api.webhook.decorators instead."""
    warnings.warn(
        "Importing webhook_endpoint from auth.decorators is deprecated. "
        "Use jvspatial.api.webhook.decorators instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from jvspatial.api.webhook.decorators import (
        webhook_endpoint as new_webhook_endpoint,
    )

    return cast(
        Union[Type[Walker], Callable[..., Any]], new_webhook_endpoint(*args, **kwargs)
    )


def _webhook_walker_endpoint(
    *args: Any, **kwargs: Any
) -> Union[Type[Walker], Callable[..., Any]]:
    """Deprecated: Import _webhook_walker_endpoint from jvspatial.api.webhook.decorators instead."""
    warnings.warn(
        "Importing _webhook_walker_endpoint from auth.decorators is deprecated. "
        "Use jvspatial.api.webhook.decorators instead.",
        DeprecationWarning,
        stacklevel=2,
    )
    from jvspatial.api.webhook.decorators import (
        _webhook_walker_endpoint as new_webhook_walker_endpoint,
    )

    return cast(
        Union[Type[Walker], Callable[..., Any]],
        new_webhook_walker_endpoint(*args, **kwargs),
    )


# Note: Use @endpoint and @walker_endpoint from jvspatial.api for public endpoints
# Use @auth_endpoint and @auth_walker_endpoint from this module for authenticated endpoints


def _admin_walker_endpoint(
    path: str, *, methods: Optional[List[str]] = None, server=None
) -> Callable[[Type[Walker]], Type[Walker]]:
    """Internal admin walker endpoint handler (use @admin_endpoint instead).

    This is an internal implementation detail. Use the unified @admin_endpoint decorator
    for both Walker classes and functions.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods allowed (defaults to ["POST"])
        server: Server instance to register with (uses default if None)

    Returns:
        Decorator function
    """
    return _auth_walker_endpoint(path, methods=methods, roles=["admin"], server=server)


def admin_endpoint(
    path: str, *, methods: Optional[List[str]] = None, server=None
) -> Callable[
    [Union[Type[Walker], Callable[..., Any]]], Union[Type[Walker], Callable[..., Any]]
]:
    """Unified admin endpoint decorator for both walkers and functions.

    Automatically detects whether decorating a Walker class or function.
    Requires admin role (equivalent to auth_endpoint with roles=["admin"]).

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (default: ["POST"] for walkers, ["GET"] for functions)
        server: Server instance to register with (uses default if None)

    Returns:
        Decorator function that works with both Walker classes and functions

    Examples:
        # Admin function endpoint (auto-detected)
        @admin_endpoint("/admin/users", methods=["GET"])
        async def manage_users(endpoint):
            return endpoint.success(data={"users": []})

        # Admin Walker endpoint (auto-detected)
        @admin_endpoint("/admin/process")
        class AdminProcessor(Walker):
            pass
    """

    def decorator(
        target: Union[Type[Walker], Callable[..., Any]]
    ) -> Union[Type[Walker], Callable[..., Any]]:
        # Detect if target is a Walker class
        if inspect.isclass(target):
            try:
                if issubclass(target, Walker):
                    # Handle as admin Walker endpoint
                    default_methods = methods or ["POST"]
                    return _admin_walker_endpoint(
                        path, methods=default_methods, server=server
                    )(target)
                else:
                    raise TypeError(
                        f"@admin_endpoint can only decorate Walker classes or functions. "
                        f"{target.__name__} is a class but not a Walker subclass. "
                        f"Did you mean to use a function instead?"
                    )
            except TypeError:
                # issubclass raises TypeError if target is not a class
                raise TypeError(
                    f"@admin_endpoint can only decorate Walker classes or functions. "
                    f"{target.__name__} is a class but not a Walker subclass. "
                    f"Did you mean to use a function instead?"
                )
        else:
            # Handle as admin function endpoint
            default_methods = methods or ["GET"]
            return auth_endpoint(
                path, methods=default_methods, roles=["admin"], server=server
            )(target)

    return decorator


# Enhanced middleware integration
class AuthAwareEndpointProcessor:
    """Helper class to process authentication metadata from endpoints."""

    @staticmethod
    def extract_auth_requirements(endpoint_func: Callable) -> dict:
        """Extract authentication requirements from an endpoint function.

        Args:
            endpoint_func: Endpoint function to analyze

        Returns:
            Dictionary with authentication requirements
        """
        return {
            "auth_required": getattr(endpoint_func, "_auth_required", True),
            "required_permissions": getattr(endpoint_func, "_required_permissions", []),
            "required_roles": getattr(endpoint_func, "_required_roles", []),
            "endpoint_path": getattr(endpoint_func, "_endpoint_path", ""),
        }

    @staticmethod
    def check_walker_auth(
        walker_class: Type[Walker], user
    ) -> Tuple[bool, Optional[str]]:
        """Check if user can access a walker endpoint.

        Args:
            walker_class: Walker class to check
            user: Current user (can be None)

        Returns:
            Tuple of (is_authorized, error_message)
        """
        auth_required = getattr(
            walker_class, "_auth_required", False
        )  # Default to public

        if not auth_required:
            return True, None  # Public endpoint

        if not user:
            return False, "Authentication required"

        if not user.is_active:
            return False, "User account is inactive"

        # Check required permissions
        required_permissions = getattr(walker_class, "_required_permissions", [])
        for permission in required_permissions:
            if not user.has_permission(permission):
                return False, f"Missing required permission: {permission}"

        # Check required roles
        required_roles = getattr(walker_class, "_required_roles", [])
        if required_roles and not any(user.has_role(role) for role in required_roles):
            return False, f"Missing required role: {', '.join(required_roles)}"

        return True, None
        return True, None


# Utility functions for checking current user context
async def require_authenticated_user(request: Request):
    """Utility to require an authenticated user in endpoint logic.

    Args:
        request: FastAPI request object

    Returns:
        Current authenticated user

    Raises:
        HTTPException: If user is not authenticated
    """
    from .middleware import get_current_user

    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User account is inactive")

    return user


async def require_permissions(request: Request, permissions: List[str]):
    """Utility to require specific permissions in endpoint logic.

    Args:
        request: FastAPI request object
        permissions: List of required permissions

    Returns:
        Current authenticated user

    Raises:
        HTTPException: If user lacks required permissions
    """
    user = await require_authenticated_user(request)

    for permission in permissions:
        if not user.has_permission(permission):
            raise HTTPException(
                status_code=403, detail=f"Missing required permission: {permission}"
            )

    return user


async def require_roles(request: Request, roles: List[str]):
    """Utility to require specific roles in endpoint logic.

    Args:
        request: FastAPI request object
        roles: List of roles (user needs at least one)

    Returns:
        Current authenticated user

    Raises:
        HTTPException: If user lacks required roles
    """
    user = await require_authenticated_user(request)

    if not any(user.has_role(role) for role in roles):
        raise HTTPException(
            status_code=403, detail=f"Missing required role: {', '.join(roles)}"
        )

    return user


async def require_admin(request: Request):
    """Utility to require admin access in endpoint logic.

    Args:
        request: FastAPI request object

    Returns:
        Current authenticated admin user

    Raises:
        HTTPException: If user is not an admin
    """
    user = await require_authenticated_user(request)

    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    return user


# Convenience alias
authenticated_endpoint = auth_endpoint  # For clarity

# Note: walker_endpoint and endpoint remain public by default in the main API
# These auth decorators are for explicit authentication requirements
