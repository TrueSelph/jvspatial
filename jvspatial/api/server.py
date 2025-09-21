"""Server class for FastAPI applications using jvspatial.

This module provides a high-level, object-oriented interface for creating
FastAPI servers with jvspatial integration, including automatic database
setup, lifecycle management, and endpoint routing.
"""

import asyncio
import importlib
import inspect
import logging
import pkgutil
import threading
from contextlib import asynccontextmanager
from typing import (
    Any,
    AsyncGenerator,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Type,
    Union,
    cast,
)

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from jvspatial.api.endpoint.response import create_endpoint_helper
from jvspatial.api.endpoint.router import EndpointRouter
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Node, Root, Walker
from jvspatial.db.factory import get_database

# Global server registry for runtime access
_global_servers: Dict[str, "Server"] = {}
_default_server: Optional["Server"] = None
_server_lock = threading.Lock()


class ServerConfig(BaseModel):
    """Configuration model for the jvspatial Server.

    Attributes:
        title: API title
        description: API description
        version: API version
        debug: Enable debug mode
        host: Server host address
        port: Server port number
        docs_url: OpenAPI documentation URL
        redoc_url: ReDoc documentation URL
        cors_enabled: Enable CORS middleware
        cors_origins: Allowed CORS origins
        cors_methods: Allowed CORS methods
        cors_headers: Allowed CORS headers
        db_type: Database type override
        db_path: Database path override
        log_level: Logging level
        startup_hooks: List of startup hook function names
        shutdown_hooks: List of shutdown hook function names
    """

    # API Configuration
    title: str = "jvspatial API"
    description: str = "API built with jvspatial framework"
    version: str = "1.0.0"
    debug: bool = False

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    docs_url: Optional[str] = "/docs"
    redoc_url: Optional[str] = "/redoc"

    # CORS Configuration
    cors_enabled: bool = True
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])
    cors_methods: List[str] = Field(default_factory=lambda: ["*"])
    cors_headers: List[str] = Field(default_factory=lambda: ["*"])

    # Database Configuration
    db_type: Optional[str] = None
    db_path: Optional[str] = None
    db_connection_string: Optional[str] = None
    db_database_name: Optional[str] = None

    # Logging Configuration
    log_level: str = "info"

    # Lifecycle Hooks
    startup_hooks: List[str] = Field(default_factory=list)
    shutdown_hooks: List[str] = Field(default_factory=list)


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
        self._startup_tasks: List[Callable[[], Any]] = []
        self._shutdown_tasks: List[Callable[[], Any]] = []
        self._custom_routes: List[Dict[str, Any]] = []
        self._middleware: List[Dict[str, Any]] = []
        self._exception_handlers: Dict[Union[int, Type[Exception]], Callable] = {}
        self._logger = logging.getLogger(__name__)
        self._graph_context: Optional[GraphContext] = None

        # Dynamic registration support
        self._is_running = False
        self._registered_walker_classes: Set[Type[Walker]] = set()
        self._walker_endpoint_mapping: Dict[Type[Walker], Dict[str, Any]] = (
            {}
        )  # Track walker->endpoint mapping
        self._function_endpoint_mapping: Dict[Callable, Dict[str, Any]] = (
            {}
        )  # Track function->endpoint mapping
        self._dynamic_routers: List[EndpointRouter] = (
            []
        )  # Track dynamic routers for removal
        self._dynamic_routes_registered = False
        self._package_discovery_enabled = True
        self._discovery_patterns: List[str] = ["*_walkers", "*_endpoints", "*_api"]
        self._app_needs_rebuild = False  # Flag to track when app needs rebuilding

        # Register this server globally
        with _server_lock:
            global _default_server
            server_id = id(self)
            _global_servers[str(server_id)] = self
            if _default_server is None:
                _default_server = self

        # Initialize GraphContext if database configuration is provided
        if self.config.db_type:
            self._initialize_graph_context()

    def _initialize_graph_context(self: "Server") -> None:
        """Initialize GraphContext with current database configuration."""
        try:
            # Create database instance based on configuration
            if self.config.db_type == "json":
                db = get_database(
                    db_type="json",
                    base_path=self.config.db_path or "./jv_data",
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
            # Track registered walker classes and their endpoint info
            self._registered_walker_classes.add(walker_class)
            self._walker_endpoint_mapping[walker_class] = {
                "path": path,
                "methods": methods or ["POST"],
                "kwargs": kwargs,
                "router": self.endpoint_router,  # Main router
            }

            # If server is already running, register the endpoint dynamically
            if self._is_running and self.app is not None:
                self._register_walker_dynamically(walker_class, path, methods, **kwargs)

            # Always register with the endpoint router
            return cast(
                Type[Walker],
                self.endpoint_router.endpoint(path, methods, **kwargs)(walker_class),
            )

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

            # Track function endpoint mapping
            self._function_endpoint_mapping[func] = {
                "path": path,
                "methods": methods,
                "kwargs": kwargs,
                "route_config": route_config,
            }

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
            self._middleware.append({"middleware_type": middleware_type, "func": func})
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
        self._startup_tasks.append(func)
        return func

    def on_shutdown(self: "Server", func: Callable[[], Any]) -> Callable[[], Any]:
        """Register shutdown task.

        Args:
            func: Shutdown function

        Returns:
            The original function
        """
        self._shutdown_tasks.append(func)
        return func

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
        """Create a new FastAPI instance with current configuration.

        This is separated from _create_app to allow for rebuilding.
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
                lifespan=self._lifespan,
            )

        # Add CORS middleware if enabled
        if self.config.cors_enabled:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self.config.cors_origins,
                allow_methods=self.config.cors_methods,
                allow_headers=self.config.cors_headers,
                allow_credentials=True,
            )

        # Add webhook middleware before other middleware
        self._add_webhook_middleware(app)

        # Add custom middleware
        for middleware_config in self._middleware:
            app.middleware(middleware_config["middleware_type"])(
                middleware_config["func"]
            )

        # Add exception handlers
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

        # Include the jvspatial endpoint router with webhook walker support
        self._setup_webhook_walker_endpoints()
        app.include_router(self.endpoint_router.router, prefix="/api")

        # Include any dynamic routers
        for dynamic_router in self._dynamic_routers:
            app.include_router(dynamic_router.router, prefix="/api")

        return app

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

            # Track the dynamic router for potential removal
            self._dynamic_routers.append(dynamic_router)

            # Update the mapping to track this dynamic router
            if walker_class in self._walker_endpoint_mapping:
                self._walker_endpoint_mapping[walker_class][
                    "dynamic_router"
                ] = dynamic_router

            # Include the new router in the existing app
            self.app.include_router(dynamic_router.router, prefix="/api")

            self._logger.info(
                f"🔄 Dynamically registered walker: {walker_class.__name__} at {path}"
            )

        except Exception as e:
            self._logger.error(
                f"❌ Failed to dynamically register walker {walker_class.__name__}: {e}"
            )

    def discover_and_register_packages(
        self: "Server", package_patterns: Optional[List[str]] = None
    ) -> int:
        """Discover and register walker endpoints from installed packages.

        Args:
            package_patterns: List of package name patterns to search for

        Returns:
            Number of walker endpoints discovered and registered
        """
        if not self._package_discovery_enabled:
            return 0

        patterns = package_patterns or self._discovery_patterns
        discovered_count = 0

        self._logger.info(f"🔍 Discovering walker packages with patterns: {patterns}")

        # Search through installed packages
        for _finder, module_name, ispkg in pkgutil.iter_modules():
            if not ispkg:
                continue

            # Check if module matches any pattern
            matches_pattern = any(
                self._matches_pattern(module_name, pattern) for pattern in patterns
            )

            if not matches_pattern:
                continue

            try:
                # Import the package
                module = importlib.import_module(module_name)
                count = self._discover_walkers_in_module(module)
                discovered_count += count

                if count > 0:
                    self._logger.info(
                        f"📦 Discovered {count} walkers in package: {module_name}"
                    )

            except Exception as e:
                self._logger.warning(f"⚠️ Failed to import package {module_name}: {e}")

        if discovered_count > 0:
            self._logger.info(f"✅ Total walkers discovered: {discovered_count}")

        return discovered_count

    def _add_webhook_middleware(self: "Server", app: FastAPI) -> None:
        """Add webhook middleware to the FastAPI app if webhook endpoints are present.

        Args:
            app: FastAPI application instance
        """
        # Check if any endpoints are webhook endpoints
        has_webhook_endpoints = False

        # Check function endpoints
        for func in self._function_endpoint_mapping.keys():
            if getattr(func, "_webhook_required", False):
                has_webhook_endpoints = True
                break

        # Check walker endpoints
        if not has_webhook_endpoints:
            for walker_class in self._walker_endpoint_mapping.keys():
                if getattr(walker_class, "_webhook_required", False):
                    has_webhook_endpoints = True
                    break

        if has_webhook_endpoints:
            try:
                from jvspatial.api.webhook.middleware import add_webhook_middleware

                add_webhook_middleware(app, server=self)
                self._logger.info("🔗 Webhook middleware added to server")
            except ImportError as e:
                self._logger.warning(f"⚠️ Could not add webhook middleware: {e}")
        else:
            self._logger.debug(
                "No webhook endpoints found, skipping webhook middleware"
            )

    def _setup_webhook_walker_endpoints(self: "Server") -> None:
        """Set up webhook wrapper for walker endpoints."""
        for walker_class, endpoint_info in self._walker_endpoint_mapping.items():
            if getattr(walker_class, "_webhook_required", False):
                try:
                    from jvspatial.api.webhook.endpoint import (
                        create_webhook_walker_wrapper,
                    )

                    # Create webhook wrapper for the walker
                    wrapper_func = create_webhook_walker_wrapper(walker_class)

                    # Register the wrapper as a custom route instead of walker route
                    path = endpoint_info.get("path", "")
                    methods = endpoint_info.get("methods", ["POST"])
                    kwargs = endpoint_info.get("kwargs", {})

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

    def _matches_pattern(self: "Server", name: str, pattern: str) -> bool:
        """Check if a name matches a glob-style pattern."""
        import fnmatch

        return fnmatch.fnmatch(name, pattern)

    def _discover_walkers_in_module(self: "Server", module: Any) -> int:
        """Discover walker classes and function endpoints in a module and register them.

        Args:
            module: Python module to search

        Returns:
            Number of endpoints discovered (walkers + functions)
        """
        discovered_count = 0

        for _name, obj in inspect.getmembers(module):
            # Discover Walker classes
            if (
                inspect.isclass(obj)
                and issubclass(obj, Walker)
                and obj is not Walker
                and obj not in self._registered_walker_classes
            ):

                # Look for endpoint configuration in the class
                endpoint_config = getattr(obj, "_jvspatial_endpoint_config", None)
                if endpoint_config:
                    path = endpoint_config.get("path")
                    methods = endpoint_config.get("methods", ["POST"])
                    kwargs = endpoint_config.get("kwargs", {})

                    if path:
                        # Register the walker
                        self._registered_walker_classes.add(obj)
                        self._walker_endpoint_mapping[obj] = {
                            "path": path,
                            "methods": methods,
                            "kwargs": kwargs,
                            "router": None,
                        }

                        if self._is_running:
                            self._register_walker_dynamically(
                                obj, path, methods, **kwargs
                            )
                        else:
                            # Register with endpoint router for later
                            self.endpoint_router.endpoint(path, methods, **kwargs)(obj)
                            self._walker_endpoint_mapping[obj][
                                "router"
                            ] = self.endpoint_router

                        discovered_count += 1

            # Discover function endpoints
            elif inspect.isfunction(obj) and hasattr(obj, "_jvspatial_endpoint_config"):

                endpoint_config = obj._jvspatial_endpoint_config
                if endpoint_config.get("is_function"):
                    path = endpoint_config.get("path")
                    methods = endpoint_config.get("methods", ["GET"])
                    kwargs = endpoint_config.get("kwargs", {})

                    if path:
                        # Create wrapper that injects endpoint helper
                        async def endpoint_wrapper(
                            *args: Any, func_obj: Any = obj, **kwargs_inner: Any
                        ) -> Any:
                            # Create endpoint helper for function endpoints
                            endpoint_helper = create_endpoint_helper(
                                walker_instance=None
                            )

                            # Inject endpoint helper into function kwargs
                            kwargs_inner["endpoint"] = endpoint_helper

                            # Call original function with injected endpoint
                            if inspect.iscoroutinefunction(func_obj):
                                return await func_obj(*args, **kwargs_inner)
                            else:
                                return func_obj(*args, **kwargs_inner)

                        # Preserve original function metadata
                        endpoint_wrapper.__name__ = obj.__name__
                        endpoint_wrapper.__doc__ = obj.__doc__

                        # Register the function as a custom route
                        route_config = {
                            "path": path,
                            "endpoint": endpoint_wrapper,
                            "methods": methods,
                            **kwargs,
                        }

                        # Check if already registered
                        if route_config not in self._custom_routes:
                            self._custom_routes.append(route_config)

                            # If server is running, add route dynamically
                            if self._is_running and self.app is not None:
                                self.app.add_api_route(
                                    path, endpoint_wrapper, methods=methods, **kwargs
                                )
                                self._logger.info(
                                    f"🔄 Dynamically registered function: {obj.__name__} at {path}"
                                )

                            discovered_count += 1

        return discovered_count

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
        if walker_class in self._registered_walker_classes:
            self._logger.warning(f"Walker {walker_class.__name__} already registered")
            return

        self._registered_walker_classes.add(walker_class)

        # Track the walker's endpoint information
        self._walker_endpoint_mapping[walker_class] = {
            "path": path,
            "methods": methods or ["POST"],
            "kwargs": kwargs,
            "router": None,  # Will be set if registered dynamically
        }

        if self._is_running and self.app is not None:
            self._register_walker_dynamically(walker_class, path, methods, **kwargs)
        else:
            self.endpoint_router.endpoint(path, methods, **kwargs)(walker_class)
            self._walker_endpoint_mapping[walker_class]["router"] = self.endpoint_router

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
        if walker_class not in self._registered_walker_classes:
            self._logger.warning(f"Walker {walker_class.__name__} not registered")
            return False

        try:
            # Get endpoint information
            endpoint_info = self._walker_endpoint_mapping.get(walker_class)
            if not endpoint_info:
                self._logger.warning(
                    f"No endpoint mapping found for {walker_class.__name__}"
                )
                return False

            # Remove from tracking
            self._registered_walker_classes.discard(walker_class)
            del self._walker_endpoint_mapping[walker_class]

            # If there's a dynamic router, remove it from tracking
            dynamic_router = endpoint_info.get("dynamic_router")
            if dynamic_router and dynamic_router in self._dynamic_routers:
                self._dynamic_routers.remove(dynamic_router)

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
        removed_walkers = []

        # Find all walkers registered to this path
        walkers_to_remove = [
            walker_class
            for walker_class, endpoint_info in self._walker_endpoint_mapping.items()
            if endpoint_info.get("path") == path
        ]

        # Remove each walker
        for walker_class in walkers_to_remove:
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
            # Remove by path
            path = endpoint
            removed_routes = []

            # Find all routes with this path
            for route_config in self._custom_routes[:]:
                if route_config.get("path") == path:
                    self._custom_routes.remove(route_config)
                    removed_routes.append(route_config)

            # Also remove from function endpoint mapping
            functions_to_remove = []
            for func, mapping in self._function_endpoint_mapping.items():
                if mapping.get("path") == path:
                    functions_to_remove.append(func)

            for func in functions_to_remove:
                del self._function_endpoint_mapping[func]

            if removed_routes:
                self._logger.info(
                    f"🗑️ Removed {len(removed_routes)} endpoints from path {path}"
                )
                success = True
            else:
                self._logger.warning(f"No endpoints found at path {path}")
                success = False

        elif callable(endpoint):
            # Remove by function reference
            func = endpoint

            # Remove from function endpoint mapping
            if func not in self._function_endpoint_mapping:
                self._logger.warning(f"Function {func.__name__} not registered")
                return False

            mapping = self._function_endpoint_mapping[func]
            del self._function_endpoint_mapping[func]

            # Remove from custom routes
            func_route_config = mapping.get("route_config")
            if (
                func_route_config is not None
                and func_route_config in self._custom_routes
            ):
                self._custom_routes.remove(func_route_config)

            self._logger.info(f"🗑️ Removed function endpoint: {func.__name__}")
            success = True

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
        removed_count = 0

        # Remove walker endpoints
        removed_walkers = self.unregister_walker_endpoint(path)
        removed_count += len(removed_walkers)

        # Remove function endpoints
        if self.unregister_endpoint(path):
            removed_count += 1

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
        function_info = {}

        for func, endpoint_info in self._function_endpoint_mapping.items():
            function_info[func.__name__] = {
                "path": endpoint_info["path"],
                "methods": endpoint_info["methods"],
                "function": func,
                "module": func.__module__,
            }

        return function_info

    def list_function_endpoints_safe(self: "Server") -> Dict[str, Dict[str, Any]]:
        """Get serializable information about all registered function endpoints (no function objects).

        Returns:
            Dictionary mapping function names to their serializable endpoint information
        """
        function_info = {}

        for func, endpoint_info in self._function_endpoint_mapping.items():
            function_info[func.__name__] = {
                "path": endpoint_info["path"],
                "methods": endpoint_info["methods"],
                "function_name": func.__name__,
                "module": func.__module__,
            }

        return function_info

    def list_all_endpoints(self: "Server") -> Dict[str, Any]:
        """Get information about all registered endpoints (walkers and functions).

        Returns:
            Dictionary with 'walkers' and 'functions' keys containing endpoint information
        """
        return {
            "walkers": self.list_walker_endpoints(),
            "functions": self.list_function_endpoints(),
        }

    def list_all_endpoints_safe(self: "Server") -> Dict[str, Any]:
        """Get serializable information about all registered endpoints (walkers and functions).

        Returns:
            Dictionary with 'walkers' and 'functions' keys containing serializable endpoint information
        """
        return {
            "walkers": self.list_walker_endpoints_safe(),
            "functions": self.list_function_endpoints_safe(),
        }

    def list_walker_endpoints(self: "Server") -> Dict[str, Dict[str, Any]]:
        """Get information about all registered walkers.

        Returns:
            Dictionary mapping walker class names to their endpoint information
        """
        walker_info = {}

        for walker_class, endpoint_info in self._walker_endpoint_mapping.items():
            walker_info[walker_class.__name__] = {
                "path": endpoint_info["path"],
                "methods": endpoint_info["methods"],
                "class": walker_class,
                "is_dynamic": "dynamic_router" in endpoint_info,
                "module": walker_class.__module__,
            }

        return walker_info

    def list_walker_endpoints_safe(self: "Server") -> Dict[str, Dict[str, Any]]:
        """Get serializable information about all registered walkers (no class objects).

        Returns:
            Dictionary mapping walker class names to their serializable endpoint information
        """
        walker_info = {}

        for walker_class, endpoint_info in self._walker_endpoint_mapping.items():
            walker_info[walker_class.__name__] = {
                "path": endpoint_info["path"],
                "methods": endpoint_info["methods"],
                "class_name": walker_class.__name__,
                "is_dynamic": "dynamic_router" in endpoint_info,
                "module": walker_class.__module__,
            }

        return walker_info

    def enable_package_discovery(
        self: "Server", enabled: bool = True, patterns: Optional[List[str]] = None
    ) -> None:
        """Enable or disable automatic package discovery.

        Args:
            enabled: Whether to enable package discovery
            patterns: List of package name patterns to search for
        """
        self._package_discovery_enabled = enabled
        if patterns:
            self._discovery_patterns = patterns

        self._logger.info(f"Package discovery {'enabled' if enabled else 'disabled'}")
        if enabled and patterns:
            self._logger.info(f"Discovery patterns: {patterns}")

    def refresh_endpoints(self: "Server") -> int:
        """Refresh and discover new endpoints from packages.

        Returns:
            Number of new endpoints discovered
        """
        if not self._is_running:
            self._logger.warning("Cannot refresh endpoints - server is not running")
            return 0

        return self.discover_and_register_packages()

    async def _default_startup(self: "Server") -> None:
        """Run default startup tasks."""
        self._logger.info(f"🚀 Starting {self.config.title}...")

        # Set running state
        self._is_running = True

        # Initialize database through GraphContext
        try:
            if self._graph_context:
                # Use explicit GraphContext
                self._logger.info(
                    f"📊 Database initialized through GraphContext: {type(self._graph_context.database).__name__}"
                )

                # Ensure root node exists
                root = await self._graph_context.get_node(Root, "root")
                if not root:
                    root = await self._graph_context.create_node(Root)
                self._logger.info(f"🌳 Root node ready: {root.id}")
            else:
                # Use default GraphContext behavior
                self._logger.info(
                    "📊 Using default GraphContext for database management"
                )

                # Ensure root node exists
                root = await Root.get(id="root")
                if not root:
                    root = await Root.create()
                self._logger.info(f"🌳 Root node ready: {root.id}")

        except Exception as e:
            self._logger.error(f"❌ Database initialization failed: {e}")
            raise

        # Discover and register packages after database is ready
        if self._package_discovery_enabled:
            try:
                discovered_count = self.discover_and_register_packages()
                if discovered_count > 0:
                    self._logger.info(
                        f"🔍 Package discovery complete: {discovered_count} endpoints"
                    )
            except Exception as e:
                self._logger.warning(f"⚠️ Package discovery failed: {e}")

    async def _default_shutdown(self: "Server") -> None:
        """Run default shutdown tasks."""
        self._logger.info(f"🛑 Shutting down {self.config.title}...")

        # Clear running state
        self._is_running = False

    @asynccontextmanager
    async def _lifespan(self: "Server", app: FastAPI) -> AsyncGenerator[None, None]:
        """Application lifespan manager."""
        # Startup
        await self._default_startup()
        for task in self._startup_tasks:
            try:
                if asyncio.iscoroutinefunction(task):
                    await task()
                else:
                    task()
            except Exception as e:
                self._logger.error(f"Startup task failed: {e}")

        yield  # Application is running

        # Shutdown
        await self._default_shutdown()
        for task in self._shutdown_tasks:
            try:
                if asyncio.iscoroutinefunction(task):
                    await task()
                else:
                    task()
            except Exception as e:
                self._logger.error(f"Shutdown task failed: {e}")

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


def get_default_server() -> Optional[Server]:
    """Get the default server instance.

    Returns:
        The default server instance if one exists, otherwise None
    """
    with _server_lock:
        return _default_server


def set_default_server(server: Server) -> None:
    """Set the default server instance.

    Args:
        server: Server instance to set as default
    """
    with _server_lock:
        global _default_server
        _default_server = server
        _global_servers[str(id(server))] = server


def get_server_by_id(server_id: str) -> Optional[Server]:
    """Get a server instance by ID.

    Args:
        server_id: Server ID to look up

    Returns:
        Server instance if found, otherwise None
    """
    with _server_lock:
        return _global_servers.get(server_id)


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

        # Try to register with default server if available
        default_server = get_default_server()
        if default_server is not None:
            default_server.register_walker_class(walker_class, path, methods, **kwargs)
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

        # Try to register with default server if available
        default_server = get_default_server()
        if default_server is not None:
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
            default_server._custom_routes.append(route_config)

            # Track function endpoint mapping
            default_server._function_endpoint_mapping[func] = {
                "path": path,
                "methods": methods or ["GET"],
                "kwargs": kwargs,
                "route_config": route_config,
                "wrapper": endpoint_wrapper,
            }

            # If server is running, add route dynamically
            if default_server._is_running and default_server.app is not None:
                default_server.app.add_api_route(
                    path, endpoint_wrapper, methods=methods or ["GET"], **kwargs
                )
                default_server._logger.info(
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
