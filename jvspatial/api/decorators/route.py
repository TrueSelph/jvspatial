"""Simplified unified endpoint decorator system for jvspatial API.

This module provides a unified @endpoint decorator for functions, walkers, and webhooks.

Examples:
    @endpoint("/api/users", methods=["GET"])
    async def get_users():
        return {"users": [...]}

    @endpoint("/api/admin", auth=True, roles=["admin"])
    async def admin_panel():
        return {"admin": "dashboard"}

    @endpoint("/webhook", webhook=True, signature_required=True)
    async def webhook_handler():
        return {"status": "ok"}
"""

from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Optional, Union

from .function_wrappers import (
    AUTH_INJECTED_PARAMS,
    AUTH_INJECTED_USER_PARAMS,
    wrap_function_auth_only,
    wrap_function_with_params,
)

# Module names containing @endpoint-decorated targets (persists across uvicorn reload)
_endpoint_modules: set[str] = set()


def get_endpoint_modules() -> frozenset[str]:
    """Return module names that contain endpoint-decorated functions/classes."""
    return frozenset(_endpoint_modules)


def endpoint(
    path: str,
    methods: Optional[List[str]] = None,
    *,
    # Authentication and authorization
    auth: bool = False,
    permissions: Optional[List[str]] = None,
    roles: Optional[List[str]] = None,
    # Webhook configuration
    webhook: bool = False,
    signature_required: bool = False,
    webhook_auth: Optional[Union[str, bool]] = None,
    # Response schema
    response: Optional[Any] = None,
    # Rate limiting
    rate_limit: Optional[Dict[str, int]] = None,
    # Additional configuration
    **kwargs: Any,
) -> Callable:
    """Unified endpoint decorator for jvspatial API.

    This decorator provides a unified interface for registering functions, walkers,
    and webhooks as API endpoints with authentication, validation, and routing.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (defaults to ["GET"])
        auth: If True, authentication is required
        permissions: List of required permissions
        roles: List of required roles
        webhook: If True, configure as webhook endpoint
        signature_required: If True, require webhook signature verification
        webhook_auth: API key authentication mode for webhooks
            - "api_key": Authenticate via query parameter or header (default for webhooks)
            - "api_key_path": Authenticate via API key in URL path
            - False/None: No API key authentication
        response: Response schema definition (ResponseSchema instance)
        rate_limit: Rate limit configuration dict with "requests" and "window" keys
        **kwargs: Additional configuration options

    Returns:
        Decorator function

    Examples:
        # Basic endpoint
        @endpoint("/api/users", methods=["GET"])
        async def get_users():
            return {"users": [...]}

        # Authenticated endpoint
        @endpoint("/api/admin", auth=True, roles=["admin"])
        async def admin_panel():
            return {"admin": "dashboard"}

        # Endpoint with rate limiting
        @endpoint("/api/search", methods=["POST"], rate_limit={"requests": 10, "window": 60})
        async def search():
            return {"results": []}

        # Endpoint with response schema
        @endpoint("/api/users", response=response_schema(
            data={
                "users": ResponseField(List[Dict], "List of users", [{"id": 1, "name": "John"}]),
                "count": ResponseField(int, "Total count", 1)
            }
        ))
        async def get_users():
            return {"users": [], "count": 0}

        # Webhook endpoint
        @endpoint("/webhook", webhook=True, signature_required=True)
        async def webhook_handler():
            return {"status": "ok"}

        # Webhook with API key authentication
        @endpoint("/webhook/third-party", methods=["POST"], webhook=True, webhook_auth="api_key")
        async def third_party_webhook(payload: dict):
            return {"status": "received"}
    """

    def decorator(
        target: Union[Callable, type], _path: str = path
    ) -> Union[Callable, type]:
        from jvspatial.api.utils.path_utils import normalize_endpoint_path

        path = normalize_endpoint_path(_path)

        # Determine if this is a function or class
        is_func = inspect.isfunction(target)

        # Extract auth-related parameters from kwargs for config
        # (but don't remove from kwargs yet, as they may be needed for registration)
        route_kwargs_for_config = {
            k: v
            for k, v in kwargs.items()
            if k not in ["path", "methods", "is_function", "kwargs"]
        }
        config_auth = route_kwargs_for_config.get(
            "auth_required", route_kwargs_for_config.get("auth", auth)
        )
        config_permissions = route_kwargs_for_config.get(
            "permissions", permissions or []
        )
        config_roles = route_kwargs_for_config.get("roles", roles or [])

        # Store endpoint configuration on the target
        # Use setattr for dynamic attribute assignment (mypy compatibility)
        # Separate kwargs from direct config fields for compatibility with tests
        config_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k
            not in [
                "path",
                "methods",
                "auth_required",
                "auth",
                "permissions",
                "roles",
                "webhook",
                "signature_required",
                "webhook_auth",
                "response",
                "rate_limit",
                "is_function",
            ]
        }
        config = {
            "path": path,
            "methods": methods or ["GET"],
            "auth_required": config_auth,
            "permissions": config_permissions,
            "roles": config_roles,
            "webhook": webhook,
            "signature_required": signature_required,
            "webhook_auth": webhook_auth,
            "response": response,
            "rate_limit": rate_limit,
            "is_function": is_func,
            "kwargs": config_kwargs,
            **kwargs,  # Also include at top level for direct access
        }

        setattr(target, "_jvspatial_endpoint_config", config)  # noqa: B010
        _endpoint_modules.add(target.__module__)

        # Register with current server if available
        try:
            from jvspatial.api.context import get_current_server

            current_server = get_current_server()

            if current_server:
                if inspect.isclass(target):
                    # Walker class - set authentication attributes and register immediately
                    target._auth_required = auth
                    target._required_permissions = permissions or []
                    target._required_roles = roles or []

                    # Extract auth-related parameters from kwargs
                    route_kwargs_for_reg = {
                        k: v
                        for k, v in kwargs.items()
                        if k not in ["path", "methods", "is_function", "kwargs"]
                    }
                    reg_auth = route_kwargs_for_reg.pop("auth_required", None)
                    if reg_auth is None:
                        reg_auth = route_kwargs_for_reg.pop("auth", auth)
                    else:
                        route_kwargs_for_reg.pop("auth", None)
                    reg_permissions = route_kwargs_for_reg.pop(
                        "permissions", permissions or []
                    )
                    reg_roles = route_kwargs_for_reg.pop("roles", roles or [])

                    # Register Walker with endpoint registry
                    current_server._endpoint_registry.register_walker(
                        target,
                        path,
                        methods or ["POST"],
                        router=current_server.endpoint_router,
                        auth=reg_auth,
                        permissions=reg_permissions,
                        roles=reg_roles,
                        **route_kwargs_for_reg,
                    )

                    # Register Walker with main endpoint router
                    current_server.endpoint_router.endpoint(path, methods, **kwargs)(
                        target
                    )

                    # Also register dynamically if server is running
                    if current_server._is_running:
                        current_server._register_walker_dynamically(
                            target, path, methods, **kwargs
                        )
                else:
                    # Function endpoint - register immediately if server is available
                    # This allows tests and dynamic registration to work properly
                    # Discovery service will skip if already registered
                    func = target

                    # Create parameter model if function has parameters
                    from jvspatial.api.endpoints.factory import ParameterModelFactory

                    param_model = ParameterModelFactory.create_model(func, path=path)

                    # Wrap function with parameter handling if needed
                    func_sig = inspect.signature(func)
                    needs_auth_injection = any(
                        p in func_sig.parameters
                        for p in (*AUTH_INJECTED_PARAMS, *AUTH_INJECTED_USER_PARAMS)
                    )
                    if param_model is not None:
                        wrapped_func = wrap_function_with_params(
                            func, param_model, methods or ["GET"], path=path
                        )
                    elif needs_auth_injection:
                        wrapped_func = wrap_function_auth_only(
                            func, methods or ["GET"], path=path
                        )
                    else:
                        wrapped_func = func

                    # Extract auth-related parameters from kwargs
                    route_kwargs_for_reg = {
                        k: v
                        for k, v in kwargs.items()
                        if k not in ["path", "methods", "is_function", "kwargs"]
                    }
                    reg_auth = route_kwargs_for_reg.pop("auth_required", None)
                    if reg_auth is None:
                        reg_auth = route_kwargs_for_reg.pop("auth", auth)
                    else:
                        route_kwargs_for_reg.pop("auth", None)
                    reg_permissions = route_kwargs_for_reg.pop(
                        "permissions", permissions or []
                    )
                    reg_roles = route_kwargs_for_reg.pop("roles", roles or [])
                    reg_response = route_kwargs_for_reg.pop("response", response)

                    # Set auth attributes on the function (consistent with walker class handling)
                    func._auth_required = reg_auth  # type: ignore[union-attr]
                    wrapped_func._auth_required = reg_auth  # type: ignore[attr-defined]

                    # Register via endpoint router
                    current_server.endpoint_router.add_route(
                        path=path,
                        endpoint=wrapped_func,
                        methods=methods or ["GET"],
                        source_obj=func,
                        auth=reg_auth,
                        permissions=reg_permissions,
                        roles=reg_roles,
                        response=reg_response,
                        **route_kwargs_for_reg,
                    )

                    # Register with endpoint registry
                    current_server._endpoint_registry.register_function(
                        func,
                        path,
                        methods=methods or ["GET"],
                        route_config={
                            "path": path,
                            "endpoint": wrapped_func,
                            "methods": methods or ["GET"],
                            "auth_required": reg_auth,
                            "permissions": reg_permissions,
                            "roles": reg_roles,
                            **route_kwargs_for_reg,
                        },
                        auth_required=reg_auth,
                        permissions=reg_permissions,
                        roles=reg_roles,
                        **route_kwargs_for_reg,
                    )
            else:
                # No server available - register to deferred registry
                from jvspatial.api.decorators.deferred_registry import (
                    register_deferred_endpoint,
                )

                register_deferred_endpoint(target, config)
        except ImportError:
            # No server context available - register to deferred registry
            from jvspatial.api.decorators.deferred_registry import (
                register_deferred_endpoint,
            )

            register_deferred_endpoint(target, config)

        return target

    return decorator


__all__ = [
    "endpoint",
]
