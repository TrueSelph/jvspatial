"""API package for the jvspatial framework."""

from .endpoint_router import EndpointField, EndpointRouter
from .server import (
    Server,
    ServerConfig,
    create_server,
    endpoint,
    get_default_server,
    set_default_server,
    walker_endpoint,
)

__all__ = [
    "Server",
    "ServerConfig",
    "create_server",
    "get_default_server",
    "set_default_server",
    "walker_endpoint",
    "endpoint",
    "EndpointRouter",
    "EndpointField",
]
