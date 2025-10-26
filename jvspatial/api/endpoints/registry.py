"""Endpoint registry service for managing API endpoints.

This module provides centralized endpoint registration and tracking,
eliminating duplicate logic across the Server class.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Type, Union

from jvspatial.api.constants import HTTPMethods
from jvspatial.api.exceptions import ResourceConflictError


class EndpointType(str, Enum):
    """Type of endpoint registration."""

    WALKER = "walker"
    FUNCTION = "function"
    CUSTOM = "custom"


@dataclass
class EndpointInfo:
    """Metadata about a registered endpoint.

    Attributes:
        path: URL path for the endpoint
        methods: HTTP methods (GET, POST, etc.)
        endpoint_type: Type of endpoint (walker/function/custom)
        handler: The walker class, function, or handler
        kwargs: Additional route parameters
        is_dynamic: Whether endpoint was registered dynamically
        module: Module where endpoint is defined
        router: Associated router object (if any)
    """

    path: str
    methods: List[str]
    endpoint_type: EndpointType
    handler: Union[Type, Callable]
    kwargs: Dict[str, Any] = field(default_factory=dict)
    is_dynamic: bool = False
    module: Optional[str] = None
    router: Optional[Any] = None

    def __post_init__(self) -> None:
        """Validate and normalize endpoint info after initialization."""
        # Ensure methods is a list
        if not isinstance(self.methods, list):
            self.methods = [self.methods]

        # Normalize methods to uppercase
        self.methods = [m.upper() for m in self.methods]

        # Extract module if not provided
        if self.module is None and hasattr(self.handler, "__module__"):
            self.module = self.handler.__module__

    @property
    def name(self) -> str:
        """Get the name of the endpoint handler.

        Returns:
            Handler name (class or function name)
        """
        if hasattr(self.handler, "__name__"):
            return self.handler.__name__
        return str(self.handler)

    def to_dict(self) -> Dict[str, Any]:
        """Convert endpoint info to dictionary.

        Returns:
            Dictionary representation (safe for serialization)
        """
        return {
            "path": self.path,
            "methods": self.methods,
            "endpoint_type": self.endpoint_type.value,
            "name": self.name,
            "is_dynamic": self.is_dynamic,
            "module": self.module,
            "kwargs": {k: v for k, v in self.kwargs.items() if k != "handler"},
        }


class EndpointRegistryService:
    """Service for managing and tracking API endpoints.

    This service centralizes endpoint registration logic, providing
    methods to register, unregister, query, and track endpoints.

    Example:
        ```python
        registry = EndpointRegistryService()

        # Register walker
        info = registry.register_walker(
            MyWalker, "/process", ["POST"], tags=["processing"]
        )

        # Query endpoints
        all_walkers = registry.list_walkers()
        walker_info = registry.get_walker_info(MyWalker)

        # Check existence
        exists = registry.has_walker(MyWalker)

        # Unregister
        success = registry.unregister_walker(MyWalker)
        ```
    """

    def __init__(self) -> None:
        """Initialize the endpoint registry."""
        # Track registered walkers by class
        self._walker_registry: Dict[Type, EndpointInfo] = {}

        # Track registered functions by callable
        self._function_registry: Dict[Callable, EndpointInfo] = {}

        # Track custom routes by path
        self._custom_routes: Dict[str, List[EndpointInfo]] = {}

        # Track all endpoints by path for fast lookup
        self._path_index: Dict[str, List[EndpointInfo]] = {}

        # Track dynamic endpoints separately
        self._dynamic_endpoints: Set[Union[Type, Callable]] = set()

    def register_walker(
        self,
        walker_class: Type,
        path: str,
        methods: Optional[List[str]] = None,
        is_dynamic: bool = False,
        **kwargs: Any,
    ) -> EndpointInfo:
        """Register a walker endpoint.

        This function works in both sync and async contexts.

        Args:
            walker_class: Walker class to register
            path: URL path for endpoint
            methods: HTTP methods (default: ["POST"])
            is_dynamic: Whether this is a dynamic registration
            **kwargs: Additional route parameters

        Returns:
            EndpointInfo object with registration details

        Raises:
            ResourceConflictError: If walker already registered
        """
        # Check for duplicate registration
        if walker_class in self._walker_registry:
            raise ResourceConflictError(
                message=f"Walker {walker_class.__name__} already registered",
                details={
                    "walker": walker_class.__name__,
                    "existing_path": self._walker_registry[walker_class].path,
                },
            )

        # Create endpoint info
        endpoint_info = EndpointInfo(
            path=path,
            methods=methods or [HTTPMethods.POST],
            endpoint_type=EndpointType.WALKER,
            handler=walker_class,
            kwargs=kwargs,
            is_dynamic=is_dynamic,
        )

        # Register walker
        self._walker_registry[walker_class] = endpoint_info
        self._add_to_path_index(path, endpoint_info)

        # Track if dynamic
        if is_dynamic:
            self._dynamic_endpoints.add(walker_class)

        return endpoint_info

    def register_function(
        self,
        func: Callable,
        path: str,
        methods: Optional[List[str]] = None,
        is_dynamic: bool = False,
        **kwargs: Any,
    ) -> EndpointInfo:
        """Register a function endpoint.

        Works in both sync and async contexts.

        Args:
            func: Function to register
            path: URL path for endpoint
            methods: HTTP methods (default: ["GET"])
            is_dynamic: Whether this is a dynamic registration
            **kwargs: Additional route parameters

        Returns:
            EndpointInfo object with registration details

        Raises:
            ResourceConflictError: If function already registered
        """
        # Check for duplicate registration
        if func in self._function_registry:
            raise ResourceConflictError(
                message=f"Function {func.__name__} already registered",
                details={
                    "function": func.__name__,
                    "existing_path": self._function_registry[func].path,
                },
            )

        # Create endpoint info
        endpoint_info = EndpointInfo(
            path=path,
            methods=methods or [HTTPMethods.GET],
            endpoint_type=EndpointType.FUNCTION,
            handler=func,
            kwargs=kwargs,
            is_dynamic=is_dynamic,
        )

        # Register function
        self._function_registry[func] = endpoint_info
        self._add_to_path_index(path, endpoint_info)

        # Track if dynamic
        if is_dynamic:
            self._dynamic_endpoints.add(func)

        return endpoint_info

    def register_custom_route(
        self,
        path: str,
        handler: Callable,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> EndpointInfo:
        """Register a custom route.

        Works in both sync and async contexts.

        Args:
            path: URL path for route
            handler: Route handler function
            methods: HTTP methods (default: ["GET"])
            **kwargs: Additional route parameters

        Returns:
            EndpointInfo object with registration details
        """
        # Create endpoint info
        endpoint_info = EndpointInfo(
            path=path,
            methods=methods or [HTTPMethods.GET],
            endpoint_type=EndpointType.CUSTOM,
            handler=handler,
            kwargs=kwargs,
        )

        # Register custom route
        if path not in self._custom_routes:
            self._custom_routes[path] = []
        self._custom_routes[path].append(endpoint_info)
        self._add_to_path_index(path, endpoint_info)

        return endpoint_info

    def unregister_walker(self, walker_class: Type) -> bool:
        """Unregister a walker endpoint.

        Args:
            walker_class: Walker class to unregister

        Returns:
            True if unregistered, False if not found
        """
        if walker_class not in self._walker_registry:
            return False

        # Get endpoint info
        endpoint_info = self._walker_registry[walker_class]

        # Remove from registries
        del self._walker_registry[walker_class]
        self._remove_from_path_index(endpoint_info.path, endpoint_info)
        self._dynamic_endpoints.discard(walker_class)

        return True

    def unregister_function(self, func: Callable) -> bool:
        """Unregister a function endpoint.

        Args:
            func: Function to unregister

        Returns:
            True if unregistered, False if not found
        """
        if func not in self._function_registry:
            return False

        # Get endpoint info
        endpoint_info = self._function_registry[func]

        # Remove from registries
        del self._function_registry[func]
        self._remove_from_path_index(endpoint_info.path, endpoint_info)
        self._dynamic_endpoints.discard(func)

        return True

    def unregister_by_path(self, path: str) -> int:
        """Unregister all endpoints at a specific path.

        Args:
            path: URL path to clear

        Returns:
            Number of endpoints removed
        """
        removed_count = 0

        # Remove walkers at this path
        walkers_to_remove = [
            walker_class
            for walker_class, info in self._walker_registry.items()
            if info.path == path
        ]
        for walker_class in walkers_to_remove:
            if self.unregister_walker(walker_class):
                removed_count += 1

        # Remove functions at this path
        functions_to_remove = [
            func for func, info in self._function_registry.items() if info.path == path
        ]
        for func in functions_to_remove:
            if self.unregister_function(func):
                removed_count += 1

        # Remove custom routes at this path
        if path in self._custom_routes:
            removed_count += len(self._custom_routes[path])
            del self._custom_routes[path]

        # Clear path index
        if path in self._path_index:
            del self._path_index[path]

        return removed_count

    def list_walkers(self) -> Dict[str, Dict[str, Any]]:
        """List all registered walker endpoints.

        Returns:
            Dictionary mapping walker names to endpoint info
        """
        return {
            walker_class.__name__: info.to_dict()
            for walker_class, info in self._walker_registry.items()
        }

    def list_functions(self) -> Dict[str, Dict[str, Any]]:
        """List all registered function endpoints.

        Returns:
            Dictionary mapping function names to endpoint info
        """
        return {
            func.__name__: info.to_dict()
            for func, info in self._function_registry.items()
        }

    def list_custom_routes(self) -> Dict[str, List[Dict[str, Any]]]:
        """List all registered custom routes.

        Returns:
            Dictionary mapping paths to route info lists
        """
        return {
            path: [info.to_dict() for info in infos]
            for path, infos in self._custom_routes.items()
        }

    def list_all(self) -> Dict[str, Any]:
        """List all registered endpoints.

        Returns:
            Dictionary with walkers, functions, and custom routes
        """
        return {
            "walkers": self.list_walkers(),
            "functions": self.list_functions(),
            "custom_routes": self.list_custom_routes(),
        }

    def get_walker_info(self, walker_class: Type) -> Optional[EndpointInfo]:
        """Get endpoint information for a walker.

        Args:
            walker_class: Walker class

        Returns:
            EndpointInfo or None if not found
        """
        return self._walker_registry.get(walker_class)

    def get_function_info(self, func: Callable) -> Optional[EndpointInfo]:
        """Get endpoint information for a function.

        Args:
            func: Function callable

        Returns:
            EndpointInfo or None if not found
        """
        return self._function_registry.get(func)

    def get_by_path(self, path: str) -> List[EndpointInfo]:
        """Get all endpoints registered at a path.

        Args:
            path: URL path

        Returns:
            List of EndpointInfo objects
        """
        return self._path_index.get(path, [])

    def has_walker(self, walker_class: Type) -> bool:
        """Check if a walker is registered.

        Args:
            walker_class: Walker class

        Returns:
            True if registered, False otherwise
        """
        return walker_class in self._walker_registry

    def has_function(self, func: Callable) -> bool:
        """Check if a function is registered.

        Args:
            func: Function callable

        Returns:
            True if registered, False otherwise
        """
        return func in self._function_registry

    def has_path(self, path: str) -> bool:
        """Check if any endpoints are registered at a path.

        Args:
            path: URL path

        Returns:
            True if path has endpoints, False otherwise
        """
        return path in self._path_index and len(self._path_index[path]) > 0

    def is_dynamic(self, handler: Union[Type, Callable]) -> bool:
        """Check if an endpoint was registered dynamically.

        Args:
            handler: Walker class or function

        Returns:
            True if dynamic, False otherwise
        """
        return handler in self._dynamic_endpoints

    def get_dynamic_endpoints(self) -> List[EndpointInfo]:
        """Get all dynamically registered endpoints.

        Returns:
            List of dynamic endpoint info
        """
        dynamic_endpoints = []

        for handler in self._dynamic_endpoints:
            # Check if handler is a Type (walker class)
            if isinstance(handler, type) and handler in self._walker_registry:
                dynamic_endpoints.append(self._walker_registry[handler])
            # Check if handler is a Callable (function)
            elif callable(handler) and handler in self._function_registry:
                dynamic_endpoints.append(self._function_registry[handler])

        return dynamic_endpoints

    def search_endpoints(
        self,
        path_pattern: Optional[str] = None,
        method_pattern: Optional[str] = None,
        endpoint_type: Optional[EndpointType] = None,
    ) -> List[EndpointInfo]:
        """Search endpoints by pattern matching.

        Args:
            path_pattern: Path pattern to match (supports wildcards)
            method_pattern: HTTP method pattern to match
            endpoint_type: Type of endpoint to filter by

        Returns:
            List of matching EndpointInfo objects
        """
        import fnmatch

        results = []

        # Get all endpoints
        all_endpoints: list[Any] = []
        all_endpoints.extend(self._walker_registry.values())
        all_endpoints.extend(self._function_registry.values())
        for route_list in self._custom_routes.values():
            all_endpoints.extend(route_list)

        for endpoint_info in all_endpoints:
            # Filter by endpoint type
            if endpoint_type and endpoint_info.endpoint_type != endpoint_type:
                continue

            # Filter by path pattern
            if path_pattern and not fnmatch.fnmatch(endpoint_info.path, path_pattern):
                continue

            # Filter by method pattern
            if method_pattern and not any(
                fnmatch.fnmatch(method, method_pattern)
                for method in endpoint_info.methods
            ):
                continue

            results.append(endpoint_info)

        return results

    def count_endpoints(self) -> Dict[str, int]:
        """Get count of registered endpoints by type.

        Returns:
            Dictionary with counts by type
        """
        custom_count = sum(len(routes) for routes in self._custom_routes.values())
        dynamic_count = len(self._dynamic_endpoints)

        return {
            "walkers": len(self._walker_registry),
            "functions": len(self._function_registry),
            "custom_routes": custom_count,
            "dynamic": dynamic_count,
            "total": len(self._walker_registry)
            + len(self._function_registry)
            + custom_count,
        }

    def clear(self) -> None:
        """Clear all registered endpoints."""
        self._walker_registry.clear()
        self._function_registry.clear()
        self._custom_routes.clear()
        self._path_index.clear()
        self._dynamic_endpoints.clear()

    def _add_to_path_index(self, path: str, endpoint_info: EndpointInfo) -> None:
        """Add endpoint to path index for fast lookup.

        Args:
            path: URL path
            endpoint_info: Endpoint information
        """
        if path not in self._path_index:
            self._path_index[path] = []
        self._path_index[path].append(endpoint_info)

    def _remove_from_path_index(self, path: str, endpoint_info: EndpointInfo) -> None:
        """Remove endpoint from path index.

        Args:
            path: URL path
            endpoint_info: Endpoint information to remove
        """
        if path in self._path_index:
            try:
                self._path_index[path].remove(endpoint_info)
                # Clean up empty path entries
                if not self._path_index[path]:
                    del self._path_index[path]
            except ValueError:
                pass  # Endpoint not in index


__all__ = ["EndpointType", "EndpointInfo", "EndpointRegistryService"]
