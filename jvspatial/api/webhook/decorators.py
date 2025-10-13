"""Webhook endpoint decorators for jvspatial."""

import inspect
import os
from functools import wraps
from typing import Any, Callable, List, Optional, Type, Union, cast

import jvspatial.api.context as context
from jvspatial.core.entities import Walker


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
) -> Callable[
    [Union[Type[Walker], Callable[..., Any]]], Union[Type[Walker], Callable[..., Any]]
]:
    """Unified webhook endpoint decorator for both walkers and functions.

    Automatically detects whether decorating a Walker class or function.
    Supports HMAC verification, idempotency, and path-based authentication.

    Args:
        path: URL path (optionally with {key} for path-based auth)
        methods: HTTP methods (default: ["POST"])
        permissions: Required permissions
        roles: Required roles
        hmac_secret: Shared secret for HMAC signature verification
        idempotency_key_field: Header field for idempotency key
        idempotency_ttl_hours: TTL for idempotency records
        async_processing: Queue for async handling
        path_key_auth: Enable path-based authentication
        server: Server instance to register with
        **route_kwargs: Additional FastAPI route parameters

    Returns:
        Decorator function that works with both Walker classes and functions

    Examples:
        # Webhook function endpoint (auto-detected)
        @webhook_endpoint("/webhook/payment")
        async def handle_payment_webhook(payload: dict, endpoint):
            return endpoint.success(message="Payment processed")

        # Webhook Walker endpoint (auto-detected)
        @webhook_endpoint("/webhook/location-update")
        class LocationUpdateWalker(Walker):
            payload: dict
    """
    if methods is None:
        methods = ["POST"]

    # Validate path pattern if path_key_auth is enabled
    if path_key_auth and "{key}" not in path:
        raise ValueError(
            "Webhook endpoint with path_key_auth=True must include {key} parameter in path"
        )

    def decorator(
        target: Union[Type[Walker], Callable]
    ) -> Union[Type[Walker], Callable[..., Any]]:
        # Detect if target is a Walker class
        if inspect.isclass(target):
            try:
                if issubclass(target, Walker):
                    # Handle as webhook Walker endpoint
                    return _webhook_walker_endpoint(
                        path,
                        methods=methods,
                        permissions=permissions,
                        roles=roles,
                        hmac_secret=hmac_secret,
                        idempotency_key_field=idempotency_key_field,
                        idempotency_ttl_hours=idempotency_ttl_hours,
                        async_processing=async_processing,
                        path_key_auth=path_key_auth,
                        server=server,
                        **route_kwargs,
                    )(target)
                else:
                    raise TypeError(
                        f"@webhook_endpoint can only decorate Walker classes or functions. "
                        f"{target.__name__} is a class but not a Walker subclass. "
                        f"Did you mean to use a function instead?"
                    )
            except TypeError:
                raise TypeError(
                    f"@webhook_endpoint can only decorate Walker classes or functions. "
                    f"{target.__name__} is a class but not a Walker subclass. "
                    f"Did you mean to use a function instead?"
                )
        else:
            # Handle as webhook function endpoint
            func = target

            @wraps(func)
            async def webhook_wrapper(*args: Any, **kwargs: Any) -> Any:
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

            # Webhook-specific metadata with environment variable fallback
            effective_hmac_secret = hmac_secret or os.getenv(
                "JVSPATIAL_WEBHOOK_HMAC_SECRET"
            )
            webhook_wrapper._hmac_secret = effective_hmac_secret  # type: ignore[attr-defined]
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
                target_server = server or context.get_current_server()
                if target_server:
                    # Register with endpoint registry
                    if hasattr(target_server, "_endpoint_registry"):
                        target_server._endpoint_registry.register_function(
                            webhook_wrapper,
                            path,
                            methods,
                            route_config=webhook_wrapper._route_config,  # type: ignore[attr-defined]
                        )

                    # Register with the unified endpoint router
                    target_server.endpoint_router.router.add_api_route(
                        path=path,
                        endpoint=webhook_wrapper,
                        methods=methods,
                        **route_kwargs,
                    )

                    target_server._logger.info(
                        f"{'🔄' if target_server._is_running else '📝'} "
                        f"{'Dynamically registered' if target_server._is_running else 'Registered'} "
                        f"webhook function endpoint: {func.__name__} at {path}"
                    )
            except (RuntimeError, AttributeError):
                # Server not available during decoration (e.g., during test collection)
                # Registration will be deferred
                pass

            return cast(Callable[..., Any], webhook_wrapper)

    return decorator


def _webhook_walker_endpoint(
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
) -> Callable[[Type[Walker]], Type[Walker]]:
    """Internal webhook walker endpoint handler (use @webhook_endpoint instead).

    This is an internal implementation detail. Use the unified @webhook_endpoint decorator
    for both Walker classes and functions.

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

        # Webhook-specific metadata with environment variable fallback
        effective_hmac_secret = hmac_secret or os.getenv(
            "JVSPATIAL_WEBHOOK_HMAC_SECRET"
        )
        walker_class._hmac_secret = effective_hmac_secret
        walker_class._idempotency_key_field = idempotency_key_field
        walker_class._idempotency_ttl_hours = idempotency_ttl_hours
        walker_class._async_processing = async_processing
        walker_class._path_key_auth = path_key_auth
        walker_class._is_webhook = True

        # Try to register with server if available, but don't fail if not
        try:
            target_server = server or context.get_current_server()
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
