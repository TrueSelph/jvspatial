"""Server class for FastAPI applications using jvspatial.

This module provides a high-level, object-oriented interface for creating
FastAPI servers with jvspatial integration, including automatic database
setup, lifecycle management, and endpoint routing.
"""

import inspect
import logging
import sys
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

from jvspatial.api.components import AppBuilder, EndpointManager, ErrorHandler
from jvspatial.api.config import ServerConfig
from jvspatial.api.constants import APIRoutes
from jvspatial.api.endpoints.response import create_endpoint_helper
from jvspatial.api.endpoints.router import EndpointRouter
from jvspatial.api.middleware.manager import MiddlewareManager
from jvspatial.api.services.discovery import PackageDiscoveryService
from jvspatial.api.services.lifecycle import LifecycleManager
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Node, Root, Walker
from jvspatial.db.factory import create_database


class Server:
    """High-level FastAPI server wrapper for jvspatial applications.

    This class provides a simplified interface for creating FastAPI servers
    with automatic jvspatial integration, database setup, and lifecycle management.

    Example:
        ```python
        from jvspatial.api.server import Server, endpoint
        from jvspatial.core.entities import Walker, Node, on_visit

        # Simple server with default GraphContext
        server = Server(
            title="My Spatial API",
            description="A spatial data management API"
        )

        @endpoint("/process")
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
        # Initialize configuration using clean merging
        self.config = ServerConfig(**self._merge_config(config, kwargs))

        # Initialize focused components
        self.app_builder = AppBuilder(self.config)
        self.endpoint_manager = EndpointManager()
        self.error_handler = ErrorHandler()
        self.middleware_manager = MiddlewareManager(self)
        self.lifecycle_manager = LifecycleManager(self)
        self.discovery_service = PackageDiscoveryService(self)

        # Initialize legacy components for backward compatibility
        self.app: Optional[FastAPI] = None
        self.endpoint_router = EndpointRouter()  # Main router for all endpoints
        self._exception_handlers: Dict[Union[int, Type[Exception]], Callable] = {}
        self._logger = logging.getLogger(__name__)
        self._graph_context: Optional[GraphContext] = None

        # File storage components
        self._file_interface: Optional[Any] = None
        self._proxy_manager: Optional[Any] = None
        self._file_storage_service: Optional[Any] = None

        # Endpoint registry service - central tracking for all endpoints
        self._endpoint_registry = self.endpoint_manager.get_registry()

        # Dynamic registration support
        self._is_running = False
        self._dynamic_routes_registered = False
        self._app_needs_rebuild = False  # Flag to track when app needs rebuilding
        self._has_auth_endpoints = False  # Flag to track if auth endpoints exist
        self._custom_routes: List[Dict[str, Any]] = []

        # Authentication configuration
        self._auth_config: Optional[Any] = None
        self._auth_endpoints_registered = False

        # Serverless/Lambda handler
        self._lambda_handler: Optional[Any] = None

        # Automatically set this server as the current server in context
        # The most recently instantiated Server becomes the current one
        from jvspatial.api.context import set_current_server

        set_current_server(self)

        # Initialize GraphContext if database configuration is provided
        if self.config.db_type:
            self._initialize_graph_context()

        # Configure authentication if enabled (after context is initialized)
        self._configure_authentication()

        # Initialize file storage if enabled
        if self.config.file_storage_enabled:
            self._initialize_file_storage()

        # Initialize serverless handler if enabled
        if self.config.serverless_mode:
            self._initialize_serverless_handler()

    def _configure_authentication(self: "Server") -> None:
        """Configure authentication middleware and register auth endpoints if enabled."""
        if not self.config.auth_enabled:
            return

        # Create auth configuration
        from jvspatial.api.auth.config import AuthConfig

        self._auth_config = AuthConfig(
            enabled=True,
            exempt_paths=self.config.auth_exempt_paths,
            jwt_secret=self.config.jwt_secret,
            jwt_algorithm=self.config.jwt_algorithm,
            jwt_expire_minutes=self.config.jwt_expire_minutes,
            api_key_header=self.config.api_key_header,
            session_cookie_name=self.config.session_cookie_name,
            session_expire_minutes=self.config.session_expire_minutes,
        )

        # Register authentication endpoints
        self._register_auth_endpoints()

        self._logger.info("🔐 Authentication configured and endpoints registered")

    def _register_auth_endpoints(self: "Server") -> None:
        """Register authentication endpoints if auth is enabled."""
        if self._auth_endpoints_registered:
            return

        # Import authentication service and models
        from typing import Optional

        from fastapi import APIRouter, Depends, Header, HTTPException
        from fastapi.security import (
            HTTPAuthorizationCredentials,
            HTTPBearer,
        )

        from jvspatial.api.auth.models import (
            TokenResponse,
            UserCreate,
            UserLogin,
            UserResponse,
        )
        from jvspatial.api.auth.service import AuthenticationService

        # Helper function to get authentication service
        def get_auth_service():
            """Get authentication service using prime database for core persistence.

            Authentication and session management always use the prime database
            regardless of the current database context.
            """
            from jvspatial.db import get_prime_database

            # Create context with prime database for auth operations
            prime_ctx = GraphContext(database=get_prime_database())
            return AuthenticationService(prime_ctx)

        # Create auth router
        auth_router = APIRouter(prefix="/auth", tags=["Authentication"])

        # Create custom security scheme for BearerAuth compatibility
        security = HTTPBearer(scheme_name="BearerAuth")

        # Helper function to get current user from token
        # Note: Header(None) is required by FastAPI for optional headers
        _default_header = Header(None)  # noqa: B008

        async def get_current_user(
            authorization: Optional[str] = _default_header,  # type: ignore[assignment]
        ) -> UserResponse:
            """Get current user from Authorization header."""
            if not authorization:
                raise HTTPException(
                    status_code=401, detail="Authorization header required"
                )

            # Extract token from "Bearer <token>" format
            try:
                scheme, token = authorization.split(" ", 1)
                if scheme.lower() != "bearer":
                    raise HTTPException(
                        status_code=401, detail="Invalid authentication scheme"
                    )
            except ValueError:
                raise HTTPException(
                    status_code=401, detail="Invalid authorization header format"
                )

            # Initialize authentication service and validate token
            auth_service = get_auth_service()
            user = await auth_service.validate_token(token)
            if not user:
                raise HTTPException(status_code=401, detail="Invalid or expired token")

            return user

        # Register endpoint
        @auth_router.post("/register", response_model=UserResponse)
        async def register(user_data: UserCreate):
            """Register a new user."""
            try:
                # Initialize authentication service with current context
                auth_service = get_auth_service()
                user = await auth_service.register_user(user_data)
                return user
            except ValueError as e:
                raise HTTPException(status_code=400, detail=str(e))
            except Exception as e:
                self._logger.error(f"Registration error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # Login endpoint
        @auth_router.post("/login", response_model=TokenResponse)
        async def login(login_data: UserLogin):
            """Login endpoint for authentication."""
            try:
                # Initialize authentication service with current context
                auth_service = get_auth_service()
                token_response = await auth_service.login_user(login_data)
                return token_response
            except ValueError as e:
                raise HTTPException(status_code=401, detail=str(e))
            except Exception as e:
                self._logger.error(f"Login error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # Logout endpoint (requires authentication)
        # Note: Depends(security) is required by FastAPI for dependency injection
        _default_security_dep = Depends(security)  # noqa: B008

        @auth_router.post("/logout", dependencies=[_default_security_dep])
        async def logout(credentials: HTTPAuthorizationCredentials = _default_security_dep):  # type: ignore[assignment]
            """Logout endpoint for authentication."""
            try:
                # Initialize authentication service with current context
                auth_service = get_auth_service()

                # Get token from credentials
                token = credentials.credentials

                # Validate token and blacklist it
                await auth_service.logout_user(token)

                return {"message": "Logged out successfully"}
            except Exception as e:
                self._logger.error(f"Logout error: {e}")
                raise HTTPException(status_code=500, detail="Internal server error")

        # Register auth router with the app when it's created
        self._auth_router = auth_router
        self._auth_endpoints_registered = True
        self._has_auth_endpoints = True  # Enable OpenAPI security configuration

    def _merge_config(self, config, kwargs) -> Dict[str, Any]:
        """Clean configuration merging.

        Args:
            config: Configuration object or dict
            kwargs: Additional configuration parameters

        Returns:
            Merged configuration dictionary
        """
        if config is None:
            return kwargs
        elif isinstance(config, ServerConfig):
            return {**config.model_dump(), **kwargs}
        else:
            return {**config, **kwargs}

    def _initialize_graph_context(self: "Server") -> None:
        """Initialize GraphContext with current database configuration.

        This sets up the prime database for core persistence operations
        (authentication, session management) and creates a GraphContext
        that uses the current database from DatabaseManager.
        """
        try:
            from jvspatial.db.manager import get_database_manager

            # Get or create database manager
            manager = get_database_manager()

            # Create prime database based on configuration
            if self.config.db_type == "json":
                prime_db = create_database(
                    db_type="json",
                    base_path=self.config.db_path or "./jvdb",
                )
            elif self.config.db_type == "mongodb":
                prime_db = create_database(
                    db_type="mongodb",
                    uri=self.config.db_connection_string or "mongodb://localhost:27017",
                    db_name=self.config.db_database_name or "jvdb",
                )
            elif self.config.db_type == "sqlite":
                prime_db = create_database(
                    db_type="sqlite",
                    db_path=self.config.db_path or "jvdb/sqlite/jvspatial.db",
                )
            elif self.config.db_type == "dynamodb":
                prime_db = create_database(
                    db_type="dynamodb",
                    table_name=self.config.dynamodb_table_name or "jvspatial",
                    region_name=self.config.dynamodb_region or "us-east-1",
                    endpoint_url=self.config.dynamodb_endpoint_url,
                    aws_access_key_id=self.config.dynamodb_access_key_id,
                    aws_secret_access_key=self.config.dynamodb_secret_access_key,
                )
            else:
                raise ValueError(f"Unsupported database type: {self.config.db_type}")

            # Initialize manager with prime database if not already initialized
            try:
                manager.get_prime_database()
                # Update prime database if it was already initialized
                manager._prime_database = prime_db
                manager._databases["prime"] = prime_db
            except (RuntimeError, AttributeError):
                # Manager not initialized yet, set it up
                manager._prime_database = prime_db
                manager._databases["prime"] = prime_db
                manager._current_database_name = "prime"

            # Create GraphContext using current database (which defaults to prime)
            self._graph_context = GraphContext(database=manager.get_current_database())

            # Set as default context so entities can use it automatically
            from jvspatial.core.context import set_default_context

            set_default_context(self._graph_context)

            self._logger.info(
                f"🎯 GraphContext initialized with {self.config.db_type} database (prime) and set as default"
            )

        except Exception as e:
            self._logger.error(f"❌ Failed to initialize GraphContext: {e}")
            raise

    def _initialize_file_storage(self: "Server") -> None:
        """Initialize file storage interface and proxy manager."""
        try:
            from jvspatial.api.services.file_storage import FileStorageService
            from jvspatial.storage import create_storage, get_proxy_manager

            # Initialize file interface
            if self.config.file_storage_provider == "local":
                self._file_interface = create_storage(
                    provider="local",
                    root_dir=self.config.file_storage_root,
                    base_url=self.config.file_storage_base_url,
                    max_file_size=self.config.file_storage_max_size,
                )
            elif self.config.file_storage_provider == "s3":
                self._file_interface = create_storage(
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

    def _initialize_serverless_handler(self: "Server") -> None:
        """Initialize serverless Lambda handler if serverless mode is enabled.

        This method automatically creates a Mangum adapter for the FastAPI app
        when serverless_mode is True in the configuration.
        """
        try:
            from mangum import Mangum
        except ImportError:
            self._logger.warning(
                "Mangum is required for serverless deployment but not installed. "
                "Install it with: pip install mangum>=0.17.0 "
                "or pip install jvspatial[serverless]"
            )
            return

        # Get the app (this will create it if it doesn't exist)
        app = self.get_app()

        # Configure Mangum with serverless settings
        mangum_config: Dict[str, Any] = {
            "lifespan": self.config.serverless_lifespan,
        }

        if self.config.serverless_api_gateway_base_path:
            mangum_config["api_gateway_base_path"] = (
                self.config.serverless_api_gateway_base_path
            )

        # Create Mangum adapter
        self._lambda_handler = Mangum(app, **mangum_config)

        # Automatically expose handler at module level for Lambda deployment
        self._expose_handler_to_caller_module()

        self._logger.info(
            "🚀 Serverless Lambda handler initialized and ready for deployment"
        )

    def _expose_handler_to_caller_module(self: "Server") -> None:
        """Expose the Lambda handler as a module-level variable in the caller's module.

        This allows AWS Lambda to access the handler without requiring
        manual assignment (e.g., `handler = server.lambda_handler`).
        """
        try:
            # Get the caller's frame (skip this method and _initialize_serverless_handler)
            frame = inspect.currentframe()
            if frame is None:
                return

            # Go up 2 frames: _expose_handler_to_caller_module -> _initialize_serverless_handler -> caller
            caller_frame = frame.f_back
            if caller_frame is None:
                return
            caller_frame = caller_frame.f_back
            if caller_frame is None:
                return

            # Get the caller's module
            caller_module = sys.modules.get(caller_frame.f_globals.get("__name__"))
            if caller_module is None:
                return

            # Only expose if 'handler' doesn't already exist in the module
            # This prevents overwriting user-defined handlers
            handler_attr = "handler"  # Use variable to avoid B010 flake8 warning
            if not hasattr(caller_module, handler_attr):
                # Dynamically set handler attribute on module for Lambda deployment
                # Using setattr with variable to satisfy flake8 B010, with type ignore for mypy
                setattr(caller_module, handler_attr, self._lambda_handler)  # type: ignore[attr-defined]
                self._logger.debug(
                    f"✅ Lambda handler automatically exposed as 'handler' in {caller_module.__name__}"
                )
            else:
                self._logger.debug(
                    f"⚠️  'handler' already exists in {caller_module.__name__}, skipping auto-exposure"
                )
        except Exception as e:
            # Don't fail if we can't expose the handler - user can still access it manually
            self._logger.debug(f"Could not auto-expose handler: {e}")

    def middleware(self: "Server", middleware_type: str = "http") -> Callable:
        """Add middleware to the application.

        Args:
            middleware_type: Type of middleware ("http" or "websocket")

        Returns:
            Decorator function for middleware
        """

        def decorator(func: Callable) -> Callable:
            # Store the middleware for later async registration
            # This is a workaround for the async/sync decorator issue
            self.middleware_manager._custom_middleware.append(
                {"func": func, "middleware_type": middleware_type}
            )

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

    async def on_startup(self: "Server", func: Callable[[], Any]) -> Callable[[], Any]:
        """Register startup task.

        Args:
            func: Startup function

        Returns:
            The original function
        """
        return self.lifecycle_manager.add_startup_hook(func)

    async def on_shutdown(self: "Server", func: Callable[[], Any]) -> Callable[[], Any]:
        """Register shutdown task.

        Args:
            func: Shutdown function

        Returns:
            The original function
        """
        return self.lifecycle_manager.add_shutdown_hook(func)

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
        """Create FastAPI instance using the focused AppBuilder component.

        Returns:
            FastAPI: Fully configured application instance
        """
        # Create base app with lifespan
        lifespan = self.lifecycle_manager.lifespan if not self._is_running else None
        app = self.app_builder.create_app(lifespan=lifespan)

        # Configure middleware using MiddlewareManager
        self.middleware_manager.configure_all(app)

        # Configure authentication middleware if enabled
        self._configure_auth_middleware(app)

        # Configure exception handlers
        self._configure_exception_handlers(app)

        # Register core routes using AppBuilder
        self.app_builder.register_core_routes(app, self._graph_context)

        # Include routers
        self._include_routers(app)

        # Include authentication router if configured
        if self._auth_endpoints_registered and hasattr(self, "_auth_router"):
            app.include_router(self._auth_router)

        # Configure OpenAPI security
        self.app_builder.configure_openapi_security(app, self._has_auth_endpoints)

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
                lifespan=self.lifecycle_manager.lifespan,
            )
        return app

    def _configure_middleware(self: "Server", app: FastAPI) -> None:
        """Configure all middleware using MiddlewareManager.

        Works in both sync and async contexts.

        Args:
            app: FastAPI application instance to configure
        """
        self.middleware_manager.configure_all(app)

    def _configure_exception_handlers(self: "Server", app: FastAPI) -> None:
        """Configure all exception handlers using the unified ErrorHandler.

        Args:
            app: FastAPI application instance to configure
        """
        # Add custom exception handlers
        for exc_class, handler in self._exception_handlers.items():
            app.add_exception_handler(exc_class, handler)

        # Add default exception handler using the unified ErrorHandler
        @app.exception_handler(Exception)
        async def global_exception_handler(
            request: Request, exc: Exception
        ) -> JSONResponse:
            return await ErrorHandler.handle_exception(request, exc)

    def _configure_auth_middleware(self: "Server", app: FastAPI) -> None:
        """Configure authentication middleware if authentication is enabled."""
        if not self.config.auth_enabled or not self._auth_config:
            return

        try:
            from jvspatial.api.components.auth_middleware import (
                AuthenticationMiddleware,
            )

            app.add_middleware(
                AuthenticationMiddleware, auth_config=self._auth_config, server=self
            )
            self._logger.info("🔐 Authentication middleware added to server")
        except ImportError as e:
            self._logger.warning(f"Could not add authentication middleware: {e}")

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
                    root = await self._graph_context.get(Root, "n:Root:root")
                    if not root:
                        root = await self._graph_context.create(Root)
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

    def _include_routers(self: "Server", app: FastAPI) -> None:
        """Include endpoint routers and dynamic routers.

        Args:
            app: FastAPI application instance to configure
        """
        # Include the unified endpoint router with all endpoints
        app.include_router(self.endpoint_router.router, prefix=APIRoutes.PREFIX)

        # Include any dynamic routers from registry
        for endpoint_info in self._endpoint_registry.get_dynamic_endpoints():
            if endpoint_info.router:
                app.include_router(endpoint_info.router.router, prefix=APIRoutes.PREFIX)

    def _configure_openapi_security(self: "Server", app: FastAPI) -> None:
        """Configure OpenAPI security schemes if auth endpoints exist.

        Args:
            app: FastAPI application instance to configure
        """
        # Check if server has any authenticated endpoints
        if getattr(self, "_has_auth_endpoints", False):
            # Configure OpenAPI security if needed
            from jvspatial.api.auth.openapi_config import configure_openapi_security

            configure_openapi_security(app)
            self._logger.debug("📄 OpenAPI security schemes configured")

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
            # Register the new router in the existing app
            self.app.include_router(dynamic_router.router, prefix=APIRoutes.PREFIX)

            # Transfer auth metadata to the FastAPI route handler
            for route in self.app.routes:
                if hasattr(route, "path") and path in route.path:
                    route_handler = route.endpoint
                    route_handler._auth_required = getattr(
                        walker_class, "_auth_required", False
                    )
                    route_handler._required_permissions = getattr(
                        walker_class, "_required_permissions", []
                    )
                    route_handler._required_roles = getattr(
                        walker_class, "_required_roles", []
                    )
                    break

            self._logger.info(
                f"🔄 Dynamically registered walker: {walker_class.__name__} at {path}"
            )

        except Exception as e:
            self._logger.error(
                f"❌ Failed to dynamically register walker {walker_class.__name__}: {e}"
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
            # Pre-configure walker class with endpoint for discovery
            walker_class._jvspatial_endpoint_config = {
                "path": path,
                "methods": methods or ["POST"],
                "kwargs": kwargs,
            }
            # Register with router
            self.endpoint_router.endpoint(path, methods, **kwargs)(walker_class)

        self._logger.info(
            f"📝 Registered walker class: {walker_class.__name__} at {path}"
        )

    async def unregister_walker_class(
        self: "Server", walker_class: Type[Walker]
    ) -> bool:
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

    async def unregister_walker_endpoint(
        self: "Server", path: str
    ) -> List[Type[Walker]]:
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

    async def unregister_endpoint(
        self: "Server", endpoint: Union[str, Callable]
    ) -> bool:
        """Remove a function endpoint from the server.

        Args:
            endpoint: Either the path string or the function to remove

        Returns:
            True if the endpoint was successfully removed, False otherwise
        """
        if isinstance(endpoint, str):
            # Remove by path using registry
            path = endpoint
            removed_count = self._endpoint_registry.unregister_by_path(path)

            if removed_count > 0:
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

    async def unregister_endpoint_by_path(self: "Server", path: str) -> int:
        """Remove all endpoints (both walker and function) from a specific path.

        Args:
            path: The URL path to remove all endpoints from

        Returns:
            Number of endpoints removed
        """
        # Use registry to remove all endpoints at path
        removed_count = self._endpoint_registry.unregister_by_path(path)

        if removed_count > 0:
            self._logger.info(
                f"🗑️ Removed {removed_count} total endpoints from path {path}"
            )

        return removed_count

    async def list_function_endpoints(self: "Server") -> Dict[str, Dict[str, Any]]:
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
        self.discovery_service.enable(enabled, patterns)

    def refresh_endpoints(self: "Server") -> int:
        """Refresh and discover new endpoints from packages.

        Returns:
            Number of new endpoints discovered
        """
        if not self._is_running:
            self._logger.warning("Cannot refresh endpoints - server is not running")
            return 0

        return self.discovery_service.discover_and_register()

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

    @property
    def lambda_handler(self: "Server") -> Optional[Any]:
        """Get the Lambda handler if serverless mode is enabled.

        Returns:
            Lambda handler function if serverless is enabled, None otherwise

        Example:
            ```python
            server = Server(serverless_mode=True, title="My Lambda API")

            # Access handler directly
            handler = server.lambda_handler
            ```
        """
        return self._lambda_handler

    def get_lambda_handler(self: "Server", **mangum_kwargs: Any) -> Any:
        """Get an AWS Lambda handler for serverless deployment.

        This method wraps the FastAPI application with Mangum, an ASGI adapter
        for AWS Lambda. If serverless mode is enabled, returns the pre-configured
        handler. Otherwise, creates a new handler with the provided options.

        Args:
            **mangum_kwargs: Additional Mangum configuration options (only used
                if serverless mode is not enabled). Common options include:
                - lifespan: "off" to disable lifespan events (default: "auto")
                - api_gateway_base_path: Base path for API Gateway
                - text_mime_types: List of text MIME types

        Returns:
            Lambda handler function compatible with AWS Lambda

        Example:
            ```python
            # Option 1: Enable serverless mode (handler created automatically)
            server = Server(serverless_mode=True, title="My API")
            handler = server.get_lambda_handler()  # Returns pre-configured handler

            # Option 2: Manual handler creation
            server = Server(title="My API")
            handler = server.get_lambda_handler(lifespan="auto")
            ```

        Note:
            Requires the 'mangum' package to be installed:
            pip install mangum>=0.17.0
            Or install optional dependencies:
            pip install jvspatial[serverless]
        """
        # If serverless mode is enabled, return the pre-configured handler
        if self.config.serverless_mode and self._lambda_handler is not None:
            if mangum_kwargs:
                self._logger.warning(
                    "Serverless mode is enabled. Additional mangum_kwargs are ignored. "
                    "Configure serverless options via ServerConfig instead."
                )
            return self._lambda_handler

        # Otherwise, create handler on-demand
        try:
            from mangum import Mangum
        except ImportError:
            raise ImportError(
                "Mangum is required for serverless deployment. "
                "Install it with: pip install mangum>=0.17.0 "
                "or pip install jvspatial[serverless]"
            )

        app = self.get_app()

        # Configure Mangum with sensible defaults for Lambda
        mangum_config = {
            "lifespan": "auto",  # Enable lifespan events (startup/shutdown)
            **mangum_kwargs,
        }

        # Create Mangum adapter
        handler = Mangum(app, **mangum_config)

        self._logger.info("🚀 Lambda handler created for serverless deployment")

        return handler

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

    def has_endpoint(self, path: str) -> bool:
        """Check if server has any endpoints at the given path.

        Args:
            path: URL path to check

        Returns:
            True if any endpoints exist at the path, False otherwise
        """
        return self._endpoint_registry.has_path(path)

    def set_graph_context(self: "Server", context: GraphContext) -> None:
        """Set a custom GraphContext for the server.

        Args:
            context: GraphContext instance to use
        """
        self._graph_context = context
        self._logger.info("🎯 Custom GraphContext set for server")

    def endpoint(
        self, path: str, methods: Optional[List[str]] = None, **kwargs: Any
    ) -> Callable:
        """Endpoint decorator for the server instance.

        Args:
            path: URL path for the endpoint
            methods: HTTP methods (default: ["POST"] for walkers, ["GET"] for functions)
            **kwargs: Additional route parameters

        Returns:
            Decorator function for endpoints
        """
        return self.endpoint_manager.register_endpoint(path, methods, **kwargs)


def endpoint(
    path: str, methods: Optional[List[str]] = None, **kwargs: Any
) -> Callable[[Union[Type[Walker], Callable]], Union[Type[Walker], Callable]]:
    """Universal endpoint decorator for both walkers and functions.

    Automatically detects whether decorating a Walker class or function.

    Args:
        path: URL path for the endpoint
        methods: HTTP methods (default: ["POST"] for walkers, ["GET"] for functions)
        **kwargs: Additional route parameters (tags, summary, etc.)

    Returns:
        Decorator function that works with both Walker classes and functions

    Examples:
        # Function endpoint (auto-detected)
        @endpoint("/users/count", methods=["GET"])
        async def get_user_count(endpoint):
            return endpoint.success(data={"count": 42})

        # Walker endpoint (auto-detected)
        @endpoint("/process", methods=["POST"])
        class ProcessData(Walker):
            data: str
    """
    # Remove server parameter from kwargs if present - FastAPI doesn't need it
    route_kwargs = {k: v for k, v in kwargs.items() if k != "server"}

    def decorator(
        target: Union[Type[Walker], Callable]
    ) -> Union[Type[Walker], Callable]:
        from jvspatial.api.context import get_current_server

        current_server = get_current_server()

        if current_server is None:
            # Store configuration for later discovery
            cast(Any, target)._jvspatial_endpoint_config = {
                "path": path,
                "methods": (
                    methods or (["POST"] if issubclass(target, Walker) else ["GET"])
                    if inspect.isclass(target)
                    else ["GET"]
                ),
                "kwargs": route_kwargs,
                "is_function": not inspect.isclass(target)
                or not issubclass(target, Walker),
            }
            return target

        # Handle Walker class
        if inspect.isclass(target) and issubclass(target, Walker):
            current_server.register_walker_class(
                target, path, methods=methods or ["POST"], **route_kwargs
            )
            return target

        # Handle function endpoint
        func = target

        # Create wrapper if endpoint helper is needed
        if "endpoint" in inspect.signature(func).parameters:
            import functools

            @functools.wraps(func)
            async def func_wrapper(*args: Any, **kwargs_inner: Any) -> Any:
                endpoint_helper = create_endpoint_helper(walker_instance=None)
                kwargs_inner["endpoint"] = endpoint_helper
                return (
                    await func(*args, **kwargs_inner)
                    if inspect.iscoroutinefunction(func)
                    else func(*args, **kwargs_inner)
                )

        else:
            # If no wrapper is needed, func_wrapper is just the original func
            func_wrapper = func  # type: ignore[assignment]

        # Register with endpoint registry and router
        try:
            current_server._endpoint_registry.register_function(
                func,
                path,
                methods=methods or ["GET"],
                route_config={
                    "path": path,
                    "endpoint": func_wrapper,
                    "methods": methods or ["GET"],
                    **route_kwargs,
                },
                **route_kwargs,
            )

            current_server.endpoint_router.router.add_api_route(
                path=path,
                endpoint=func_wrapper,
                methods=methods or ["GET"],
                **route_kwargs,
            )

            current_server._logger.info(
                f"{'🔄' if current_server._is_running else '📝'} "
                f"{'Dynamically registered' if current_server._is_running else 'Registered'} "
                f"function endpoint: {func.__name__} at {path}"
            )

        except Exception as e:
            current_server._logger.warning(
                f"Function {func.__name__} already registered: {e}"
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


def create_lambda_handler(
    server: Optional[Server] = None,
    **server_kwargs: Any,
) -> Any:
    """Create a Lambda handler from a Server instance or create a new one.

    This is a convenience function for creating Lambda handlers. If a server
    instance is provided, it will use that. Otherwise, it creates a new server
    with the provided configuration.

    Args:
        server: Optional Server instance. If None, a new server will be created.
        **server_kwargs: Configuration for creating a new server if server is None.
            Also accepts **mangum_kwargs for Mangum configuration.

    Returns:
        Lambda handler function compatible with AWS Lambda

    Example:
        ```python
        from jvspatial.api import endpoint, create_lambda_handler

        @endpoint("/hello")
        async def hello():
            return {"message": "Hello from Lambda!"}

        # Create handler - server will be auto-created
        handler = create_lambda_handler(title="My Lambda API")
        ```

    Note:
        Requires the 'mangum' package to be installed:
        pip install mangum>=0.17.0
        Or install optional dependencies:
        pip install jvspatial[serverless]
    """
    # Separate mangum kwargs from server kwargs
    mangum_kwargs = {}
    server_config = {}

    # Known Mangum configuration keys
    mangum_keys = {
        "lifespan",
        "api_gateway_base_path",
        "text_mime_types",
        "exclude_headers",
        "exclude_query_strings",
    }

    for key, value in server_kwargs.items():
        if key in mangum_keys:
            mangum_kwargs[key] = value
        else:
            server_config[key] = value

    # Use provided server or create a new one
    if server is None:
        server = Server(**server_config)

    # Get Lambda handler from server
    return server.get_lambda_handler(**mangum_kwargs)
