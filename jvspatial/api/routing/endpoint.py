"""Router implementation for Walker-based endpoints."""

import inspect
from typing import Any, Callable, Dict, List, Optional, Type, Union, cast

from fastapi import Body, HTTPException
from fastapi.params import Query
from pydantic import ValidationError

from jvspatial.api.response.formatter import (
    format_response as create_formatted_response,
)
from jvspatial.api.response.helpers import ResponseHelper
from jvspatial.core.entities import Node, Walker

from ..parameters import ParameterModelFactory
from .base import BaseRouter

DEFAULT_BODY = Body()


class EndpointRouter(BaseRouter):
    """Router for Walker-based endpoints."""

    def raise_error(self, status: int, message: str) -> None:
        """Raise an HTTP error with the given status code and message.

        Args:
            status: HTTP status code
            message: Error message
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
        """Format a response using the standard format helper as a plain dict."""
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

    def walker_endpoint(
        self,
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Callable[[Type[Walker]], Type[Walker]]:
        """Register a Walker class as an endpoint.

        Args:
            path: URL path
            methods: HTTP methods (default: ["POST"])
            **kwargs: Additional route parameters

        Returns:
            Decorator for registering Walker endpoints
        """
        if methods is None:
            methods = ["POST"]

        def decorator(walker_cls: Type[Walker]) -> Type[Walker]:
            # Generate parameter model
            param_model = ParameterModelFactory.create_model(walker_cls)

            # Handle GET requests differently
            is_get_request = "GET" in methods

            if is_get_request:
                self._register_get_handler(
                    path=path,
                    walker_cls=walker_cls,
                    param_model=param_model,
                    **kwargs,
                )

                # Also register POST handler if there are other methods
                if len(methods) > 1:
                    self._register_post_handler(
                        path=path,
                        walker_cls=walker_cls,
                        param_model=param_model,
                        methods=[m for m in methods if m != "GET"],
                        **kwargs,
                    )
            else:
                self._register_post_handler(
                    path=path,
                    walker_cls=walker_cls,
                    param_model=param_model,
                    methods=methods,
                    **kwargs,
                )

            return walker_cls

        return decorator

    def endpoint(
        self,
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Callable[[Union[Type[Walker], Callable]], Union[Type[Walker], Callable]]:
        """Register a Walker class or function as an endpoint.

        Args:
            path: URL path
            methods: HTTP methods (default: ["POST"])
            **kwargs: Additional route parameters

        Returns:
            Decorator for registering endpoints
        """

        def decorator(
            target: Union[Type[Walker], Callable]
        ) -> Union[Type[Walker], Callable]:
            if isinstance(target, type) and issubclass(target, Walker):
                # Handle Walker class
                return self.walker_endpoint(path, methods=methods, **kwargs)(target)
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
                    start = await Node.get(start_node)
                    if not start:
                        self.raise_error(
                            404,
                            f"Start node '{start_node}' not found",
                        )
                else:
                    start = None

                # Execute walker
                result = await walker.spawn(start=start)

                # Process response
                reports = result.get_report()
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
                    start = await Node.get(start_node)
                    if not start:
                        self.raise_error(
                            404,
                            f"Start node '{start_node}' not found",
                        )
                else:
                    start = None

                # Execute walker
                result = await walker.spawn(start=start)

                # Process response
                reports = result.get_report()
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
        if methods is None:
            methods = ["POST"]

        # Create wrapper with response helper
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Inject response helper
            kwargs["endpoint"] = ResponseHelper()

            if inspect.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)

        # Preserve metadata
        wrapper.__name__ = func.__name__
        wrapper.__doc__ = func.__doc__
        wrapper.__module__ = func.__module__

        # Add route
        self.add_route(
            path=path,
            endpoint=wrapper,
            methods=methods,
            source_obj=func,
            **kwargs,
        )

        return func
