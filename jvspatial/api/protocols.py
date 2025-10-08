"""Type protocols for jvspatial API interfaces.

This module defines Protocol classes that specify the contracts for various
components in the API, enabling better type checking and clearer interfaces.
"""

from typing import Any, Callable, Dict, List, Optional, Protocol, Tuple

from fastapi import FastAPI


class FileStorageProvider(Protocol):
    """Protocol for file storage providers.

    Defines the interface that all file storage implementations must follow,
    whether local filesystem, S3, or other storage backends.
    """

    async def save_file(self, path: str, content: bytes) -> None:
        """Save file content to storage.

        Args:
            path: Relative file path
            content: File content as bytes
        """
        ...

    async def get_file(self, path: str) -> bytes:
        """Retrieve file content from storage.

        Args:
            path: Relative file path

        Returns:
            File content as bytes
        """
        ...

    async def delete_file(self, path: str) -> bool:
        """Delete a file from storage.

        Args:
            path: Relative file path

        Returns:
            True if file was deleted, False otherwise
        """
        ...

    async def file_exists(self, path: str) -> bool:
        """Check if a file exists in storage.

        Args:
            path: Relative file path

        Returns:
            True if file exists, False otherwise
        """
        ...

    async def get_file_url(self, path: str) -> str:
        """Get public URL for a file.

        Args:
            path: Relative file path

        Returns:
            Public URL to access the file
        """
        ...

    async def serve_file(self, path: str) -> Any:
        """Serve a file directly (for HTTP responses).

        Args:
            path: Relative file path

        Returns:
            FastAPI FileResponse or similar
        """
        ...


class ProxyManager(Protocol):
    """Protocol for URL proxy managers.

    Defines the interface for managing temporary proxy URLs for files,
    with expiration and one-time access support.
    """

    async def create_proxy(
        self,
        file_path: str,
        expires_in: int,
        one_time: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a temporary proxy URL for a file.

        Args:
            file_path: Path to the file
            expires_in: Expiration time in seconds
            one_time: Whether the proxy should expire after first use
            metadata: Optional metadata to store with proxy

        Returns:
            Proxy URL
        """
        ...

    async def resolve_proxy(self, code: str) -> Tuple[str, Dict[str, Any]]:
        """Resolve a proxy code to file path and metadata.

        Args:
            code: Proxy code from URL

        Returns:
            Tuple of (file_path, metadata)
        """
        ...

    async def revoke_proxy(self, code: str) -> bool:
        """Revoke a proxy URL.

        Args:
            code: Proxy code to revoke

        Returns:
            True if revoked, False if not found
        """
        ...

    async def get_stats(self, code: str) -> Optional[Dict[str, Any]]:
        """Get statistics for a proxy.

        Args:
            code: Proxy code

        Returns:
            Statistics dictionary or None if not found
        """
        ...


class EndpointRegistry(Protocol):
    """Protocol for endpoint registry.

    Manages registration and tracking of API endpoints (walkers and functions).
    """

    def register_walker(
        self,
        walker_class: type,
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> Any:
        """Register a walker endpoint.

        Args:
            walker_class: Walker class to register
            path: URL path for endpoint
            methods: HTTP methods
            **kwargs: Additional route parameters

        Returns:
            Endpoint information object
        """
        ...

    def unregister_walker(self, walker_class: type) -> bool:
        """Unregister a walker endpoint.

        Args:
            walker_class: Walker class to unregister

        Returns:
            True if unregistered, False if not found
        """
        ...

    def list_walkers(self) -> Dict[str, Dict[str, Any]]:
        """List all registered walker endpoints.

        Returns:
            Dictionary of walker information
        """
        ...

    def get_walker_info(self, walker_class: type) -> Optional[Any]:
        """Get endpoint information for a walker.

        Args:
            walker_class: Walker class

        Returns:
            Endpoint information or None
        """
        ...


class LifecycleManager(Protocol):
    """Protocol for lifecycle management.

    Manages application startup and shutdown hooks and execution.
    """

    def add_startup_hook(self, func: Callable) -> Callable:
        """Add a startup hook.

        Args:
            func: Function to run on startup

        Returns:
            The function (for decorator pattern)
        """
        ...

    def add_shutdown_hook(self, func: Callable) -> Callable:
        """Add a shutdown hook.

        Args:
            func: Function to run on shutdown

        Returns:
            The function (for decorator pattern)
        """
        ...

    async def execute_startup(self, *additional_hooks: Callable) -> None:
        """Execute all startup hooks.

        Args:
            *additional_hooks: Additional hooks to execute
        """
        ...

    async def execute_shutdown(self, *additional_hooks: Callable) -> None:
        """Execute all shutdown hooks.

        Args:
            *additional_hooks: Additional hooks to execute
        """
        ...

    @property
    def is_running(self) -> bool:
        """Check if application is running.

        Returns:
            True if running, False otherwise
        """
        ...


class MiddlewareManager(Protocol):
    """Protocol for middleware management.

    Manages middleware configuration and application.
    """

    def add_cors(
        self,
        origins: Optional[List[str]] = None,
        methods: Optional[List[str]] = None,
        headers: Optional[List[str]] = None,
        credentials: bool = True,
    ) -> None:
        """Add CORS middleware configuration.

        Args:
            origins: Allowed origins
            methods: Allowed HTTP methods
            headers: Allowed headers
            credentials: Allow credentials

        Note:
            This is a protocol method; implementations must initialize default
            empty lists for origins, methods, and headers when None is provided.
        """
        """Add CORS middleware configuration.

        Args:
            origins: Allowed origins
            methods: Allowed HTTP methods
            headers: Allowed headers
            credentials: Allow credentials
        """
        ...

    def add_custom(self, middleware_type: str, func: Callable) -> None:
        """Add custom middleware.

        Args:
            middleware_type: Type of middleware
            func: Middleware function
        """
        ...

    def apply_to_app(self, app: FastAPI) -> None:
        """Apply all middleware to FastAPI app.

        Args:
            app: FastAPI application instance
        """
        ...


class PackageDiscovery(Protocol):
    """Protocol for package discovery service.

    Discovers and catalogs endpoints from installed packages.
    """

    def discover_packages(self) -> Dict[str, List[Any]]:
        """Discover packages matching patterns.

        Returns:
            Dictionary with 'walkers' and 'functions' lists
        """
        ...


class HealthChecker(Protocol):
    """Protocol for health check service.

    Performs health checks on application components.
    """

    async def check_health(self) -> Dict[str, Any]:
        """Perform comprehensive health check.

        Returns:
            Health status dictionary
        """
        ...


__all__ = [
    "FileStorageProvider",
    "ProxyManager",
    "EndpointRegistry",
    "LifecycleManager",
    "MiddlewareManager",
    "PackageDiscovery",
    "HealthChecker",
]
