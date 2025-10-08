"""API package for the jvspatial framework."""

from .config import ServerConfig
from .context import ServerContext, get_current_server, set_current_server
from .endpoint.router import EndpointField, EndpointRouter
from .server import Server, create_server, endpoint, walker_endpoint

__all__ = [
    "Server",
    "ServerConfig",
    "create_server",
    "get_current_server",
    "set_current_server",
    "ServerContext",
    "walker_endpoint",
    "endpoint",
    "EndpointRouter",
    "EndpointField",
]
