"""Consolidated router implementation for jvspatial API.

This module provides all routing functionality including:
- Base router with common functionality
- Auth-aware endpoint protocol
- Walker-based endpoint router
- Function endpoint registration
"""

import inspect
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Protocol,
    Type,
    TypeVar,
    Union,
    cast,
    runtime_checkable,
)

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.params import Query
from pydantic import ValidationError

from jvspatial.core.context import get_default_context
from jvspatial.core.entities import Node, Walker

from .response import ResponseHelper

T = TypeVar("T")
DEFAULT_BODY = Body()


def _get_endpoint_helper():
    """Get endpoint helper instance."""
    return ResponseHelper()


# Create dependency function at module level to avoid B008
def _get_endpoint_dependency():
    """Get endpoint dependency for FastAPI."""
    return ResponseHelper()


# Create the dependency at module level
_endpoint_dependency = Depends(_get_endpoint_dependency)


# ============================================================================
# Protocols
# ============================================================================


@runtime_checkable
class AuthEndpoint(Protocol):
    """Protocol for auth-aware endpoint functions.

    This protocol defines the interface for endpoints that support
    authentication and authorization checks.
    """

    _auth_required: bool
    _required_permissions: List[str]
    _required_roles: List[str]
    __call__: Callable[..., Any]


# ============================================================================
# Base Router
# ============================================================================


class BaseRouter:
    """Base router class with common functionality for all router types.

    Provides core routing capabilities including route registration
    and auth metadata propagation.
    """

    def __init__(self) -> None:
        """Initialize the router with an APIRouter."""
        self.router = APIRouter()

    def add_route(
        self,
        path: str,
        endpoint: Any,
        methods: Optional[List[str]] = None,
        source_obj: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Add a route to the router.

        Args:
            path: URL path for the endpoint
            endpoint: Endpoint handler function
            methods: HTTP methods (defaults to ["POST"])
            source_obj: Source object for metadata propagation
            **kwargs: Additional FastAPI route parameters
        """
        if methods is None:
            methods = ["POST"]

        if source_obj and isinstance(source_obj, AuthEndpoint):
            # Propagate auth metadata to the endpoint function
            endpoint._auth_required = source_obj._auth_required  # type: ignore[attr-defined]
            endpoint._required_permissions = source_obj._required_permissions  # type: ignore[attr-defined]
            endpoint._required_roles = source_obj._required_roles  # type: ignore[attr-defined]

        self.router.add_api_route(
            path=path,
            endpoint=endpoint,
            methods=methods,
            **kwargs,
        )

    def include_router(self, router: APIRouter, **kwargs: Any) -> None:
        """Include another router.

        Args:
            router: Router to include
            **kwargs: Additional FastAPI include_router parameters
        """
        self.router.include_router(router, **kwargs)


# ============================================================================
# Endpoint Router
# ============================================================================


class EndpointRouter(BaseRouter):
    """Router for Walker-based and function endpoints.

    This router handles both Walker class registration and plain function
    endpoints, providing automatic parameter model generation, request
    handling, and response formatting.
    """

    def raise_error(self, status: int, message: str) -> None:
        """Raise an HTTP error with the given status code and message.

        Args:
            status: HTTP status code
            message: Error message

        Raises:
            HTTPException: Always raises with the specified status and message
        """
        raise HTTPException(status_code=status, detail=message)

    def format_response(
        self,
        data: Optional[Dict[str, Any]] = None,
        *,
        success: bool = True,
        message: Optional[str] = None,
        error: Optional[str] = None,
        detail: Optional[str] = None,
        code: Optional[str] = None,
        status: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Format a response using the standard format helper as a plain dict.

        Args:
            data: Response data for successful responses
            success: Whether the request was successful
            message: Optional message for successful responses
            error: Error message for failed responses
            detail: Additional error details
            code: Error code
            status: HTTP status code for error responses

        Returns:
            Formatted response dictionary
        """
        # Import here to avoid circular dependency
        from .response import format_response as create_formatted_response

        resp = create_formatted_response(
            data=data,
            success=success,
            message=message,
            error=error,
            detail=detail,
            code=code,
            status=status,
        )
        # Convert Pydantic model to dict for FastAPI JSON serialization
        resp_dict = resp.model_dump() if hasattr(resp, "model_dump") else dict(resp)
        return cast(Dict[str, Any], resp_dict)

    def endpoint(
        self,
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Callable[[Union[Type[Walker], Callable]], Union[Type[Walker], Callable]]:
        """Register a Walker class or function as an endpoint.

        Args:
            path: URL path
            methods: HTTP methods (default: ["POST"] for walkers, ["GET"] for functions)
            **kwargs: Additional route parameters

        Returns:
            Decorator for registering endpoints

        Example:
            @router.endpoint("/api/users", methods=["GET", "POST"])
            class UserWalker(Walker):
                ...
        """

        def decorator(
            target: Union[Type[Walker], Callable]
        ) -> Union[Type[Walker], Callable]:
            if isinstance(target, type) and issubclass(target, Walker):
                # Handle Walker class
                walker_cls = target
                walker_methods = methods or ["POST"]

                # Generate parameter model
                from .factory import ParameterModelFactory

                param_model = ParameterModelFactory.create_model(walker_cls)

                # Handle GET requests differently
                is_get_request = "GET" in walker_methods

                if is_get_request:
                    self._register_get_handler(
                        path=path,
                        walker_cls=walker_cls,
                        param_model=param_model,
                        **kwargs,
                    )

                    # Also register POST handler if there are other methods
                    if len(walker_methods) > 1:
                        self._register_post_handler(
                            path=path,
                            walker_cls=walker_cls,
                            param_model=param_model,
                            methods=[m for m in walker_methods if m != "GET"],
                            **kwargs,
                        )
                else:
                    self._register_post_handler(
                        path=path,
                        walker_cls=walker_cls,
                        param_model=param_model,
                        methods=walker_methods,
                        **kwargs,
                    )

                return walker_cls
            else:
                # Handle function
                return self._register_function(
                    path=path,
                    func=target,
                    methods=methods,
                    **kwargs,
                )

        return decorator

    def _register_get_handler(
        self,
        path: str,
        walker_cls: Type[Walker],
        param_model: Type[Any],
        **kwargs: Any,
    ) -> None:
        """Register a GET handler for a Walker endpoint.

        Args:
            path: URL path
            walker_cls: Walker class
            param_model: Parameter model
            **kwargs: Additional route parameters
        """
        # Import here to avoid circular dependency
        from .response import ResponseHelper

        # Create query parameters
        params = {}
        for name, field in param_model.model_fields.items():
            default = (
                field.default
                if field.default is not None
                else field.default_factory() if field.default_factory else ...
            )
            params[name] = Query(
                default=default,
                description=field.description,
            )

        async def get_handler(**kwargs) -> Dict[str, Any]:
            """Handle GET request."""
            try:
                # Create walker instance
                start_node = kwargs.pop("start_node", None)
                walker = walker_cls(**kwargs)
                walker.endpoint = ResponseHelper(walker_instance=walker)

                # Handle start node
                if start_node:
                    start = await get_default_context().get(Node, start_node)
                    if not start:
                        self.raise_error(
                            404,
                            f"Start node '{start_node}' not found",
                        )
                else:
                    start = None

                # Execute walker
                if start is None:
                    raise HTTPException(
                        status_code=400, detail="No valid start node provided"
                    )
                result = await walker.spawn(start)

                # Process response
                reports = await result.get_report()
                if not reports:
                    return self.format_response()

                # Merge reports
                response = {}
                for report in reports:
                    if not isinstance(report, dict):
                        continue

                    # Check for error reports
                    if (
                        isinstance(report.get("status"), int)
                        and report["status"] >= 400
                    ):
                        error_msg = str(
                            report.get("error")
                            or report.get("detail")
                            or "Unknown error"
                        )
                        self.raise_error(
                            report["status"],
                            error_msg,
                        )

                    response.update(report)

                return self.format_response(data=response)

            except ValidationError as e:
                self.raise_error(422, str(e))
                raise  # Unreachable, but helps type checkers

        # Dynamically set function signature to expose query params
        import inspect as _inspect

        sig_params = []
        for name, default in params.items():
            sig_params.append(
                _inspect.Parameter(
                    name,
                    _inspect.Parameter.KEYWORD_ONLY,
                    default=default,
                )
            )
        get_handler.__signature__ = _inspect.Signature(parameters=sig_params)  # type: ignore[attr-defined]

        # Add route
        self.add_route(
            path=path,
            endpoint=get_handler,
            methods=["GET"],
            source_obj=walker_cls,
            **kwargs,
        )

    def _register_post_handler(
        self,
        path: str,
        walker_cls: Type[Walker],
        param_model: Type[Any],
        methods: List[str],
        **kwargs: Any,
    ) -> None:
        """Register a POST/PUT/etc handler for a Walker endpoint.

        Args:
            path: URL path
            walker_cls: Walker class
            param_model: Parameter model
            methods: HTTP methods
            **kwargs: Additional route parameters
        """
        # Import here to avoid circular dependency
        from .response import ResponseHelper

        async def post_handler(params: Any = DEFAULT_BODY) -> Dict[str, Any]:
            """Handle POST request."""
            # Copy auth metadata from walker class to handler
            from typing import Any, cast

            handler = cast(Any, post_handler)  # cast to Any to allow attribute setting
            handler._auth_required = getattr(walker_cls, "_auth_required", False)
            handler._required_permissions = getattr(
                walker_cls, "_required_permissions", []
            )
            handler._required_roles = getattr(walker_cls, "_required_roles", [])
            try:
                # Extract parameters
                if isinstance(params, dict):
                    data = params
                elif hasattr(params, "model_dump"):
                    data = params.model_dump()
                else:
                    data = {
                        k: getattr(params, k)
                        for k in dir(params)
                        if not k.startswith("_")
                    }

                # Handle start node
                start_node = data.pop("start_node", None)

                # Create walker instance
                walker = walker_cls(**data)
                walker.endpoint = ResponseHelper(walker_instance=walker)

                # Handle start node
                if start_node:
                    start = await get_default_context().get(Node, start_node)
                    if not start:
                        self.raise_error(
                            404,
                            f"Start node '{start_node}' not found",
                        )
                else:
                    start = None

                # Execute walker
                if start is None:
                    raise HTTPException(
                        status_code=400, detail="No valid start node provided"
                    )
                result = await walker.spawn(start)

                # Process response
                reports = await result.get_report()
                if not reports:
                    return self.format_response()

                # Merge reports
                response = {}
                for report in reports:
                    if not isinstance(report, dict):
                        continue

                    # Check for error reports
                    if (
                        isinstance(report.get("status"), int)
                        and report["status"] >= 400
                    ):
                        error_msg = str(
                            report.get("error")
                            or report.get("detail")
                            or "Unknown error"
                        )
                        self.raise_error(
                            report["status"],
                            error_msg,
                        )

                    response.update(report)

                return self.format_response(data=response)

            except ValidationError as e:
                self.raise_error(422, str(e))
                raise  # Unreachable, but helps type checkers

        # Add route
        post_handler.__annotations__["params"] = param_model

        self.add_route(
            path=path,
            endpoint=post_handler,
            methods=methods,
            source_obj=walker_cls,
            **kwargs,
        )

    def _register_function(
        self,
        path: str,
        func: Callable,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Callable:
        """Register a function as an endpoint.

        Args:
            path: URL path
            func: Function to register
            methods: HTTP methods (default: ["POST"])
            **kwargs: Additional route parameters

        Returns:
            Registered function
        """
        # Import here to avoid circular dependency
        from .response import ResponseHelper

        if methods is None:
            methods = ["POST"]

        # Use the original function directly to avoid FastAPI seeing wrapper parameters
        # We'll handle endpoint injection through FastAPI's dependency system
        func_params = inspect.signature(func).parameters
        if "endpoint" in func_params:
            # Create a new function that uses FastAPI's dependency injection
            # This preserves the original function signature for OpenAPI
            async def endpoint_injected_func(
                *,
                endpoint: ResponseHelper = _endpoint_dependency,
                **kwargs: Any,
            ) -> Any:
                # Call the original function with the injected endpoint
                if inspect.iscoroutinefunction(func):
                    return await func(endpoint=endpoint, **kwargs)
                else:
                    return func(endpoint=endpoint, **kwargs)

            # Copy all metadata from the original function
            endpoint_injected_func.__name__ = func.__name__
            endpoint_injected_func.__doc__ = func.__doc__
            endpoint_injected_func.__module__ = func.__module__
            endpoint_injected_func.__annotations__ = func.__annotations__
            endpoint_injected_func.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]

            selected_endpoint = endpoint_injected_func
        else:
            selected_endpoint = func

        # Add route
        self.add_route(
            path=path,
            endpoint=selected_endpoint,
            methods=methods,
            source_obj=func,
            **kwargs,
        )

        return func


__all__ = [
    "AuthEndpoint",
    "BaseRouter",
    "EndpointRouter",
]
