"""Global deferred endpoint registry for automatic endpoint discovery.

This module provides a thread-safe global registry that stores endpoint
decorations that occur before a Server instance is available. When a Server
is initialized, it automatically flushes all deferred endpoints to register
them, ensuring endpoints work regardless of import order.
"""

import inspect
import logging
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Type, Union, cast

if TYPE_CHECKING:
    from jvspatial.api.server import Server

# Thread-safe global registry
_deferred_endpoints: List["DeferredEndpoint"] = []
_registry_lock = threading.Lock()
_logger = logging.getLogger(__name__)


@dataclass
class DeferredEndpoint:
    """Represents an endpoint that was decorated before server initialization.

    Attributes:
        target: The function or walker class that was decorated
        config: The endpoint configuration dictionary
        is_walker: Whether this is a walker class (True) or function (False)
    """

    target: Union[Callable, Type]
    config: Dict[str, Any]
    is_walker: bool = False

    def __post_init__(self) -> None:
        """Determine if target is a walker class if not explicitly set."""
        if not self.is_walker:
            self.is_walker = inspect.isclass(self.target)


def register_deferred_endpoint(
    target: Union[Callable, Type], config: Dict[str, Any]
) -> None:
    """Register an endpoint to be registered later when a server is available.

    This function is called by the @endpoint decorator when no server is
    currently available in the context. The endpoint will be automatically
    registered when flush_deferred_endpoints() is called.

    Args:
        target: The function or walker class that was decorated
        config: The endpoint configuration dictionary from the decorator
    """
    is_walker = inspect.isclass(target)
    deferred = DeferredEndpoint(target=target, config=config, is_walker=is_walker)

    with _registry_lock:
        _deferred_endpoints.append(deferred)
        _logger.debug(
            f"Registered deferred endpoint: {target.__name__ if hasattr(target, '__name__') else str(target)} "
            f"(path: {config.get('path', 'unknown')}, is_walker: {is_walker})"
        )


def flush_deferred_endpoints(server: "Server") -> int:
    """Flush all deferred endpoints to the given server.

    This function registers all endpoints that were decorated before the
    server was initialized. It should be called once during Server.__init__
    after set_current_server() is called.

    Args:
        server: The server instance to register endpoints with

    Returns:
        Number of endpoints that were registered

    Raises:
        RuntimeError: If server is None or not properly initialized
    """
    if server is None:
        raise RuntimeError("Cannot flush deferred endpoints: server is None")

    with _registry_lock:
        if not _deferred_endpoints:
            return 0

        count = len(_deferred_endpoints)
        _logger.debug(
            f"Flushing {count} deferred endpoint(s) to server: {server.config.title}"
        )

        # Process all deferred endpoints
        for deferred in _deferred_endpoints:
            try:
                _register_deferred_endpoint(server, deferred)
            except Exception as e:
                _logger.warning(
                    f"Failed to register deferred endpoint {deferred.target.__name__ if hasattr(deferred.target, '__name__') else str(deferred.target)}: {e}",
                    exc_info=True,
                )

        # Clear the registry after successful flush
        _deferred_endpoints.clear()

        _logger.debug(f"Successfully flushed {count} deferred endpoint(s)")

        return count


def _register_deferred_endpoint(server: "Server", deferred: DeferredEndpoint) -> None:
    """Register a single deferred endpoint with the server.

    This is an internal helper that performs the actual registration logic,
    mirroring what the @endpoint decorator does when a server is available.

    Args:
        server: The server instance to register with
        deferred: The deferred endpoint to register
    """
    target = deferred.target
    config = deferred.config
    is_walker = deferred.is_walker

    path = config.get("path")
    if not path:
        _logger.warning(
            f"Skipping deferred endpoint {target.__name__ if hasattr(target, '__name__') else str(target)}: no path in config"
        )
        return

    methods = config.get("methods", ["POST"] if is_walker else ["GET"])
    auth = config.get("auth_required", config.get("auth", False))
    permissions = config.get("permissions", [])
    roles = config.get("roles", [])

    # Extract route kwargs (excluding special fields)
    route_kwargs = {
        k: v
        for k, v in config.items()
        if k
        not in [
            "path",
            "methods",
            "is_function",
            "auth_required",
            "auth",
            "permissions",
            "roles",
            "webhook",
            "signature_required",
            "webhook_auth",
            "response",
            "rate_limit",
            "kwargs",
        ]
    }

    # Merge in nested kwargs if present
    if "kwargs" in config:
        route_kwargs.update(config["kwargs"])

    if is_walker:
        # Register walker
        target_type = cast(Type[Any], target)
        target_type._auth_required = auth  # type: ignore[attr-defined]
        target_type._required_permissions = permissions  # type: ignore[attr-defined]
        target_type._required_roles = roles  # type: ignore[attr-defined]

        # Register with endpoint registry
        server._endpoint_registry.register_walker(
            target_type,
            path,
            methods,
            router=server.endpoint_router,
            auth=auth,
            permissions=permissions,
            roles=roles,
            **route_kwargs,
        )

        # Register with endpoint router
        server.endpoint_router.endpoint(path, methods, **route_kwargs)(target_type)

        # Register dynamically if server is running
        if server._is_running:
            server._register_walker_dynamically(
                target_type, path, methods, **route_kwargs
            )

    else:
        # Register function endpoint
        from jvspatial.api.decorators.route import _wrap_function_with_params
        from jvspatial.api.endpoints.factory import ParameterModelFactory

        func = cast(Callable[..., Any], target)
        param_model = ParameterModelFactory.create_model(func, path=path)

        # Wrap function with parameter handling if needed
        if param_model is not None:
            wrapped_func = _wrap_function_with_params(
                func, param_model, methods, path=path
            )
        else:
            wrapped_func = func

        reg_response = config.get("response")

        # Set auth attributes
        func._auth_required = auth  # type: ignore[attr-defined]
        wrapped_func._auth_required = auth  # type: ignore[attr-defined]

        # Register via endpoint router
        server.endpoint_router.add_route(
            path=path,
            endpoint=wrapped_func,
            methods=methods,
            source_obj=func,
            auth=auth,
            permissions=permissions,
            roles=roles,
            response=reg_response,
            **route_kwargs,
        )

        # Register with endpoint registry
        server._endpoint_registry.register_function(
            func,
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


def get_deferred_endpoint_count() -> int:
    """Get the current count of deferred endpoints.

    This is useful for debugging and testing.

    Returns:
        Number of endpoints currently in the deferred registry
    """
    with _registry_lock:
        return len(_deferred_endpoints)


def clear_deferred_endpoints() -> None:
    """Clear all deferred endpoints from the registry.

    This is primarily useful for testing. In production, endpoints should
    be flushed to a server rather than cleared.

    Warning:
        This will permanently lose any deferred endpoints that haven't been
        flushed. Use with caution.
    """
    with _registry_lock:
        count = len(_deferred_endpoints)
        _deferred_endpoints.clear()
        _logger.debug(f"Cleared {count} deferred endpoint(s) from registry")


__all__ = [
    "register_deferred_endpoint",
    "flush_deferred_endpoints",
    "get_deferred_endpoint_count",
    "clear_deferred_endpoints",
    "DeferredEndpoint",
]
