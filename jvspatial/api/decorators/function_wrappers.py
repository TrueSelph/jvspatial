"""Function wrappers for endpoint parameter handling and auth injection.

Extracted from route.py for separation of concerns. Handles parameter model
validation, auth param injection (user_id, current_user), and Request extraction.
"""

from __future__ import annotations

import inspect
import re
from typing import Any, Callable, Dict, List, Optional, Tuple, Type

from pydantic import BaseModel

# Constants for parameter names that are injected from authentication
AUTH_INJECTED_PARAMS = frozenset(["user_id", "current_user_id"])
AUTH_INJECTED_USER_PARAMS = frozenset(["current_user"])
EXCLUDED_BODY_PARAMS = frozenset(["start_node"])


def _extract_user_id_from_user_object(user: Any) -> Optional[str]:
    """Extract user_id from various user object formats."""
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
    """Check if a parameter annotation is a Request type."""
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
    """Find Request parameter in function signature."""
    for param_name, param in func_sig.parameters.items():
        if _is_request_type(param.annotation):
            return True, param_name
    return False, None


def _extract_request_from_call_args(
    args: Tuple[Any, ...], kwargs: dict[str, Any]
) -> Optional[Any]:
    """Extract Request object from function call arguments."""
    for arg in args:
        if hasattr(arg, "state") and hasattr(arg, "headers"):
            return arg
    for value in kwargs.values():
        if hasattr(value, "state") and hasattr(value, "headers"):
            return value
    return None


def _inject_auth_params_from_request(
    request_obj: Any,
    data: dict[str, Any],
    func_sig: inspect.Signature,
) -> None:
    """Inject user_id, current_user_id, and current_user from request.state.user."""
    if not request_obj or not hasattr(request_obj, "state"):
        return
    if not hasattr(request_obj.state, "user"):
        return
    user = request_obj.state.user
    if not user:
        return

    user_id = _extract_user_id_from_user_object(user)
    if user_id:
        for param_name in AUTH_INJECTED_PARAMS:
            if param_name in func_sig.parameters and (
                param_name not in data or data.get(param_name) is None
            ):
                data[param_name] = user_id

    for param_name in AUTH_INJECTED_USER_PARAMS:
        if param_name in func_sig.parameters and (
            param_name not in data or data.get(param_name) is None
        ):
            data[param_name] = user


def _ensure_auth_injected_when_required(
    data: dict[str, Any],
    func_sig: inspect.Signature,
    auth_required: bool,
) -> None:
    """When auth=True, ensure user_id/current_user_id is set or raise 401."""
    if not auth_required:
        return
    for param_name in AUTH_INJECTED_PARAMS:
        if param_name in func_sig.parameters and (
            data.get(param_name) is None or data.get(param_name) == ""
        ):
            from fastapi import HTTPException

            raise HTTPException(status_code=401, detail="Authentication required")


def wrap_function_auth_only(
    func: Callable,
    methods: Optional[List[str]] = None,
    path: Optional[str] = None,
) -> Callable:
    """Wrap function to inject auth params (user_id, current_user) when no param model."""
    from fastapi import Request as FastAPIRequest

    func_sig = inspect.signature(func)
    has_request, _ = _find_request_parameter(func_sig)
    auth_required = getattr(func, "_jvspatial_endpoint_config", {}).get(
        "auth_required", False
    )

    if has_request:

        async def wrapped(*args: Any, **kwargs: Any) -> Any:
            request_obj = _extract_request_from_call_args(args, kwargs)
            if request_obj is None and has_request:
                for arg in args:
                    if hasattr(arg, "state") and hasattr(arg, "headers"):
                        request_obj = arg
                        break
            _inject_auth_params_from_request(request_obj, kwargs, func_sig)
            _ensure_auth_injected_when_required(kwargs, func_sig, auth_required)
            return await func(*args, **kwargs)

        wrapped.__signature__ = func_sig  # type: ignore[attr-defined]
    else:

        async def wrapped(  # type: ignore[misc]
            request: FastAPIRequest, **kwargs: Any
        ) -> Any:
            _inject_auth_params_from_request(request, kwargs, func_sig)
            _ensure_auth_injected_when_required(kwargs, func_sig, auth_required)
            return await func(**kwargs)

        excluded = AUTH_INJECTED_PARAMS | AUTH_INJECTED_USER_PARAMS
        new_params = [
            inspect.Parameter(
                "request",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=FastAPIRequest,
            )
        ] + [p for p in func_sig.parameters.values() if p.name not in excluded]
        wrapped.__signature__ = inspect.Signature(  # type: ignore[attr-defined]
            new_params, return_annotation=func_sig.return_annotation
        )
        wrapped.__annotations__ = {
            "request": FastAPIRequest,
            **{
                k: v
                for k, v in getattr(func, "__annotations__", {}).items()
                if k not in excluded
            },
        }

    wrapped.__name__ = func.__name__
    wrapped.__doc__ = func.__doc__
    wrapped.__module__ = func.__module__
    if has_request:
        wrapped.__annotations__ = getattr(func, "__annotations__", {})
    if hasattr(func, "_jvspatial_endpoint_config"):
        wrapped._jvspatial_endpoint_config = func._jvspatial_endpoint_config  # type: ignore[attr-defined]
    return wrapped


def wrap_function_with_params(
    func: Callable,
    param_model: Type[BaseModel],
    methods: Optional[List[str]] = None,
    path: Optional[str] = None,
) -> Callable:
    """Wrap function to handle parameter model validation.

    For GET/HEAD requests, parameters are treated as query parameters.
    For other methods, parameters are in the request body.
    """
    from fastapi import Body
    from fastapi import Request as FastAPIRequest
    from starlette.requests import Request as StarletteRequest

    is_get_request = methods and any(m.upper() in ("GET", "HEAD") for m in methods)

    if is_get_request:
        func_sig = inspect.signature(func)
        needs_auth_injection = any(
            p in func_sig.parameters
            for p in (*AUTH_INJECTED_PARAMS, *AUTH_INJECTED_USER_PARAMS)
        )
        if needs_auth_injection:
            has_request, _ = _find_request_parameter(func_sig)
            auth_required = getattr(func, "_jvspatial_endpoint_config", {}).get(
                "auth_required", False
            )

            if has_request:

                async def wrapped_get_func(*args: Any, **kwargs: Any) -> Any:
                    request_obj = _extract_request_from_call_args(args, kwargs)
                    _inject_auth_params_from_request(request_obj, kwargs, func_sig)
                    _ensure_auth_injected_when_required(kwargs, func_sig, auth_required)
                    return await func(*args, **kwargs)

            else:

                async def wrapped_get_func(  # type: ignore[misc]
                    request: FastAPIRequest, **kwargs: Any
                ) -> Any:
                    _inject_auth_params_from_request(request, kwargs, func_sig)
                    _ensure_auth_injected_when_required(kwargs, func_sig, auth_required)
                    return await func(**kwargs)

                excluded = AUTH_INJECTED_PARAMS | AUTH_INJECTED_USER_PARAMS
                new_params = [
                    inspect.Parameter(
                        "request",
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=FastAPIRequest,
                    )
                ] + [p for p in func_sig.parameters.values() if p.name not in excluded]
                new_sig = inspect.Signature(
                    new_params, return_annotation=func_sig.return_annotation
                )
                wrapped_get_func.__signature__ = new_sig  # type: ignore[attr-defined]
                wrapped_get_func.__annotations__ = {
                    "request": FastAPIRequest,
                    **{
                        k: v
                        for k, v in func.__annotations__.items()
                        if k not in (AUTH_INJECTED_PARAMS | AUTH_INJECTED_USER_PARAMS)
                    },
                }

            wrapped_get_func.__name__ = func.__name__
            wrapped_get_func.__doc__ = func.__doc__
            wrapped_get_func.__module__ = func.__module__
            if hasattr(func, "_jvspatial_endpoint_config"):
                wrapped_get_func._jvspatial_endpoint_config = func._jvspatial_endpoint_config  # type: ignore[attr-defined]
            return wrapped_get_func

        return func

    path_params = set()
    if path:
        path_param_matches = re.findall(r"\{(\w+)\}", path)
        path_params = set(path_param_matches)

    func_sig = inspect.signature(func)
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

    has_path_params = path_params and any(
        name in func_sig.parameters for name in path_params
    )
    has_body_params = param_model is not None

    if has_path_params and has_body_params:
        new_params = []
        needs_user_id_injection = any(
            p in func_sig.parameters
            for p in (*AUTH_INJECTED_PARAMS, *AUTH_INJECTED_USER_PARAMS)
        )
        if needs_user_id_injection and not has_request_param:
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
            orig_param = func_sig.parameters[request_param_name]
            new_params.append(
                inspect.Parameter(
                    request_param_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=orig_param.default,
                    annotation=orig_param.annotation,
                )
            )

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

        if methods and any(m.upper() in ("DELETE", "GET", "HEAD") for m in methods):
            new_params.append(
                inspect.Parameter(
                    "body",
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=Body(None),
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

        new_sig = inspect.Signature(
            new_params, return_annotation=func_sig.return_annotation
        )

        async def wrapped_func(*args: Any, **kwargs: Any) -> Any:
            request_obj = None
            if has_request_param and request_param_name:
                request_obj = kwargs.pop(request_param_name, None)
                if request_obj is None:
                    request_obj = _extract_request_from_call_args(args, {})

            body_data = {}
            body_obj = kwargs.pop("body", None)
            if body_obj is not None:
                if isinstance(body_obj, param_model):
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
                    body_data = body_obj

            for excluded_param in EXCLUDED_BODY_PARAMS:
                body_data.pop(excluded_param, None)

            combined = {**kwargs, **body_data}
            orig_has_request_param, _ = _find_request_parameter(func_sig)
            if (
                orig_has_request_param
                and request_param_name
                and request_obj is not None
            ):
                combined[request_param_name] = request_obj

            if request_obj is None:
                request_obj = _extract_request_from_call_args(args, {})
            _inject_auth_params_from_request(request_obj, combined, func_sig)
            _ensure_auth_injected_when_required(
                combined,
                func_sig,
                getattr(func, "_jvspatial_endpoint_config", {}).get(
                    "auth_required", False
                ),
            )

            for param_name, param in func_sig.parameters.items():
                if (
                    param_name not in path_params
                    and param_name != request_param_name
                    and param_name not in AUTH_INJECTED_PARAMS
                    and param_name in combined
                    and combined[param_name] is None
                    and param.default == inspect.Parameter.empty
                ):
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=422,
                        detail=f"Required parameter '{param_name}' cannot be None",
                    )

            return await func(**combined)

        wrapped_func.__signature__ = new_sig  # type: ignore[attr-defined]
        wrapped_func.__annotations__ = {
            param.name: param.annotation for param in new_sig.parameters.values()
        }
        wrapped_func.__annotations__["return"] = new_sig.return_annotation
        wrapped_func.__name__ = func.__name__
        wrapped_func.__doc__ = func.__doc__
        wrapped_func.__module__ = func.__module__
        if hasattr(func, "_jvspatial_endpoint_config"):
            wrapped_func._jvspatial_endpoint_config = func._jvspatial_endpoint_config  # type: ignore[attr-defined]
        return wrapped_func

    elif has_path_params and not has_body_params:
        if any(
            p in func_sig.parameters
            for p in (*AUTH_INJECTED_PARAMS, *AUTH_INJECTED_USER_PARAMS)
        ):
            has_request, _ = _find_request_parameter(func_sig)
            auth_required = getattr(func, "_jvspatial_endpoint_config", {}).get(
                "auth_required", False
            )

            if has_request:

                async def wrapped_path_func(*args: Any, **kwargs: Any) -> Any:
                    request_obj = _extract_request_from_call_args(args, kwargs)
                    _inject_auth_params_from_request(request_obj, kwargs, func_sig)
                    _ensure_auth_injected_when_required(kwargs, func_sig, auth_required)
                    return await func(*args, **kwargs)

                wrapped_path_func.__name__ = func.__name__
                wrapped_path_func.__doc__ = func.__doc__
                wrapped_path_func.__module__ = func.__module__
                wrapped_path_func.__signature__ = func_sig  # type: ignore[attr-defined]
                wrapped_path_func.__annotations__ = func.__annotations__
                if hasattr(func, "_jvspatial_endpoint_config"):
                    wrapped_path_func._jvspatial_endpoint_config = func._jvspatial_endpoint_config  # type: ignore[attr-defined]
                return wrapped_path_func
            else:

                async def wrapped_path_func(  # type: ignore[misc]
                    request: FastAPIRequest, **kwargs: Any
                ) -> Any:
                    _inject_auth_params_from_request(request, kwargs, func_sig)
                    _ensure_auth_injected_when_required(kwargs, func_sig, auth_required)
                    return await func(**kwargs)

                new_params = [
                    inspect.Parameter(
                        "request",
                        inspect.Parameter.POSITIONAL_OR_KEYWORD,
                        annotation=FastAPIRequest,
                    )
                ] + [
                    p
                    for p in func_sig.parameters.values()
                    if p.name not in AUTH_INJECTED_PARAMS
                ]
                new_sig = inspect.Signature(
                    new_params, return_annotation=func_sig.return_annotation
                )
                wrapped_path_func.__signature__ = new_sig  # type: ignore[attr-defined]
                wrapped_path_func.__annotations__ = {
                    "request": FastAPIRequest,
                    **{
                        k: v
                        for k, v in func.__annotations__.items()
                        if k not in AUTH_INJECTED_PARAMS
                    },
                }
                wrapped_path_func.__name__ = func.__name__
                wrapped_path_func.__doc__ = func.__doc__
                wrapped_path_func.__module__ = func.__module__
                if hasattr(func, "_jvspatial_endpoint_config"):
                    wrapped_path_func._jvspatial_endpoint_config = func._jvspatial_endpoint_config  # type: ignore[attr-defined]
                return wrapped_path_func

        return func
    else:
        new_params = []
        needs_user_id_injection = any(
            p in func_sig.parameters
            for p in (*AUTH_INJECTED_PARAMS, *AUTH_INJECTED_USER_PARAMS)
        )
        if needs_user_id_injection and not has_request_param:
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
            orig_param = func_sig.parameters[request_param_name]
            new_params.append(
                inspect.Parameter(
                    request_param_name,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                    default=orig_param.default,
                    annotation=orig_param.annotation,
                )
            )

        new_params.append(
            inspect.Parameter(
                "params",
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                default=Body(),
                annotation=param_model,
            )
        )

        new_sig = inspect.Signature(
            new_params, return_annotation=func_sig.return_annotation
        )

        async def wrapped_func(*args: Any, **kwargs: Any) -> Any:  # type: ignore[assignment,misc]
            request_obj = None
            if has_request_param and request_param_name:
                request_obj = kwargs.pop(request_param_name, None)
                if request_obj is None:
                    request_obj = _extract_request_from_call_args(args, {})

            params_obj = kwargs.pop("params", None)
            if params_obj is None:
                for arg in args:
                    if not (hasattr(arg, "state") and hasattr(arg, "headers")):
                        params_obj = arg
                        break

            data: Dict[str, Any] = {}
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

            for excluded_param in EXCLUDED_BODY_PARAMS:
                data.pop(excluded_param, None)

            orig_has_request_param, _ = _find_request_parameter(func_sig)
            if (
                orig_has_request_param
                and request_param_name
                and request_obj is not None
            ):
                data[request_param_name] = request_obj

            if request_obj is None:
                request_obj = _extract_request_from_call_args(args, {})
            _inject_auth_params_from_request(request_obj, data, func_sig)
            _ensure_auth_injected_when_required(
                data,
                func_sig,
                getattr(func, "_jvspatial_endpoint_config", {}).get(
                    "auth_required", False
                ),
            )

            for param_name, param in func_sig.parameters.items():
                if (
                    param_name != request_param_name
                    and param_name not in AUTH_INJECTED_PARAMS
                    and param_name in data
                    and data[param_name] is None
                    and param.default == inspect.Parameter.empty
                ):
                    from fastapi import HTTPException

                    raise HTTPException(
                        status_code=422,
                        detail=f"Required parameter '{param_name}' cannot be None",
                    )

            return await func(**data)

        wrapped_func.__signature__ = new_sig  # type: ignore[attr-defined]
        wrapped_func.__annotations__ = {
            param.name: param.annotation for param in new_sig.parameters.values()
        }
        wrapped_func.__annotations__["return"] = new_sig.return_annotation
        wrapped_func.__name__ = func.__name__
        wrapped_func.__doc__ = func.__doc__
        wrapped_func.__module__ = func.__module__
        if hasattr(func, "_jvspatial_endpoint_config"):
            wrapped_func._jvspatial_endpoint_config = func._jvspatial_endpoint_config  # type: ignore[attr-defined]
        return wrapped_func
