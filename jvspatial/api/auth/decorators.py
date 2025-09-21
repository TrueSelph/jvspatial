"""Enhanced decorators with authentication support for jvspatial.

This module extends the existing @walker_endpoint and @endpoint decorators
to support authentication requirements, permissions, and roles.
"""

import inspect
from functools import wraps
from typing import Any, Callable, List, Optional, Tuple, Type

from fastapi import HTTPException, Request

from jvspatial.api.server import get_default_server
from jvspatial.core.entities import Walker


def auth_walker_endpoint(
    path: str,
    *,
    methods: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    server=None,
):
    """Authenticated walker endpoint decorator.

    This decorator creates walker endpoints that require authentication,
    with optional permission and role-based access control.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods allowed (defaults to ["GET", "POST"])
        permissions: List of required permissions (all must be present)
        roles: List of required roles (user must have at least one)
        server: Server instance to register with (uses default if None)

    Returns:
        Decorator function

    Example:
        ```python
        @auth_walker_endpoint(
            "/protected/data",
            permissions=["read_spatial_data"],
            roles=["analyst", "admin"]
        )
        class ProtectedDataWalker(Walker):
            @on_visit(Node)
            async def process(self, here):
                # This endpoint requires authentication and specific permissions
                pass
        ```
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
            target_server = server or get_default_server()
            if target_server:
                # Register the walker with the server
                target_server.register_walker_class(walker_class, path, methods)
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
):
    """Authenticated endpoint decorator.

    This decorator creates endpoints that require authentication,
    with optional permission and role-based access control.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods allowed (defaults to ["GET"])
        permissions: List of required permissions (all must be present)
        roles: List of required roles (user must have at least one)
        server: Server instance to register with (uses default if None)

    Returns:
        Decorator function

    Example:
        ```python
        @auth_endpoint(
            "/admin/users",
            methods=["GET", "POST"],
            roles=["admin"]
        )
        async def manage_users():
            # This endpoint requires admin role
            pass
        ```
    """
    if methods is None:
        methods = ["GET"]

    def decorator(func: Callable) -> Callable:
        # Create wrapped function with auth metadata
        @wraps(func)
        async def auth_wrapper(*args: tuple, **kwargs: dict):
            # The middleware will handle authentication before this runs
            return await func(*args, **kwargs)

        # Store authentication metadata on the function
        auth_wrapper._auth_required = True  # type: ignore[attr-defined]
        auth_wrapper._required_permissions = permissions or []  # type: ignore[attr-defined]
        auth_wrapper._required_roles = roles or []  # type: ignore[attr-defined]
        auth_wrapper._endpoint_path = path  # type: ignore[attr-defined]
        auth_wrapper._endpoint_methods = methods  # type: ignore[attr-defined]
        auth_wrapper._endpoint_server = server  # type: ignore[attr-defined]

        # Store registration data for deferred registration
        auth_wrapper._route_config = {  # type: ignore[attr-defined]
            "path": path,
            "endpoint": auth_wrapper,
            "methods": methods,
        }

        # Try to register with server if available, but don't fail if not
        try:
            target_server = server or get_default_server()
            if target_server:
                # Register the function with the server using the route decorator pattern
                target_server._custom_routes.append(auth_wrapper._route_config)  # type: ignore[attr-defined]

                # Track function endpoint mapping
                target_server._function_endpoint_mapping[auth_wrapper] = {
                    "path": path,
                    "methods": methods,
                    "kwargs": {},
                    "route_config": auth_wrapper._route_config,  # type: ignore[attr-defined]
                }
        except (RuntimeError, AttributeError):
            # Server not available during decoration (e.g., during test collection)
            # Registration will be deferred
            pass

        return auth_wrapper

    return decorator


def webhook_endpoint(
    path: str,
    *,
    methods: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    hmac_secret: Optional[str] = None,
    idempotency_key_field: str = "X-Idempotency-Key",
    idempotency_ttl_hours: int = 24,
    async_processing: bool = False,
    path_key_auth: bool = False,
    server=None,
    **route_kwargs: Any,
):
    """Webhook endpoint decorator.

    This decorator creates webhook endpoints that support webhook-specific functionality
    including HMAC verification, idempotency handling, and optional path-based authentication.

    Args:
        path: URL path for the endpoint (optionally with {key} for path-based auth)
        methods: HTTP methods allowed (defaults to ["POST"])
        permissions: List of required permissions (all must be present)
        roles: List of required roles (user must have at least one)
        hmac_secret: Shared secret for HMAC signature verification
        idempotency_key_field: Header field for idempotency key
        idempotency_ttl_hours: TTL for idempotency records in hours
        async_processing: Queue for async handling
        path_key_auth: Enable path-based authentication with {key} parameter
        server: Server instance to register with (uses default if None)
        **route_kwargs: Additional FastAPI route parameters

    Returns:
        Decorator function

    Examples:
        ```python
        @webhook_endpoint("/webhooks/payment")
        async def handle_payment_webhook(payload: dict, endpoint):
            # payload is verified JSON from request.body
            return endpoint.success(message="Payment processed")

        @webhook_endpoint(
            "/webhooks/stripe/{key}",
            path_key_auth=True,
            hmac_secret="stripe-webhook-secret"  # pragma: allowlist secret
        )
        async def stripe_webhook_handler(raw_body: bytes, content_type: str, endpoint):
            # Handle raw payload with path-based auth and HMAC verification
            return endpoint.success(data={"processed": True})
        ```
    """
    if methods is None:
        methods = ["POST"]

    # Validate path pattern if path_key_auth is enabled
    if path_key_auth and "{key}" not in path:
        raise ValueError(
            "Webhook endpoint with path_key_auth=True must include {key} parameter in path"
        )

    def decorator(func: Callable) -> Callable:
        if inspect.isclass(func):
            raise TypeError(
                "@webhook_endpoint can only be used on functions, not classes"
            )

        @wraps(func)
        async def webhook_wrapper(*args: tuple, **kwargs: dict):
            # The middleware will handle webhook processing before this runs
            return await func(*args, **kwargs)

        # Store webhook metadata on the function
        webhook_wrapper._webhook_required = True  # type: ignore[attr-defined]
        webhook_wrapper._auth_required = bool(permissions or roles)  # type: ignore[attr-defined]
        webhook_wrapper._required_permissions = permissions or []  # type: ignore[attr-defined]
        webhook_wrapper._required_roles = roles or []  # type: ignore[attr-defined]
        webhook_wrapper._endpoint_path = path  # type: ignore[attr-defined]
        webhook_wrapper._endpoint_methods = methods  # type: ignore[attr-defined]
        webhook_wrapper._endpoint_server = server  # type: ignore[attr-defined]

        # Webhook-specific metadata
        webhook_wrapper._hmac_secret = hmac_secret  # type: ignore[attr-defined]
        webhook_wrapper._idempotency_key_field = idempotency_key_field  # type: ignore[attr-defined]
        webhook_wrapper._idempotency_ttl_hours = idempotency_ttl_hours  # type: ignore[attr-defined]
        webhook_wrapper._async_processing = async_processing  # type: ignore[attr-defined]
        webhook_wrapper._path_key_auth = path_key_auth  # type: ignore[attr-defined]
        webhook_wrapper._is_webhook = True  # type: ignore[attr-defined]

        # Store registration data for deferred registration
        webhook_wrapper._route_config = {  # type: ignore[attr-defined]
            "path": path,
            "endpoint": webhook_wrapper,
            "methods": methods,
            **route_kwargs,
        }

        # Try to register with server if available, but don't fail if not
        try:
            target_server = server or get_default_server()
            if target_server:
                # Register the function with the server using the route decorator pattern
                target_server._custom_routes.append(webhook_wrapper._route_config)  # type: ignore[attr-defined]

                # Track function endpoint mapping
                target_server._function_endpoint_mapping[webhook_wrapper] = {
                    "path": path,
                    "methods": methods,
                    "kwargs": route_kwargs,
                    "route_config": webhook_wrapper._route_config,  # type: ignore[attr-defined]
                }
        except (RuntimeError, AttributeError):
            # Server not available during decoration (e.g., during test collection)
            # Registration will be deferred
            pass

        return webhook_wrapper

    return decorator


def webhook_walker_endpoint(
    path: str,
    *,
    methods: Optional[List[str]] = None,
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    hmac_secret: Optional[str] = None,
    idempotency_key_field: str = "X-Idempotency-Key",
    idempotency_ttl_hours: int = 24,
    async_processing: bool = False,
    path_key_auth: bool = False,
    server=None,
    **route_kwargs: Any,
):
    """Webhook walker endpoint decorator.

    This decorator creates webhook endpoints that use Walker classes for processing,
    with webhook-specific functionality including HMAC verification, idempotency handling,
    and optional path-based authentication.

    Args:
        path: URL path for the endpoint (optionally with {key} for path-based auth)
        methods: HTTP methods allowed (defaults to ["POST"])
        permissions: List of required permissions (all must be present)
        roles: List of required roles (user must have at least one)
        hmac_secret: Shared secret for HMAC signature verification
        idempotency_key_field: Header field for idempotency key
        idempotency_ttl_hours: TTL for idempotency records in hours
        async_processing: Queue for async handling
        path_key_auth: Enable path-based authentication with {key} parameter
        server: Server instance to register with (uses default if None)
        **route_kwargs: Additional FastAPI route parameters

    Returns:
        Decorator function

    Examples:
        ```python
        @webhook_walker_endpoint("/webhooks/location-update")
        class LocationUpdateWalker(Walker):
            def __init__(self, payload: dict):
                self.payload = payload  # Webhook data available here

            @on_visit(Node)
            async def update_location(self, here: Node):
                # Update node with location from self.payload
                here.location = self.payload.get("coordinates")
                await here.save()
                self.response["updated"] = True

        @webhook_walker_endpoint(
            "/webhooks/stripe/{key}",
            path_key_auth=True,
            hmac_secret="stripe-webhook-secret"  # pragma: allowlist secret
        )
        class StripeWebhookWalker(Walker):
            def __init__(self, raw_body: bytes, content_type: str):
                self.raw_body = raw_body
                self.content_type = content_type
        ```
    """
    if methods is None:
        methods = ["POST"]

    # Validate path pattern if path_key_auth is enabled
    if path_key_auth and "{key}" not in path:
        raise ValueError(
            "Webhook walker endpoint with path_key_auth=True must include {key} parameter in path"
        )

    def decorator(walker_class: Type[Walker]) -> Type[Walker]:
        if not inspect.isclass(walker_class):
            raise TypeError(
                "@webhook_walker_endpoint can only be used on Walker classes, not functions"
            )

        if not issubclass(walker_class, Walker):
            raise TypeError(
                "@webhook_walker_endpoint can only be used on Walker subclasses"
            )

        # Store webhook metadata on the walker class
        walker_class._webhook_required = True
        walker_class._auth_required = bool(permissions or roles)
        walker_class._required_permissions = permissions or []
        walker_class._required_roles = roles or []
        walker_class._endpoint_path = path
        walker_class._endpoint_methods = methods
        walker_class._endpoint_server = server

        # Webhook-specific metadata
        walker_class._hmac_secret = hmac_secret
        walker_class._idempotency_key_field = idempotency_key_field
        walker_class._idempotency_ttl_hours = idempotency_ttl_hours
        walker_class._async_processing = async_processing
        walker_class._path_key_auth = path_key_auth
        walker_class._is_webhook = True

        # Try to register with server if available, but don't fail if not
        try:
            target_server = server or get_default_server()
            if target_server:
                # Register the walker with the server
                target_server.register_walker_class(
                    walker_class, path, methods, **route_kwargs
                )
        except (RuntimeError, AttributeError):
            # Server not available during decoration (e.g., during test collection)
            # Registration will be deferred
            pass

        return walker_class

    return decorator


# Note: Use @endpoint and @walker_endpoint from jvspatial.api for public endpoints
# Use @auth_endpoint and @auth_walker_endpoint from this module for authenticated endpoints


def admin_walker_endpoint(
    path: str, *, methods: Optional[List[str]] = None, server=None
):
    """Walker endpoint decorator that requires admin role.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods allowed (defaults to ["GET", "POST"])
        server: Server instance to register with (uses default if None)

    Returns:
        Decorator function
    """
    return auth_walker_endpoint(path, methods=methods, roles=["admin"], server=server)


def admin_endpoint(path: str, *, methods: Optional[List[str]] = None, server=None):
    """Endpoint decorator that requires admin role.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods allowed (defaults to ["GET"])
        server: Server instance to register with (uses default if None)

    Returns:
        Decorator function
    """
    return auth_endpoint(path, methods=methods, roles=["admin"], server=server)


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
        auth_required = getattr(walker_class, "_auth_required", True)

        if not auth_required:
            return True, None

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


# Convenience aliases
authenticated_walker_endpoint = auth_walker_endpoint  # For clarity
authenticated_endpoint = auth_endpoint  # For clarity

# Note: walker_endpoint and endpoint remain public by default in the main API
# These auth decorators are for explicit authentication requirements
