"""Context-based server management for thread-safe server access.

This module provides a context-based approach to managing server instances,
replacing the previous global server registry with thread-safe ContextVar
implementation. This ensures proper isolation between threads and async tasks.
"""

from contextvars import ContextVar, Token
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from jvspatial.api.server import Server

# Context variable for the current server instance
_current_server: ContextVar[Optional["Server"]] = ContextVar(
    "current_server", default=None
)


def get_current_server() -> Optional["Server"]:
    """Get the current server from context.

    This function retrieves the server instance from the current context.
    It is thread-safe and async-safe, ensuring proper isolation between
    different execution contexts.

    Returns:
        The current server instance if one is set in the context, otherwise None.

    Example:
        ```python
        from jvspatial.api.context import get_current_server

        # Get the current server
        server = get_current_server()
        if server:
            print(f"Current server: {server.config.title}")
        ```
    """
    return _current_server.get()


def set_current_server(server: Optional["Server"]) -> None:
    """Set the current server in context.

    This function sets the server instance in the current context. It is
    thread-safe and async-safe, ensuring that each thread/task has its own
    server context.

    Args:
        server: The server instance to set as current, or None to clear.

    Example:
        ```python
        from jvspatial.api.context import set_current_server
        from jvspatial.api.server import Server

        # Create and set a server
        server = Server(title="My API")
        set_current_server(server)
        ```
    """
    _current_server.set(server)


class ServerContext:
    """Context manager for temporary server context.

    This class provides a context manager that temporarily sets a server
    as the current server within a specific scope. When the context exits,
    the previous server context is restored.

    This is useful for testing, nested server operations, or when you need
    to temporarily switch between different server instances.

    Attributes:
        server: The server instance to set as current within the context.
        token: Token for resetting the context variable after exit.

    Example:
        ```python
        from jvspatial.api.context import ServerContext
        from jvspatial.api.server import Server

        server1 = Server(title="API 1")
        server2 = Server(title="API 2")

        # Use server2 temporarily
        with ServerContext(server2):
            current = get_current_server()
            assert current is server2
            # Do work with server2

        # Original context restored automatically
        ```

    Example with nested contexts:
        ```python
        from jvspatial.api.context import ServerContext, set_current_server
        from jvspatial.api.server import Server

        server1 = Server(title="API 1")
        server2 = Server(title="API 2")

        set_current_server(server1)

        with ServerContext(server2):
            # server2 is current here
            assert get_current_server() is server2

        # server1 is current again
        assert get_current_server() is server1
        ```
    """

    def __init__(self, server: "Server") -> None:
        """Initialize the context manager.

        Args:
            server: The server instance to use within the context.
        """
        self.server = server
        self.token: Optional[Token[Optional["Server"]]] = None

    def __enter__(self) -> "Server":
        """Enter the context and set the server as current.

        Returns:
            The server instance that was set as current.
        """
        self.token = _current_server.set(self.server)
        return self.server

    def __exit__(self, *args: object) -> None:
        """Exit the context and restore the previous server.

        Args:
            *args: Exception information (exc_type, exc_value, traceback).
        """
        if self.token is not None:
            _current_server.reset(self.token)
