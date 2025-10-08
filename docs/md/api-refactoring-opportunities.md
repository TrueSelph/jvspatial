
# jvspatial API Module - Refactoring Opportunities

**Date**: 2025-10-08
**Base Analysis**: [API Architecture Analysis](api-architecture-analysis.md)
**Primary File**: [`jvspatial/api/server.py`](../../jvspatial/api/server.py) (1857 lines)

---

## Executive Summary

This document provides **concrete, actionable refactoring opportunities** for the jvspatial API module, with specific code examples, priority levels, and effort estimates. Each refactoring includes:
- Exact file and line references
- Current code smell/anti-pattern
- Before/after code examples
- Measurable benefits
- Implementation effort

**Total Identified Issues**: 15 major refactoring opportunities
**Estimated Total Effort**: ~96 hours (12 developer days)

---

## 🔥 Critical Refactorings (Must Do)

### 1. Extract File Storage Service Class

**Priority**: 🔥 Critical
**Effort**: 8 hours
**Location**: [`server.py:650-808`](../../jvspatial/api/server.py:650)

#### Problem
159 lines of inline file storage endpoint definitions violate Single Responsibility Principle and make the Server class bloated.

#### Current Code
```python
# server.py:650-808
def _add_file_storage_endpoints(self: "Server", app: FastAPI) -> None:
    """Add file storage and proxy endpoints to the app."""

    # File upload endpoint
    @app.post("/api/storage/upload")
    async def upload_file(
        file: UploadFile,
        path: str = "",
        create_proxy: bool = False,
        proxy_expires_in: int = 3600,
        proxy_one_time: bool = False,
    ):
        # ... 40 lines of logic

    @app.get("/api/storage/files/{file_path:path}")
    async def serve_file(file_path: str):
        # ... inline logic

    @app.delete("/api/storage/files/{file_path:path}")
    async def delete_file(file_path: str):
        # ... inline logic

    # ... 6 more inline endpoints (159 total lines)
```

#### Proposed Refactoring

**Step 1**: Create service class
```python
# jvspatial/api/services/file_storage_service.py
from typing import Optional, Dict, Any
from fastapi import FastAPI, UploadFile, HTTPException

class FileStorageService:
    """Manages file storage endpoints and operations."""

    def __init__(
        self,
        file_interface: Any,
        proxy_manager: Optional[Any] = None,
        logger: Optional[Any] = None
    ):
        self.file_interface = file_interface
        self.proxy_manager = proxy_manager
        self._logger = logger or logging.getLogger(__name__)

    def register_endpoints(self, app: FastAPI, prefix: str = "/api/storage") -> None:
        """Register all file storage endpoints on the app."""
        app.add_api_route(
            f"{prefix}/upload",
            self.upload_file,
            methods=["POST"]
        )
        app.add_api_route(
            f"{prefix}/files/{{file_path:path}}",
            self.serve_file,
            methods=["GET"]
        )
        app.add_api_route(
            f"{prefix}/files/{{file_path:path}}",
            self.delete_file,
            methods=["DELETE"]
        )

        if self.proxy_manager:
            self._register_proxy_endpoints(app, prefix)

    async def upload_file(
        self,
        file: UploadFile,
        path: str = "",
        create_proxy: bool = False,
        proxy_expires_in: int = 3600,
        proxy_one_time: bool = False,
    ) -> Dict[str, Any]:
        """Handle file upload with optional proxy creation."""
        try:
            content = await file.read()
            file_path = f"{path}/{file.filename}" if path else file.filename

            await self.file_interface.save_file(file_path, content)

            result = {
                "success": True,
                "file_path": file_path,
                "file_size": len(content),
                "file_url": await self.file_interface.get_file_url(file_path),
            }

            if create_proxy and self.proxy_manager:
                proxy_url = await self.proxy_manager.create_proxy(
                    file_path=file_path,
                    expires_in=proxy_expires_in,
                    one_time=proxy_one_time,
                )
                result["proxy_url"] = proxy_url
                result["proxy_code"] = proxy_url.split("/")[-1]

            return result

        except (PathTraversalError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except StorageError as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def serve_file(self, file_path: str):
        """Serve a file directly."""
        try:
            return await self.file_interface.serve_file(file_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="File not found")
        except StorageError as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def delete_file(self, file_path: str) -> Dict[str, Any]:
        """Delete a file."""
        try:
            success = await self.file_interface.delete_file(file_path)
            return {"success": success, "file_path": file_path}
        except StorageError as e:
            raise HTTPException(status_code=500, detail=str(e))

    def _register_proxy_endpoints(self, app: FastAPI, prefix: str) -> None:
        """Register proxy-related endpoints."""
        # Similar extraction for proxy endpoints
        pass
```

**Step 2**: Update Server class
```python
# server.py (updated)
def _initialize_file_storage(self: "Server") -> None:
    """Initialize file storage interface and service."""
    from jvspatial.storage import get_file_interface, get_proxy_manager
    from jvspatial.api.services.file_storage_service import FileStorageService

    # ... existing initialization logic ...

    # Create service instead of keeping references
    proxy_manager = get_proxy_manager() if self.config.proxy_enabled else None
    self._file_storage_service = FileStorageService(
        file_interface=self._file_interface,
        proxy_manager=proxy_manager,
        logger=self._logger
    )

    self._logger.info(f"📁 File storage service initialized")

def _create_app_instance(self: "Server") -> FastAPI:
    # ... other setup ...

    # Replace inline endpoints with service registration
    if self.config.file_storage_enabled and self._file_storage_service:
        self._file_storage_service.register_endpoints(app)
        self._logger.info("📁 File storage endpoints registered")

    # ... rest of method ...
```

#### Benefits
- ✅ Reduces Server class by 159 lines (8.5%)
- ✅ Single Responsibility: Service only handles file operations
- ✅ Testable: Can mock file_interface and test in isolation
- ✅ Reusable: Service can be used outside Server context
- ✅ Clear dependency injection

---

### 2. Extract Endpoint Registration Service

**Priority**: 🔥 Critical
**Effort**: 12 hours
**Location**: [`server.py:810-1311`](../../jvspatial/api/server.py:810)

#### Problem
500+ lines of complex endpoint registration logic with duplicate patterns for walkers, functions, and dynamic registration.

#### Current Code (Duplicate Patterns)
```python
# server.py:810-852 - Dynamic walker registration
def _register_walker_dynamically(
    self, walker_class, path, methods, **kwargs
):
    dynamic_router = EndpointRouter()
    dynamic_router.endpoint(path, methods, **kwargs)(walker_class)
    self._dynamic_routers.append(dynamic_router)
    # ... tracking logic ...
    self.app.include_router(dynamic_router.router, prefix="/api")

# server.py:1091-1131 - Programmatic walker registration
def register_walker_class(
    self, walker_class, path, methods, **kwargs
):
    self._registered_walker_classes.add(walker_class)
    self._walker_endpoint_mapping[walker_class] = {
        "path": path, "methods": methods, "kwargs": kwargs
    }
    # ... similar logic ...

# server.py:333-380 - Decorator-based walker registration
def walker(self, path, methods, **kwargs):
    def decorator(walker_class):
        self._registered_walker_classes.add(walker_class)
        # ... duplicate tracking logic ...
```

#### Proposed Refactoring

```python
# jvspatial/api/services/endpoint_registry.py
from typing import Type, Optional, List, Dict, Any, Callable, Set
from dataclasses import dataclass
from jvspatial.core.entities import Walker
from jvspatial.api.endpoint.router import EndpointRouter

@dataclass
class EndpointInfo:
    """Value object for endpoint configuration."""
    path: str
    methods: List[str]
    kwargs: Dict[str, Any]
    router: Optional[EndpointRouter] = None
    is_dynamic: bool = False

class EndpointRegistry:
    """Centralized registry for all API endpoints."""

    def __init__(self, logger=None):
        self._walker_endpoints: Dict[Type[Walker], EndpointInfo] = {}
        self._function_endpoints: Dict[Callable, EndpointInfo] = {}
        self._registered_walkers: Set[Type[Walker]] = set()
        self._dynamic_routers: List[EndpointRouter] = []
        self._logger = logger or logging.getLogger(__name__)

    def register_walker(
        self,
        walker_class: Type[Walker],
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs
    ) -> EndpointInfo:
        """Register a walker endpoint (single source of truth)."""
        if walker_class in self._registered_walkers:
            self._logger.warning(f"Walker {walker_class.__name__} already registered")
            return self._walker_endpoints[walker_class]

        endpoint_info = EndpointInfo(
            path=path,
            methods=methods or ["POST"],
            kwargs=kwargs,
            is_dynamic=False
        )

        self._registered_walkers.add(walker_class)
        self._walker_endpoints[walker_class] = endpoint_info

        self._logger.info(f"📝 Registered walker: {walker_class.__name__} at {path}")
        return endpoint_info

    def register_walker_dynamic(
        self,
        walker_class: Type[Walker],
        path: str,
        methods: Optional[List[str]] = None,
        **kwargs
    ) -> EndpointRouter:
        """Register a walker dynamically (for running server)."""
        router = EndpointRouter()
        router.endpoint(path, methods or ["POST"], **kwargs)(walker_class)

        endpoint_info = self.register_walker(walker_class, path, methods, **kwargs)
        endpoint_info.router = router
        endpoint_info.is_dynamic = True

        self._dynamic_routers.append(router)
        self._logger.info(f"🔄 Dynamically registered: {walker_class.__name__}")

        return router

    def unregister_walker(self, walker_class: Type[Walker]) -> bool:
        """Unregister a walker endpoint."""
        if walker_class not in self._registered_walkers:
            return False

        endpoint_info = self._walker_endpoints.get(walker_class)
        if endpoint_info and endpoint_info.router in self._dynamic_routers:
            self._dynamic_routers.remove(endpoint_info.router)

        self._registered_walkers.discard(walker_class)
        del self._walker_endpoints[walker_class]

        self._logger.info(f"🗑️ Unregistered walker: {walker_class.__name__}")
        return True

    def get_walker_info(self, walker_class: Type[Walker]) -> Optional[EndpointInfo]:
        """Get endpoint info for a walker."""
        return self._walker_endpoints.get(walker_class)

    def list_walkers(self) -> Dict[str, Dict[str, Any]]:
        """List all registered walker endpoints."""
        return {
            cls.__name__: {
                "path": info.path,
                "methods": info.methods,
                "class_name": cls.__name__,
                "module": cls.__module__,
                "is_dynamic": info.is_dynamic,
            }
            for cls, info in self._walker_endpoints.items()
        }

    def get_dynamic_routers(self) -> List[EndpointRouter]:
        """Get all dynamic routers for app inclusion."""
        return self._dynamic_routers.copy()
```

**Update Server class**:
```python
# server.py (simplified)
class Server:
    def __init__(self, config, **kwargs):
        # ... existing init ...
        self.endpoint_registry = EndpointRegistry(logger=self._logger)
        self.endpoint_router = EndpointRouter()

    def walker(self, path, methods=None, **kwargs):
        """Register walker - now delegates to registry."""
        def decorator(walker_class):
            endpoint_info = self.endpoint_registry.register_walker(
                walker_class, path, methods, **kwargs
            )

            if self._is_running and self.app:
                # Register dynamically
                router = self.endpoint_registry.register_walker_dynamic(
                    walker_class, path, methods, **kwargs
                )
                self.app.include_router(router.router, prefix="/api")
            else:
                # Register with main router
                self.endpoint_router.endpoint(path, methods, **kwargs)(walker_class)

            return walker_class
        return decorator

    def register_walker_class(self, walker_class, path, methods=None, **kwargs):
        """Simplified - delegates to registry."""
        endpoint_info = self.endpoint_registry.register_walker(
            walker_class, path, methods, **kwargs
        )

        if self._is_running and self.app:
            router = self.endpoint_registry.register_walker_dynamic(
                walker_class, path, methods, **kwargs
            )
            self.app.include_router(router.router, prefix="/api")
        else:
            self.endpoint_router.endpoint(path, methods, **kwargs)(walker_class)

    def list_walker_endpoints_safe(self):
        """Delegates to registry."""
        return self.endpoint_registry.list_walkers()
```

#### Benefits
- ✅ Eliminates 400+ lines of duplicate registration logic
- ✅ Single source of truth for endpoint management
- ✅ Easier to test registration logic in isolation
- ✅ Clear value object (EndpointInfo) instead of dictionaries
- ✅ Type-safe operations

---

### 3. Eliminate Global Server Registry

**Priority**: 🔥 Critical
**Effort**: 6 hours
**Location**: [`server.py:46-48, 1668-1700`](../../jvspatial/api/server.py:46)

#### Problem
Global mutable state creates hidden dependencies, test isolation issues, and violates dependency inversion.

#### Current Code
```python
# server.py:46-48
_global_servers: Dict[str, "Server"] = {}
_default_server: Optional["Server"] = None
_server_lock = threading.Lock()

# server.py:194-256 - Server __init__ modifies global state
def __init__(self, config, **kwargs):
    # ... initialization ...

    # Register this server globally
    with _server_lock:
        global _default_server
        server_id = id(self)
        _global_servers[str(server_id)] = self
        if _default_server is None:
            _default_server = self

# server.py:1703-1747 - Decorators depend on global state
def walker_endpoint(path, methods=None, **kwargs):
    def decorator(walker_class):
        # Try to register with default server if available
        default_server = get_default_server()  # ❌ Hidden dependency
        if default_server is not None:
            default_server.register_walker_class(walker_class, path, methods, **kwargs)
        return walker_class
    return decorator
```

#### Proposed Refactoring

**Step 1**: Use dependency injection with context variable
```python
# jvspatial/api/context.py
from contextvars import ContextVar
from typing import Optional
from jvspatial.api.server import Server

# Use context variable instead of global
_current_server: ContextVar[Optional[Server]] = ContextVar('current_server', default=None)

class ServerContext:
    """Context manager for server scope."""

    def __init__(self, server: Server):
        self.server = server
        self.token = None

    def __enter__(self):
        self.token = _current_server.set(self.server)
        return self.server

    def __exit__(self, *args):
        if self.token:
            _current_server.reset(self.token)

def get_current_server() -> Optional[Server]:
    """Get server from current context."""
    return _current_server.get()

def set_current_server(server: Server) -> None:
    """Set server in current context."""
    _current_server.set(server)
```

**Step 2**: Update decorators to require explicit server
```python
# jvspatial/api/decorators.py
from typing import Optional, Type, Callable, List, Any
from jvspatial.core.entities import Walker
from jvspatial.api.context import get_current_server

def walker_endpoint(
    path: str,
    methods: Optional[List[str]] = None,
    server: Optional["Server"] = None,  # ✅ Explicit dependency
    **kwargs
) -> Callable[[Type[Walker]], Type[Walker]]:
    """Register a walker endpoint.

    Args:
        path: URL path
        methods: HTTP methods
        server: Server instance (if None, uses current context)
        **kwargs: Additional route parameters
    """
    def decorator(walker_class: Type[Walker]) -> Type[Walker]:
        # Store config for discovery
        walker_class._jvspatial_endpoint_config = {
            "path": path,
            "methods": methods or ["POST"],
            "kwargs": kwargs,
        }

        # Use explicit server or get from context
        target_server = server or get_current_server()

        if target_server:
            target_server.register_walker_class(walker_class, path, methods, **kwargs)
        else:
            # No server available - config stored for later discovery
            pass

        return walker_class

    return decorator
```

**Step 3**: Update Server initialization
```python
# server.py (updated)
class Server:
    def __init__(self, config, **kwargs):
        # ... existing initialization ...

        # NO global registration - use context instead
        # Remove: _global_servers[str(id(self))] = self
        # Remove: _default_server = self

        # Optionally set as current context server
        from jvspatial.api.context import set_current_server
        set_current_server(self)
```

**Step 4**: Update usage patterns
```python
# Before (hidden dependency):
from jvspatial.api.server import walker_endpoint

@walker_endpoint("/users")  # ❌ Depends on global state
class ListUsers(Walker):
    pass

# After (explicit dependency):
from jvspatial.api.server import Server
from jvspatial.api.decorators import walker_endpoint
from jvspatial.api.context import ServerContext

server = Server(title="My API")

# Option 1: Explicit server parameter
@walker_endpoint("/users", server=server)
class ListUsers(Walker):
    pass

# Option 2: Context manager
with ServerContext(server):
    @walker_endpoint("/users")  # Uses context
    class ListUsers(Walker):
        pass

# Option 3: Server's own decorators (existing pattern)
@server.walker("/users")
class ListUsers(Walker):
    pass
```

#### Benefits
- ✅ No global mutable state
- ✅ Explicit dependencies (testable)
- ✅ Thread-safe by default (ContextVar)
- ✅ Clear scope management
- ✅ Easy to test with multiple servers
- ✅ No hidden side effects

---

### 4. Split `_create_app_instance` Method

**Priority**: 🔥 Critical
**Effort**: 10 hours
**Location**: [`server.py:511-648`](../../jvspatial/api/server.py:511)

#### Problem
138-line method doing too many things: app creation, middleware setup, CORS, exception handlers, routes, health checks.

#### Current Code Structure
```python
# server.py:511-648 - All in one method
def _create_app_instance(self: "Server") -> FastAPI:
    # 1. Create FastAPI app (20 lines)
    # 2. Add CORS middleware (8 lines)
    # 3. Add webhook middleware (1 line)
    # 4. Add file storage endpoints (1 line)
    # 5. Add custom middleware (5 lines)
    # 6. Add exception handlers (14 lines)
    # 7. Add default exception handler (12 lines)
    # 8. Add custom routes (12 lines)
    # 9. Add health check endpoint (30 lines)
    # 10. Add root endpoint (10 lines)
    # 11. Include routers (7 lines)
    # Total: 138 lines
```

#### Proposed Refactoring

**Extract into focused methods**:
```python
# server.py (refactored)
class Server:
    def _create_app_instance(self: "Server") -> FastAPI:
        """Create FastAPI app - orchestrates setup."""
        app = self._create_base_app()

        self._configure_middleware(app)
        self._configure_exception_handlers(app)
        self._register_core_routes(app)
        self._register_custom_routes(app)
        self._include_routers(app)

        return app

    def _create_base_app(self) -> FastAPI:
        """Create base FastAPI instance with lifespan."""
        if self._is_running:
            # Skip lifespan for rebuilt apps
            return FastAPI(
                title=self.config.title,
                description=self.config.description,
                version=self.config.version,
                docs_url=self.config.docs_url,
                redoc_url=self.config.redoc_url,
                debug=self.config.debug,
            )
        else:
            return FastAPI(
                title=self.config.title,
                description=self.config.description,
                version=self.config.version,
                docs_url=self.config.docs_url,
                redoc_url=self.config.redoc_url,
                debug=self.config.debug,
                lifespan=self._lifespan,
            )

    def _configure_middleware(self, app: FastAPI) -> None:
        """Configure all middleware in correct order."""
        # CORS first
        if self.config.cors_enabled:
            app.add_middleware(
                CORSMiddleware,
                allow_origins=self.config.cors_origins,
                allow_methods=self.config.cors_methods,
                allow_headers=self.config.cors_headers,
                allow_credentials=True,
            )

        # Webhook middleware
        self._add_webhook_middleware(app)

        # Custom middleware
        for middleware_config in self._middleware:
            app.middleware(middleware_config["middleware_type"])(
                middleware_config["func"]
            )

        self._logger.info("🔧 Middleware configured")

    def _configure_exception_handlers(self, app: FastAPI) -> None:
        """Configure exception handlers."""
        # Custom handlers
        for exc_class, handler in self._exception_handlers.items():
            app.add_exception_handler(exc_class, handler)

        # Default global handler
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

        self._logger.info("⚠️ Exception handlers configured")

    def _register_core_routes(self, app: FastAPI) -> None:
        """Register core system routes (health, root)."""

        @app.get("/health", response_model=None)
        async def health_check() -> Union[Dict[str, Any], JSONResponse]:
            """Health check endpoint."""
            return await self._handle_health_check()

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

        # File storage endpoints
        if self.config.file_storage_enabled and self._file_storage_service:
            self._file_storage_service.register_endpoints(app)

        self._logger.info("🏥 Core routes registered")

    async def _handle_health_check(self) -> Union[Dict[str, Any], JSONResponse]:
        """Handle health check logic."""
        try:
            if self._graph_context:
                root = await self._graph_context.get_node(Root, "root")
                if not root:
                    root = await self._graph_context.create_node(Root)
            else:
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

    def _register_custom_routes(self, app: FastAPI) -> None:
        """Register user-defined custom routes."""
        for route_config in self._custom_routes:
            endpoint_func = route_config.get("endpoint")

            # Wrap webhook endpoints
            if endpoint_func and getattr(endpoint_func, "_webhook_required", False):
                from jvspatial.api.webhook.endpoint import create_webhook_wrapper
                wrapped_endpoint = create_webhook_wrapper(endpoint_func)
                route_config = route_config.copy()
                route_config["endpoint"] = wrapped_endpoint

            app.add_api_route(**route_config)

        if self._custom_routes:
            self._logger.info(f"📍 Registered {len(self._custom_routes)} custom routes")

    def _include_routers(self, app: FastAPI) -> None:
        """Include all API routers."""
        # Setup webhook walkers
        self._setup_webhook_walker_endpoints()

        # Main endpoint router
        app.include_router(self.endpoint_router.router, prefix="/api")

        # Dynamic routers
        for dynamic_router in self._dynamic_routers:
            app.include_router(dynamic_router.router, prefix="/api")

        router_count = 1 + len(self._dynamic_routers)
        self._logger.info(f"🔌 Included {router_count} routers")
```

#### Benefits
- ✅ Each method has single responsibility
- ✅ Clear setup sequence and dependencies
- ✅ Easier to test individual components
- ✅ Can override specific setup steps
- ✅ Reduced cognitive load (10-30 lines per method)
- ✅ Better logging visibility

---

### 5. Extract Package Discovery Service

**Priority**: 🔥 Critical
**Effort**: 8 hours
**Location**: [`server.py:854-1089`](../../jvspatial/api/server.py:854)

#### Problem
235+ lines of complex package discovery logic mixed with endpoint registration.

#### Current Code
```python
# server.py:854-903 - Discovery loop
def discover_and_register_packages(self, package_patterns=None):
    # Complex iteration logic
    for _finder, module_name, ispkg in pkgutil.iter_modules():
        # Pattern matching
        # Module importing
        # Error handling
        # Registration

# server.py:984-1089 - Discovery in module
def _discover_walkers_in_module(self, module):
    # 100+ lines of walker discovery
    # Function endpoint discovery
    # Wrapper creation
    # Registration logic
```

#### Proposed Refactoring

```python
# jvspatial/api/services/package_discovery.py
from typing import List, Set, Type, Callable, Any, Dict
import importlib
import inspect
import pkgutil
import fnmatch
import logging
from jvspatial.core.entities import Walker

class PackageDiscoveryService:
    """Discovers and catalogs endpoints from installed packages."""

    def __init__(
        self,
        patterns: List[str] = None,
        logger: logging
.Logger = None,
    ):
        self.patterns = patterns or ["*_walkers", "*_endpoints", "*_api"]
        self._logger = logger or logging.getLogger(__name__)
        self._discovered_walkers: Set[Type[Walker]] = set()
        self._discovered_functions: Set[Callable] = set()

    def discover_packages(self) -> Dict[str, List[Any]]:
        """Discover packages matching patterns.

        Returns:
            Dict with 'walkers' and 'functions' lists
        """
        discovered = {"walkers": [], "functions": []}

        self._logger.info(f"🔍 Discovering packages: {self.patterns}")

        for _finder, module_name, ispkg in pkgutil.iter_modules():
            if not ispkg or not self._matches_any_pattern(module_name):
                continue

            try:
                module = importlib.import_module(module_name)
                walkers, functions = self._discover_in_module(module)

                discovered["walkers"].extend(walkers)
                discovered["functions"].extend(functions)

                if walkers or functions:
                    self._logger.info(
                        f"📦 Found in {module_name}: "
                        f"{len(walkers)} walkers, {len(functions)} functions"
                    )

            except Exception as e:
                self._logger.warning(f"⚠️ Failed to import {module_name}: {e}")

        total = len(discovered["walkers"]) + len(discovered["functions"])
        self._logger.info(f"✅ Discovery complete: {total} endpoints")

        return discovered

    def _discover_in_module(self, module: Any) -> tuple[List[Type[Walker]], List[Callable]]:
        """Discover endpoints within a module."""
        walkers = []
        functions = []

        for _name, obj in inspect.getmembers(module):
            # Discover walkers
            if self._is_walker_endpoint(obj):
                config = getattr(obj, "_jvspatial_endpoint_config", None)
                if config and config.get("path"):
                    walkers.append((obj, config))
                    self._discovered_walkers.add(obj)

            # Discover functions
            elif self._is_function_endpoint(obj):
                config = getattr(obj, "_jvspatial_endpoint_config", None)
                if config and config.get("path"):
                    functions.append((obj, config))
                    self._discovered_functions.add(obj)

        return walkers, functions

    def _is_walker_endpoint(self, obj: Any) -> bool:
        """Check if object is a Walker endpoint."""
        return (
            inspect.isclass(obj)
            and issubclass(obj, Walker)
            and obj is not Walker
            and obj not in self._discovered_walkers
            and hasattr(obj, "_jvspatial_endpoint_config")
        )

    def _is_function_endpoint(self, obj: Any) -> bool:
        """Check if object is a function endpoint."""
        return (
            inspect.isfunction(obj)
            and obj not in self._discovered_functions
            and hasattr(obj, "_jvspatial_endpoint_config")
            and getattr(obj._jvspatial_endpoint_config, "is_function", False)
        )

    def _matches_any_pattern(self, name: str) -> bool:
        """Check if name matches any pattern."""
        return any(fnmatch.fnmatch(name, p) for p in self.patterns)
```

**Update Server class**:
```python
# server.py (simplified)
def discover_and_register_packages(self, package_patterns=None):
    """Discover and register endpoints - delegates to service."""
    from jvspatial.api.services.package_discovery import PackageDiscoveryService

    if not self._package_discovery_enabled:
        return 0

    # Create discovery service
    discovery_service = PackageDiscoveryService(
        patterns=package_patterns or self._discovery_patterns,
        logger=self._logger
    )

    # Discover packages
    discovered = discovery_service.discover_packages()

    # Register discovered endpoints using endpoint registry
    count = 0
    for walker_class, config in discovered["walkers"]:
        self.endpoint_registry.register_walker(
            walker_class,
            config["path"],
            config.get("methods"),
            **config.get("kwargs", {})
        )
        count += 1

    for func, config in discovered["functions"]:
        # Register function endpoints
        # ... simplified registration
        count += 1

    return count
```

#### Benefits
- ✅ Separation of concerns: discovery vs registration
- ✅ Testable discovery logic in isolation
- ✅ Reusable for other discovery scenarios
- ✅ Clear responsibility boundaries
- ✅ Reduces Server class by 235+ lines

---

## 🔧 High Priority Refactorings (Should Do)

### 6. Create Lifecycle Manager Service

**Priority**: 🔧 High
**Effort**: 6 hours
**Location**: [`server.py:458-1526`](../../jvspatial/api/server.py:458)

#### Problem
Lifecycle management scattered across multiple methods with duplicate async checking logic.

#### Current Code
```python
# server.py:458-480 - Registration methods
def on_startup(self, func):
    self._startup_tasks.append(func)
    return func

def on_shutdown(self, func):
    self._shutdown_tasks.append(func)
    return func

# server.py:1438-1492 - Execution logic
async def _default_startup(self):
    # Complex startup logic
    self._is_running = True
    # Database init, discovery, etc.

async def _default_shutdown(self):
    self._is_running = False

# server.py:1500-1526 - Lifespan management
@asynccontextmanager
async def _lifespan(self, app):
    await self._default_startup()
    for task in self._startup_tasks:
        if asyncio.iscoroutinefunction(task):
            await task()
        else:
            task()
    yield
    await self._default_shutdown()
    for task in self._shutdown_tasks:
        if asyncio.iscoroutinefunction(task):
            await task()
        else:
            task()
```

#### Proposed Refactoring

```python
# jvspatial/api/services/lifecycle_manager.py
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import List, Callable, Any, AsyncGenerator

class LifecycleManager:
    """Manages application lifecycle hooks and events."""

    def __init__(self, logger: logging.Logger = None):
        self._startup_hooks: List[Callable] = []
        self._shutdown_hooks: List[Callable] = []
        self._is_running = False
        self._logger = logger or logging.getLogger(__name__)

    def add_startup_hook(self, func: Callable) -> Callable:
        """Register a startup hook."""
        self._startup_hooks.append(func)
        return func

    def add_shutdown_hook(self, func: Callable) -> Callable:
        """Register a shutdown hook."""
        self._shutdown_hooks.append(func)
        return func

    async def execute_startup(self, *additional_hooks: Callable) -> None:
        """Execute all startup hooks."""
        self._logger.info("🚀 Executing startup hooks...")
        self._is_running = True

        all_hooks = list(additional_hooks) + self._startup_hooks

        for hook in all_hooks:
            try:
                await self._execute_hook(hook, "startup")
            except Exception as e:
                self._logger.error(f"❌ Startup hook failed: {e}", exc_info=True)
                raise

        self._logger.info("✅ Startup complete")

    async def execute_shutdown(self, *additional_hooks: Callable) -> None:
        """Execute all shutdown hooks."""
        self._logger.info("🛑 Executing shutdown hooks...")

        all_hooks = list(additional_hooks) + self._shutdown_hooks

        for hook in all_hooks:
            try:
                await self._execute_hook(hook, "shutdown")
            except Exception as e:
                self._logger.error(f"⚠️ Shutdown hook failed: {e}", exc_info=True)
                # Don't raise - allow other hooks to run

        self._is_running = False
        self._logger.info("✅ Shutdown complete")

    async def _execute_hook(self, hook: Callable, phase: str) -> None:
        """Execute a single hook (async or sync)."""
        hook_name = getattr(hook, "__name__", str(hook))

        try:
            if asyncio.iscoroutinefunction(hook):
                await hook()
            else:
                hook()
            self._logger.debug(f"✓ {phase} hook: {hook_name}")
        except Exception as e:
            self._logger.error(f"✗ {phase} hook failed: {hook_name} - {e}")
            raise

    @asynccontextmanager
    async def lifespan(
        self,
        startup_hook: Callable = None,
        shutdown_hook: Callable = None
    ) -> AsyncGenerator[None, None]:
        """Lifespan context manager for FastAPI."""
        startup_hooks = [startup_hook] if startup_hook else []
        shutdown_hooks = [shutdown_hook] if shutdown_hook else []

        await self.execute_startup(*startup_hooks)
        try:
            yield
        finally:
            await self.execute_shutdown(*shutdown_hooks)

    @property
    def is_running(self) -> bool:
        """Check if application is running."""
        return self._is_running
```

**Update Server class**:
```python
# server.py (simplified)
class Server:
    def __init__(self, config, **kwargs):
        # ... other init ...
        from jvspatial.api.services.lifecycle_manager import LifecycleManager
        self._lifecycle = LifecycleManager(logger=self._logger)

    def on_startup(self, func):
        """Register startup hook - delegates to lifecycle manager."""
        return self._lifecycle.add_startup_hook(func)

    def on_shutdown(self, func):
        """Register shutdown hook - delegates to lifecycle manager."""
        return self._lifecycle.add_shutdown_hook(func)

    @property
    def _is_running(self):
        """Running state from lifecycle manager."""
        return self._lifecycle.is_running

    async def _default_startup(self):
        """Default startup tasks."""
        self._logger.info(f"🚀 Starting {self.config.title}...")
        # Database initialization
        # File storage verification
        # Package discovery

    async def _default_shutdown(self):
        """Default shutdown tasks."""
        self._logger.info(f"🛑 Shutting down {self.config.title}...")

    @asynccontextmanager
    async def _lifespan(self, app):
        """Application lifespan - uses lifecycle manager."""
        async with self._lifecycle.lifespan(
            startup_hook=self._default_startup,
            shutdown_hook=self._default_shutdown
        ):
            yield
```

#### Benefits
- ✅ Single responsibility for lifecycle management
- ✅ Consistent hook execution logic
- ✅ Better error handling and logging
- ✅ Testable in isolation
- ✅ Reusable across different contexts

---

### 7. Replace Magic Strings with Constants

**Priority**: 🔧 High
**Effort**: 4 hours
**Location**: Multiple files

#### Problem
Magic strings scattered throughout codebase make refactoring difficult and error-prone.

#### Current Code Examples
```python
# server.py:642 - Magic string
app.include_router(self.endpoint_router.router, prefix="/api")

# server.py:700 - Magic path
@app.get("/api/storage/files/{file_path:path}")

# server.py:763 - Magic path
@app.get("/p/{code}")

# Multiple files - Magic collection names
await User.find_by_username(username)  # Uses "users" collection
await APIKey.find_by_key_id(key_id)    # Uses "api_keys" collection

# server.py:286 - Magic log messages
self._logger.info("🎯 GraphContext initialized...")
```

#### Proposed Refactoring

```python
# jvspatial/api/constants.py
"""Constants for the API module."""

from enum import Enum

# API Routes
class APIRoutes:
    """API route constants."""
    PREFIX = "/api"
    HEALTH = "/health"
    ROOT = "/"

    # Storage routes
    STORAGE_PREFIX = "/api/storage"
    STORAGE_UPLOAD = f"{STORAGE_PREFIX}/upload"
    STORAGE_FILES = f"{STORAGE_PREFIX}/files"
    STORAGE_PROXY = f"{STORAGE_PREFIX}/proxy"

    # Proxy routes
    PROXY_PREFIX = "/p"
    PROXY_ACCESS = f"{PROXY_PREFIX}/{{code}}"

# HTTP Methods
class HTTPMethods:
    """Standard HTTP methods."""
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"

# Collection Names
class Collections:
    """Database collection names."""
    USERS = "users"
    API_KEYS = "api_keys"
    SESSIONS = "sessions"
    WEBHOOKS = "webhooks"
    WEBHOOK_REQUESTS = "webhook_requests"

# Log Icons
class LogIcons:
    """Emoji icons for logging."""
    START = "🚀"
    STOP = "🛑"
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    INFO = "ℹ️"
    DATABASE = "📊"
    STORAGE = "📁"
    NETWORK = "🔌"
    DISCOVERY = "🔍"
    REGISTERED = "📝"
    UNREGISTERED = "🗑️"
    DYNAMIC = "🔄"
    WEBHOOK = "🔗"
    CONTEXT = "🎯"
    HEALTH = "🏥"

# Error Messages
class ErrorMessages:
    """Standard error messages."""
    AUTH_REQUIRED = "Authentication required"
    INVALID_CREDENTIALS = "Invalid credentials"
    INACTIVE_USER = "User account is inactive"
    ADMIN_REQUIRED = "Admin access required"
    PERMISSION_DENIED = "Permission denied"
    NOT_FOUND = "Resource not found"
    INTERNAL_ERROR = "Internal server error"

# Status Codes (from http.HTTPStatus)
from http import HTTPStatus

# Configuration Defaults
class Defaults:
    """Default configuration values."""
    API_TITLE = "jvspatial API"
    API_VERSION = "1.0.0"
    HOST = "0.0.0.0"
    PORT = 8000
    LOG_LEVEL = "info"

    # File Storage
    FILE_STORAGE_ROOT = ".files"
    FILE_STORAGE_MAX_SIZE = 100 * 1024 * 1024  # 100MB
    PROXY_EXPIRATION = 3600  # 1 hour
    PROXY_MAX_EXPIRATION = 86400  # 24 hours
```

**Update usage**:
```python
# server.py (updated)
from jvspatial.api.constants import (
    APIRoutes,
    HTTPMethods,
    LogIcons,
    HTTPStatus,
    ErrorMessages
)

# Before:
app.include_router(self.endpoint_router.router, prefix="/api")

# After:
app.include_router(self.endpoint_router.router, prefix=APIRoutes.PREFIX)

# Before:
@app.get("/api/storage/files/{file_path:path}")

# After:
@app.get(f"{APIRoutes.STORAGE_FILES}/{{file_path:path}}")

# Before:
self._logger.info("🎯 GraphContext initialized...")

# After:
self._logger.info(f"{LogIcons.CONTEXT} GraphContext initialized...")

# Before:
raise HTTPException(status_code=401, detail="Authentication required")

# After:
raise HTTPException(
    status_code=HTTPStatus.UNAUTHORIZED,
    detail=ErrorMessages.AUTH_REQUIRED
)
```

#### Benefits
- ✅ Single source of truth for strings
- ✅ Easier refactoring (change in one place)
- ✅ Type safety and IDE autocomplete
- ✅ Reduced typos and errors
- ✅ Self-documenting code

---

### 8. Standardize Exception Handling

**Priority**: 🔧 High
**Effort**: 8 hours
**Location**: Multiple files

#### Problem
Inconsistent exception handling with mix of HTTPException, custom exceptions, and error dictionaries.

#### Current Code (Inconsistent Patterns)
```python
# Pattern 1: HTTPException with magic numbers
raise HTTPException(status_code=401, detail="Not authenticated")

# Pattern 2: HTTPException without status import
raise HTTPException(404, "File not found")

# Pattern 3: Custom exceptions (some places)
raise InvalidCredentialsError("Invalid username")

# Pattern 4: JSONResponse with errors
return JSONResponse(status_code=503, content={"status": "unhealthy"})

# Pattern 5: Error dictionaries
return {"status": "error", "error": "login_failed"}
```

#### Proposed Refactoring

```python
# jvspatial/api/exceptions.py
"""Standardized exception hierarchy for API."""

from http import HTTPStatus
from typing import Optional, Dict, Any

class JVSpatialAPIException(Exception):
    """Base exception for all API errors."""

    status_code: int = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    default_message: str = "An internal error occurred"

    def __init__(
        self,
        message: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ):
        self.message = message or self.default_message
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON response."""
        result = {
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.details:
            result["details"] = self.details
        return result

# Authentication Errors
class AuthenticationError(JVSpatialAPIException):
    """Base authentication error."""
    status_code = HTTPStatus.UNAUTHORIZED
    error_code = "authentication_failed"
    default_message = "Authentication failed"

class InvalidCredentialsError(AuthenticationError):
    """Invalid username or password."""
    error_code = "invalid_credentials"
    default_message = "Invalid username or password"

class TokenExpiredError(AuthenticationError):
    """Authentication token expired."""
    error_code = "token_expired"
    default_message = "Authentication token has expired"

class InvalidTokenError(AuthenticationError):
    """Invalid authentication token."""
    error_code = "invalid_token"
    default_message = "Invalid authentication token"

# Authorization Errors
class AuthorizationError(JVSpatialAPIException):
    """Base authorization error."""
    status_code = HTTPStatus.FORBIDDEN
    error_code = "authorization_failed"
    default_message = "Access denied"

class InsufficientPermissionsError(AuthorizationError):
    """User lacks required permissions."""
    error_code = "insufficient_permissions"
    default_message = "Insufficient permissions"

class InactiveUserError(AuthorizationError):
    """User account is inactive."""
    error_code = "inactive_user"
    default_message = "User account is inactive"

class AdminRequiredError(AuthorizationError):
    """Admin access required."""
    error_code = "admin_required"
    default_message = "Admin access required"

# Resource Errors
class ResourceError(JVSpatialAPIException):
    """Base resource error."""
    pass

class ResourceNotFoundError(ResourceError):
    """Resource not found."""
    status_code = HTTPStatus.NOT_FOUND
    error_code = "not_found"
    default_message = "Resource not found"

class ResourceConflictError(ResourceError):
    """Resource conflict (duplicate)."""
    status_code = HTTPStatus.CONFLICT
    error_code = "conflict"
    default_message = "Resource already exists"

# Validation Errors
class ValidationError(JVSpatialAPIException):
    """Validation error."""
    status_code = HTTPStatus.UNPROCESSABLE_ENTITY
    error_code = "validation_error"
    default_message = "Validation failed"

# Storage Errors
class StorageError(JVSpatialAPIException):
    """Base storage error."""
    status_code = HTTPStatus.INTERNAL_SERVER_ERROR
    error_code = "storage_error"
    default_message = "Storage operation failed"

class FileNotFoundError(StorageError):
    """File not found."""
    status_code = HTTPStatus.NOT_FOUND
    error_code = "file_not_found"
    default_message = "File not found"

class PathTraversalError(StorageError):
    """Path traversal attempt detected."""
    status_code = HTTPStatus.BAD_REQUEST
    error_code = "path_traversal"
    default_message = "Invalid file path"
```

**Exception Handler**:
```python
# jvspatial/api/error_handlers.py
from fastapi import Request, status
from fastapi.responses import JSONResponse
from jvspatial.api.exceptions import JVSpatialAPIException

async def jvspatial_exception_handler(
    request: Request,
    exc: JVSpatialAPIException
) -> JSONResponse:
    """Handle JVSpatial API exceptions."""
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )

def register_exception_handlers(app):
    """Register all exception handlers on app."""
    app.add_exception_handler(JVSpatialAPIException, jvspatial_exception_handler)
```

**Updated usage**:
```python
# Before:
raise HTTPException(status_code=401, detail="Not authenticated")

# After:
raise AuthenticationError()

# Before:
raise HTTPException(404, "File not found")

# After:
raise FileNotFoundError()

# Before:
raise HTTPException(403, f"Missing permission: {perm}")

# After:
raise InsufficientPermissionsError(
    message=f"Missing permission: {perm}",
    details={"required_permission": perm}
)
```

#### Benefits
- ✅ Consistent error responses
- ✅ Type-safe exception hierarchy
- ✅ Structured error details
- ✅ Better client experience
- ✅ Easier error tracking

---

### 9. Extract Middleware Configuration

**Priority**: 🔧 High
**Effort**: 5 hours
**Location**: [`server.py:539-560`](../../jvspatial/api/server.py:539)

#### Problem
Middleware configuration logic scattered and hardcoded in app creation.

#### Proposed Refactoring

```python
# jvspatial/api/services/middleware_manager.py
from typing import List, Dict, Any, Callable
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

class MiddlewareConfig:
    """Middleware configuration."""

    def __init__(self, middleware_type: str, func: Callable, **options):
        self.middleware_type = middleware_type
        self.func = func
        self.options = options

class MiddlewareManager:
    """Manages application middleware configuration."""

    def __init__(self, logger: logging.Logger = None):
        self._middleware: List[MiddlewareConfig] = []
        self._logger = logger or logging.getLogger(__name__)

    def add_cors(
        self,
        origins: List[str] = ["*"],
        methods: List[str] = ["*"],
        headers: List[str] = ["*"],
        credentials: bool = True
    ) -> None:
        """Add CORS middleware configuration."""
        config = MiddlewareConfig(
            "cors",
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=methods,
            allow_headers=headers,
            allow_credentials=credentials
        )
        self._middleware.insert(0, config)  # CORS should be first

    def add_custom(self, middleware_type: str, func: Callable) -> None:
        """Add custom middleware."""
        config = MiddlewareConfig(middleware_type, func)
        self._middleware.append(config)

    def apply_to_app(self, app: FastAPI) -> None:
        """Apply all middleware to the app."""
        for config in self._middleware:
            if config.middleware_type == "cors":
                app.add_middleware(config.func, **config.options)
                self._logger.info("🌐 CORS middleware added")
            elif config.middleware_type == "http":
                app.middleware("http")(config.func)
                self._logger.info(f"🔧 HTTP middleware added: {config.func.__name__}")
            else:
                app.middleware(config.middleware_type)(config.func)
                self._logger.info(f"🔧 Middleware added: {config.middleware_type}")

        self._logger.info(f"✅ Applied {len(self._middleware)} middleware layers")
```

**Update Server**:
```python
# server.py
from jvspatial.api.services.middleware_manager import MiddlewareManager

class Server:
    def __init__(self, config, **kwargs):
        # ... other init ...
        self._middleware_manager = MiddlewareManager(logger=self._logger)

        # Configure CORS if enabled
        if self.config.cors_enabled:
            self._middleware_manager.add_cors(
                origins=self.config.cors_origins,
                methods=self.config.cors_methods,
                headers=self.config.cors_headers
            )

    def middleware(self, middleware_type: str = "http"):
        """Decorator to add middleware."""
        def decorator(func):
            self._middleware_manager.add_custom(middleware_type, func)
            return func
        return decorator

    def _configure_middleware(self, app: FastAPI):
        """Apply all middleware to app."""
        self._middleware_manager.apply_to_app(app)

        # Add webhook middleware if needed
        self._add_webhook_middleware(app)
```

#### Benefits
- ✅ Centralized middleware management
- ✅ Clear ordering control
- ✅ Easier testing
- ✅ Better logging

---

### 10. Add Type Protocols for Interfaces

**Priority**: 🔧 High
**Effort**: 6 hours
**Location**: Multiple files

#### Problem
No defined interfaces/protocols make duck typing unclear and type checking weak.

#### Proposed Refactoring

```python
# jvspatial/api/protocols.py
"""Type protocols for API interfaces."""

from typing import Protocol, Any, Dict, Optional, List
from fastapi import FastAPI

class FileStorageProvider(Protocol):
    """Protocol for file storage providers."""

    async def save_file(self, path: str, content: bytes) -> None:
        """Save file content."""
        ...

    async def get_file(self, path: str) -> bytes:
        """Get file content."""
        ...

    async def delete_file(self, path: str) -> bool:
        """Delete a file."""
        ...

    async def file_exists(self, path: str) -> bool:
        """Check if file exists."""
        ...

    async def get_file_url(self, path: str) -> str:
        """Get public URL for file."""
        ...

class ProxyManager(Protocol):
    """Protocol for URL proxy managers."""

    async def create_proxy(
        self,
        file_path: str,
        expires_in: int,
        one_time: bool = False,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a proxy URL."""
        ...

    async def resolve_proxy(self, code: str) -> tuple[str, Dict[str, Any]]:
        """Resolve proxy code to file path."""
        ...

    async def revoke_proxy(self, code: str) -> bool:
        """Revoke a proxy."""
        ...

class EndpointRegistry(Protocol):
    """Protocol for endpoint registry."""

    def register_walker(
        self,
        walker_class: type,
        path: str,
        methods: Optional[List[str]],
        **kwargs
    ) -> Any:
        """Register a walker endpoint."""
        ...

    def unregister_walker(self, walker_class: type) -> bool:
        """Unregister a walker endpoint."""
        ...

    def list_walkers(self) -> Dict[str, Dict[str, Any]]:
        """List all registered walkers."""
        ...

class LifecycleManager(Protocol):
    """Protocol for lifecycle management."""

    def add_startup_hook(self, func) -> None:
        """Add startup hook."""
        ...

    def add_shutdown_hook(self, func) -> None:
        """Add shutdown hook."""
        ...

    async def execute_startup(self) -> None:
        """Execute startup sequence."""
        ...

    async def execute_shutdown(self) -> None:
        """Execute shutdown sequence."""
        ...
```

**Usage with type hints**:
```python
# server.py
from jvspatial.api.protocols import (
    FileStorageProvider,
    ProxyManager,
    EndpointRegistry,
    LifecycleManager
)

class Server:
    def __init__(self, config, **kwargs):
        # Type-safe attributes
        self._file_interface: Optional[FileStorageProvider] = None
        self._proxy_manager: Optional[ProxyManager] = None
        self.endpoint_registry: EndpointRegistry
        self._lifecycle: LifecycleManager
```

#### Benefits
- ✅ Clear interface contracts
- ✅ Better type checking
- ✅ IDE autocomplete
- ✅ Easier mocking for tests
- ✅ Documentation through types

---

## 🟡 Medium Priority Refactorings (Nice to Have)

### 11. Extract Configuration Validation

**Priority**: 🟡 Medium
**Effort**: 4 hours
**Location**: [`server.py:51-150`](../../jvspatial/api/server.py:51)

#### Problem
ServerConfig validation happens implicitly through Pydantic, but complex validation logic is missing.

#### Proposed Refactoring

```python
# jvspatial/api/config.py
from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional, List

class ServerConfig(BaseModel):
    """Server configuration with validation."""

    # ... existing fields ...

    @field_validator('port')
    @classmethod
    def validate_port(cls, v):
        """Validate port is in valid range."""
        if not (1 <= v <= 65535):
            raise ValueError('Port must be between 1 and 65535')
        return v

    @field_validator('log_level')
    @classmethod
    def validate_log_level(cls, v):
        """Validate log level."""
        valid_levels = ['debug', 'info', 'warning',
 'error', 'critical']
        if v.lower() not in valid_levels:
            raise ValueError(f'Invalid log level. Must be one of: {valid_levels}')
        return v.lower()

    @model_validator(mode='after')
    def validate_s3_config(self):
        """Validate S3 configuration when S3 provider is selected."""
        if self.file_storage_provider == 's3':
            if not self.s3_bucket_name:
                raise ValueError('s3_bucket_name required when using S3 storage')
            if not self.s3_region:
                raise ValueError('s3_region required when using S3 storage')
        return self

    @model_validator(mode='after')
    def validate_proxy_expiration(self):
        """Validate proxy expiration settings."""
        if self.proxy_default_expiration > self.proxy_max_expiration:
            raise ValueError(
                'proxy_default_expiration cannot exceed proxy_max_expiration'
            )
        return self
```

#### Benefits
- ✅ Fail-fast configuration validation
- ✅ Clear error messages
- ✅ Prevents runtime errors

---

### 12. Consolidate Logging Configuration

**Priority**: 🟡 Medium
**Effort**: 3 hours
**Location**: Multiple files

#### Problem
50+ scattered log statements with inconsistent formatting and no centralized logging strategy.

#### Proposed Refactoring

```python
# jvspatial/api/logging_config.py
import logging
from typing import Optional

class APILogger:
    """Structured logging for API operations."""

    def __init__(self, name: str = __name__, level: str = "INFO"):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

    def server_starting(self, title: str, host: str, port: int):
        """Log server startup."""
        self.logger.info(f"🔧 Server starting: {title} at http://{host}:{port}")

    def database_initialized(self, db_type: str):
        """Log database initialization."""
        self.logger.info(f"📊 Database initialized: {db_type}")

    def endpoint_registered(self, endpoint_type: str, name: str, path: str):
        """Log endpoint registration."""
        self.logger.info(f"📝 Registered {endpoint_type}: {name} at {path}")

    def service_initialized(self, service_name: str, details: Optional[str] = None):
        """Log service initialization."""
        msg = f"✅ {service_name} initialized"
        if details:
            msg += f": {details}"
        self.logger.info(msg)

    # ... more structured logging methods
```

#### Benefits
- ✅ Consistent log formatting
- ✅ Structured log data
- ✅ Easier log parsing
- ✅ Single source of truth

---

### 13. Simplify Dynamic Registration Logic

**Priority**: 🟡 Medium
**Effort**: 6 hours
**Location**: [`server.py:482-509, 810-852`](../../jvspatial/api/server.py:482)

#### Problem
Complex dynamic registration with app rebuilding that doesn't actually work with running uvicorn.

#### Current Code
```python
# server.py:482-509
def _rebuild_app_if_needed(self):
    """Rebuild the FastAPI app to reflect dynamic changes."""
    if not self._is_running or self.app is None:
        return

    try:
        self._logger.info("🔄 Rebuilding FastAPI app...")
        self.app = self._create_app_instance()

        # Warning: This won't work with running uvicorn!
        self._logger.warning(
            "App rebuilt internally. For changes to take effect, "
            "you may need to restart..."
        )
    except Exception as e:
        self._logger.error(f"❌ Failed to rebuild app: {e}")
```

#### Proposed Refactoring

**Option 1**: Remove app rebuilding, use explicit restart
```python
# server.py (simplified)
def _mark_for_reload(self):
    """Mark that server needs reload for changes."""
    if self._is_running:
        self._logger.warning(
            "⚠️ Dynamic changes detected. "
            "Please restart server or use reload=True mode for changes to take effect."
        )
        self._needs_restart = True

def register_walker_class(self, walker_class, path, methods=None, **kwargs):
    """Register walker - simplified."""
    self.endpoint_registry.register_walker(walker_class, path, methods, **kwargs)

    if self._is_running:
        self._mark_for_reload()
    else:
        # Normal registration
        self.endpoint_router.endpoint(path, methods, **kwargs)(walker_class)
```

**Option 2**: Use dynamic router include (current approach but cleaner)
```python
def register_walker_dynamically(self, walker_class, path, methods=None, **kwargs):
    """Register walker on running server using dynamic router."""
    if not self.app:
        return

    router = self.endpoint_registry.register_walker_dynamic(
        walker_class, path, methods, **kwargs
    )
    self.app.include_router(router.router, prefix="/api")

    self._logger.info(f"✅ Dynamic registration: {walker_class.__name__}")
```

#### Benefits
- ✅ Simpler, clearer logic
- ✅ No false promises
- ✅ Better user expectations
- ✅ Reduced complexity

---

### 14. Extract Health Check Logic

**Priority**: 🟡 Medium
**Effort**: 3 hours
**Location**: [`server.py:595-626`](../../jvspatial/api/server.py:595)

#### Problem
30-line health check logic embedded in app creation.

#### Proposed Refactoring

```python
# jvspatial/api/health.py
from typing import Dict, Any, Optional
from fastapi.responses import JSONResponse
from jvspatial.core.entities import Root

class HealthChecker:
    """Health check service."""

    def __init__(self, graph_context=None, config=None):
        self.graph_context = graph_context
        self.config = config

    async def check_health(self) -> Dict[str, Any] | JSONResponse:
        """Perform health check."""
        try:
            # Database check
            db_status = await self._check_database()

            return {
                "status": "healthy",
                "database": db_status,
                "service": self.config.title if self.config else "jvspatial API",
                "version": self.config.version if self.config else "unknown",
            }
        except Exception as e:
            return self._unhealthy_response(str(e))

    async def _check_database(self) -> str:
        """Check database connectivity."""
        if self.graph_context:
            root = await self.graph_context.get_node(Root, "root")
            if not root:
                root = await self.graph_context.create_node(Root)
        else:
            root = await Root.get("n:Root:root")
            if not root:
                root = await Root.create()

        return "connected"

    def _unhealthy_response(self, error: str) -> JSONResponse:
        """Create unhealthy response."""
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": error,
                "service": self.config.title if self.config else "jvspatial API",
                "version": self.config.version if self.config else "unknown",
            }
        )
```

#### Benefits
- ✅ Testable health check logic
- ✅ Reusable across contexts
- ✅ Cleaner app creation
- ✅ Extensible health checks

---

### 15. Create Router Factory

**Priority**: 🟡 Medium
**Effort**: 4 hours
**Location**: [`server.py:640-647`](../../jvspatial/api/server.py:640)

#### Problem
Router inclusion logic hardcoded in app creation.

#### Proposed Refactoring

```python
# jvspatial/api/services/router_factory.py
from typing import List
from fastapi import FastAPI, APIRouter
from jvspatial.api.endpoint.router import EndpointRouter

class RouterFactory:
    """Factory for creating and managing routers."""

    def __init__(self, prefix: str = "/api"):
        self.prefix = prefix
        self.routers: List[APIRouter] = []

    def add_router(self, router: APIRouter) -> None:
        """Add a router to be included."""
        self.routers.append(router)

    def include_all(self, app: FastAPI) -> None:
        """Include all routers in the app."""
        for router in self.routers:
            app.include_router(router, prefix=self.prefix)

    @staticmethod
    def create_endpoint_router() -> EndpointRouter:
        """Create a new endpoint router."""
        return EndpointRouter()
```

#### Benefits
- ✅ Centralized router management
- ✅ Easier testing
- ✅ Clear router organization

---

## 📊 Summary Tables

### Refactoring Impact Summary

| ID | Refactoring | Priority | Effort | LOC Reduced | Testability | Maintainability |
|----|-------------|----------|--------|-------------|-------------|-----------------|
| 1  | File Storage Service | 🔥 Critical | 8h | 159 | ⬆️⬆️⬆️ | ⬆️⬆️⬆️ |
| 2  | Endpoint Registry | 🔥 Critical | 12h | 400+ | ⬆️⬆️⬆️ | ⬆️⬆️⬆️ |
| 3  | Eliminate Global State | 🔥 Critical | 6h | 50 | ⬆️⬆️⬆️ | ⬆️⬆️⬆️ |
| 4  | Split `_create_app_instance` | 🔥 Critical | 10h | 0 (reorganize) | ⬆️⬆️ | ⬆️⬆️⬆️ |
| 5  | Package Discovery Service | 🔥 Critical | 8h | 235+ | ⬆️⬆️⬆️ | ⬆️⬆️ |
| 6  | Lifecycle Manager | 🔧 High | 6h | 88 | ⬆️⬆️ | ⬆️⬆️ |
| 7  | Magic String Constants | 🔧 High | 4h | 0 (improve) | ⬆️ | ⬆️⬆️⬆️ |
| 8  | Exception Hierarchy | 🔧 High | 8h | 0 (standardize) | ⬆️⬆️ | ⬆️⬆️⬆️ |
| 9  | Middleware Manager | 🔧 High | 5h | 40 | ⬆️⬆️ | ⬆️⬆️ |
| 10 | Type Protocols | 🔧 High | 6h | 0 (improve) | ⬆️⬆️⬆️ | ⬆️⬆️ |
| 11 | Config Validation | 🟡 Medium | 4h | 0 (improve) | ⬆️⬆️ | ⬆️ |
| 12 | Logging Config | 🟡 Medium | 3h | 0 (standardize) | ⬆️ | ⬆️⬆️ |
| 13 | Dynamic Registration | 🟡 Medium | 6h | 30 | ⬆️ | ⬆️⬆️ |
| 14 | Health Check Service | 🟡 Medium | 3h | 30 | ⬆️⬆️ | ⬆️ |
| 15 | Router Factory | 🟡 Medium | 4h | 20 | ⬆️ | ⬆️ |

**Total Estimated Effort**: 97 hours (~12 developer days)
**Total Lines Reduced/Improved**: 1,042+ lines
**Server.py Target**: From 1857 lines → ~800 lines (57% reduction)

---

### Implementation Roadmap

#### Phase 1: Critical Foundation (4-5 weeks)
**Goal**: Extract core services, eliminate global state

1. **Week 1-2**:
   - Refactoring #3: Eliminate Global State (6h)
   - Refactoring #7: Magic String Constants (4h)
   - Refactoring #8: Exception Hierarchy (8h)
   - Refactoring #10: Type Protocols (6h)
   - **Subtotal**: 24h

2. **Week 3-4**:
   - Refactoring #1: File Storage Service (8h)
   - Refactoring #2: Endpoint Registry (12h)
   - Refactoring #6: Lifecycle Manager (6h)
   - **Subtotal**: 26h

3. **Week 5**:
   - Refactoring #4: Split `_create_app_instance` (10h)
   - Refactoring #9: Middleware Manager (5h)
   - **Subtotal**: 15h

**Phase 1 Total**: ~65 hours

#### Phase 2: Service Extraction (2-3 weeks)
**Goal**: Extract remaining services, improve structure

1. **Week 6-7**:
   - Refactoring #5: Package Discovery Service (8h)
   - Refactoring #13: Simplify Dynamic Registration (6h)
   - Refactoring #14: Health Check Service (3h)
   - **Subtotal**: 17h

2. **Week 8**:
   - Refactoring #11: Config Validation (4h)
   - Refactoring #12: Logging Config (3h)
   - Refactoring #15: Router Factory (4h)
   - **Subtotal**: 11h

**Phase 2 Total**: ~28 hours

#### Phase 3: Testing & Documentation (1-2 weeks)
- Write unit tests for extracted services
- Update documentation
- Integration testing
- Performance validation

**Phase 3 Total**: ~20 hours

---

## 🎯 Top 5 Most Critical Refactorings

### 1. 🥇 Extract Endpoint Registry Service
**Why**: Eliminates 400+ lines of duplicate registration logic, creates single source of truth

**Impact**:
- Reduces Server class by ~22%
- Makes endpoint management testable
- Eliminates shotgun surgery for new endpoint types
- Clear separation of concerns

**Risk**: Medium (touches many decorators, but well-defined interface)

---

### 2. 🥈 Eliminate Global Server Registry
**Why**: Removes hidden dependencies, makes code testable, eliminates global mutable state

**Impact**:
- Makes tests isolated and reliable
- Explicit dependencies (no magic)
- Thread-safe by default (ContextVar)
- Enables multiple server instances

**Risk**: Medium (requires updating decorators and usage patterns)

---

### 3. 🥉 Split `_create_app_instance` Method
**Why**: 138-line god method violates SRP, makes testing and understanding difficult

**Impact**:
- Each setup step becomes testable unit
- Clear orchestration sequence
- Easy to override specific behaviors
- Reduced cognitive load

**Risk**: Low (internal refactoring, public API unchanged)

---

### 4. Extract File Storage Service
**Why**: 159 lines of inline endpoints bloat Server class, violate SRP

**Impact**:
- Reduces Server by 8.5%
- Makes file storage testable
- Reusable outside Server context
- Clear dependency injection

**Risk**: Low (well-defined interface, isolated functionality)

---

### 5. Standardize Exception Handling
**Why**: Inconsistent error handling creates poor client experience and maintenance burden

**Impact**:
- Consistent error responses
- Type-safe exception handling
- Better error tracking
- Improved client experience

**Risk**: Medium (requires updating ~36 error call sites)

---

## 📋 Quick Wins (< 4 hours each)

For immediate impact with minimal effort:

1. **Magic String Constants** (4h)
   - Immediate benefit: Fewer typos, better refactoring
   - Easy to implement incrementally

2. **Logging Configuration** (3h)
   - Immediate benefit: Consistent, searchable logs
   - Can be done in parallel with other work

3. **Health Check Service** (3h)
   - Immediate benefit: Testable health checks
   - Low risk, high value

4. **Config Validation** (4h)
   - Immediate benefit: Fail-fast on misconfiguration
   - Prevents runtime errors

---

## 🔬 Testing Strategy

Each refactoring should include:

### Unit Tests
```python
# Example: Testing FileStorageService
async def test_file_upload_success():
    mock_interface = Mock(spec=FileStorageProvider)
    service = FileStorageService(mock_interface)

    file = create_test_upload_file("test.txt", b"content")
    result = await service.upload_file(file)

    assert result["success"] is True
    mock_interface.save_file.assert_called_once()

async def test_file_upload_validation_error():
    service = FileStorageService(mock_interface)

    with pytest.raises(HTTPException) as exc_info:
        await service.upload_file(file, path="../etc/passwd")

    assert exc_info.value.status_code == 400
```

### Integration Tests
```python
# Example: Testing endpoint registration
async def test_walker_registration_flow():
    server = Server(title="Test")

    @server.walker("/test")
    class TestWalker(Walker):
        pass

    # Verify registration
    endpoints = server.list_walker_endpoints_safe()
    assert "TestWalker" in endpoints
    assert endpoints["TestWalker"]["path"] == "/test"
```

---

## 📚 Benefits Summary

### Code Quality Improvements
- ✅ **Reduced Complexity**: 1857 → ~800 lines in Server class (57% reduction)
- ✅ **Single Responsibility**: Each service has one clear purpose
- ✅ **DRY Principle**: Eliminate 400+ lines of duplicate logic
- ✅ **Type Safety**: Clear protocols and interfaces
- ✅ **Testability**: Isolated, mockable components

### Developer Experience
- ✅ **Faster Onboarding**: Clear, focused classes
- ✅ **Easier Debugging**: Smaller, testable units
- ✅ **Better IDE Support**: Type hints and protocols
- ✅ **Clearer Documentation**: Self-documenting structure

### Maintainability
- ✅ **Easier Refactoring**: Small, focused changes
- ✅ **Reduced Bugs**: Consistent error handling
- ✅ **Better Testing**: 80%+ test coverage achievable
- ✅ **Clear Dependencies**: Explicit injection

---

## ⚠️ Migration Guide

### Breaking Changes
Most refactorings maintain backward compatibility, but:

1. **Global Server Registry** (#3):
   - Old: `walker_endpoint()` uses global default
   - New: Explicit server parameter or context
   - Migration: Add `server=` or use context manager

2. **Exception Handling** (#8):
   - Old: Mix of HTTPException patterns
   - New: Consistent exception hierarchy
   - Migration: Replace HTTPException with typed exceptions

### Backward Compatibility
Provide deprecated wrappers:

```python
# Deprecated but working
def get_default_server():
    """Deprecated: Use explicit server or context."""
    warnings.warn(
        "get_default_server() is deprecated. "
        "Use explicit server parameter or ServerContext.",
        DeprecationWarning
    )
    return get_current_server()
```

---

## 📖 References

- **Architecture Analysis**: [`api-architecture-analysis.md`](api-architecture-analysis.md)
- **SOLID Principles**: [Clean Architecture](https://blog.cleancoder.com/uncle-bob/2012/08/13/the-clean-architecture.html)
- **FastAPI Best Practices**: [FastAPI Docs](https://fastapi.tiangolo.com/)
- **Design Patterns**: Gang of Four patterns

---

**Document Version**: 1.0
**Last Updated**: 2025-10-08
**Next Review**: After Phase 1 completion