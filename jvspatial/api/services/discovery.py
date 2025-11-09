"""Package discovery service for automatic endpoint registration.

This module provides automatic discovery and registration of Walker classes
and function endpoints from installed packages matching specified patterns.
"""

import fnmatch
import importlib
import inspect
import logging
import pkgutil
from typing import TYPE_CHECKING, Any, List, Optional

from jvspatial.api.constants import LogIcons
from jvspatial.core.entities import Walker

from ..endpoints.response import create_endpoint_helper

if TYPE_CHECKING:
    from jvspatial.api.server import Server


class PackageDiscoveryService:
    """Service for discovering and registering endpoints from packages.

    This service scans installed packages matching specified patterns,
    discovers Walker classes and function endpoints, and registers them
    with the server's endpoint registry.

    Example:
        ```python
        discovery = PackageDiscoveryService(server)

        # Discover with default patterns
        count = discovery.discover_and_register()

        # Discover with custom patterns
        count = discovery.discover_and_register(["my_*_walkers"])

        # Enable/disable discovery
        discovery.enable(enabled=True, patterns=["*_api"])
        ```
    """

    def __init__(self, server: "Server") -> None:
        """Initialize the package discovery service.

        Args:
            server: Server instance for registration
        """
        self.server = server
        self.enabled = True
        self.patterns: List[str] = ["*_walkers", "*_endpoints", "*_api"]
        self._logger = logging.getLogger(__name__)

    def discover_and_register(self, patterns: Optional[List[str]] = None) -> int:
        """Discover and register walker endpoints from packages.

        Scans all installed packages matching the specified patterns,
        discovers Walker classes and function endpoints, and registers
        them with the server.

        Args:
            patterns: List of package name patterns (glob-style).
                     If None, uses configured patterns.

        Returns:
            Number of endpoints discovered and registered
        """
        if not self.enabled:
            return 0

        search_patterns = patterns or self.patterns
        discovered_count = 0

        self._logger.info(
            f"{LogIcons.DISCOVERY} Discovering walker packages with patterns: {search_patterns}"
        )

        # Search through installed packages
        for _finder, module_name, ispkg in pkgutil.iter_modules():
            if not ispkg:
                continue

            # Check if module matches any pattern
            if not self._matches_any_pattern(module_name, search_patterns):
                continue

            try:
                # Import the package
                module = importlib.import_module(module_name)
                count = self.discover_in_module(module)
                discovered_count += count

                if count > 0:
                    self._logger.info(
                        f"{LogIcons.PACKAGE} Discovered {count} endpoints in package: {module_name}"
                    )

            except Exception as e:
                self._logger.warning(
                    f"{LogIcons.WARNING} Failed to import package {module_name}: {e}"
                )

        if discovered_count > 0:
            self._logger.info(
                f"{LogIcons.SUCCESS} Total endpoints discovered: {discovered_count}"
            )

        return discovered_count

    def discover_in_module(self, module: Any) -> int:
        """Discover endpoints in a specific module.

        Analyzes module members to find Walker classes and function
        endpoints, then registers them with the server.

        Args:
            module: Python module to analyze

        Returns:
            Number of endpoints discovered in the module
        """
        discovered_count = 0
        discovered_count += self._discover_walkers(module)
        discovered_count += self._discover_functions(module)
        return discovered_count

    def enable(
        self, enabled: bool = True, patterns: Optional[List[str]] = None
    ) -> None:
        """Enable or disable package discovery.

        Args:
            enabled: Whether to enable package discovery
            patterns: Optional new list of package patterns to use
        """
        self.enabled = enabled
        if patterns is not None:
            self.patterns = patterns

        status = "enabled" if enabled else "disabled"
        self._logger.info(f"{LogIcons.CONFIG} Package discovery {status}")

        if enabled and patterns:
            self._logger.info(f"{LogIcons.DISCOVERY} Discovery patterns: {patterns}")

    def _matches_pattern(self, name: str, pattern: str) -> bool:
        """Check if name matches glob pattern.

        Args:
            name: Package name to check
            pattern: Glob-style pattern (e.g., "*_walkers")

        Returns:
            True if name matches pattern, False otherwise
        """
        return fnmatch.fnmatch(name, pattern)

    def _matches_any_pattern(self, name: str, patterns: List[str]) -> bool:
        """Check if name matches any of the provided patterns.

        Args:
            name: Package name to check
            patterns: List of glob-style patterns

        Returns:
            True if name matches any pattern, False otherwise
        """
        return any(self._matches_pattern(name, pattern) for pattern in patterns)

    def _discover_walkers(self, module: Any) -> int:
        """Discover walker classes in module.

        Finds Walker subclasses with endpoint configuration and
        registers them with the server.

        Args:
            module: Python module to search

        Returns:
            Number of walkers discovered
        """
        discovered_count = 0

        for _name, obj in inspect.getmembers(module):
            # Check if this is a Walker class
            if not (
                inspect.isclass(obj)
                and issubclass(obj, Walker)
                and obj is not Walker
                and not self.server._endpoint_registry.has_walker(obj)
            ):
                continue

            # Look for endpoint configuration
            endpoint_config = getattr(obj, "_jvspatial_endpoint_config", None)
            if not endpoint_config:
                continue

            path = endpoint_config.get("path")
            if not path:
                continue

            methods = endpoint_config.get("methods", ["POST"])
            kwargs = endpoint_config.get("kwargs", {})

            # Register the walker
            try:
                self.server._endpoint_registry.register_walker(
                    obj, path, methods, router=self.server.endpoint_router, **kwargs
                )
            except Exception as e:
                self._logger.warning(
                    f"{LogIcons.WARNING} Walker {obj.__name__} already registered: {e}"
                )
                continue

            # Register with endpoint router
            if self.server._is_running:
                self.server._register_walker_dynamically(obj, path, methods, **kwargs)
            else:
                self.server.endpoint_router.endpoint(path, methods, **kwargs)(obj)

            discovered_count += 1

        return discovered_count

    def _discover_functions(self, module: Any) -> int:
        """Discover function endpoints in module.

        Finds functions with endpoint configuration and registers
        them as custom routes.

        Args:
            module: Python module to search

        Returns:
            Number of function endpoints discovered
        """
        discovered_count = 0

        for _name, obj in inspect.getmembers(module):
            # Check if this is a function with endpoint config
            if not (
                inspect.isfunction(obj) and hasattr(obj, "_jvspatial_endpoint_config")
            ):
                continue

            endpoint_config = obj._jvspatial_endpoint_config
            if not endpoint_config.get("is_function"):
                continue

            path = endpoint_config.get("path")
            if not path:
                continue

            methods = endpoint_config.get("methods", ["GET"])
            kwargs = endpoint_config.get("kwargs", {})

            # Create wrapper that injects endpoint helper
            discovered_count += self._register_function_endpoint(
                obj, path, methods, kwargs
            )

        return discovered_count

    def _register_function_endpoint(
        self, func: Any, path: str, methods: List[str], kwargs: dict
    ) -> int:
        """Register a function as an endpoint.

        Creates a wrapper that injects the endpoint helper and
        registers the function as a custom route.

        Args:
            func: Function to register
            path: URL path for endpoint
            methods: HTTP methods
            kwargs: Additional route parameters

        Returns:
            1 if registered, 0 if already exists
        """

        async def endpoint_wrapper(
            *args: Any, func_obj: Any = func, **kwargs_inner: Any
        ) -> Any:
            # Create endpoint helper for function endpoints
            endpoint_helper = create_endpoint_helper(walker_instance=None)

            # Inject endpoint helper into function kwargs
            kwargs_inner["endpoint"] = endpoint_helper

            # Call original function with injected endpoint
            if inspect.iscoroutinefunction(func_obj):
                return await func_obj(*args, **kwargs_inner)
            else:
                return func_obj(*args, **kwargs_inner)

        # Preserve original function metadata
        endpoint_wrapper.__name__ = func.__name__
        endpoint_wrapper.__doc__ = func.__doc__

        # Create route configuration
        route_config = {
            "path": path,
            "endpoint": endpoint_wrapper,
            "methods": methods,
            **kwargs,
        }

        # Check if already registered
        if route_config in self.server._custom_routes:
            return 0

        # Add to custom routes
        self.server._custom_routes.append(route_config)

        # If server is running, add route dynamically
        if self.server._is_running and self.server.app is not None:
            self.server.app.add_api_route(
                path, endpoint_wrapper, methods=methods, **kwargs
            )
            self._logger.info(
                f"{LogIcons.DYNAMIC} Dynamically registered function: {func.__name__} at {path}"
            )

        return 1


__all__ = ["PackageDiscoveryService"]
