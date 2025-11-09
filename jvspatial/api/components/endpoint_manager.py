"""Endpoint Manager component for handling endpoint registration and management.

This module provides the EndpointManager class that handles all endpoint-related
operations, following the single responsibility principle.
"""

import inspect
import logging
from typing import Any, Callable, Dict, List, Optional, Type, Union

from jvspatial.api.endpoints.registry import EndpointRegistryService
from jvspatial.api.endpoints.response import create_endpoint_helper
from jvspatial.core.entities import Walker


class EndpointManager:
    """Component responsible for managing endpoint registration and operations.

    This class handles all endpoint-related operations including registration,
    unregistration, and endpoint discovery, following the single responsibility
    principle by focusing solely on endpoint management.

    Attributes:
        _endpoint_registry: Central registry for all endpoints
        _logger: Logger instance for endpoint operations
    """

    def __init__(self):
        """Initialize the EndpointManager."""
        self._endpoint_registry = EndpointRegistryService()
        self._endpoint_router = None  # Will be set when needed
        self._logger = logging.getLogger(__name__)

    def register_endpoint(
        self, path: str, methods: Optional[List[str]] = None, **kwargs: Any
    ) -> Callable:
        """Register an endpoint (Walker or function).

        Args:
            path: URL path for the endpoint
            methods: HTTP methods (default: ["POST"] for walkers, ["GET"] for functions)
            **kwargs: Additional route parameters

        Returns:
            Decorator function for endpoints
        """

        def decorator(
            target: Union[Type[Walker], Callable]
        ) -> Union[Type[Walker], Callable]:
            # Handle Walker class
            if inspect.isclass(target) and issubclass(target, Walker):
                return self._register_walker(target, path, methods, **kwargs)

            # Handle function endpoint
            return self._register_function(target, path, methods, **kwargs)

        return decorator

    def _register_walker(
        self,
        walker_class: Type[Walker],
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Type[Walker]:
        """Register a Walker class as an endpoint.

        Args:
            walker_class: Walker class to register
            path: URL path for the endpoint
            methods: HTTP methods (default: ["POST"])
            **kwargs: Additional route parameters

        Returns:
            The registered Walker class
        """
        if self._endpoint_registry.has_walker(walker_class):
            self._logger.warning(f"Walker {walker_class.__name__} already registered")
            return walker_class

        # Register with endpoint registry
        try:
            self._endpoint_registry.register_walker(
                walker_class,
                path,
                methods=methods or ["POST"],
                route_config={
                    "path": path,
                    "walker_class": walker_class,
                    "methods": methods or ["POST"],
                    **kwargs,
                },
                **kwargs,
            )

            self._logger.info(
                f"📝 Registered walker class: {walker_class.__name__} at {path}"
            )

        except Exception as e:
            self._logger.warning(
                f"Walker {walker_class.__name__} already registered: {e}"
            )

        return walker_class

    def _register_function(
        self,
        func: Callable,
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Callable:
        """Register a function as an endpoint.

        Args:
            func: Function to register
            path: URL path for the endpoint
            methods: HTTP methods (default: ["GET"])
            **kwargs: Additional route parameters

        Returns:
            The registered function
        """
        # Create wrapper if endpoint helper is needed
        if "endpoint" in inspect.signature(func).parameters:
            import functools

            @functools.wraps(func)
            async def func_wrapper(*args: Any, **kwargs_inner: Any) -> Any:
                endpoint_helper = create_endpoint_helper(walker_instance=None)
                kwargs_inner["endpoint"] = endpoint_helper
                return (
                    await func(*args, **kwargs_inner)
                    if inspect.iscoroutinefunction(func)
                    else func(*args, **kwargs_inner)
                )

        else:
            func_wrapper = func  # type: ignore[assignment]

        # Register with endpoint registry
        try:
            self._endpoint_registry.register_function(
                func,
                path,
                methods=methods or ["GET"],
                route_config={
                    "path": path,
                    "endpoint": func_wrapper,
                    "methods": methods or ["GET"],
                    **kwargs,
                },
                **kwargs,
            )

            self._logger.info(
                f"📝 Registered function endpoint: {func.__name__} at {path}"
            )

        except Exception as e:
            self._logger.warning(f"Function {func.__name__} already registered: {e}")

        return func

    def register_walker_class(
        self,
        walker_class: Type[Walker],
        path: str,
        methods: Optional[List[str]] = None,
        router: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Programmatically register a walker class.

        Args:
            walker_class: Walker class to register
            path: URL path for the endpoint
            methods: HTTP methods (default: ["POST"])
            router: Optional router instance
            **kwargs: Additional route parameters
        """
        if self._endpoint_registry.has_walker(walker_class):
            self._logger.warning(f"Walker {walker_class.__name__} already registered")
            return

        # Register with endpoint registry
        self._endpoint_registry.register_walker(
            walker_class,
            path,
            methods or ["POST"],
            router=router,
            **kwargs,
        )

        self._logger.info(
            f"📝 Registered walker class: {walker_class.__name__} at {path}"
        )

    async def unregister_walker_class(self, walker_class: Type[Walker]) -> bool:
        """Remove a walker class and its endpoint from the server.

        Args:
            walker_class: Walker class to remove

        Returns:
            True if the walker was successfully removed, False otherwise
        """
        if not self._endpoint_registry.has_walker(walker_class):
            self._logger.warning(f"Walker {walker_class.__name__} not registered")
            return False

        try:
            # Unregister from endpoint registry
            success = self._endpoint_registry.unregister_walker(walker_class)

            if success:
                self._logger.info(
                    f"🗑️ Unregistered walker class: {walker_class.__name__}"
                )

            return success

        except Exception as e:
            self._logger.error(
                f"❌ Failed to unregister walker {walker_class.__name__}: {e}"
            )
            return False

    async def unregister_endpoint(self, endpoint: Union[str, Callable]) -> bool:
        """Remove a function endpoint from the server.

        Args:
            endpoint: Either the path string or the function to remove

        Returns:
            True if the endpoint was successfully removed, False otherwise
        """
        if isinstance(endpoint, str):
            # Remove by path using registry
            path = endpoint
            removed_count = self._endpoint_registry.unregister_by_path(path)

            if removed_count > 0:
                self._logger.info(
                    f"🗑️ Removed {removed_count} endpoints from path {path}"
                )
                return True
            else:
                self._logger.warning(f"No endpoints found at path {path}")
                return False

        elif callable(endpoint):
            # Remove by function reference
            func = endpoint

            if not self._endpoint_registry.has_function(func):
                self._logger.warning(f"Function {func.__name__} not registered")
                return False

            # Unregister from registry
            success = self._endpoint_registry.unregister_function(func)

            if success:
                self._logger.info(f"🗑️ Removed function endpoint: {func.__name__}")

            return success

        else:
            self._logger.error(
                "Invalid endpoint parameter: must be string path or callable function"
            )
            return False

    def list_all_endpoints(self) -> Dict[str, Any]:
        """Get information about all registered endpoints (walkers and functions).

        Returns:
            Dictionary with 'walkers' and 'functions' keys containing endpoint information
        """
        return self._endpoint_registry.list_all()

    def list_walker_endpoints(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all registered walkers.

        Returns:
            Dictionary mapping walker class names to their endpoint information
        """
        return self._endpoint_registry.list_walkers()

    def list_function_endpoints(self) -> Dict[str, Dict[str, Any]]:
        """Get information about all registered function endpoints.

        Returns:
            Dictionary mapping function names to their endpoint information
        """
        return self._endpoint_registry.list_functions()

    def has_endpoint(self, path: str) -> bool:
        """Check if server has any endpoints at the given path.

        Args:
            path: URL path to check

        Returns:
            True if any endpoints exist at the path, False otherwise
        """
        return self._endpoint_registry.has_path(path)

    def get_registry(self) -> EndpointRegistryService:
        """Get the endpoint registry service.

        Returns:
            The endpoint registry service instance
        """
        return self._endpoint_registry

    def get_router(self):
        """Get the endpoint router.

        Returns:
            The endpoint router instance (None if not set)
        """
        return self._endpoint_router


__all__ = ["EndpointManager"]
