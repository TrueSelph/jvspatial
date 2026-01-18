"""Endpoint discovery service for automatic endpoint registration.

This module provides comprehensive automatic discovery and registration of all
Walker classes and function endpoints decorated with @endpoint across ALL
modules in the application. It scans all loaded modules (excluding jvspatial
and built-in modules) to ensure complete endpoint discovery.
"""

import inspect
import logging
import warnings
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

from jvspatial.api.constants import LogIcons
from jvspatial.core.entities import Walker

try:
    from cryptography.utils import CryptographyDeprecationWarning

    # Filter all CryptographyDeprecationWarning at module level
    warnings.filterwarnings(
        "ignore",
        category=CryptographyDeprecationWarning,
    )
except ImportError:
    pass

# Filter Starlette HTTP status code deprecation warnings
# These warnings are triggered when inspect.getmembers() accesses module attributes
# that import Starlette's deprecated status constants
warnings.filterwarnings(
    "ignore",
    message=".*HTTP_413.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*HTTP_414.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*HTTP_416.*",
    category=DeprecationWarning,
)
warnings.filterwarnings(
    "ignore",
    message=".*HTTP_422.*",
    category=DeprecationWarning,
)
# Also filter all Starlette deprecation warnings
warnings.filterwarnings(
    "ignore",
    category=DeprecationWarning,
    module="starlette.*",
)

if TYPE_CHECKING:
    from jvspatial.api.server import Server


class EndpointDiscoveryService:
    """Service for discovering and registering all endpoints in the application.

    This service comprehensively scans ALL loaded modules in the application
    (excluding jvspatial and built-in modules) to discover Walker classes and
    function endpoints decorated with @endpoint. This ensures complete endpoint
    discovery without requiring specific naming conventions or patterns.

    Example:
        ```python
        discovery = EndpointDiscoveryService(server)

        # Discover all endpoints in the application
        count = discovery.discover_and_register()

        # Enable/disable discovery
        discovery.enable(enabled=False)
        ```
    """

    def __init__(self, server: "Server") -> None:
        """Initialize the endpoint discovery service.

        Args:
            server: Server instance for registration
        """
        self.server = server
        self.enabled = True
        self._patterns: List[str] = []  # Explicit module patterns to scan
        self._logger = logging.getLogger(__name__)

    def discover_and_register(self, patterns: Optional[List[str]] = None) -> int:
        """Discover and register endpoints from explicitly configured modules.

        This method scans only explicitly configured module patterns for security.
        Endpoints are automatically registered via the @endpoint decorator, so
        explicit discovery is only needed for modules imported after server initialization.

        Args:
            patterns: List of module name patterns to scan (e.g., ["myapp.routes", "myapp.api"]).
                     If None, uses patterns configured via enable().

        Returns:
            Number of endpoints discovered and registered
        """
        if not self.enabled:
            return 0

        # Use provided patterns or fall back to configured patterns
        scan_patterns = patterns or getattr(self, "_patterns", [])

        if not scan_patterns:
            # No patterns configured - endpoints are registered via decorators automatically
            # Report on total number of registered endpoints
            all_endpoints = self.server._endpoint_registry.list_all()
            function_count = len(all_endpoints.get("functions", {}))
            walker_count = len(all_endpoints.get("walkers", {}))
            total_count = function_count + walker_count

            if total_count > 0:
                self._logger.debug(
                    f"{LogIcons.DISCOVERY} Using automatic endpoint registration: "
                    f"{total_count} endpoint(s) registered ({function_count} function(s), {walker_count} walker(s))"
                )
            else:
                self._logger.debug(
                    f"{LogIcons.DISCOVERY} Using automatic endpoint registration: no endpoints registered yet"
                )
            return 0

        self._logger.debug(
            f"{LogIcons.DISCOVERY} Scanning {len(scan_patterns)} explicitly configured module(s)..."
        )

        discovered_count = 0
        discovered_endpoints = []

        # Scan only explicitly configured modules
        for pattern in scan_patterns:
            try:
                # Import the module
                import importlib

                module = importlib.import_module(pattern)

                # Discover endpoints in this module
                walkers, functions = self._discover_in_module(module)

                for walker_name, path, methods in walkers:
                    discovered_count += 1
                    discovered_endpoints.append(("walker", walker_name, path, methods))

                for func_name, path, methods in functions:
                    discovered_count += 1
                    discovered_endpoints.append(("function", func_name, path, methods))

            except ImportError as e:
                self._logger.debug(
                    f"{LogIcons.WARNING} Could not import module {pattern}: {e}"
                )
            except Exception as e:
                self._logger.debug(
                    f"{LogIcons.WARNING} Error scanning module {pattern}: {e}"
                )

        # Log discovered endpoints
        if discovered_endpoints:
            # Log individual endpoints in debug mode
            for endpoint_type, name, path, methods in discovered_endpoints:
                methods_str = ", ".join(methods) if methods else "GET"
                self._logger.debug(
                    f"  {LogIcons.SUCCESS} {endpoint_type.capitalize()}: {name} -> {path} [{methods_str}]"
                )
        else:
            self._logger.debug(f"{LogIcons.DISCOVERY} No new endpoints discovered")

        return discovered_count

    def discover_in_module(self, module: Any) -> int:
        """Discover endpoints in a specific module.

        Analyzes module members to find Walker classes and function
        endpoints, then registers them with the server.

        Args:
            module: Python module to analyze

        Returns:
            Number of endpoints discovered and registered
        """
        discovered_walkers, discovered_functions = self._discover_in_module(module)
        return len(discovered_walkers) + len(discovered_functions)

    def _discover_in_module(
        self, module: Any
    ) -> Tuple[List[Tuple[str, str, List[str]]], List[Tuple[str, str, List[str]]]]:
        """Internal method to discover endpoints in a module.

        Args:
            module: Python module to analyze

        Returns:
            Tuple of (walkers, functions) where each is a list of
            (name, path, methods) tuples
        """
        discovered_walkers = []
        discovered_functions = []

        module_name = getattr(module, "__name__", "unknown")

        # Discover walkers
        # Suppress deprecation warnings when accessing module attributes
        # (some modules may import Starlette's deprecated status constants or cryptography deprecated types)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            try:
                from cryptography.utils import CryptographyDeprecationWarning

                warnings.simplefilter("ignore", CryptographyDeprecationWarning)
            except ImportError:
                pass
            members = inspect.getmembers(module)

        for name, obj in members:
            if not (
                inspect.isclass(obj) and issubclass(obj, Walker) and obj is not Walker
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

            # Extract auth-related parameters
            auth_required = endpoint_config.get("auth_required", False)
            permissions = endpoint_config.get("permissions", [])
            roles = endpoint_config.get("roles", [])

            # Extract all route parameters from config (including tags)
            route_kwargs = {
                k: v
                for k, v in endpoint_config.items()
                if k
                not in [
                    "path",
                    "methods",
                    "is_function",
                    "auth_required",
                    "permissions",
                    "roles",
                    "webhook",
                    "signature_required",
                    "webhook_auth",
                    "response",
                    "rate_limit",
                ]
            }

            # Merge in any nested kwargs
            if "kwargs" in endpoint_config:
                route_kwargs.update(endpoint_config["kwargs"])

            # Set authentication attributes on Walker class
            obj._auth_required = auth_required  # type: ignore[attr-defined]
            obj._required_permissions = permissions  # type: ignore[attr-defined]
            obj._required_roles = roles  # type: ignore[attr-defined]

            # Check if already registered - if so, still log it but skip registration
            # (may have been registered via deferred registry or immediate registration)
            if self.server._endpoint_registry.has_walker(obj):
                discovered_walkers.append((name, path, methods))
                self._logger.debug(
                    f"{LogIcons.DISCOVERY} Found already-registered walker: {module_name}.{name} -> {path}"
                )
                continue

            # Register the walker
            try:
                self.server._endpoint_registry.register_walker(
                    obj,
                    path,
                    methods,
                    router=self.server.endpoint_router,
                    auth=auth_required,
                    permissions=permissions,
                    roles=roles,
                    **route_kwargs,
                )

                # Register with endpoint router (pass auth explicitly for OpenAPI security)
                if self.server._is_running:
                    self.server._register_walker_dynamically(
                        obj,
                        path,
                        methods,
                        auth=auth_required,
                        permissions=permissions,
                        roles=roles,
                        **route_kwargs,
                    )
                else:
                    self.server.endpoint_router.endpoint(
                        path,
                        methods,
                        auth=auth_required,
                        permissions=permissions,
                        roles=roles,
                        **route_kwargs,
                    )(obj)

                discovered_walkers.append((name, path, methods))
                # Individual registration logs removed - summary shown in discover_and_register()

            except Exception as e:
                # Already registered or registration failed
                self._logger.debug(f"{LogIcons.WARNING} Skipped walker {name}: {e}")

        # Discover functions
        # Suppress deprecation warnings when accessing module attributes
        # (some modules may import Starlette's deprecated status constants or cryptography deprecated types)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            try:
                from cryptography.utils import CryptographyDeprecationWarning

                warnings.simplefilter("ignore", CryptographyDeprecationWarning)
            except ImportError:
                pass
            module_dict = module.__dict__

        for name, obj in module_dict.items():
            # Skip private attributes
            if name.startswith("_") and name != "_jvspatial_endpoint_config":
                continue

            # Check if this is a function with endpoint config
            if not inspect.isfunction(obj):
                continue

            if not hasattr(obj, "_jvspatial_endpoint_config"):
                continue

            endpoint_config = getattr(obj, "_jvspatial_endpoint_config", {})
            if not endpoint_config.get("is_function", False):
                continue

            path = endpoint_config.get("path")
            if not path:
                continue

            methods = endpoint_config.get("methods", ["GET"])

            # Check if already registered - if so, still log it but skip registration
            # (may have been registered via deferred registry or immediate registration)
            if self.server._endpoint_registry.has_function(obj):
                discovered_functions.append((name, path, methods))
                self._logger.debug(
                    f"{LogIcons.DISCOVERY} Found already-registered function: {module_name}.{name} -> {path}"
                )
                continue

            # Extract all route parameters from config
            route_kwargs = {
                k: v
                for k, v in endpoint_config.items()
                if k
                not in [
                    "path",
                    "methods",
                    "is_function",
                    "kwargs",
                    "webhook",
                    "signature_required",
                    "webhook_auth",
                    "response",
                    "rate_limit",
                ]
            }

            if "kwargs" in endpoint_config:
                route_kwargs.update(endpoint_config["kwargs"])

            # Register the function
            try:
                # Create parameter model if function has parameters
                from jvspatial.api.endpoints.factory import ParameterModelFactory

                param_model = ParameterModelFactory.create_model(obj, path=path)

                # Wrap function with parameter handling if needed
                if param_model is not None:
                    from jvspatial.api.decorators.route import (
                        _wrap_function_with_params,
                    )

                    wrapped_func = _wrap_function_with_params(
                        obj, param_model, methods, path=path
                    )
                else:
                    wrapped_func = obj

                # Extract auth-related parameters
                auth = route_kwargs.pop("auth_required", None)
                if auth is None:
                    auth = route_kwargs.pop("auth", False)
                else:
                    route_kwargs.pop("auth", None)
                permissions = route_kwargs.pop("permissions", [])
                roles = route_kwargs.pop("roles", [])
                response = route_kwargs.pop("response", None)

                # Set auth attributes on the function (consistent with endpoint decorator handling)
                obj._auth_required = auth  # type: ignore[attr-defined]
                wrapped_func._auth_required = auth  # type: ignore[attr-defined]

                # Propagate endpoint config onto the wrapped function
                config = getattr(obj, "_jvspatial_endpoint_config", {})
                if config:
                    config = dict(config)
                    config["is_function"] = True
                    wrapped_func._jvspatial_endpoint_config = config  # type: ignore[attr-defined]  # noqa: B010

                # Register via endpoint router
                self.server.endpoint_router.add_route(
                    path=path,
                    endpoint=wrapped_func,
                    methods=methods,
                    source_obj=obj,  # Use original function as source_obj
                    auth=auth,
                    permissions=permissions,
                    roles=roles,
                    response=response,
                    **route_kwargs,
                )

                # Register with endpoint registry
                self.server._endpoint_registry.register_function(
                    obj,
                    path,
                    methods=methods,
                    route_config={
                        "path": path,
                        "endpoint": wrapped_func,
                        "methods": methods,
                        "auth_required": auth,
                        "permissions": permissions,
                        "roles": roles,
                        **route_kwargs,
                    },
                    auth_required=auth,
                    permissions=permissions,
                    roles=roles,
                    **route_kwargs,
                )

                # Mark server as having auth endpoints if auth is required
                if auth:
                    self.server._has_auth_endpoints = True

                discovered_functions.append((name, path, methods))
                # Individual registration logs removed - summary shown in discover_and_register()

            except Exception as e:
                # Already registered or registration failed
                self._logger.debug(f"{LogIcons.WARNING} Skipped function {name}: {e}")

        return discovered_walkers, discovered_functions

    def enable(
        self, enabled: bool = True, patterns: Optional[List[str]] = None
    ) -> None:
        """Enable or disable endpoint discovery.

        Args:
            enabled: Whether to enable endpoint discovery
            patterns: List of module name patterns to scan (e.g., ["myapp.routes"]).
                     Required for discovery to work - endpoints are otherwise
                     registered automatically via @endpoint decorators.
        """
        self.enabled = enabled
        if patterns is not None:
            self._patterns = patterns
        status = "enabled" if enabled else "disabled"
        pattern_info = (
            f" with {len(self._patterns)} pattern(s)"
            if self._patterns
            else " (no patterns - decorator-based only)"
        )
        self._logger.debug(
            f"{LogIcons.CONFIG} Endpoint discovery {status}{pattern_info}"
        )


__all__ = ["EndpointDiscoveryService"]
