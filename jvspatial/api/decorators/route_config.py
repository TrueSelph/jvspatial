"""Configuration classes for route decorators.

This module provides the foundational configuration classes and base decorator
logic used by route-level decorators in the JVspatial API system.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class WebhookConfig:
    """Configuration for webhook endpoints.

    Attributes:
        hmac_secret: Optional HMAC secret for webhook verification
        idempotency_key_field: Header field name for idempotency keys
        idempotency_ttl_hours: Time-to-live for idempotency keys in hours
        async_processing: Whether to process webhooks asynchronously
        path_key_auth: Whether to use path-based key authentication
    """

    hmac_secret: Optional[str] = None
    idempotency_key_field: str = "X-Idempotency-Key"
    idempotency_ttl_hours: int = 24
    async_processing: bool = False
    path_key_auth: bool = False


@dataclass
class EndpointConfig:
    """Configuration for API endpoints.

    Attributes:
        path: URL path for the endpoint
        methods: HTTP methods allowed for this endpoint
        auth_required: Whether authentication is required
        permissions: List of required permissions
        roles: List of required roles
        webhook: Optional webhook configuration
        openapi_extra: Additional OpenAPI metadata
    """

    path: str
    methods: List[str] = field(default_factory=lambda: ["GET"])
    auth_required: bool = False
    permissions: List[str] = field(default_factory=list)
    roles: List[str] = field(default_factory=list)
    webhook: Optional[WebhookConfig] = None
    openapi_extra: Dict[str, Any] = field(default_factory=dict)


class EndpointDecorator:
    """Base decorator class for API endpoints."""

    @staticmethod
    def endpoint(
        config: EndpointConfig,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Create an endpoint decorator with the given configuration.

        Args:
            config: Endpoint configuration

        Returns:
            Decorator function
        """

        def decorator(target: Callable[..., Any]) -> Callable[..., Any]:
            from jvspatial.api.context import get_current_server

            current_server = get_current_server()

            if current_server is None:
                # No server in context, store config for later discovery
                if inspect.isclass(target):
                    target._jvspatial_endpoint_config = {
                        "path": config.path,
                        "methods": config.methods,
                        "kwargs": {
                            "auth_required": config.auth_required,
                            "permissions": config.permissions,
                            "roles": config.roles,
                            **config.openapi_extra,
                        },
                        "is_function": False,
                    }
                    # Also set _endpoint_config for testing
                    target._endpoint_config = config
                else:
                    func = target

                    async def wrapper(*args: Any, **kwargs: Any):
                        return await func(*args, **kwargs)

                    wrapper._jvspatial_endpoint_config = {  # type: ignore[attr-defined]
                        "path": config.path,
                        "methods": config.methods,
                        "kwargs": {
                            "auth_required": config.auth_required,
                            "permissions": config.permissions,
                            "roles": config.roles,
                            **config.openapi_extra,
                        },
                        "is_function": True,
                    }
                    # Also set _endpoint_config for testing
                    wrapper._endpoint_config = config  # type: ignore[attr-defined]
                    return wrapper
                return target

            # Server is available, register immediately like @endpoint decorator
            if inspect.isclass(target):
                # Walker class - register with server
                # Remove auth-related params from kwargs for FastAPI
                route_kwargs = {
                    k: v
                    for k, v in config.openapi_extra.items()
                    if k not in ["auth_required", "permissions", "roles"]
                }

                # Add security requirements for OpenAPI if auth is required
                if config.auth_required:
                    from jvspatial.api.auth.openapi_config import (
                        get_endpoint_security_requirements,
                    )

                    security_requirements = get_endpoint_security_requirements(
                        permissions=config.permissions, roles=config.roles
                    )
                    route_kwargs["responses"] = route_kwargs.get("responses", {})
                    route_kwargs["responses"].update(
                        {
                            401: {"description": "Authentication required"},
                            403: {"description": "Insufficient permissions"},
                        }
                    )
                    # Add security to openapi_extra for FastAPI to pick up
                    route_kwargs["openapi_extra"] = route_kwargs.get(
                        "openapi_extra", {}
                    )
                    route_kwargs["openapi_extra"]["security"] = security_requirements

                # Set authentication attributes on the Walker class
                if config.auth_required:
                    target._auth_required = True
                    target._required_permissions = config.permissions
                    target._required_roles = config.roles

                # Set the endpoint configuration for testing and introspection
                target._endpoint_config = config

                current_server.register_walker_class(
                    target, config.path, methods=config.methods, **route_kwargs
                )

                # Mark server as having auth endpoints
                current_server._has_auth_endpoints = True

                return target
            else:
                # Function - register with server
                func = target

                # Create wrapper if endpoint helper is needed
                if "endpoint" in inspect.signature(func).parameters:
                    # Create a function that matches the original signature but without endpoint parameter
                    # This will be used for OpenAPI generation
                    original_sig = inspect.signature(func)
                    original_params = list(original_sig.parameters.values())

                    # Remove the endpoint parameter from the signature
                    filtered_params = [
                        p for p in original_params if p.name != "endpoint"
                    ]
                    new_sig = original_sig.replace(parameters=filtered_params)

                    # Create a new function with the filtered signature
                    async def endpoint_injected_func(*args: Any, **kwargs: Any) -> Any:
                        # Set authentication attributes on request state for middleware
                        if config.auth_required:
                            # Get the request object from the first argument (if it's a Request)
                            request = None
                            for arg in args:
                                if hasattr(arg, "state") and hasattr(arg, "headers"):
                                    request = arg
                                    break

                            if request:
                                request.state.endpoint_auth = True
                                request.state.required_permissions = config.permissions
                                request.state.required_roles = config.roles

                        # Inject the endpoint helper
                        from jvspatial.api.endpoints.response import (
                            create_endpoint_helper,
                        )

                        endpoint_helper = create_endpoint_helper(walker_instance=None)
                        kwargs["endpoint"] = endpoint_helper

                        # Call the original function and await if it's a coroutine
                        if inspect.iscoroutinefunction(func):
                            result = await func(*args, **kwargs)
                        else:
                            result = func(*args, **kwargs)

                        # If the result is a coroutine (from endpoint helper methods), await it
                        if hasattr(result, "__await__"):
                            result = await result

                        return result

                    # Apply the filtered signature and metadata
                    endpoint_injected_func.__name__ = func.__name__
                    endpoint_injected_func.__doc__ = func.__doc__
                    endpoint_injected_func.__module__ = func.__module__
                    endpoint_injected_func.__signature__ = new_sig  # type: ignore[attr-defined]

                    # Copy annotations but remove endpoint
                    original_annotations = func.__annotations__.copy()
                    if "endpoint" in original_annotations:
                        del original_annotations["endpoint"]
                    endpoint_injected_func.__annotations__ = original_annotations

                    func_wrapper = endpoint_injected_func
                else:
                    func_wrapper = func

                # Set the endpoint configuration for testing and introspection
                func_wrapper._endpoint_config = config  # type: ignore[attr-defined]

                # Set authentication attributes on the wrapper function
                # This is what the AuthenticationMiddleware looks for
                if config.auth_required:
                    func_wrapper._auth_required = True  # type: ignore[attr-defined]
                    func_wrapper._required_permissions = config.permissions  # type: ignore[attr-defined]
                    func_wrapper._required_roles = config.roles  # type: ignore[attr-defined]

                # Note: Standard auth endpoints are automatically available
                # when using @auth_endpoint decorators through the existing
                # auth system in jvspatial.api.auth.endpoints

                # Register with endpoint registry and router
                try:
                    current_server._endpoint_registry.register_function(
                        func,
                        config.path,
                        methods=config.methods,
                        route_config={
                            "path": config.path,
                            "endpoint": func_wrapper,
                            "methods": config.methods,
                            "auth_required": config.auth_required,
                            "permissions": config.permissions,
                            "roles": config.roles,
                            **config.openapi_extra,
                        },
                        auth_required=config.auth_required,
                        permissions=config.permissions,
                        roles=config.roles,
                        **config.openapi_extra,
                    )

                    # Remove auth-related params from FastAPI route
                    route_kwargs = {
                        k: v
                        for k, v in config.openapi_extra.items()
                        if k not in ["auth_required", "permissions", "roles"]
                    }

                    # Add security requirements for OpenAPI if auth is required
                    if config.auth_required:
                        from jvspatial.api.auth.openapi_config import (
                            get_endpoint_security_requirements,
                        )

                        security_requirements = get_endpoint_security_requirements(
                            permissions=config.permissions, roles=config.roles
                        )
                        route_kwargs["responses"] = route_kwargs.get("responses", {})
                        route_kwargs["responses"].update(
                            {
                                401: {"description": "Authentication required"},
                                403: {"description": "Insufficient permissions"},
                            }
                        )
                        # Add security to openapi_extra for FastAPI to pick up
                        route_kwargs["openapi_extra"] = route_kwargs.get(
                            "openapi_extra", {}
                        )
                        route_kwargs["openapi_extra"][
                            "security"
                        ] = security_requirements

                    current_server.endpoint_router.router.add_api_route(
                        path=config.path,
                        endpoint=func_wrapper,
                        methods=config.methods,
                        **route_kwargs,
                    )

                    # Mark server as having auth endpoints
                    current_server._has_auth_endpoints = True

                    current_server._logger.info(
                        f"{'🔄' if current_server._is_running else '📝'} "
                        f"{'Dynamically registered' if current_server._is_running else 'Registered'} "
                        f"auth endpoint: {func.__name__} at {config.path}"
                    )

                except Exception as e:
                    current_server._logger.warning(
                        f"Auth endpoint {func.__name__} already registered: {e}"
                    )

                return func_wrapper

        return decorator
