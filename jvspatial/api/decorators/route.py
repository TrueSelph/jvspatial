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
from typing import Any, Callable, List, Optional, Tuple, Type, Union

from pydantic import BaseModel

# Constants for parameter names that are injected from authentication
_AUTH_INJECTED_PARAMS = frozenset(["user_id", "current_user_id"])
_EXCLUDED_BODY_PARAMS = frozenset(["start_node"])


def _extract_user_id_from_user_object(user: Any) -> Optional[str]:
    """Extract user_id from various user object formats.

    Handles user objects as:
    - Objects with 'id' attribute
    - Objects with 'user_id' attribute
    - Dictionaries with 'id' or 'user_id' keys

    Args:
        user: User object in various formats

    Returns:
        Extracted user_id as string, or None if not found
    """
    if user is None:
        return None
    if hasattr(user, "id"):
        return str(user.id)
    if hasattr(user, "user_id"):
        return str(user.user_id)
    if isinstance(user, dict):
        return str(user.get("id") or user.get("user_id") or "")
    return None


def _is_request_type(param_annotation: Any) -> bool:
    """Check if a parameter annotation is a Request type.

    Supports both FastAPI and Starlette Request types.

    Args:
        param_annotation: Type annotation to check

    Returns:
        True if the annotation is a Request type
    """
    from fastapi import Request as FastAPIRequest
    from starlette.requests import Request as StarletteRequest

    if param_annotation in (FastAPIRequest, StarletteRequest):
        return True

    if hasattr(param_annotation, "__name__") and param_annotation.__name__ == "Request":
        module_str = str(getattr(param_annotation, "__module__", ""))
        if "fastapi" in module_str or "starlette" in module_str:
            return True

    return False


def _find_request_parameter(func_sig: inspect.Signature) -> Tuple[bool, Optional[str]]:
    """Find Request parameter in function signature.

    Args:
        func_sig: Function signature to inspect

    Returns:
        Tuple of (has_request, param_name)
    """
    for param_name, param in func_sig.parameters.items():
        if _is_request_type(param.annotation):
            return True, param_name
    return False, None


def _extract_request_from_call_args(
    args: Tuple[Any, ...], kwargs: dict[str, Any]
) -> Optional[Any]:
    """Extract Request object from function call arguments.

    Args:
        args: Positional arguments
        kwargs: Keyword arguments

    Returns:
        Request object if found, None otherwise
    """
    # Check positional args
    for arg in args:
        if hasattr(arg, "state") and hasattr(arg, "headers"):
            return arg

    # Check keyword args
    for value in kwargs.values():
        if hasattr(value, "state") and hasattr(value, "headers"):
            return value

    return None


def _inject_user_id_from_request(
    request_obj: Any,
    kwargs: dict[str, Any],
    target_param_names: List[str] = None,
) -> None:
    """Inject user_id from request.state.user into kwargs.

    Modifies kwargs in-place by adding user_id for specified parameter names.

    Args:
        request_obj: Request object with state.user
        kwargs: Dictionary to inject user_id into (modified in-place)
        target_param_names: List of parameter names to inject (defaults to user_id)
    """
    if target_param_names is None:
        target_param_names = ["user_id"]

    if not request_obj or not hasattr(request_obj, "state"):
        return

    if not hasattr(request_obj.state, "user"):
        return

    user = request_obj.state.user
    if not user:
        return

    user_id = _extract_user_id_from_user_object(user)
    if user_id:
        for param_name in target_param_names:
            kwargs[param_name] = user_id


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
                "response",
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
            "response": response,
            "is_function": is_func,
            "kwargs": config_kwargs,
            **kwargs,  # Also include at top level for direct access
        }

        setattr(target, "_jvspatial_endpoint_config", config)  # noqa: B010

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
                    if param_model is not None:
                        wrapped_func = _wrap_function_with_params(
                            func, param_model, methods or ["GET"], path=path
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

    from fastapi import Request as FastAPIRequest
    from starlette.requests import Request as StarletteRequest

    # Determine if this is a GET/HEAD request (query params) or other (body)
    is_get_request = methods and any(m.upper() in ("GET", "HEAD") for m in methods)

    if is_get_request:
        # For GET requests, FastAPI automatically handles query parameters from function signature
        # But we still need to inject user_id from request.state.user if function has user_id parameter
        func_sig = inspect.signature(func)
        if "user_id" in func_sig.parameters:
            has_request, _ = _find_request_parameter(func_sig)

            if has_request:
                # Function already has Request parameter - wrap to inject user_id
                async def wrapped_get_func(*args: Any, **kwargs: Any) -> Any:
                    """Wrapped GET function with user_id injection."""
                    request_obj = _extract_request_from_call_args(args, kwargs)
                    _inject_user_id_from_request(request_obj, kwargs, ["user_id"])
                    return await func(*args, **kwargs)

            else:
                # Function doesn't have Request parameter - add it
                async def wrapped_get_func(  # type: ignore[misc]
                    request: FastAPIRequest, *args: Any, **kwargs: Any
                ) -> Any:
                    """Wrapped GET function with user_id injection."""
                    _inject_user_id_from_request(request, kwargs, ["user_id"])
                    return await func(*args, **kwargs)

                # Update signature to include Request parameter
                # Exclude user_id from signature since it's injected from request.state.user
                new_params = [
                    inspect.Parameter(
                        "request",
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=FastAPIRequest,
                    )
                ] + [p for p in func_sig.parameters.values() if p.name != "user_id"]
                new_sig = inspect.Signature(
                    new_params, return_annotation=func_sig.return_annotation
                )
                wrapped_get_func.__signature__ = new_sig  # type: ignore[attr-defined]
                wrapped_get_func.__annotations__ = {
                    "request": FastAPIRequest,
                    **{k: v for k, v in func.__annotations__.items() if k != "user_id"},
                }

            # Copy metadata
            wrapped_get_func.__name__ = func.__name__
            wrapped_get_func.__doc__ = func.__doc__
            wrapped_get_func.__module__ = func.__module__
            if not has_request:
                # Signature already set above
                pass

            return wrapped_get_func

        # No user_id parameter, return function as-is
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

    # Check if function has Request parameter (needs to be preserved for FastAPI injection)
    has_request_param = False
    request_param_name = None
    for param_name, param in func_sig.parameters.items():
        param_type = param.annotation
        if param_type in (FastAPIRequest, StarletteRequest) or (
            hasattr(param_type, "__name__")
            and param_type.__name__ == "Request"
            and (
                "fastapi" in str(getattr(param_type, "__module__", ""))
                or "starlette" in str(getattr(param_type, "__module__", ""))
            )
        ):
            has_request_param = True
            request_param_name = param_name
            break

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

        # Add Request parameter first if function needs user_id or current_user_id injection
        # (needed to access request.state.user)
        needs_user_id_injection = (
            "user_id" in func_sig.parameters or "current_user_id" in func_sig.parameters
        )
        if needs_user_id_injection and not has_request_param:
            # Add Request parameter for user_id injection
            new_params.append(
                inspect.Parameter(
                    "request",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=FastAPIRequest,
                )
            )
            has_request_param = True
            request_param_name = "request"
        elif has_request_param and request_param_name:
            # Add existing Request parameter
            orig_param = func_sig.parameters[request_param_name]
            new_params.append(
                inspect.Parameter(
                    request_param_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=orig_param.default,
                    annotation=orig_param.annotation,
                )
            )

        # Add path parameters (preserve their original annotations)
        # Note: user_id and current_user_id can be BOTH path params AND injected from auth
        # If they're path params, include them; injection will override if needed
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
        # For DELETE/GET methods, make body optional since it's typically not needed
        if methods and any(m.upper() in ("DELETE", "GET", "HEAD") for m in methods):
            new_params.append(
                inspect.Parameter(
                    "body",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=Body(None),  # Make body optional for DELETE/GET
                    annotation=Optional[param_model],
                )
            )
        else:
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
            # Extract Request parameter if present (FastAPI injects it)
            request_obj = None
            if has_request_param and request_param_name:
                request_obj = kwargs.pop(request_param_name, None)
                # Also check args in case it was passed positionally
                if request_obj is None:
                    request_obj = _extract_request_from_call_args(args, {})

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

            # Remove excluded params (like start_node added by base model)
            for excluded_param in _EXCLUDED_BODY_PARAMS:
                body_data.pop(excluded_param, None)

            # Merge path params (from kwargs) with body params
            combined = {**kwargs, **body_data}

            # Add Request parameter back if it was present in the ORIGINAL function signature
            orig_has_request_param, _ = _find_request_parameter(func_sig)
            if (
                orig_has_request_param
                and request_param_name
                and request_obj is not None
            ):
                combined[request_param_name] = request_obj

            # Inject user_id / current_user_id from request.state.user if function has these parameters
            # and they're not already provided (or are None)
            for param_name in _AUTH_INJECTED_PARAMS:
                if param_name in func_sig.parameters and (
                    param_name not in combined or combined.get(param_name) is None
                ):
                    if request_obj is None:
                        request_obj = _extract_request_from_call_args(args, {})

                    if request_obj:
                        user_id = _extract_user_id_from_user_object(
                            getattr(getattr(request_obj, "state", None), "user", None)
                        )
                        if user_id:
                            combined[param_name] = user_id

            # Filter out None values for required non-path fields
            # Skip validation for user_id and current_user_id if they're injected from auth
            for param_name, param in func_sig.parameters.items():
                if (
                    param_name not in path_params
                    and param_name != request_param_name
                    and param_name not in _AUTH_INJECTED_PARAMS
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

        # Copy function metadata
        wrapped_func.__name__ = func.__name__
        wrapped_func.__doc__ = func.__doc__
        wrapped_func.__module__ = func.__module__

        return wrapped_func

    elif has_path_params and not has_body_params:
        # Only path parameters (and possibly Request) - FastAPI handles these directly
        # But we still need to inject user_id from request.state.user if function has user_id parameter
        if "user_id" in func_sig.parameters:
            has_request, _ = _find_request_parameter(func_sig)

            if has_request:
                # Function already has Request parameter - wrap to inject user_id
                async def wrapped_path_func(*args: Any, **kwargs: Any) -> Any:
                    """Wrapped function with user_id injection for path-only params."""
                    request_obj = _extract_request_from_call_args(args, kwargs)
                    _inject_user_id_from_request(request_obj, kwargs, ["user_id"])
                    return await func(*args, **kwargs)

                # Copy metadata
                wrapped_path_func.__name__ = func.__name__
                wrapped_path_func.__doc__ = func.__doc__
                wrapped_path_func.__module__ = func.__module__
                wrapped_path_func.__signature__ = func_sig  # type: ignore[attr-defined]
                wrapped_path_func.__annotations__ = func.__annotations__

                return wrapped_path_func
            else:
                # Function doesn't have Request parameter - add it
                async def wrapped_path_func(  # type: ignore[misc]
                    request: FastAPIRequest, *args: Any, **kwargs: Any
                ) -> Any:
                    """Wrapped function with user_id injection for path-only params."""
                    _inject_user_id_from_request(request, kwargs, ["user_id"])
                    return await func(*args, **kwargs)

                # Update signature to include Request parameter before path params
                new_params = [
                    inspect.Parameter(
                        "request",
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=FastAPIRequest,
                    )
                ] + list(func_sig.parameters.values())
                new_sig = inspect.Signature(
                    new_params, return_annotation=func_sig.return_annotation
                )
                wrapped_path_func.__signature__ = new_sig  # type: ignore[attr-defined]
                wrapped_path_func.__annotations__ = {
                    "request": FastAPIRequest,
                    **func.__annotations__,
                }

                # Copy metadata
                wrapped_path_func.__name__ = func.__name__
                wrapped_path_func.__doc__ = func.__doc__
                wrapped_path_func.__module__ = func.__module__

                return wrapped_path_func

        # No user_id parameter, return function as-is
        return func
    else:
        # No path parameters - simple body parameter model
        # This branch handles: not has_path_params (with or without body params)
        # Note: Body() in default is required by FastAPI for body params
        # wrapped_func is defined here and used only within this else block

        # Build parameters for the new signature
        new_params = []

        # Add Request parameter if function needs user_id or current_user_id injection
        # (needed to access request.state.user)
        needs_user_id_injection = (
            "user_id" in func_sig.parameters or "current_user_id" in func_sig.parameters
        )
        if needs_user_id_injection and not has_request_param:
            # Add Request parameter for user_id injection
            new_params.append(
                inspect.Parameter(
                    "request",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    annotation=FastAPIRequest,
                )
            )
            has_request_param = True
            request_param_name = "request"
        elif has_request_param and request_param_name:
            # Add existing Request parameter
            orig_param = func_sig.parameters[request_param_name]
            new_params.append(
                inspect.Parameter(
                    request_param_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=orig_param.default,
                    annotation=orig_param.annotation,
                )
            )

        # Add body parameter with the param_model type
        new_params.append(
            inspect.Parameter(
                "params",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=Body(),
                annotation=param_model,
            )
        )

        # Create new signature
        new_sig = inspect.Signature(
            new_params, return_annotation=func_sig.return_annotation
        )

        async def wrapped_func(*args: Any, **kwargs: Any) -> Any:  # type: ignore[assignment,misc]  # noqa: B008
            """Wrapped function with parameter validation."""
            # Extract Request parameter if present (FastAPI injects it)
            request_obj = None
            if has_request_param and request_param_name:
                request_obj = kwargs.pop(request_param_name, None)
                # Also check args in case it was passed positionally
                if request_obj is None:
                    request_obj = _extract_request_from_call_args(args, {})

            # Extract parameters from the model
            params_obj = kwargs.pop("params", None)
            if params_obj is None:
                # Try to get from args
                for arg in args:
                    if not (hasattr(arg, "state") and hasattr(arg, "headers")):
                        params_obj = arg
                        break

            data = {}
            if params_obj is not None:
                if hasattr(params_obj, "model_dump"):
                    data = params_obj.model_dump(
                        exclude_none=False, exclude_unset=False
                    )
                else:
                    data = {
                        k: getattr(params_obj, k)
                        for k in dir(params_obj)
                        if not k.startswith("_")
                    }

            # Remove excluded params (like start_node added by base model)
            for excluded_param in _EXCLUDED_BODY_PARAMS:
                data.pop(excluded_param, None)

            # Add Request parameter back if it was present in the ORIGINAL function signature
            orig_has_request_param, _ = _find_request_parameter(func_sig)
            if (
                orig_has_request_param
                and request_param_name
                and request_obj is not None
            ):
                data[request_param_name] = request_obj

            # Inject user_id / current_user_id from request.state.user if function has these parameters
            # and they're not already provided (or are None)
            for param_name in _AUTH_INJECTED_PARAMS:
                if param_name in func_sig.parameters and (
                    param_name not in data or data.get(param_name) is None
                ):
                    if request_obj is None:
                        request_obj = _extract_request_from_call_args(args, {})

                    if request_obj:
                        user_id = _extract_user_id_from_user_object(
                            getattr(getattr(request_obj, "state", None), "user", None)
                        )
                        if user_id:
                            data[param_name] = user_id

            # Filter out None values for required fields - they should have been validated by Pydantic
            # But ensure we don't pass None for required fields
            # Skip validation for user_id and current_user_id if they're injected from auth
            for param_name, param in func_sig.parameters.items():
                if (
                    param_name != request_param_name
                    and param_name not in _AUTH_INJECTED_PARAMS
                    and param_name in data
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

        # Set the proper signature so FastAPI can introspect it
        wrapped_func.__signature__ = new_sig  # type: ignore[attr-defined]

        # Set annotations to match the signature
        wrapped_func.__annotations__ = {
            param.name: param.annotation for param in new_sig.parameters.values()
        }
        wrapped_func.__annotations__["return"] = new_sig.return_annotation

        # Copy function metadata
        wrapped_func.__name__ = func.__name__
        wrapped_func.__doc__ = func.__doc__
        wrapped_func.__module__ = func.__module__

        return wrapped_func


__all__ = [
    "endpoint",
]
