"""Server class for FastAPI applications using jvspatial.

This module provides a high-level, object-oriented interface for creating
FastAPI servers with jvspatial integration, including automatic database
setup, lifecycle management, and endpoint routing.
"""

import inspect
import logging
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    Union,
    cast,
)

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from jvspatial.api.config import ServerConfig
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Node, Root, Walker
from jvspatial.db.factory import get_database

from .endpoint.response import create_endpoint_helper
from .endpoint.router import EndpointRouter
from .services.discovery import PackageDiscoveryService
from .services.endpoint_registry import EndpointRegistryService
from .services.lifecycle import LifecycleManager
from .services.middleware import MiddlewareManager


class Server:
    """High-level FastAPI server wrapper for jvspatial applications.

    This class provides a simplified interface for creating FastAPI servers
    with automatic jvspatial integration, database setup, and lifecycle management.

    Example:
        ```python
        from jvspatial.api.server import Server
        from jvspatial.core.entities import Walker, Node, on_visit

        # Simple server with default GraphContext
        server = Server(
            title="My Spatial API",
            description="A spatial data management API"
        )

        @server.walker("/process")
        class ProcessData(Walker):
            data: str

            @on_visit(Node)
            async def process(self, here):
                self.response["processed"] = self.data.upper()

        if __name__ == "__main__":
            server.run()
        ```

        Advanced GraphContext configuration:
        ```python
        server = Server(
            title="My API",
            db_type="json",
            db_path="./my_data"
        )

        # Access GraphContext if needed
        ctx = server.get_graph_context()
        ```
    """

    def __init__(
        self: "Server",
        config: Optional[Union[ServerConfig, Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize the Server.

        Args:
            config: Server configuration as ServerConfig or dict
            **kwargs: Additional configuration parameters
        """
        # Initialize configuration
        if config is None:
            config_dict = {}
        elif isinstance(config, ServerConfig):
            config_dict = config.model_dump()
        else:
            config_dict = config

        # Merge kwargs into config
        config_dict.update(kwargs)
        self.config = ServerConfig(**config_dict)

        # Initialize components
        self.app: Optional[FastAPI] = None
        self.endpoint_router = EndpointRouter()
        self._custom_routes: List[Dict[str, Any]] = []
        self._exception_handlers: Dict[Union[int, Type[Exception]], Callable] = {}
        self._logger = logging.getLogger(__name__)
        self._graph_context: Optional[GraphContext] = None

        # File storage components
        self._file_interface: Optional[Any] = None
        self._proxy_manager: Optional[Any] = None
        self._file_storage_service: Optional[Any] = None

        # Endpoint registry service - central tracking for all endpoints
        self._endpoint_registry = EndpointRegistryService()

        # Dynamic registration support
        self._is_running = False
        self._dynamic_routes_registered = False
        self._app_needs_rebuild = False  # Flag to track when app needs rebuilding

        # Initialize lifecycle manager
        self._lifecycle_manager = LifecycleManager(self)

        # Initialize middleware manager
        self._middleware_manager = MiddlewareManager(self)

        # Initialize package discovery service
        self._discovery_service = PackageDiscoveryService(self)

        # Set this server as current in context
        from jvspatial.api.context import get_current_server, set_current_server

        if get_current_server() is None:
            set_current_server(self)

        # Initialize GraphContext if database configuration is provided
        if self.config.db_type:
            self._initialize_graph_context()

        # Initialize file storage if enabled
        if self.config.file_storage_enabled:
            self._initialize_file_storage()

    def _initialize_graph_context(self: "Server") -> None:
        """Initialize GraphContext with current database configuration."""
        try:
            # Create database instance based on configuration
            if self.config.db_type == "json":
                db = get_database(
                    db_type="json",
                    base_path=self.config.db_path or "./jvdb",
                    auto_create=True,
                )
            elif self.config.db_type == "mongodb":
                db = get_database(
                    db_type="mongodb",
                    connection_string=self.config.db_connection_string,
                    database_name=self.config.db_database_name,
                )
            else:
                raise ValueError(f"Unsupported database type: {self.config.db_type}")

            # Create GraphContext
            self._graph_context = GraphContext(database=db)
            self._logger.info(
                f"🎯 GraphContext initialized with {self.config.db_type} database"
            )

        except Exception as e:
            self._logger.error(f"❌ Failed to initialize GraphContext: {e}")
            raise

    def _initialize_file_storage(self: "Server") -> None:
        """Initialize file storage interface and proxy manager."""
        try:
            from jvspatial.api.services.file_storage import FileStorageService
            from jvspatial.storage import get_file_interface, get_proxy_manager

            # Initialize file interface
            if self.config.file_storage_provider == "local":
                self._file_interface = get_file_interface(
                    provider="local",
                    root_dir=self.config.file_storage_root,
                    base_url=self.config.file_storage_base_url,
                    max_file_size=self.config.file_storage_max_size,
                )
            elif self.config.file_storage_provider == "s3":
                self._file_interface = get_file_interface(
                    provider="s3",
                    bucket_name=self.config.s3_bucket_name,
                    region=self.config.s3_region,
                    access_key=self.config.s3_access_key,
                    secret_key=self.config.s3_secret_key,
                    endpoint_url=self.config.s3_endpoint_url,
                )
            else:
                raise ValueError(
                    f"Unsupported file storage provider: {self.config.file_storage_provider}"
                )

            # Initialize proxy manager if enabled
            if self.config.proxy_enabled:
                self._proxy_manager = get_proxy_manager()

            # Create FileStorageService instance
            self._file_storage_service = FileStorageService(
                file_interface=self._file_interface,
                proxy_manager=self._proxy_manager,
                config=self.config,
            )

            self._logger.info(
                f"📁 File storage initialized: {self.config.file_storage_provider}"
            )

        except Exception as e:
            self._logger.error(f"❌ Failed to initialize file storage: {e}")
            raise

    def walker(
        self: "Server", path: str, methods: Optional[List[str]] = None, **kwargs: Any
    ) -> Callable[[Type[Walker]], Type[Walker]]:
        """Register a Walker class as an API endpoint.

        Args:
            path: URL path for the endpoint
            methods: HTTP methods (default: ["POST"])
            **kwargs: Additional route parameters

        Returns:
            Decorator function for Walker classes
        """

        def decorator(walker_class: Type[Walker]) -> Type[Walker]:
            # Remove auth-related kwargs (they should only be set by auth decorators)
            endpoint_kwargs = kwargs.copy()
            auth_attrs = ["_auth_required", "_required_roles", "_required_permissions"]
            for attr in auth_attrs:
                endpoint_kwargs.pop(attr, None)

            # Register with endpoint registry
            try:
                self._endpoint_registry.register_walker(
                    walker_class,
                    path,
                    methods or ["POST"],
                    router=self.endpoint_router,
                    **endpoint_kwargs,
                )
            except Exception as e:
                self._logger.warning(
                    f"Walker {walker_class.__name__} already registered: {e}"
                )

            # If server is already running, register the endpoint dynamically
            if self._is_running and self.app is not None:
                self._register_walker_dynamically(walker_class, path, methods, **kwargs)

            # Always register with the endpoint router for FastAPI integration
            register_kwargs = kwargs.copy()
            register_kwargs.pop("_auth_required", None)
            decorated_walker = self.endpoint_router.endpoint(
                path, methods, **register_kwargs
            )(walker_class)
            return cast(Type[Walker], decorated_walker)

        return decorator

    def route(
        self: "Server", path: str, methods: Optional[List[str]] = None, **kwargs: Any
    ) -> Callable[[Callable], Callable]:
        """Register a custom route handler.

        Args:
            path: URL path for the route
            methods: HTTP methods (default: ["GET"])
            **kwargs: Additional route parameters

        Returns:
            Decorator function for route handlers
        """
        if methods is None:
            methods = ["GET"]

        def decorator(func: Callable) -> Callable:
            route_config = {
                "path": path,
                "endpoint": func,
                "methods": methods,
                **kwargs,
            }
            self._custom_routes.append(route_config)

            # Register with endpoint registry
            try:
                self._endpoint_registry.register_function(
                    func, path, methods, route_config=route_config, **kwargs
                )
            except Exception as e:
                self._logger.warning(
                    f"Function {func.__name__} already registered: {e}"
                )

            # If server is running, add route dynamically
            if self._is_running and self.app is not None:
                self._rebuild_app_if_needed()
                self._logger.info(f"🔄 Dynamically registered route: {methods} {path}")

            return func

        return decorator

    def middleware(self: "Server", middleware_type: str = "http") -> Callable:
        """Add middleware to the application.

        Args:
            middleware_type: Type of middleware ("http" or "websocket")

        Returns:
            Decorator function for middleware
        """

        def decorator(func: Callable) -> Callable:
            self._middleware_manager.add_middleware(middleware_type, func)
            return func

        return decorator

    def exception_handler(
        self: "Server", exc_class_or_status_code: Union[int, Type[Exception]]
    ) -> Callable:
        """Add exception handler.

        Args:
            exc_class_or_status_code: Exception class or HTTP status code

        Returns:
            Decorator function for exception handlers
        """

        def decorator(func: Callable) -> Callable:
            self._exception_handlers[exc_class_or_status_code] = func
            return func

        return decorator

    def on_startup(self: "Server", func: Callable[[], Any]) -> Callable[[], Any]:
        """Register startup task.

        Args:
            func: Startup function

        Returns:
            The original function
        """
        return self._lifecycle_manager.add_startup_hook(func)

    def on_shutdown(self: "Server", func: Callable[[], Any]) -> Callable[[], Any]:
        """Register shutdown task.

        Args:
            func: Shutdown function

        Returns:
            The original function
        """
        return self._lifecycle_manager.add_shutdown_hook(func)

    def _rebuild_app_if_needed(self: "Server") -> None:
        """Rebuild the FastAPI app to reflect dynamic changes.

        This is necessary because FastAPI doesn't support removing routes/routers
        at runtime, so we need to recreate the entire app.
        """
        if not self._is_running or self.app is None:
            return

        try:
            self._logger.info(
                "🔄 Rebuilding FastAPI app for dynamic endpoint changes..."
            )

            # Store the old app reference (not used but kept for clarity)

            # Create a new app with current configuration
            self.app = self._create_app_instance()

            # The server will need to be restarted manually or this won't take effect
            # in a running uvicorn server, but we can at least update our internal state
            self._logger.warning(
                "App rebuilt internally. For changes to take effect in a running server, "
                "you may need to restart or use a development server with reload=True"
            )

        except Exception as e:
            self._logger.error(f"❌ Failed to rebuild app: {e}")

    def _create_app_instance(self: "Server") -> FastAPI:
        """Create FastAPI instance by orchestrating focused setup methods.

        This orchestrator method delegates to focused, single-responsibility methods
        to create and configure the FastAPI application instance.

        Returns:
            FastAPI: Fully configured application instance
        """
        app = self._create_base_app()
        self._configure_middleware(app)
        self._configure_exception_handlers(app)
        self._register_core_routes(app)
        self._register_custom_routes(app)
        self._include_routers(app)
        return app

    def _create_base_app(self: "Server") -> FastAPI:
        """Create base FastAPI app with lifespan configuration.

        Returns:
            FastAPI: Configured base application instance
        """
        # Create FastAPI app with lifespan - but only if not already running
        # to avoid lifespan conflicts
        if self._is_running:
            app = FastAPI(
                title=self.config.title,
                description=self.config.description,
                version=self.config.version,
                docs_url=self.config.docs_url,
                redoc_url=self.config.redoc_url,
                debug=self.config.debug,
                # Skip lifespan for rebuilt apps
            )
        else:
            app = FastAPI(
                title=self.config.title,
                description=self.config.description,
                version=self.config.version,
                docs_url=self.config.docs_url,
                redoc_url=self.config.redoc_url,
                debug=self.config.debug,
                lifespan=self._lifecycle_manager.lifespan,
            )
        return app

    def _configure_middleware(self: "Server", app: FastAPI) -> None:
        """Configure all middleware using MiddlewareManager.

        Args:
            app: FastAPI application instance to configure
        """
        self._middleware_manager.configure_all(app)

    def _configure_exception_handlers(self: "Server", app: FastAPI) -> None:
        """Configure all exception handlers.

        Args:
            app: FastAPI application instance to configure
        """
        # Add custom exception handlers
        for exc_class, handler in self._exception_handlers.items():
            app.add_exception_handler(exc_class, handler)

        # Add default exception handler
        @app.exception_handler(Exception)
        async def global_exception_handler(
            request: Request, exc: Exception
        ) -> JSONResponse:
            self._logger.error(f"Unhandled exception: {exc}", exc_info=True)
            return JSONResponse(
                status_code=500,
                content={
                    "error": "Internal server error",
                    "detail": str(exc) if self.config.debug else "An error occurred",
                },
            )

    def _register_core_routes(self: "Server", app: FastAPI) -> None:
        """Register core routes (health, root).

        Args:
            app: FastAPI application instance to configure
        """

        # Add default health check endpoint
        @app.get("/health", response_model=None)
        async def health_check() -> Union[Dict[str, Any], JSONResponse]:
            """Health check endpoint."""
            try:
                # Test database connectivity through GraphContext
                if self._graph_context:
                    # Use explicit GraphContext
                    root = await self._graph_context.get_node(Root, "root")
                    if not root:
                        root = await self._graph_context.create_node(Root)
                else:
                    # Use default GraphContext behavior
                    root = await Root.get("n:Root:root")
                    if not root:
                        root = await Root.create()
                return {
                    "status": "healthy",
                    "database": "connected",
                    "root_node": root.id,
                    "service": self.config.title,
                    "version": self.config.version,
                }
            except Exception as e:
                return JSONResponse(
                    status_code=503,
                    content={
                        "status": "unhealthy",
                        "error": str(e),
                        "service": self.config.title,
                        "version": self.config.version,
                    },
                )

        # Add root endpoint
        @app.get("/")
        async def root_info() -> Dict[str, Any]:
            """Root endpoint with API information."""
            return {
                "service": self.config.title,
                "description": self.config.description,
                "version": self.config.version,
                "docs": self.config.docs_url,
                "health": "/health",
            }

    def _register_custom_routes(self: "Server", app: FastAPI) -> None:
        """Register custom user-defined routes.

        Args:
            app: FastAPI application instance to configure
        """
        # Add custom routes with webhook support
        for route_config in self._custom_routes:
            # Check if this is a webhook endpoint
            endpoint_func = route_config.get("endpoint")
            if endpoint_func and getattr(endpoint_func, "_webhook_required", False):
                # Wrap webhook endpoint with payload injection
                from jvspatial.api.webhook.endpoint import create_webhook_wrapper

                wrapped_endpoint = create_webhook_wrapper(endpoint_func)
                route_config = route_config.copy()
                route_config["endpoint"] = wrapped_endpoint

            app.add_api_route(**route_config)

    def _include_routers(self: "Server", app: FastAPI) -> None:
        """Include endpoint routers and dynamic routers.

        Args:
            app: FastAPI application instance to configure
        """
        # Include the jvspatial endpoint router with webhook walker support
        self._setup_webhook_walker_endpoints()
        app.include_router(self.endpoint_router.router)

        # Include any dynamic routers from registry
        for endpoint_info in self._endpoint_registry.get_dynamic_endpoints():
            if endpoint_info.router:
                app.include_router(endpoint_info.router.router, prefix="/api")

    def _register_walker_dynamically(
        self: "Server",
        walker_class: Type[Walker],
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Register a walker endpoint dynamically while server is running.

        Args:
            walker_class: Walker class to register
            path: URL path for the endpoint
            methods: HTTP methods
            **kwargs: Additional route parameters
        """
        if self.app is None:
            return

        try:
            # Create a new endpoint router for the dynamic walker
            dynamic_router = EndpointRouter()
            dynamic_router.endpoint(path, methods, **kwargs)(walker_class)

            # Register as dynamic endpoint in registry
            endpoint_info = self._endpoint_registry.get_walker_info(walker_class)
            if endpoint_info:
                endpoint_info.is_dynamic = True
                endpoint_info.router = dynamic_router

            # Include the new router in the existing app
            self.app.include_router(dynamic_router.router, prefix="/api")

            self._logger.info(
                f"🔄 Dynamically registered walker: {walker_class.__name__} at {path}"
            )

        except Exception as e:
            self._logger.error(
                f"❌ Failed to dynamically register walker {walker_class.__name__}: {e}"
            )

    def _setup_webhook_walker_endpoints(self: "Server") -> None:
        """Set up webhook wrapper for walker endpoints."""
        for (
            walker_class,
            endpoint_info,
        ) in self._endpoint_registry._walker_registry.items():
            if getattr(walker_class, "_webhook_required", False):
                try:
                    from jvspatial.api.webhook.endpoint import (
                        create_webhook_walker_wrapper,
                    )

                    # Create webhook wrapper for the walker
                    wrapper_func = create_webhook_walker_wrapper(walker_class)

                    # Register the wrapper as a custom route instead of walker route
                    path = endpoint_info.path
                    methods = endpoint_info.methods
                    kwargs = endpoint_info.kwargs

                    # Add as custom route
                    route_config = {
                        "path": path,
                        "endpoint": wrapper_func,
                        "methods": methods,
                        **kwargs,
                    }

                    # Add to custom routes if not already there
                    if route_config not in self._custom_routes:
                        self._custom_routes.append(route_config)

                    self._logger.debug(
                        f"🔗 Set up webhook wrapper for walker: {walker_class.__name__} at {path}"
                    )

                except Exception as e:
                    self._logger.warning(
                        f"⚠️ Failed to setup webhook walker {walker_class.__name__}: {e}"
                    )

    def register_walker_class(
        self: "Server",
        walker_class: Type[Walker],
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs: Any,
    ) -> None:
        """Programmatically register a walker class.

        This method allows registration of walker classes without using decorators,
        useful for dynamic registration from external packages.

        Args:
            walker_class: Walker class to register
            path: URL path for the endpoint
            methods: HTTP methods (default: ["POST"])
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
            router=self.endpoint_router,
            **kwargs,
        )

        if self._is_running and self.app is not None:
            self._register_walker_dynamically(walker_class, path, methods, **kwargs)
        else:
            self.endpoint_router.endpoint(path, methods, **kwargs)(walker_class)

        self._logger.info(
            f"📝 Registered walker class: {walker_class.__name__} at {path}"
        )

    def unregister_walker_class(self: "Server", walker_class: Type[Walker]) -> bool:
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

            if not success:
                return False

            # Mark app for rebuilding if server is running
            if self._is_running:
                self._app_needs_rebuild = True
                self._rebuild_app_if_needed()
                self._logger.info(
                    f"🔄 FastAPI app rebuilt to remove walker endpoint: {walker_class.__name__}"
                )

            self._logger.info(f"🗑️ Unregistered walker class: {walker_class.__name__}")
            return True

        except Exception as e:
            self._logger.error(
                f"❌ Failed to unregister walker {walker_class.__name__}: {e}"
            )
            return False

    def unregister_walker_endpoint(self: "Server", path: str) -> List[Type[Walker]]:
        """Remove all walkers registered to a specific path.

        Args:
            path: The URL path to remove walkers from

        Returns:
            List of walker classes that were removed
        """
        removed_walkers: List[Type[Walker]] = []

        # Get all endpoints at this path from registry
        endpoints = self._endpoint_registry.get_by_path(path)

        # Remove walker endpoints
        for endpoint_info in endpoints:
            if endpoint_info.endpoint_type.value == "walker":
                handler = endpoint_info.handler
                # Type check: ensure handler is a Type (class) before treating as walker
                if isinstance(handler, type):
                    walker_class = cast(Type[Walker], handler)
                    if self.unregister_walker_class(walker_class):
                        removed_walkers.append(walker_class)

        if removed_walkers:
            walker_names = [cls.__name__ for cls in removed_walkers]
            self._logger.info(
                f"🗑️ Removed {len(removed_walkers)} walkers from path {path}: {walker_names}"
            )

        return removed_walkers

    def unregister_endpoint(self: "Server", endpoint: Union[str, Callable]) -> bool:
        """Remove a function endpoint from the server.

        Args:
            endpoint: Either the path string or the function to remove

        Returns:
            True if the endpoint was successfully removed, False otherwise
        """
        if isinstance(endpoint, str):
            # Remove by path - use registry
            path = endpoint
            removed_count = self._endpoint_registry.unregister_by_path(path)

            # Also remove from custom routes
            removed_routes = [r for r in self._custom_routes if r.get("path") == path]
            for route in removed_routes:
                self._custom_routes.remove(route)

            if removed_count > 0 or removed_routes:
                self._logger.info(
                    f"🗑️ Removed {removed_count} endpoints from path {path}"
                )
                success = True
            else:
                self._logger.warning(f"No endpoints found at path {path}")
                success = False

        elif callable(endpoint):
            # Remove by function reference
            func = endpoint

            if not self._endpoint_registry.has_function(func):
                self._logger.warning(f"Function {func.__name__} not registered")
                return False

            # Unregister from registry
            success = self._endpoint_registry.unregister_function(func)

            # Remove from custom routes
            for route_config in self._custom_routes[:]:
                if route_config.get("endpoint") == func:
                    self._custom_routes.remove(route_config)

            if success:
                self._logger.info(f"🗑️ Removed function endpoint: {func.__name__}")

        else:
            self._logger.error(
                "Invalid endpoint parameter: must be string path or callable function"
            )
            return False

        # Mark app for rebuilding if server is running and we removed something
        if success and self._is_running:
            self._app_needs_rebuild = True
            self._rebuild_app_if_needed()
            self._logger.info("🔄 FastAPI app rebuilt to remove function endpoint")

        return success

    def unregister_endpoint_by_path(self: "Server", path: str) -> int:
        """Remove all endpoints (both walker and function) from a specific path.

        Args:
            path: The URL path to remove all endpoints from

        Returns:
            Number of endpoints removed
        """
        # Use registry to remove all endpoints at path
        removed_count = self._endpoint_registry.unregister_by_path(path)

        # Also remove from custom routes
        for route_config in self._custom_routes[:]:
            if route_config.get("path") == path:
                self._custom_routes.remove(route_config)

        if removed_count > 0:
            self._logger.info(
                f"🗑️ Removed {removed_count} total endpoints from path {path}"
            )

        return removed_count

    def list_function_endpoints(self: "Server") -> Dict[str, Dict[str, Any]]:
        """Get information about all registered function endpoints.

        Returns:
            Dictionary mapping function names to their endpoint information
        """
        return self._endpoint_registry.list_functions()

    def list_function_endpoints_safe(self: "Server") -> Dict[str, Dict[str, Any]]:
        """Get serializable information about all registered function endpoints (no function objects).

        Returns:
            Dictionary mapping function names to their serializable endpoint information
        """
        return self._endpoint_registry.list_functions()

    def list_all_endpoints(self: "Server") -> Dict[str, Any]:
        """Get information about all registered endpoints (walkers and functions).

        Returns:
            Dictionary with 'walkers' and 'functions' keys containing endpoint information
        """
        return self._endpoint_registry.list_all()

    def list_all_endpoints_safe(self: "Server") -> Dict[str, Any]:
        """Get serializable information about all registered endpoints (walkers and functions).

        Returns:
            Dictionary with 'walkers' and 'functions' keys containing serializable endpoint information
        """
        return self._endpoint_registry.list_all()

    def list_walker_endpoints(self: "Server") -> Dict[str, Dict[str, Any]]:
        """Get information about all registered walkers.

        Returns:
            Dictionary mapping walker class names to their endpoint information
        """
        return self._endpoint_registry.list_walkers()

    def list_walker_endpoints_safe(self: "Server") -> Dict[str, Dict[str, Any]]:
        """Get serializable information about all registered walkers (no class objects).

        Returns:
            Dictionary mapping walker class names to their serializable endpoint information
        """
        return self._endpoint_registry.list_walkers()

    def enable_package_discovery(
        self: "Server", enabled: bool = True, patterns: Optional[List[str]] = None
    ) -> None:
        """Enable or disable automatic package discovery.

        Args:
            enabled: Whether to enable package discovery
            patterns: List of package name patterns to search for
        """
        self._discovery_service.enable(enabled, patterns)

    def refresh_endpoints(self: "Server") -> int:
        """Refresh and discover new endpoints from packages.

        Returns:
            Number of new endpoints discovered
        """
        if not self._is_running:
            self._logger.warning("Cannot refresh endpoints - server is not running")
            return 0

        return self._discovery_service.discover_and_register()

    def _create_app(self: "Server") -> FastAPI:
        """Create and configure the FastAPI application."""
        return self._create_app_instance()

    def get_app(self: "Server") -> FastAPI:
        """Get the FastAPI application instance.

        Returns:
            Configured FastAPI application
        """
        if self.app is None:
            self.app = self._create_app()
        return self.app

    def run(
        self: "Server",
        host: Optional[str] = None,
        port: Optional[int] = None,
        reload: Optional[bool] = None,
        **uvicorn_kwargs: Any,
    ) -> None:
        """Run the server using uvicorn.

        Args:
            host: Override host address
            port: Override port number
            reload: Enable auto-reload for development
            **uvicorn_kwargs: Additional uvicorn parameters
        """
        # Set up logging
        logging.basicConfig(
            level=getattr(logging, self.config.log_level.upper()),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )

        # Use provided values or fall back to config
        run_host = host or self.config.host
        run_port = port or self.config.port
        run_reload = reload if reload is not None else self.config.debug

        self._logger.info(f"🔧 Server starting at http://{run_host}:{run_port}")
        if self.config.docs_url:
            self._logger.info(
                f"📖 API docs: http://{run_host}:{run_port}{self.config.docs_url}"
            )

        # Get the app
        app = self.get_app()

        # Configure uvicorn parameters
        uvicorn_config = {
            "host": run_host,
            "port": run_port,
            "reload": run_reload,
            "log_level": self.config.log_level,
            **uvicorn_kwargs,
        }

        # Run the server
        uvicorn.run(app, **uvicorn_config)

    async def run_async(
        self: "Server",
        host: Optional[str] = None,
        port: Optional[int] = None,
        **uvicorn_kwargs: Any,
    ) -> None:
        """Run the server asynchronously.

        Args:
            host: Override host address
            port: Override port number
            **uvicorn_kwargs: Additional uvicorn parameters
        """
        run_host = host or self.config.host
        run_port = port or self.config.port

        app = self.get_app()

        config = uvicorn.Config(
            app,
            host=run_host,
            port=run_port,
            log_level=self.config.log_level,
            **uvicorn_kwargs,
        )
        server = uvicorn.Server(config)
        await server.serve()

    def add_node_type(self: "Server", node_class: Type[Node]) -> None:
        """Register a Node type for use in walkers.

        Args:
            node_class: Node subclass to register
        """
        # This is mainly for documentation/organization purposes
        # The actual registration happens automatically in jvspatial
        self._logger.info(f"Registered node type: {node_class.__name__}")

    def configure_database(self: "Server", db_type: str, **db_config: Any) -> None:
        """Configure database settings using GraphContext.

        Args:
            db_type: Database type ("json", "mongodb", etc.)
            **db_config: Database-specific configuration
        """
        # Update configuration
        self.config.db_type = db_type

        # Handle common database configurations
        if db_type == "json" and "base_path" in db_config:
            self.config.db_path = db_config["base_path"]
        elif db_type == "mongodb":
            if "connection_string" in db_config:
                self.config.db_connection_string = db_config["connection_string"]
            if "database_name" in db_config:
                self.config.db_database_name = db_config["database_name"]

        # Initialize or re-initialize GraphContext
        self._initialize_graph_context()

        self._logger.info(f"🗄️ Database configured with GraphContext: {db_type}")

    def get_graph_context(self: "Server") -> Optional[GraphContext]:
        """Get the GraphContext instance used by the server.

        Returns:
            GraphContext instance if configured, otherwise None (uses default GraphContext)
        """
        return self._graph_context

    def set_graph_context(self: "Server", context: GraphContext) -> None:
        """Set a custom GraphContext for the server.

        Args:
            context: GraphContext instance to use
        """
        self._graph_context = context
        self._logger.info("🎯 Custom GraphContext set for server")


def walker_endpoint(
    path: str, methods: Optional[List[str]] = None, **kwargs: Any
) -> Callable[[Type[Walker]], Type[Walker]]:
    """Register a walker to the default server instance.

    This decorator allows packages to register walkers without having
    direct access to a server instance. The decorator automatically injects
    an 'endpoint' response helper into walker instances for semantic HTTP responses.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (default: ["POST"])
        **kwargs: Additional route parameters (tags, summary, etc.)

    Returns:
        Decorator function for Walker classes

    Example:
        @walker_endpoint("/users/create", methods=["POST"])
        class CreateUser(Walker):
            name: str = EndpointField(description="User name")

            async def visit_root(self, node):
                return self.endpoint.success(data={"name": self.name})
    """

    def decorator(walker_class: Type[Walker]) -> Type[Walker]:
        # Store endpoint configuration on the class for discovery
        walker_class._jvspatial_endpoint_config = {  # type: ignore
            "path": path,
            "methods": methods or ["POST"],
            "kwargs": kwargs,
        }

        # Try to register with current server if available
        from jvspatial.api.context import get_current_server

        current_server = get_current_server()
        if current_server is not None:
            current_server.register_walker_class(walker_class, path, methods, **kwargs)
        else:
            # Server not available yet - configuration stored for discovery
            pass

        return walker_class

    return decorator


def endpoint(
    path: str, methods: Optional[List[str]] = None, **kwargs: Any
) -> Callable[[Callable], Callable]:
    """Register a regular function as an endpoint on the default server.

    This decorator allows packages to register simple function endpoints
    without Walker classes, similar to Flask or FastAPI decorators.
    The decorator automatically injects an 'endpoint' parameter with response utilities.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (default: ["GET"])
        **kwargs: Additional route parameters (tags, summary, etc.)

    Returns:
        Decorator function for regular functions

    Example:
        @endpoint("/users/count", methods=["GET"])
        async def get_user_count(endpoint):
            users = await User.all()
            return endpoint.success(data={"count": len(users)})
    """

    def decorator(func: Callable) -> Callable:
        # Store endpoint configuration on the function for discovery
        func._jvspatial_endpoint_config = {  # type: ignore
            "path": path,
            "methods": methods or ["GET"],
            "kwargs": kwargs,
            "is_function": True,
        }

        # Try to register with current server if available
        from jvspatial.api.context import get_current_server

        current_server = get_current_server()
        if current_server is not None:
            # Create wrapper that injects endpoint helper
            async def endpoint_wrapper(*args: Any, **kwargs_inner: Any) -> Any:
                # Create endpoint helper for function endpoints
                endpoint_helper = create_endpoint_helper(walker_instance=None)

                # Inject endpoint helper into function kwargs
                kwargs_inner["endpoint"] = endpoint_helper

                # Call original function with injected endpoint
                if inspect.iscoroutinefunction(func):
                    return await func(*args, **kwargs_inner)
                else:
                    return func(*args, **kwargs_inner)

            # Preserve original function metadata
            endpoint_wrapper.__name__ = func.__name__
            endpoint_wrapper.__doc__ = func.__doc__

            route_config = {
                "path": path,
                "endpoint": endpoint_wrapper,
                "methods": methods or ["GET"],
                **kwargs,
            }

            # Register as a custom route
            current_server._custom_routes.append(route_config)

            # Register with endpoint registry
            try:
                current_server._endpoint_registry.register_function(
                    func, path, methods or ["GET"], route_config=route_config, **kwargs
                )
            except Exception as e:
                current_server._logger.warning(
                    f"Function {func.__name__} already registered: {e}"
                )

            # If server is running, add route dynamically
            if current_server._is_running and current_server.app is not None:
                current_server.app.add_api_route(
                    path, endpoint_wrapper, methods=methods or ["GET"], **kwargs
                )
                current_server._logger.info(
                    f"🔄 Dynamically registered function endpoint: {func.__name__} at {path}"
                )

        return func

    return decorator


# Convenience function for quick server creation
def create_server(
    title: str = "jvspatial API",
    description: str = "API built with jvspatial framework",
    version: str = "1.0.0",
    **config_kwargs: Any,
) -> Server:
    """Create a Server instance with common configuration.

    Args:
        title: API title
        description: API description
        version: API version
        **config_kwargs: Additional server configuration

    Returns:
        Configured Server instance
    """
    return Server(
        title=title, description=description, version=version, **config_kwargs
    )
