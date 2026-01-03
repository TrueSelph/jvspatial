"""Server class for FastAPI applications using jvspatial.

This module provides a high-level, object-oriented interface for creating
FastAPI servers with jvspatial integration, including automatic database
setup, lifecycle management, and endpoint routing.

"""

import contextlib
import logging
import re
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

from jvspatial.api.components import AppBuilder, EndpointManager
from jvspatial.api.components.error_handler import APIErrorHandler
from jvspatial.api.config import ServerConfig
from jvspatial.api.constants import APIRoutes
from jvspatial.api.endpoints.router import EndpointRouter
from jvspatial.api.middleware.manager import MiddlewareManager
from jvspatial.api.services.discovery import EndpointDiscoveryService
from jvspatial.api.services.lifecycle import LifecycleManager
from jvspatial.core.context import GraphContext
from jvspatial.core.entities import Node, Root, Walker
from jvspatial.db.factory import create_database
from jvspatial.logging import configure_standard_logging


class _LevelColorFormatter(logging.Formatter):
    """Colorize only the level name to match jvspatial console format."""

    _LEVEL_COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",  # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",  # Red
        "CRITICAL": "\033[41m\033[97m",  # White on red background
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:  # type: ignore[override]
        color = self._LEVEL_COLORS.get(record.levelname, "")
        original_levelname = record.levelname
        if color:
            record.levelname = f"{color}{record.levelname}{self._RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


class Server:
    """Base server class for FastAPI applications using jvspatial.

    This class provides core server functionality including:
    - FastAPI application creation and configuration
    - Database and file storage initialization
    - Endpoint registration and routing
    - Middleware and exception handling
    - Authentication setup
    - Lifecycle management

    For Lambda/serverless deployments, use LambdaServer which extends this class
    with Lambda-specific functionality.

    Example:
        ```python
        from jvspatial.api.server import Server, endpoint
        from jvspatial.core.entities import Walker, Node, on_visit

        # Standard server
        server = Server(
            title="My Spatial API",
            description="A spatial data management API",
            db_type="json",
            db_path="./data"
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
        merged_config = self._merge_config(config, kwargs)

        self.config = ServerConfig(**merged_config)

        # Initialize focused components
        self.app_builder = AppBuilder(self.config)
        self.endpoint_manager = EndpointManager()
        self.error_handler = APIErrorHandler()
        self.middleware_manager = MiddlewareManager(self)
        self.lifecycle_manager = LifecycleManager(self)
        self.discovery_service = EndpointDiscoveryService(self)

        # Initialize application components
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

        self._logger.debug("🔐 Authentication configured and endpoints registered")

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
        auth_router = APIRouter(prefix="/auth", tags=["App"])

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
            """Register a new user.

            The email field is validated by Pydantic's EmailStr type,
            which ensures proper email format before this function is called.
            """
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
            from jvspatial.db.manager import (
                DatabaseManager,
                get_database_manager,
                set_database_manager,
            )

            # Create prime database based on configuration FIRST
            # This ensures we use the server's configuration, not default environment variables
            prime_db = None

            if self.config.db_type == "json":
                # Check if db_path is an S3 path (not supported for file-based databases)
                db_path = self.config.db_path or "./jvdb"
                if db_path.startswith("s3://"):
                    raise ValueError(
                        f"JSON database does not support S3 paths. "
                        f"Received: {db_path}. "
                        f"Use a local path or DynamoDB (db_type='dynamodb') for cloud storage."
                    )

                # Create database with the (potentially overridden) db_path
                prime_db = create_database(
                    db_type="json",
                    base_path=db_path,
                )
            elif self.config.db_type == "mongodb":
                prime_db = create_database(
                    db_type="mongodb",
                    uri=self.config.db_connection_string or "mongodb://localhost:27017",
                    db_name=self.config.db_database_name or "jvdb",
                )
            elif self.config.db_type == "sqlite":
                # Check if db_path is an S3 path (not supported for file-based databases)
                db_path = self.config.db_path or "jvdb/sqlite/jvspatial.db"
                if db_path.startswith("s3://"):
                    raise ValueError(
                        f"SQLite database does not support S3 paths. "
                        f"Received: {db_path}. "
                        f"Use a local path or DynamoDB (db_type='dynamodb') for cloud storage."
                    )
                prime_db = create_database(
                    db_type="sqlite",
                    db_path=db_path,
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

            # Get or create database manager and set the prime database
            # This ensures the manager uses our configured database, not defaults

            try:
                manager = get_database_manager()
                # Update prime database if manager already exists
                manager._prime_database = prime_db
                manager._databases["prime"] = prime_db
            except (RuntimeError, AttributeError):
                # Manager doesn't exist yet, create it with our prime database
                manager = DatabaseManager(prime_database=prime_db)
                set_database_manager(manager)

            # Create GraphContext using current database (which defaults to prime)
            self._graph_context = GraphContext(database=manager.get_current_database())

            # Set as default context so entities can use it automatically
            from jvspatial.core.context import set_default_context

            set_default_context(self._graph_context)

            self._logger.debug(
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
                storage_root = self.config.file_storage_root or ".files"
                self._file_interface = create_storage(
                    provider="local",
                    root_dir=storage_root,
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

        # Add error logging context middleware for cleanup
        self._configure_error_logging_context_middleware(app)

        # Configure authentication middleware if enabled
        self._configure_auth_middleware(app)

        # Configure exception handlers
        self._configure_exception_handlers(app)

        # Register core routes using AppBuilder
        self.app_builder.register_core_routes(app, self._graph_context, server=self)

        # Discover and register endpoints from pre-loaded modules BEFORE including routers
        # This ensures all @endpoint decorated functions/classes are registered with the
        # endpoint router before it's included in the FastAPI app
        if self.discovery_service.enabled and not self._is_running:
            try:
                discovered_count = self.discovery_service.discover_and_register()
                if discovered_count > 0:
                    self._logger.info(f"🔍 Endpoints: {discovered_count} discovered")
            except Exception as e:
                self._logger.warning(f"⚠️ Endpoint discovery failed: {e}")

        # Include routers (endpoint router now contains all discovered endpoints)
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
        """Configure all exception handlers using the unified APIErrorHandler.

        Args:
            app: FastAPI application instance to configure
        """
        # Add custom exception handlers
        for exc_class, handler in self._exception_handlers.items():
            app.add_exception_handler(exc_class, handler)

        # Explicitly register JVSpatialAPIException handler BEFORE HTTPException
        # This ensures function endpoints that raise ResourceNotFoundError, etc.
        # are handled gracefully without triggering Starlette's error logging
        from jvspatial.exceptions import JVSpatialAPIException

        @app.exception_handler(JVSpatialAPIException)
        async def jvspatial_exception_handler(
            request: Request, exc: JVSpatialAPIException
        ) -> JSONResponse:
            # Known errors (4xx) are handled gracefully - no stack trace needed
            # Only 5xx errors will be logged with stack traces for debugging
            return await APIErrorHandler.handle_exception(request, exc)

        # Explicitly register HTTPException handler to ensure consistent formatting
        # This must be registered before the generic Exception handler
        # FastAPI's default HTTPException handler returns {"detail": "..."} format
        # We override it to use our consistent error structure
        from fastapi import HTTPException

        @app.exception_handler(HTTPException)
        async def http_exception_handler(
            request: Request, exc: HTTPException
        ) -> JSONResponse:
            # Known errors (4xx) are handled gracefully - no stack trace needed
            # Only 5xx errors will be logged with stack traces for debugging
            return await APIErrorHandler.handle_exception(request, exc)

        # Add default exception handler using the unified ErrorHandler
        # This catches unexpected exceptions (not HTTPException, not JVSpatialAPIException)
        # These are treated as 500 errors and logged with full stack traces
        @app.exception_handler(Exception)
        async def global_exception_handler(
            request: Request, exc: Exception
        ) -> JSONResponse:
            # All unexpected exceptions are treated as 500 errors
            # They will be logged with stack traces for debugging
            return await APIErrorHandler.handle_exception(request, exc)

        # Configure Starlette's error logger to suppress stack traces for known errors
        # Starlette logs exceptions before they reach our handlers, so we need to
        # configure the logger to not print stack traces for HTTPException and JVSpatialAPIException
        import logging

        from fastapi import HTTPException

        from jvspatial.exceptions import JVSpatialAPIException

        starlette_error_logger = logging.getLogger("starlette.error")
        uvicorn_error_logger = logging.getLogger("uvicorn.error")
        uvicorn_access_logger = logging.getLogger("uvicorn.access")

        # Set log level to CRITICAL to prevent these loggers from emitting ERROR logs
        # This adds defense in depth alongside the filter
        starlette_error_logger.setLevel(logging.CRITICAL)
        uvicorn_error_logger.setLevel(logging.CRITICAL)

        def _is_client_error(exc_type, exc_value) -> bool:
            """Check if exception is a known client error (4xx)."""
            # Check for FastAPI HTTPException
            if exc_type is HTTPException:
                return exc_value.status_code < 500

            # Check for JVSpatialAPIException
            if exc_type is JVSpatialAPIException or isinstance(
                exc_value, JVSpatialAPIException
            ):
                return hasattr(exc_value, "status_code") and exc_value.status_code < 500

            # Check for httpx.HTTPStatusError (external API errors)
            try:
                import httpx

                if isinstance(exc_value, httpx.HTTPStatusError):
                    return exc_value.response.status_code < 500
            except ImportError:
                pass  # httpx not installed

            return False

        # Create a filter that suppresses framework-level error logs
        # Our APIErrorHandler is the authoritative source for error logging
        class CentralizedErrorFilter(logging.Filter):
            """Filter that suppresses framework-level error logs.

            Our APIErrorHandler is the authoritative source for error logging.
            This filter suppresses uvicorn/starlette error logs to prevent duplicates,
            ensuring each exception is logged exactly once with proper context.
            """

            def filter(self, record: logging.LogRecord) -> bool:
                """Filter out framework-level exception log records."""
                # Only filter exception logs from uvicorn/starlette
                logger_name = record.name

                # NEVER filter our own error handler logs - it's the authoritative source
                if logger_name == "jvspatial.api.components.error_handler":
                    return True  # Always allow our error handler logs

                # Check for exact logger name match
                # Suppress ALL ERROR/CRITICAL level logs from uvicorn/starlette
                # Our custom exception handlers log all exceptions with proper context
                # This prevents duplicate logging - we suppress unconditionally since uvicorn
                # logs BEFORE our handler runs, so timing-based checks won't work
                if (
                    logger_name == "uvicorn.error" or logger_name == "starlette.error"
                ) and record.levelno >= logging.ERROR:
                    # Suppress ALL ERROR/CRITICAL logs from these loggers
                    # Our handler will log all exceptions properly
                    return False

                # Also check root logger handlers for propagated uvicorn/starlette errors
                # Sometimes errors propagate to root logger, but only suppress if NOT from our handler
                if (
                    record.levelno >= logging.ERROR
                    and logger_name != "jvspatial.api.components.error_handler"
                ):
                    try:
                        message = str(record.getMessage())
                        # Check if this looks like a uvicorn/starlette error message
                        # But be careful - our error handler also includes tracebacks
                        # Only suppress if it's clearly a uvicorn/starlette message
                        if any(
                            pattern in message
                            for pattern in [
                                "Exception in ASGI application",
                                "During handling of the above exception",
                            ]
                        ):
                            # This is likely a propagated uvicorn/starlette error
                            # Suppress it since our handler will log it
                            return False
                    except Exception:
                        pass

                # Allow all other logs
                return True

        # Create a filter that suppresses uvicorn access logs for error responses
        # that were already logged by our error handler
        class ErrorAwareAccessFilter(logging.Filter):
            """Filter that suppresses access logs for error responses already logged by error handler.

            This filter intelligently correlates access logs with error logs to prevent
            duplicate reporting. If an error response (4xx/5xx) was already logged by
            the internal error handler, the corresponding access log is suppressed.
            Successful responses (2xx/3xx) are always logged.
            """

            def filter(self, record: logging.LogRecord) -> bool:
                """Filter out access logs for error responses that were already logged."""
                # Only filter uvicorn.access logs
                if record.name != "uvicorn.access":
                    return True  # Allow all non-access logs

                # Parse status code and request details from access log message
                # Format: "127.0.0.1:57637 - "POST /auth/login HTTP/1.1" 401"
                try:
                    message = record.getMessage()

                    # Extract status code from end of message (last 3-digit number)
                    status_match = re.search(r"\s(\d{3})\s*$", message)
                    if not status_match:
                        # Can't parse status code, allow the log (fail open)
                        return True

                    status_code = int(status_match.group(1))

                    # Only suppress error responses (4xx, 5xx)
                    # Successful responses (2xx, 3xx) should always be logged
                    if status_code < 400:
                        return True  # Always log successful responses

                    # Check if this error response was already logged by error handler
                    from jvspatial.api.components.error_handler import (
                        _logged_error_responses,
                    )

                    try:
                        logged_responses = _logged_error_responses.get()
                        # Check if any error response with matching status code was logged
                        # Since access logs come after error logs in the request lifecycle,
                        # any error logged by our handler should be in the context
                        # We check for matching status code - if multiple errors with same
                        # status occur, we suppress all (conservative approach)
                        if any(status == status_code for _, status in logged_responses):
                            # An error with this status code was logged by our handler
                            # Suppress the access log to avoid duplication
                            return False
                    except LookupError:
                        # No logged errors in context, allow the log
                        # This can happen if error handler didn't run or context wasn't initialized
                        pass

                    # If we can't determine correlation, allow the log (fail open)
                    return True

                except Exception:
                    # If parsing fails, allow the log (fail open for safety)
                    # Better to have duplicate logs than missing logs
                    return True

        # Create a custom formatter that suppresses tracebacks for known errors
        class KnownErrorFormatter(logging.Formatter):
            """Formatter that suppresses stack traces for known errors."""

            def formatException(self, ei):  # noqa: N802
                """Override to return empty string for known errors."""
                if ei:
                    exc_type, exc_value, _ = ei
                    # Suppress stack traces for client errors (4xx) - they're not real exceptions
                    if _is_client_error(exc_type, exc_value):
                        return ""  # No stack trace for client errors
                return super().formatException(ei) if ei else ""

        # Apply filter and formatter to Starlette's error logger
        # Apply filter at logger level FIRST to catch all logs before handlers process them
        centralized_error_filter = CentralizedErrorFilter()
        error_aware_access_filter = ErrorAwareAccessFilter()
        known_error_formatter = KnownErrorFormatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )

        # Add filter to logger itself FIRST (applies to all handlers, including future ones)
        # This ensures the filter runs before any handlers process the log records
        starlette_error_logger.addFilter(centralized_error_filter)
        uvicorn_error_logger.addFilter(centralized_error_filter)
        uvicorn_access_logger.addFilter(error_aware_access_filter)

        # Apply filter and formatter to existing handlers
        from logging import Handler

        # Get a fresh copy of handlers list to avoid modification during iteration
        starlette_handlers = list(starlette_error_logger.handlers)
        uvicorn_handlers = list(uvicorn_error_logger.handlers)
        uvicorn_access_handlers = list(uvicorn_access_logger.handlers)

        for log_handler in starlette_handlers:
            # Remove any existing CentralizedErrorFilter to avoid duplicates
            log_handler.filters = [
                f
                for f in log_handler.filters
                if not isinstance(f, CentralizedErrorFilter)
            ]
            log_handler.addFilter(centralized_error_filter)
            log_handler.setFormatter(known_error_formatter)

        # Also configure uvicorn's error logger
        for uvicorn_log_handler in uvicorn_handlers:
            # Remove any existing CentralizedErrorFilter to avoid duplicates
            uvicorn_log_handler.filters = [
                f
                for f in uvicorn_log_handler.filters
                if not isinstance(f, CentralizedErrorFilter)
            ]
            uvicorn_log_handler.addFilter(centralized_error_filter)
            uvicorn_log_handler.setFormatter(known_error_formatter)

        # Configure uvicorn's access logger with error-aware filter
        for uvicorn_access_handler in uvicorn_access_handlers:
            # Remove any existing ErrorAwareAccessFilter to avoid duplicates
            uvicorn_access_handler.filters = [
                f
                for f in uvicorn_access_handler.filters
                if not isinstance(f, ErrorAwareAccessFilter)
            ]
            uvicorn_access_handler.addFilter(error_aware_access_filter)

        # Also add filter to root logger handlers to catch any propagated logs
        root_logger = logging.getLogger()
        for root_handler in root_logger.handlers:
            # Only add filter if it's not already there
            if not any(
                isinstance(f, CentralizedErrorFilter) for f in root_handler.filters
            ):
                root_handler.addFilter(centralized_error_filter)
            # Also add access filter if not present
            if not any(
                isinstance(f, ErrorAwareAccessFilter) for f in root_handler.filters
            ):
                root_handler.addFilter(error_aware_access_filter)

        # Also configure the logger to use this formatter for any new handlers
        if not starlette_error_logger.handlers:
            new_handler: Handler = logging.StreamHandler()
            new_handler.addFilter(centralized_error_filter)
            new_handler.setFormatter(known_error_formatter)
            starlette_error_logger.addHandler(new_handler)

    def _configure_error_logging_context_middleware(
        self: "Server", app: FastAPI
    ) -> None:
        """Configure middleware to clean up error logging context after each request.

        This middleware ensures that context variables used for tracking logged
        error responses are properly cleaned up after each request to prevent
        memory leaks and context pollution between requests.

        Args:
            app: FastAPI application instance
        """
        from starlette.middleware.base import BaseHTTPMiddleware

        class ErrorLoggingContextMiddleware(BaseHTTPMiddleware):
            """Middleware to manage error logging context lifecycle."""

            async def dispatch(self, request: Request, call_next):
                """Process request and clean up context after response."""
                from jvspatial.api.components.error_handler import (
                    _logged_error_responses,
                )

                # Initialize context for this request
                with contextlib.suppress(Exception):
                    # If context initialization fails, continue without it
                    _logged_error_responses.set(set())

                try:
                    # Process request
                    response = await call_next(request)
                    return response
                finally:
                    # Clean up context after request completes
                    with contextlib.suppress(Exception):
                        # If cleanup fails, continue - context will be reset on next request
                        # Clear the context variable for this request
                        # This prevents memory leaks and ensures clean state
                        _logged_error_responses.set(set())

        # Add middleware early in the stack to ensure context is available
        # for the entire request lifecycle
        app.add_middleware(ErrorLoggingContextMiddleware)

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
            # Authentication middleware logging handled by middleware manager
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
                # Test database connectivity - Root.get() always returns singleton
                root = await Root.get()
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
            info = {
                "service": self.config.title,
                "description": self.config.description,
                "version": self.config.version,
                "docs": self.config.docs_url,
                "health": "/health",
            }
            if self.config.graph_endpoint_enabled:
                info["graph"] = "/api/graph"
            return info

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
            walker_class._jvspatial_endpoint_config = {  # type: ignore[attr-defined]
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

    def disable_auth_endpoint(self: "Server", path: str) -> bool:
        """Disable a specific authentication endpoint by removing it from the auth router.

        This method removes routes from the auth router before the app is created.
        It only works with auth endpoints registered through the auth router.

        Args:
            path: The path of the auth endpoint to disable (e.g., "/register", "/login")
                  Can be relative to router prefix or full path including prefix.

        Returns:
            True if the endpoint was found and disabled, False otherwise
        """
        if not hasattr(self, "_auth_router") or self._auth_router is None:
            self._logger.debug("Auth router not found - cannot disable endpoint")
            return False

        # Normalize path (ensure it starts with "/")
        normalized_path = path if path.startswith("/") else f"/{path}"

        # Get router prefix (default is "/auth")
        router_prefix = getattr(self._auth_router, "prefix", "/auth")
        if not router_prefix:
            router_prefix = ""

        # Build full path with prefix for matching
        # FastAPI routes store the full path including the router prefix
        full_path_with_prefix = f"{router_prefix}{normalized_path}"

        # Find and remove routes matching the path
        routes_to_remove = []
        for route in self._auth_router.routes:
            # FastAPI routes include the router prefix in the path
            # So "/auth/register" is stored as "/auth/register", not "/register"
            if hasattr(route, "path") and route.path == full_path_with_prefix:
                routes_to_remove.append(route)
                self._logger.debug(f"Found route to remove: {route.path}")

        if routes_to_remove:
            for route in routes_to_remove:
                self._auth_router.routes.remove(route)
            self._logger.debug(f"🔒 Disabled auth endpoint: {full_path_with_prefix}")

            # If the app has already been created, mark it for rebuilding
            # so the changes take effect
            if hasattr(self, "app") and self.app is not None:
                self._app_needs_rebuild = True
                self._logger.debug("App already exists - marked for rebuild")

            return True
        else:
            # Log available routes for debugging
            available_paths = [
                route.path
                for route in self._auth_router.routes
                if hasattr(route, "path")
            ]
            self._logger.debug(
                f"Could not find endpoint {full_path_with_prefix} to disable. "
                f"Available routes: {available_paths}"
            )
            return False

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
        # Set up standard logging (colorized level names, consistent format)
        # Preserve DBLogHandler to ensure database logging continues to work
        configure_standard_logging(
            level=self.config.log_level,
            enable_colors=True,
            preserve_handler_class_names=["DBLogHandler", "StartupLogCounter"],
        )

        # Use provided values or fall back to config
        run_host = host or self.config.host
        run_port = port or self.config.port
        run_reload = reload if reload is not None else self.config.debug

        # Log concise server startup info
        server_info = f"http://{run_host}:{run_port}"
        if self.config.docs_url:
            server_info += f" | docs: {self.config.docs_url}"
        self._logger.info(f"🔧 Server: {server_info}")

        # Get the app
        app = self.get_app()

        # Configure uvicorn parameters with aligned logging format
        formatter = _LevelColorFormatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )

        uvicorn_config = {
            "host": run_host,
            "port": run_port,
            "reload": run_reload,
            "log_level": self.config.log_level,
            "log_config": {
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {
                        "()": _LevelColorFormatter,
                        "fmt": formatter._fmt,
                        "datefmt": formatter.datefmt,
                    }
                },
                "handlers": {
                    "default": {
                        "class": "logging.StreamHandler",
                        "formatter": "default",
                        "stream": "ext://sys.stdout",
                    }
                },
                "loggers": {
                    "uvicorn": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                    "uvicorn.error": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                    "uvicorn.access": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                },
            },
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

        formatter = _LevelColorFormatter(
            fmt="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )

        config = uvicorn.Config(
            app,
            host=run_host,
            port=run_port,
            log_level=self.config.log_level,
            log_config={
                "version": 1,
                "disable_existing_loggers": False,
                "formatters": {
                    "default": {
                        "()": _LevelColorFormatter,
                        "fmt": formatter._fmt,
                        "datefmt": formatter.datefmt,
                    }
                },
                "handlers": {
                    "default": {
                        "class": "logging.StreamHandler",
                        "formatter": "default",
                        "stream": "ext://sys.stdout",
                    }
                },
                "loggers": {
                    "uvicorn": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                    "uvicorn.error": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                    "uvicorn.access": {
                        "handlers": ["default"],
                        "level": self.config.log_level.upper(),
                        "propagate": False,
                    },
                },
            },
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
