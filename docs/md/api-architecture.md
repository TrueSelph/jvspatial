# jvspatial API Architecture

The jvspatial API module provides a comprehensive FastAPI integration layer that enables RESTful access to graph-based spatial data operations. The architecture is built around a central [`Server`](../../jvspatial/api/server.py:38) class that orchestrates all components.

## Core Architecture

### Server Class

The [`Server`](../../jvspatial/api/server.py:38) class is the main orchestrator that manages:

- FastAPI application lifecycle via [`LifecycleManager`](../../jvspatial/api/services/lifecycle.py:1)
- Endpoint registration through [`EndpointRegistryService`](../../jvspatial/api/services/endpoint_registry.py:88)
- Middleware configuration via [`MiddlewareManager`](../../jvspatial/api/services/middleware.py:1)
- GraphContext integration for database operations
- Optional file storage and scheduler services

```python
from jvspatial.api import Server

server = Server(
    title="My Spatial API",
    description="Graph-based API",
    version="1.0.0",
    db_type="json",
    db_path="./jvdb"
)
```

### Configuration

API configuration is managed through [`ServerConfig`](../../jvspatial/api/config.py:12) which supports:

- API metadata (title, description, version)
- Server settings (host, port, debug mode)
- CORS configuration
- Database configuration (type, path, connection strings)
- File storage settings (local/S3)
- Proxy settings for temporary file URLs
- Lifecycle hooks (startup/shutdown)

Environment variables follow the pattern `JVSPATIAL_*` for configuration overrides.

## Core Components

### 1. Context Management

[`context.py`](../../jvspatial/api/context.py:1) provides thread-safe server instance management:

- [`get_current_server()`](../../jvspatial/api/context.py:20) - Retrieve current server from context
- [`set_current_server()`](../../jvspatial/api/context.py:43) - Set server in current context
- [`ServerContext`](../../jvspatial/api/context.py:66) - Context manager for temporary server switching

This enables package-level decorators like `@walker_endpoint` to work without explicit server references.

### 2. Endpoint System

The endpoint system consists of two main files:

**[`endpoint/router.py`](../../jvspatial/api/endpoint/router.py:1)** - Endpoint registration and routing:
- [`EndpointRouter`](../../jvspatial/api/endpoint/router.py:514) - Main router class for walker and function endpoints
- [`EndpointField`](../../jvspatial/api/endpoint/router.py:50) - Enhanced Pydantic field with endpoint configuration
- [`ParameterModelFactory`](../../jvspatial/api/endpoint/router.py:153) - Creates parameter models from Walker classes

**[`endpoint/response.py`](../../jvspatial/api/endpoint/response.py:1)** - Response utilities:
- [`EndpointResponseHelper`](../../jvspatial/api/endpoint/response.py:65) - Semantic response methods (success, error, created, etc.)
- [`EndpointResponse`](../../jvspatial/api/endpoint/response.py:8) - Response wrapper with status codes and headers

#### Endpoint Types

**Walker Endpoints** - Graph traversal via HTTP:
```python
from jvspatial.api import endpoint
from jvspatial.api.decorators import EndpointField

@endpoint("/process", methods=["POST"])
class DataProcessor(Walker):
    query: str = EndpointField(description="Search query")
    limit: int = EndpointField(default=10, ge=1, le=100)
```

**Function Endpoints** - Direct API functions:
```python
from jvspatial.api import endpoint

@endpoint("/users/count", methods=["GET"])
async def get_user_count(endpoint) -> Dict[str, Any]:
    users = await User.find({})
    count = len(users)
    return endpoint.success(data={"count": count})
```

### 3. Services Layer

[`services/`](../../jvspatial/api/services/__init__.py:1) provides core service implementations:

**[`EndpointRegistryService`](../../jvspatial/api/services/endpoint_registry.py:88)** - Central endpoint tracking:
- [`register_walker()`](../../jvspatial/api/services/endpoint_registry.py:132) - Register walker endpoints
- [`register_function()`](../../jvspatial/api/services/endpoint_registry.py:185) - Register function endpoints
- [`list_all()`](../../jvspatial/api/services/endpoint_registry.py:390) - List all registered endpoints
- [`unregister_walker()`](../../jvspatial/api/services/endpoint_registry.py:273) - Remove walker endpoints
- Dynamic endpoint tracking and management

**[`LifecycleManager`](../../jvspatial/api/services/lifecycle.py:1)** - Application lifecycle:
- Startup and shutdown hook registration
- Lifespan context manager for FastAPI
- Asynchronous hook execution

**[`MiddlewareManager`](../../jvspatial/api/services/middleware.py:1)** - Middleware configuration:
- CORS middleware setup
- Custom middleware registration
- Middleware application to FastAPI app

**[`FileStorageService`](../../jvspatial/api/services/file_storage.py:1)** - File operations:
- Upload/download file handling
- Proxy URL generation for temporary access
- Local and S3 storage backend support

**[`PackageDiscoveryService`](../../jvspatial/api/services/discovery.py:1)** - Automatic endpoint discovery:
- Discovers walker and function endpoints from installed packages
- Pattern-based package scanning
- Dynamic endpoint registration

### 4. Authentication System

[`auth/`](../../jvspatial/api/auth/__init__.py:1) provides comprehensive authentication and authorization:

**Core Entities** ([`auth/entities.py`](../../jvspatial/api/auth/entities.py:1)):
- [`User`](../../jvspatial/api/auth/entities.py:1) - User accounts with roles and permissions
- [`Session`](../../jvspatial/api/auth/entities.py:1) - JWT session management
- [`APIKey`](../../jvspatial/api/auth/entities.py:1) - API key authentication

**Middleware** ([`auth/middleware.py`](../../jvspatial/api/auth/middleware.py:1)):
- [`AuthenticationMiddleware`](../../jvspatial/api/auth/middleware.py:1) - Request authentication
- [`JWTManager`](../../jvspatial/api/auth/middleware.py:1) - JWT token handling
- [`RateLimiter`](../../jvspatial/api/auth/middleware.py:1) - Rate limiting

**Decorators** - Use the unified `@endpoint` decorator with parameters:
- `@endpoint(..., auth=True)` - Authenticated endpoint
- `@endpoint(..., auth=True, roles=["admin"])` - Role-based access control
- `@endpoint(..., auth=True, permissions=["read_data"])` - Permission-based access control
- `@endpoint(..., webhook=True)` - Webhook endpoint

```python
from jvspatial.api import endpoint

@endpoint("/protected/data", methods=["GET"], auth=True, permissions=["read_data"])
async def get_protected_data(endpoint):
    return endpoint.success(data={"secret": "info"})

@endpoint("/admin/process", methods=["POST"], auth=True, roles=["admin"])
class AdminProcessor(Walker):
    pass
```

### 5. Webhook System

[`webhook/`](../../jvspatial/api/webhook/) provides webhook endpoint support:

**[`webhook/endpoint.py`](../../jvspatial/api/webhook/endpoint.py:1)** - Webhook endpoint helpers:
- [`create_webhook_wrapper()`](../../jvspatial/api/webhook/endpoint.py:155) - Wrap function endpoints
- [`create_webhook_walker_wrapper()`](../../jvspatial/api/webhook/endpoint.py:237) - Wrap walker endpoints
- [`inject_webhook_payload()`](../../jvspatial/api/webhook/endpoint.py:54) - Automatic payload injection
- [`WebhookEndpointResponseHelper`](../../jvspatial/api/webhook/endpoint.py:17) - Webhook-specific responses

**[`webhook/middleware.py`](../../jvspatial/api/webhook/middleware.py:1)** - Request processing:
- HMAC signature verification
- Payload parsing (JSON/XML/binary)
- Idempotency key handling
- Path-based authentication token extraction

**[`webhook/entities.py`](../../jvspatial/api/webhook/entities.py:1)** - Webhook data models:
- Webhook request tracking
- Idempotency management
- Webhook configuration storage

**[`webhook/utils.py`](../../jvspatial/api/webhook/utils.py:1)** - Utility functions:
- HMAC signature generation and verification
- Content type detection
- Payload parsing helpers

### 6. Scheduler (Optional)

[`scheduler/`](../../jvspatial/api/scheduler/__init__.py:1) provides optional task scheduling:

**Installation**: `pip install jvspatial[scheduler]`

**Core Components**:
- [`SchedulerService`](../../jvspatial/api/scheduler/scheduler.py:1) - Task scheduling engine
- `@on_schedule` - Decorator for scheduled functions
- [`SchedulerMiddleware`](../../jvspatial/api/scheduler/middleware.py:1) - FastAPI lifecycle integration

```python
from jvspatial.api.scheduler import on_schedule

@on_schedule("every 30 minutes")
async def cleanup_old_data():
    # Cleanup logic
    pass
```

### 7. Exception Handling

**[`exceptions.py`](../../jvspatial/api/exceptions.py:1)** - Standardized exception hierarchy:
- [`JVSpatialAPIException`](../../jvspatial/api/exceptions.py:11) - Base exception class
- [`AuthenticationError`](../../jvspatial/api/exceptions.py:61) - Authentication failures
- [`AuthorizationError`](../../jvspatial/api/exceptions.py:102) - Permission denials
- [`ResourceError`](../../jvspatial/api/exceptions.py:143) - Resource operations
- [`ValidationError`](../../jvspatial/api/exceptions.py:180) - Input validation
- [`StorageError`](../../jvspatial/api/exceptions.py:214) - File storage errors
- [`WebhookError`](../../jvspatial/api/exceptions.py:259) - Webhook processing

**[`error_handlers.py`](../../jvspatial/api/error_handlers.py:1)** - FastAPI exception handlers:
- [`jvspatial_exception_handler()`](../../jvspatial/api/error_handlers.py:17) - Handles JVSpatialAPIException
- [`generic_exception_handler()`](../../jvspatial/api/error_handlers.py:56) - Handles unexpected errors
- [`register_exception_handlers()`](../../jvspatial/api/error_handlers.py:81) - Registers all handlers

All exceptions provide consistent JSON responses with error codes, messages, and optional details.

### 8. Constants and Protocols

**[`constants.py`](../../jvspatial/api/constants.py:1)** - Centralized constants:
- [`APIRoutes`](../../jvspatial/api/constants.py:10) - Route path constants
- [`HTTPMethods`](../../jvspatial/api/constants.py:28) - HTTP method constants
- [`Collections`](../../jvspatial/api/constants.py:40) - Database collection names
- [`LogIcons`](../../jvspatial/api/constants.py:51) - Emoji icons for logging
- [`ErrorMessages`](../../jvspatial/api/constants.py:77) - Standard error messages
- [`Defaults`](../../jvspatial/api/constants.py:112) - Default configuration values

**[`protocols.py`](../../jvspatial/api/protocols.py:1)** - Type protocols for interfaces:
- [`FileStorageProvider`](../../jvspatial/api/protocols.py:12) - File storage interface
- [`ProxyManager`](../../jvspatial/api/protocols.py:84) - URL proxy interface
- [`EndpointRegistry`](../../jvspatial/api/protocols.py:145) - Endpoint registry interface
- [`LifecycleManager`](../../jvspatial/api/protocols.py:202) - Lifecycle management interface
- [`MiddlewareManager`](../../jvspatial/api/protocols.py:256) - Middleware configuration interface
- [`PackageDiscovery`](../../jvspatial/api/protocols.py:309) - Package discovery interface
- [`HealthChecker`](../../jvspatial/api/protocols.py:324) - Health check interface

## Request/Response Flow

### Walker Endpoint Request Flow

1. **Request arrives** → FastAPI routing
2. **Middleware processing** → Authentication, CORS, etc.
3. **Parameter validation** → Pydantic model created from `EndpointField` definitions
4. **Walker instantiation** → Parameters mapped to Walker fields
5. **Endpoint helper injection** → `walker.endpoint` created for semantic responses
6. **Graph traversal** → `walker.spawn(start_node)` executes
7. **Response collection** → Results gathered via `walker.get_report()`
8. **Response formatting** → JSON response with appropriate status code

### Function Endpoint Request Flow

1. **Request arrives** → FastAPI routing
2. **Middleware processing** → Authentication, CORS, etc.
3. **Parameter injection** → Function parameters bound
4. **Endpoint helper injection** → `endpoint` parameter injected
5. **Function execution** → Business logic runs
6. **Response formatting** → `endpoint.success()`, `endpoint.error()`, etc.

### Webhook Request Flow

1. **Request arrives** → Webhook-specific route
2. **Webhook middleware** → HMAC verification, payload parsing, idempotency check
3. **Payload injection** → Webhook data attached to `request.state`
4. **Handler execution** → Function or Walker processes payload
5. **200 OK response** → Always return success (webhook best practice)

## Key Design Patterns

### 1. Context-Based Server Access

Server instances are managed via context variables, enabling:
- Thread-safe server access
- Package-level decorators without explicit server references
- Multiple server instances in testing scenarios

### 2. Service-Oriented Architecture

Each major feature is isolated in a service:
- **Separation of concerns** - Services focus on single responsibilities
- **Testability** - Services can be tested independently
- **Extensibility** - New services can be added without modifying core

### 3. Protocol-Based Interfaces

Type protocols define clear contracts:
- **Flexibility** - Multiple implementations possible
- **Type safety** - Static type checking with mypy
- **Documentation** - Protocols serve as interface documentation

### 4. Decorator-Based Registration

Endpoints are registered via decorators:
- **Clean syntax** - Natural Python idioms
- **Metadata preservation** - Function signatures maintained
- **Dynamic discovery** - Endpoints can be discovered from packages

### 5. Semantic Response Helpers

Response helpers provide semantic methods:
- **Readability** - `endpoint.success()` vs manual status codes
- **Consistency** - Standardized response formats
- **Type safety** - Proper return type hints

## Integration Points

### Database Integration

The Server class integrates with jvspatial's GraphContext:
- Automatic database initialization based on `ServerConfig`
- Support for JSON and MongoDB backends
- Optional explicit GraphContext configuration

```python
server = Server(
    title="My API",
    db_type="mongodb",
    db_connection_string="mongodb://localhost:27017",
    db_database_name="mydb"
)

# Or set explicitly
ctx = GraphContext(database=my_database)
server.set_graph_context(ctx)
```

### File Storage Integration

File storage is optional and configured via `ServerConfig`:
- Local filesystem storage with configurable root directory
- S3-compatible storage with AWS credentials
- Proxy URL generation for temporary file access
- Automatic cleanup and expiration handling

### Scheduler Integration

Scheduler is optional and requires separate installation:
- Integrates with FastAPI lifecycle (startup/shutdown)
- Supports cron-like scheduling syntax
- Thread-based execution separate from request handling
- Automatic task discovery from decorated functions

## API Endpoint Structure

Standard endpoint patterns follow RESTful conventions:

```
/                       - Root endpoint (API info)
/health                 - Health check endpoint
/api/                   - API prefix for user endpoints
  /api/walkers/*        - Walker-based graph operations
  /api/functions/*      - Function-based operations
/storage/               - File storage endpoints (if enabled)
  /storage/upload       - File upload
  /storage/files        - File listing
  /storage/proxy        - Proxy URL generation
/p/{code}              - Proxy URL short links (if enabled)
```

## Best Practices

### 1. Use Semantic Response Methods

```python
# ✅ Good - Semantic and clear
@endpoint("/users/{user_id}")
async def get_user(user_id: str, endpoint):
    user = await User.get(user_id)
    if not user:
        return endpoint.not_found(message="User not found")
    return endpoint.success(data={"user": user.export()})

# ❌ Avoid - Manual status codes
async def get_user(user_id: str):
    user = await User.get(user_id)
    if not user:
        return JSONResponse(status_code=404, content={"error": "Not found"})
    return {"user": user.export()}
```

### 2. Use EndpointField for Parameter Configuration

```python
# ✅ Good - Explicit field configuration
@walker_endpoint("/search")
class SearchWalker(Walker):
    query: str = EndpointField(
        description="Search query",
        examples=["python", "fastapi"],
        min_length=1,
        max_length=100
    )
    limit: int = EndpointField(
        default=10,
        ge=1,
        le=100,
        description="Maximum results"
    )
```

### 3. Leverage Service Isolation

```python
# ✅ Good - Use service methods
server = Server(title="My API")
registry = server._endpoint_registry

# Check if endpoint exists before registering
if not registry.has_walker(MyWalker):
    registry.register_walker(MyWalker, "/process", ["POST"])

# ❌ Avoid - Direct manipulation of internal state
server._walker_registry[MyWalker] = {...}
```

### 4. Handle Errors Consistently

```python
# ✅ Good - Use standardized exceptions
from jvspatial.api.exceptions import ResourceNotFoundError

@endpoint("/items/{item_id}")
async def get_item(item_id: str, endpoint):
    item = await Item.get(item_id)
    if not item:
        raise ResourceNotFoundError(
            message="Item not found",
            details={"item_id": item_id}
        )
    return endpoint.success(data=item.export())
```

### 5. Follow Webhook Best Practices

```python
# ✅ Good - Always return 200 for webhooks
@webhook_endpoint("/webhook/github")
async def github_webhook(payload: dict, endpoint):
    try:
        # Process webhook
        await process_github_event(payload)
        return endpoint.response(content={"status": "processed"})
    except Exception as e:
        # Log error but still return 200
        logger.error(f"Webhook error: {e}")
        return endpoint.response(content={"status": "received", "error": "logged"})
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                         Server                              │
│  ┌───────────┐  ┌──────────────┐  ┌───────────────────┐   │
│  │  Config   │  │  GraphContext│  │  LifecycleManager │   │
│  └───────────┘  └──────────────┘  └───────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
┌───────▼───────┐  ┌──────▼──────┐  ┌───────▼────────┐
│  Endpoint     │  │  Services   │  │  Middleware    │
│  System       │  │  Layer      │  │  Manager       │
├───────────────┤  ├─────────────┤  ├────────────────┤
│ - Router      │  │ - Registry  │  │ - Auth         │
│ - Response    │  │ - Discovery │  │ - CORS         │
│ - Fields      │  │ - File      │  │ - Custom       │
└───────────────┘  │ - Lifecycle │  └────────────────┘
                   └─────────────┘
        │                  │
┌───────▼───────┐  ┌──────▼──────────────────┐
│  Auth System  │  │  Optional Components    │
├───────────────┤  ├─────────────────────────┤
│ - Users       │  │ - Scheduler             │
│ - Sessions    │  │ - Webhooks              │
│ - API Keys    │  │ - File Storage          │
│ - Decorators  │  └─────────────────────────┘
└───────────────┘
```

## Summary

The jvspatial API architecture provides a complete FastAPI integration with:

- **Flexible endpoint system** supporting both walkers and functions
- **Comprehensive authentication** with JWT, API keys, and RBAC
- **Service-oriented design** for maintainability and extensibility
- **Optional components** (scheduler, webhooks, file storage)
- **Type-safe interfaces** via protocols and Pydantic models
- **Consistent error handling** through standardized exceptions
- **Context-based management** for thread-safe server access
- **Semantic response helpers** for clean, readable code

The architecture emphasizes:
- Clean separation of concerns
- Type safety and protocol-based interfaces
- Extensibility through services and middleware
- Developer experience via semantic APIs
- Production readiness with authentication and error handling