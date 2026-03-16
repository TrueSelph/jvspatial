"""API module for jvspatial.

This module provides:
- Server implementation with FastAPI integration
- Authentication and authorization
- Response handling
- Endpoint configuration
- Error handling
"""

from typing import TYPE_CHECKING

from .config import ServerConfig

if TYPE_CHECKING:
    from jvspatial.api.auth.service import AuthenticationService
from .context import ServerContext, get_current_server, set_current_server
from .decorators.deferred_registry import (
    clear_deferred_endpoints,
    flush_deferred_endpoints,
    get_deferred_endpoint_count,
    register_deferred_endpoint,
    sync_endpoint_modules,
)
from .decorators.field import EndpointField, EndpointFieldInfo, endpoint_field
from .decorators.route import endpoint
from .endpoints.response import ResponseHelper, format_response
from .endpoints.router import BaseRouter, EndpointRouter
from .server import Server, create_server


def get_auth_service() -> "AuthenticationService":
    """Get the configured AuthenticationService singleton from the current server.

    Use this in consumer apps (e.g. custom auth endpoints) to access the same
    auth service instance used by jvspatial's middleware and built-in endpoints.
    Ensures consistent JWT config (secret, algorithm, expiry) without manual wiring.

    Returns:
        AuthenticationService instance

    Raises:
        RuntimeError: If no server is set in context or auth is not configured
    """
    from .context import get_current_server

    server = get_current_server()
    if not server:
        raise RuntimeError(
            "get_auth_service() requires a Server to be set in context. "
            "Ensure Server is instantiated before calling (e.g. import app.main)."
        )
    if not getattr(server, "_auth_service", None):
        raise RuntimeError(
            "Authentication is not configured. Enable auth in Server config "
            "(auth={'enabled': True, ...})."
        )
    return server._auth_service


__all__ = [
    "Server",
    "ServerConfig",
    "get_auth_service",
    "create_server",
    "get_current_server",
    "set_current_server",
    "ServerContext",
    "endpoint",
    "BaseRouter",
    "EndpointRouter",
    "endpoint_field",
    "EndpointField",
    "EndpointFieldInfo",
    "format_response",
    "ResponseHelper",
    # Deferred registry utilities (for debugging and testing)
    "register_deferred_endpoint",
    "flush_deferred_endpoints",
    "get_deferred_endpoint_count",
    "clear_deferred_endpoints",
    "sync_endpoint_modules",
]
