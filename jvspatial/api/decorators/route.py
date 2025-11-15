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
from typing import Any, Callable, List, Optional, Type, Union

from pydantic import BaseModel


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
    # Response schema
    response: Optional[Any] = None,
    # Additional configuration
    **kwargs: Any,
) -> Callable:
    """Unified endpoint decorator for jvspatial API.

    This decorator replaces the old endpoint decorator system with a single

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (defaults to ["GET"])
        auth: If True, authentication is required
        permissions: List of required permissions
        roles: List of required roles
        webhook: If True, configure as webhook endpoint
        signature_required: If True, require webhook signature verification
        response: Response schema definition (ResponseSchema instance)
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
    """

    def decorator(target: Union[Callable, type]) -> Union[Callable, type]:
        # Store endpoint configuration on the target
        # Use setattr for dynamic attribute assignment (mypy compatibility)
        setattr(  # noqa: B010
            target,
            "_jvspatial_endpoint_config",
            {  # type: ignore[union-attr]  # noqa: B010
                "path": path,
                "methods": methods or ["GET"],
                "auth_required": auth,
                "permissions": permissions or [],
                "roles": roles or [],
                "webhook": webhook,
                "signature_required": signature_required,
                "response": response,
                "is_function": inspect.isfunction(target),
                **kwargs,
            },
        )

        # Register with current server if available
        try:
            from jvspatial.api.context import get_current_server

            current_server = get_current_server()

            if current_server:
                if inspect.isclass(target):
                    # Walker class - set authentication attributes
                    target._auth_required = auth
                    target._required_permissions = permissions or []
                    target._required_roles = roles or []

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
                    # Function - create parameter model and wrap with authentication
                    from jvspatial.api.endpoints.factory import ParameterModelFactory

                    # Create parameter model for function
                    # Pass the path to detect path parameters that should be excluded
                    param_model = ParameterModelFactory.create_model(target, path=path)

                    if param_model is not None:
                        # Function has parameters - wrap with parameter handling
                        # Pass methods so GET requests use query params instead of body
                        wrapped_func = _wrap_function_with_params(
                            target, param_model, methods or ["GET"], path=path
                        )
                    else:
                        # Function has no parameters - use as-is
                        wrapped_func = target

                    if auth:
                        wrapped_func = _wrap_function_with_auth(
                            wrapped_func, auth, permissions, roles
                        )

                    # Propagate endpoint config (including response) onto the wrapped function
                    config = getattr(target, "_jvspatial_endpoint_config", {})
                    config = dict(config)
                    config["is_function"] = True
                    wrapped_func._jvspatial_endpoint_config = config  # type: ignore[attr-defined]  # noqa: B010

                    # Register function via EndpointRouter to ensure response_model and security are applied
                    current_server.endpoint_router.add_route(
                        path=path,
                        endpoint=wrapped_func,
                        methods=methods or ["GET"],
                        source_obj=wrapped_func,
                        auth=auth,
                        permissions=permissions or [],
                        roles=roles or [],
                        response=response,
                        **kwargs,
                    )

                    # Mark server as having auth endpoints
                    current_server._has_auth_endpoints = True
        except ImportError:
            # No server context available, configuration will be picked up later
            pass

        return target

    return decorator


def _wrap_function_with_params(
    func: Callable,
    param_model: Type[BaseModel],
    methods: Optional[List[str]] = None,
    path: Optional[str] = None,
) -> Callable:
    """Wrap function to handle parameter model validation.

    For GET/HEAD requests, parameters are treated as query parameters.
    For other methods, parameters are in the request body.
    """
    import inspect

    # Determine if this is a GET/HEAD request (query params) or other (body)
    is_get_request = methods and any(m.upper() in ("GET", "HEAD") for m in methods)

    if is_get_request:
        # For GET requests, FastAPI automatically handles query parameters from function signature
        # No wrapping needed - FastAPI will extract params from the function signature
        return func

    # For POST/PUT/etc, use Body for request body parameters
    # But we need to handle path parameters separately - FastAPI passes them directly
    import re

    from fastapi import Body

    # Extract path parameters from path string (e.g., {user_id} from "/users/{user_id}")
    path_params = set()
    if path:
        path_param_matches = re.findall(r"\{(\w+)\}", path)
        path_params = set(path_param_matches)

    # Get function signature to check which params are path params
    func_sig = inspect.signature(func)

    # If function has path parameters and body parameters, we need special handling
    # If only path parameters, FastAPI handles it directly - no wrapper needed
    # If path + body params, we need to handle both
    has_path_params = path_params and any(
        name in func_sig.parameters for name in path_params
    )
    has_body_params = param_model is not None

    if has_path_params and has_body_params:
        # Function has both path and body parameters - create wrapper with proper signature
        # Create a proper function signature that FastAPI can introspect
        # Body is already imported above

        # Build parameters for the new signature
        new_params = []

        # Add path parameters first (preserve their original annotations)
        for param_name in func_sig.parameters:
            if param_name in path_params:
                orig_param = func_sig.parameters[param_name]
                new_params.append(
                    inspect.Parameter(
                        param_name,
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        default=orig_param.default,
                        annotation=orig_param.annotation,
                    )
                )

        # Add body parameter with the param_model type
        new_params.append(
            inspect.Parameter(
                "body",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=Body(),
                annotation=param_model,
            )
        )

        # Create new signature
        new_sig = inspect.Signature(
            new_params, return_annotation=func_sig.return_annotation
        )

        async def wrapped_func(*args: Any, **kwargs: Any) -> Any:
            """Wrapped function with parameter validation for both path and body."""
            # Separate path params from body params
            body_data = {}
            body_obj = kwargs.pop("body", None)

            if body_obj is not None:
                if isinstance(body_obj, param_model):
                    # Extract body parameters from the model
                    if hasattr(body_obj, "model_dump"):
                        body_data = body_obj.model_dump(
                            exclude_none=False, exclude_unset=False
                        )
                    else:
                        body_data = {
                            k: getattr(body_obj, k)
                            for k in dir(body_obj)
                            if not k.startswith("_")
                        }
                elif isinstance(body_obj, dict):
                    # Already a dict (from FastAPI)
                    body_data = body_obj

            # Remove start_node if it exists (it's added by the base model)
            body_data.pop("start_node", None)

            # Merge path params (from kwargs) with body params
            combined = {**kwargs, **body_data}

            # Filter out None values for required non-path fields
            for param_name, param in func_sig.parameters.items():
                if (
                    param_name not in path_params
                    and param_name in combined
                    and combined[param_name] is None
                    and param.default == inspect.Parameter.empty
                ):
                    # Required parameter should not be None
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=422,
                        detail=f"Required parameter '{param_name}' cannot be None",
                    )

            # Call original function with all parameters
            return await func(**combined)

        # Set the proper signature so FastAPI can introspect it
        # Type ignore: We're dynamically setting __signature__ on a callable for FastAPI introspection
        wrapped_func.__signature__ = new_sig  # type: ignore[attr-defined]

        # Set annotations to match the signature
        wrapped_func.__annotations__ = {
            param.name: param.annotation for param in new_sig.parameters.values()
        }
        wrapped_func.__annotations__["return"] = new_sig.return_annotation

    elif has_path_params and not has_body_params:
        # Only path parameters - FastAPI handles these directly, no wrapper needed
        return func
    else:
        # No path parameters - simple body parameter model
        # Note: Body() in default is required by FastAPI for body params
        async def wrapped_func(params: Any = Body()) -> Any:  # type: ignore[assignment,misc]  # noqa: B008
            """Wrapped function with parameter validation."""
            # Extract parameters from the model
            if hasattr(params, "model_dump"):
                data = params.model_dump(exclude_none=False, exclude_unset=False)
            else:
                data = {
                    k: getattr(params, k) for k in dir(params) if not k.startswith("_")
                }

            # Remove start_node if it exists (it's added by the base model)
            data.pop("start_node", None)

            # Filter out None values for required fields - they should have been validated by Pydantic
            # But ensure we don't pass None for required fields
            for param_name, param in func_sig.parameters.items():
                if (
                    param_name in data
                    and data[param_name] is None
                    and param.default == inspect.Parameter.empty
                ):
                    # Required parameter should not be None - validation should catch this
                    # But if it got here, raise an error
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=422,
                        detail=f"Required parameter '{param_name}' cannot be None",
                    )

            # Call original function with parameters
            return await func(**data)

    # Copy function metadata
    wrapped_func.__name__ = func.__name__
    wrapped_func.__doc__ = func.__doc__
    wrapped_func.__module__ = func.__module__

    # Set annotations if not already set (for the case without path params)
    if not has_path_params and has_body_params:
        # No path parameters - simple body parameter model
        # The signature already has the correct annotation for 'params'
        wrapped_func.__annotations__ = {
            "params": param_model,
            "return": func_sig.return_annotation,
        }
    # For has_path_params and has_body_params case, annotations were already set above
    # For only path params case, func was returned directly above

    return wrapped_func


def _wrap_function_with_auth(
    func: Callable,
    auth: bool,
    permissions: Optional[List[str]],
    roles: Optional[List[str]],
) -> Callable:
    """Wrap a function with authentication checks.

    Args:
        func: Original function to wrap
        auth: Whether authentication is required
        permissions: Required permissions
        roles: Required roles

    Returns:
        Wrapped function with authentication checks
    """
    # For now, just return the original function
    # Authentication will be handled by middleware
    # TODO: Implement proper function-level auth checks
    return func


__all__ = [
    "endpoint",
]
