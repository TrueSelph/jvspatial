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

        # Check if endpoint has authentication configuration
        endpoint_config = getattr(endpoint, "_jvspatial_endpoint_config", None)
        source_config = (
            getattr(source_obj, "_jvspatial_endpoint_config", None)
            if source_obj is not None
            else None
        )
        auth_required = kwargs.get("auth", False) or (
            endpoint_config and endpoint_config.get("auth_required", False)
        )

        # Handle response schema: read from endpoint config, else fallback to source object config (e.g., walker class)
        response_schema = None
        from jvspatial.api.endpoints.response import ResponseSchema

        response_def = None
        if endpoint_config and endpoint_config.get("response"):
            response_def = endpoint_config.get("response")
        elif source_config and source_config.get("response"):
            response_def = source_config.get("response")
        if isinstance(response_def, ResponseSchema):
            # Use a stable name if possible
            model_name = f"{getattr(source_obj, '__name__', getattr(endpoint, '__name__', 'Response'))}Response"
            response_schema = response_def.to_pydantic_model(model_name)

        # Prepare FastAPI route parameters
        fastapi_kwargs = {
            k: v
            for k, v in kwargs.items()
            if k
            not in [
                "auth",
                "permissions",
                "roles",
                "webhook",
                "signature_required",
                "response",
            ]
        }

        # Extract summary and description from docstring if not explicitly provided
        # FastAPI uses __doc__ automatically, but we should also extract summary/description
        # for better OpenAPI documentation. Prefer endpoint's docstring, then source_obj's docstring
        if not fastapi_kwargs.get("summary") and not fastapi_kwargs.get("description"):
            # Prefer endpoint's docstring (which may have been set from source_obj)
            docstring = getattr(endpoint, "__doc__", None)
            # If endpoint doesn't have a docstring, try source_obj (e.g., Walker class)
            if not docstring and source_obj:
                docstring = getattr(source_obj, "__doc__", None)

            if docstring:
                # Clean and split docstring into lines
                # Remove common indentation and empty lines
                doc_lines = [
                    line.strip()
                    for line in docstring.strip().split("\n")
                    if line.strip()
                ]
                if doc_lines:
                    # First non-empty line is the summary
                    fastapi_kwargs["summary"] = doc_lines[0]
                    # Rest is the description
                    if len(doc_lines) > 1:
                        fastapi_kwargs["description"] = "\n".join(doc_lines[1:])
                    elif len(doc_lines[0]) > 120:
                        # If first line is very long, use it as description and create a shorter summary
                        fastapi_kwargs["summary"] = doc_lines[0][:120] + "..."
                        fastapi_kwargs["description"] = doc_lines[0]

        # Add response model if defined
        if response_schema:
            fastapi_kwargs["response_model"] = response_schema

        # Add security requirements for OpenAPI if auth is required
        if auth_required:
            from jvspatial.api.auth.openapi_config import (
                get_endpoint_security_requirements,
            )

            permissions = (
                kwargs.get("permissions", [])
                or (endpoint_config and endpoint_config.get("permissions", []))
                or []
            )
            roles = (
                kwargs.get("roles", [])
                or (endpoint_config and endpoint_config.get("roles", []))
                or []
            )

            # Add security to the route
            fastapi_kwargs["responses"] = fastapi_kwargs.get("responses", {})
            fastapi_kwargs["responses"].update(
                {
                    401: {"description": "Authentication required"},
                    403: {"description": "Insufficient permissions"},
                }
            )

            # Add security requirements to OpenAPI extra
            security_requirements = get_endpoint_security_requirements(
                permissions=permissions, roles=roles
            )
            fastapi_kwargs["openapi_extra"] = fastapi_kwargs.get("openapi_extra", {})
            fastapi_kwargs["openapi_extra"]["security"] = security_requirements

        self.router.add_api_route(
            path=path,
            endpoint=endpoint,
            methods=methods,
            **fastapi_kwargs,
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

        # Only pass supported arguments to the simple formatter.
        if success:
            resp = create_formatted_response(
                data=data,
                message=message,
                success=True,
            )
            return cast(Dict[str, Any], resp)

        # Error path: construct structured error dict directly
        error_resp: Dict[str, Any] = {"success": False}
        if error is not None:
            error_resp["error"] = error
        if detail is not None:
            error_resp["detail"] = detail
        if code is not None:
            error_resp["code"] = code
        if status is not None:
            error_resp["status"] = status
        if message is not None:
            error_resp["message"] = message
        if data is not None:
            error_resp["data"] = data
        return error_resp

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
            target: Union[Type[Walker], Callable],
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

        # Get Walker class docstring for the handler function
        walker_docstring = (
            (walker_cls.__doc__ or f"Execute {walker_cls.__name__} Walker")
            if walker_cls.__doc__
            else f"Execute {walker_cls.__name__} Walker"
        )

        async def get_handler(**kwargs) -> Dict[str, Any]:
            try:
                # Create walker instance
                start_node = kwargs.pop("start_node", None)
                walker = walker_cls(**kwargs)
                walker.endpoint = ResponseHelper(walker_instance=walker)

                # Execute walker
                # Check if walker has direct execution methods (API-style walkers)
                if hasattr(walker, "analyze_users"):
                    # Direct method execution for user analysis walkers
                    result = await walker.analyze_users()
                    # If a response schema is defined, return the flat result to match the model
                    has_response_schema = bool(
                        getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                            "response"
                        )
                    )
                    return (
                        result
                        if has_response_schema
                        else self.format_response(data=result)
                    )
                elif hasattr(walker, "process_documents"):
                    # Direct method execution for document processing walkers
                    result = await walker.process_documents()
                    has_response_schema = bool(
                        getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                            "response"
                        )
                    )
                    return (
                        result
                        if has_response_schema
                        else self.format_response(data=result)
                    )
                elif hasattr(walker, "analyze_products"):
                    # Direct method execution for product analysis walkers
                    result = await walker.analyze_products()
                    has_response_schema = bool(
                        getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                            "response"
                        )
                    )
                    return (
                        result
                        if has_response_schema
                        else self.format_response(data=result)
                    )
                elif hasattr(walker, "generate_report"):
                    # Direct method execution for report generation walkers
                    result = await walker.generate_report()
                    has_response_schema = bool(
                        getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                            "response"
                        )
                    )
                    return (
                        result
                        if has_response_schema
                        else self.format_response(data=result)
                    )
                else:
                    # Only resolve start node when performing traditional traversal
                    if start_node:
                        start = await get_default_context().get(Node, start_node)
                        if not start:
                            self.raise_error(
                                404,
                                f"Start node '{start_node}' not found",
                            )
                    else:
                        # Default to root node if no start node provided
                        start = await get_default_context().get(Node, "n:Root:root")
                        if not start:
                            self.raise_error(
                                500,
                                "Root node not found - database may not be properly initialized",
                            )
                    # Traditional graph traversal walker
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

                        # Check for error reports - look for status field or error field
                        status = report.get("status")
                        error_msg = report.get("error") or report.get("detail")

                        # Determine error status code
                        if isinstance(status, int) and status >= 400:
                            # Explicit status code in report
                            error_status = status
                        elif error_msg:
                            # Error message present - determine status from context
                            if report.get("conflict"):
                                error_status = 409  # Conflict
                            elif report.get("not_found"):
                                error_status = 404  # Not Found
                            elif report.get("unauthorized"):
                                error_status = 401  # Unauthorized
                            elif report.get("forbidden"):
                                error_status = 403  # Forbidden
                            elif report.get("validation_error"):
                                error_status = 422  # Unprocessable Entity
                            else:
                                error_status = (
                                    400  # Bad Request (default for error messages)
                                )
                        else:
                            error_status = None

                        # If this is an error report, raise it before validation
                        if error_status is not None:
                            # Extract error message - use the error field from report
                            error_message = (
                                str(error_msg) if error_msg else "An error occurred"
                            )
                            # Don't append details to message - error handler will format consistently
                            # Just pass the clean error message
                            self.raise_error(error_status, error_message)

                        response.update(report)

                    has_response_schema = bool(
                        getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                            "response"
                        )
                    )
                    return (
                        response
                        if has_response_schema
                        else self.format_response(data=response)
                    )

            except HTTPException:
                # Re-raise HTTPException as-is to preserve status code
                raise
            except ValidationError as e:
                # Extract useful information from ValidationError
                error_details = []
                if hasattr(e, "errors"):
                    for err in e.errors():
                        field_path = " -> ".join(str(loc) for loc in err.get("loc", []))
                        error_type = err.get("type", "validation_error")
                        error_msg = err.get("msg", "Validation failed")
                        error_details.append(
                            f"{field_path}: {error_msg} ({error_type})"
                        )

                error_message = "Validation failed"
                if error_details:
                    error_message = "Validation failed: " + "; ".join(error_details)
                elif str(e):
                    error_message = f"Validation failed: {str(e)}"

                self.raise_error(422, error_message)
                raise  # Unreachable, but helps type checkers
            except Exception as e:  # pragma: no cover
                # Ensure walker endpoint errors are consistently reported
                self.raise_error(500, f"Walker execution error: {e}")
                raise

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

        # Set the docstring and name from Walker class
        get_handler.__doc__ = walker_docstring
        get_handler.__name__ = f"{walker_cls.__name__}_endpoint"

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
        param_model: Optional[Type[Any]],
        methods: List[str],
        **kwargs: Any,
    ) -> None:
        """Register a POST/PUT/etc handler for a Walker endpoint.

        Args:
            path: URL path
            walker_cls: Walker class
            param_model: Parameter model (None if no parameters)
            methods: HTTP methods
            **kwargs: Additional route parameters
        """
        # Import here to avoid circular dependency
        from .response import ResponseHelper

        if param_model is not None:
            # Walker has parameters - create handler with parameter model
            # Get Walker class docstring for the handler function
            walker_docstring = (
                (walker_cls.__doc__ or f"Execute {walker_cls.__name__} Walker")
                if walker_cls.__doc__
                else f"Execute {walker_cls.__name__} Walker"
            )

            # Create handler function - docstring will be set from Walker class
            # We'll set the proper type annotation after function creation
            async def post_handler(
                params: Any = DEFAULT_BODY,  # type: ignore[assignment]
            ) -> Dict[str, Any]:  # noqa: B008
                # Copy auth metadata from walker class to handler
                from typing import Any, cast

                handler = cast(
                    Any, post_handler
                )  # cast to Any to allow attribute setting

                handler._auth_required = getattr(walker_cls, "_auth_required", False)
                handler._required_permissions = getattr(
                    walker_cls, "_required_permissions", []
                )
                handler._required_roles = getattr(walker_cls, "_required_roles", [])

                # Also set the endpoint configuration for OpenAPI
                handler._jvspatial_endpoint_config = {
                    "path": path,
                    "methods": methods,
                    "auth_required": getattr(walker_cls, "_auth_required", False),
                    "permissions": getattr(walker_cls, "_required_permissions", []),
                    "roles": getattr(walker_cls, "_required_roles", []),
                    "response": getattr(
                        walker_cls, "_jvspatial_endpoint_config", {}
                    ).get("response"),
                    "is_function": False,
                }

                handler.__name__ = f"{walker_cls.__name__}_endpoint"

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
                    start_node = (
                        data.pop("start_node", None) if isinstance(data, dict) else None
                    )

                    # Create walker instance
                    walker = walker_cls(**data)
                    walker.endpoint = ResponseHelper(walker_instance=walker)

                    # Execute walker
                    # Check if walker has direct execution methods (API-style walkers)
                    if hasattr(walker, "analyze_users"):
                        # Direct method execution for user analysis walkers
                        result = await walker.analyze_users()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    elif hasattr(walker, "process_documents"):
                        # Direct method execution for document processing walkers
                        result = await walker.process_documents()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    elif hasattr(walker, "check_status"):
                        # Direct method execution for status check walkers
                        result = await walker.check_status()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    elif hasattr(walker, "analyze_products"):
                        # Direct method execution for product analysis walkers
                        result = await walker.analyze_products()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    elif hasattr(walker, "generate_report"):
                        # Direct method execution for report generation walkers
                        result = await walker.generate_report()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    else:
                        # Only resolve start node when performing traditional traversal
                        if start_node:
                            start = await get_default_context().get(Node, start_node)
                            if not start:
                                self.raise_error(
                                    404,
                                    f"Start node '{start_node}' not found",
                                )
                        else:
                            # Default to root node if no start node provided
                            start = await get_default_context().get(Node, "n:Root:root")
                            if not start:
                                self.raise_error(
                                    500,
                                    "Root node not found - database may not be properly initialized",
                                )
                        # Traditional graph traversal walker
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

                            # Check for error reports - look for status field or error field
                            status = report.get("status")
                            error_msg = report.get("error") or report.get("detail")

                            # Determine error status code
                            if isinstance(status, int) and status >= 400:
                                # Explicit status code in report
                                error_status = status
                            elif error_msg:
                                # Error message present - determine status from context
                                if report.get("conflict"):
                                    error_status = 409  # Conflict
                                elif report.get("not_found"):
                                    error_status = 404  # Not Found
                                elif report.get("unauthorized"):
                                    error_status = 401  # Unauthorized
                                elif report.get("forbidden"):
                                    error_status = 403  # Forbidden
                                elif report.get("validation_error"):
                                    error_status = 422  # Unprocessable Entity
                                else:
                                    error_status = (
                                        400  # Bad Request (default for error messages)
                                    )
                            else:
                                error_status = None

                            # If this is an error report, raise it before validation
                            if error_status is not None:
                                error_message = str(error_msg or "An error occurred")
                                # Include additional details if available
                                details = {
                                    k: v
                                    for k, v in report.items()
                                    if k not in ("status", "error", "detail")
                                }
                                if details:
                                    error_message += f" | Details: {details}"
                                self.raise_error(error_status, error_message)

                            response.update(report)

                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            response
                            if has_response_schema
                            else self.format_response(data=response)
                        )

                except HTTPException:
                    # Re-raise HTTPException as-is to preserve status code
                    raise
                except ValidationError as e:
                    # Extract useful information from ValidationError
                    error_details = []
                    if hasattr(e, "errors"):
                        for err in e.errors():
                            field_path = " -> ".join(
                                str(loc) for loc in err.get("loc", [])
                            )
                            error_type = err.get("type", "validation_error")
                            error_msg = err.get("msg", "Validation failed")
                            error_details.append(
                                f"{field_path}: {error_msg} ({error_type})"
                            )

                    error_message = "Validation failed"
                    if error_details:
                        error_message = "Validation failed: " + "; ".join(error_details)
                    elif str(e):
                        error_message = f"Validation failed: {str(e)}"

                    self.raise_error(422, error_message)
                    raise  # Unreachable, but helps type checkers
                except Exception as e:  # pragma: no cover
                    # Ensure walker endpoint errors are consistently reported
                    self.raise_error(500, f"Walker execution error: {e}")
                    raise

            # Set the docstring from Walker class - MUST be done outside the function
            # so FastAPI can read it when the route is registered
            post_handler.__doc__ = walker_docstring
            post_handler.__name__ = f"{walker_cls.__name__}_endpoint"

            # Explicitly set annotations so FastAPI can introspect the type
            # This MUST be done outside the function body so FastAPI can read it during registration
            # This allows FastAPI to generate proper request body schema with field definitions
            post_handler.__annotations__ = {
                "params": param_model,
                "return": Dict[str, Any],
            }

        else:
            # Walker has no parameters - create handler without parameter model
            # Get Walker class docstring for the handler function
            walker_docstring = (
                (walker_cls.__doc__ or f"Execute {walker_cls.__name__} Walker")
                if walker_cls.__doc__
                else f"Execute {walker_cls.__name__} Walker"
            )

            async def post_handler() -> Dict[str, Any]:  # type: ignore[misc]
                # Copy auth metadata from walker class to handler
                from typing import Any, cast

                handler = cast(
                    Any, post_handler
                )  # cast to Any to allow attribute setting
                handler._auth_required = getattr(walker_cls, "_auth_required", False)
                handler._required_permissions = getattr(
                    walker_cls, "_required_permissions", []
                )
                handler._required_roles = getattr(walker_cls, "_required_roles", [])

                # Also set the endpoint configuration for OpenAPI
                handler._jvspatial_endpoint_config = {
                    "path": path,
                    "methods": methods,
                    "auth_required": getattr(walker_cls, "_auth_required", False),
                    "permissions": getattr(walker_cls, "_required_permissions", []),
                    "roles": getattr(walker_cls, "_required_roles", []),
                    "response": getattr(
                        walker_cls, "_jvspatial_endpoint_config", {}
                    ).get("response"),
                    "is_function": False,
                }

                handler.__name__ = f"{walker_cls.__name__}_endpoint"

                try:
                    # Create walker instance with no parameters
                    walker = walker_cls()
                    walker.endpoint = ResponseHelper(walker_instance=walker)

                    # Execute walker
                    # Check if walker has direct execution methods (API-style walkers)
                    if hasattr(walker, "analyze_users"):
                        # Direct method execution for user analysis walkers
                        result = await walker.analyze_users()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    elif hasattr(walker, "process_documents"):
                        # Direct method execution for document processing walkers
                        result = await walker.process_documents()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    elif hasattr(walker, "check_status"):
                        # Direct method execution for status check walkers
                        result = await walker.check_status()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    elif hasattr(walker, "analyze_products"):
                        # Direct method execution for product analysis walkers
                        result = await walker.analyze_products()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    elif hasattr(walker, "generate_report"):
                        # Direct method execution for report generation walkers
                        result = await walker.generate_report()
                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            result
                            if has_response_schema
                            else self.format_response(data=result)
                        )
                    else:
                        # Default to root node only when performing traversal
                        start = await get_default_context().get(Node, "n:Root:root")
                        if not start:
                            self.raise_error(
                                500,
                                "Root node not found - database may not be properly initialized",
                            )
                        # Traditional graph traversal walker
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

                            # Check for error reports - look for status field or error field
                            status = report.get("status")
                            error_msg = report.get("error") or report.get("detail")

                            # Determine error status code
                            if isinstance(status, int) and status >= 400:
                                # Explicit status code in report
                                error_status = status
                            elif error_msg:
                                # Error message present - determine status from context
                                if report.get("conflict"):
                                    error_status = 409  # Conflict
                                elif report.get("not_found"):
                                    error_status = 404  # Not Found
                                elif report.get("unauthorized"):
                                    error_status = 401  # Unauthorized
                                elif report.get("forbidden"):
                                    error_status = 403  # Forbidden
                                elif report.get("validation_error"):
                                    error_status = 422  # Unprocessable Entity
                                else:
                                    error_status = (
                                        400  # Bad Request (default for error messages)
                                    )
                            else:
                                error_status = None

                            # If this is an error report, raise it before validation
                            if error_status is not None:
                                error_message = str(error_msg or "An error occurred")
                                # Include additional details if available
                                details = {
                                    k: v
                                    for k, v in report.items()
                                    if k not in ("status", "error", "detail")
                                }
                                if details:
                                    error_message += f" | Details: {details}"
                                self.raise_error(error_status, error_message)

                            response.update(report)

                        has_response_schema = bool(
                            getattr(walker_cls, "_jvspatial_endpoint_config", {}).get(
                                "response"
                            )
                        )
                        return (
                            response
                            if has_response_schema
                            else self.format_response(data=response)
                        )

                except ValidationError as e:
                    # Extract useful information from ValidationError
                    error_details = []
                    if hasattr(e, "errors"):
                        for err in e.errors():
                            field_path = " -> ".join(
                                str(loc) for loc in err.get("loc", [])
                            )
                            error_type = err.get("type", "validation_error")
                            error_msg = err.get("msg", "Validation failed")
                            error_details.append(
                                f"{field_path}: {error_msg} ({error_type})"
                            )

                    error_message = "Validation failed"
                    if error_details:
                        error_message = "Validation failed: " + "; ".join(error_details)
                    elif str(e):
                        error_message = f"Validation failed: {str(e)}"

                    self.raise_error(422, error_message)
                    raise  # Unreachable, but helps type checkers

            # Set the docstring from Walker class - MUST be done outside the function
            # so FastAPI can read it when the route is registered
            post_handler.__doc__ = walker_docstring
            post_handler.__name__ = f"{walker_cls.__name__}_endpoint"

        # Add route
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
