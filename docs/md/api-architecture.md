# jvspatial API Architecture

The jvspatial API module provides a comprehensive FastAPI integration layer with authentication, webhooks, scheduling, and file storage capabilities. This document outlines the architecture and key components of the API system.

## Core Components

### Server

The `Server` class serves as the central orchestrator for the API, managing:

- FastAPI application lifecycle
- Endpoint registration
- Middleware configuration
- Authentication
- File storage
- Health checks

```python
from jvspatial.api import Server

server = Server(
    title="My API",
    description="API Description",
    auth_enabled=True
)
```

### Endpoint Registry

The `EndpointRegistry` service manages the registration and tracking of API endpoints:

- Walker endpoints (for graph traversal)
- Function endpoints (for direct API functions)
- Custom routes
- Dynamic registration

```python
from jvspatial.api.services import EndpointRegistryService

# Registry manages endpoints internally
registry = EndpointRegistryService()

# Register a walker
registry.register_walker(
    MyWalker,
    "/process",
    methods=["POST"],
    tags=["processing"]
)
```

### Middleware Management

The `MiddlewareManager` handles configuration and application of middleware:

- CORS configuration
- Authentication middleware
- Custom middleware chains
- Request/response processing

```python
from jvspatial.api.services import MiddlewareManager

middleware = MiddlewareManager()
middleware.add_cors(
    origins=["http://localhost:3000"],
    methods=["GET", "POST"]
)
```

### File Storage Integration

File storage capabilities are provided through the `FileStorageProvider` protocol:

- Local filesystem storage
- S3-compatible storage
- File URL generation
- File serving for HTTP responses

```python
from jvspatial.api.protocols import FileStorageProvider

class S3StorageProvider(FileStorageProvider):
    async def save_file(self, path: str, content: bytes) -> None:
        # Implementation for S3 storage
        ...
```

### Authentication System

Authentication is handled through multiple components:

- JWT token authentication
- API key authentication
- Session management
- Role-based access control (RBAC)

```python
from jvspatial.api.auth.decorators import auth_endpoint

@auth_endpoint("/protected")
async def protected_route():
    return {"message": "Authenticated access only"}
```

### Webhook System

The webhook system provides:

- HMAC signature verification
- Request validation
- Idempotency handling
- Async webhook processing

```python
from jvspatial.api.webhook.decorators import webhook_endpoint

@webhook_endpoint("/webhook")
async def handle_webhook(payload: dict):
    # Process webhook payload
    ...
```

## Endpoint Types

### Walker Endpoints

Walker endpoints enable graph traversal through HTTP:

```python
from jvspatial.core.entities import Walker
from jvspatial.api.endpoint import EndpointField

@server.walker("/graph/traverse")
class GraphWalker(Walker):
    query: str = EndpointField(description="Search query")
    limit: int = EndpointField(default=10, description="Result limit")
```

### Function Endpoints

Direct function endpoints for simple API routes:

```python
@server.route("/hello/{name}")
async def hello(name: str):
    return {"message": f"Hello, {name}!"}
```

### Custom Routes

Custom routes for specialized handling:

```python
@server.route("/custom", methods=["POST"])
async def custom_handler(request: Request):
    # Custom request handling
    ...
```

## Service Protocols

The API module defines several protocols that specify contracts for key services:

### EndpointRegistry Protocol

```python
from jvspatial.api.protocols import EndpointRegistry

class EndpointRegistry(Protocol):
    def register_walker(self, walker_class: type, path: str, ...) -> Any: ...
    def unregister_walker(self, walker_class: type) -> bool: ...
    def list_walkers(self) -> Dict[str, Dict[str, Any]]: ...
```

### MiddlewareManager Protocol

```python
from jvspatial.api.protocols import MiddlewareManager

class MiddlewareManager(Protocol):
    def add_cors(self, origins: Optional[List[str]] = None, ...) -> None: ...
    def add_custom(self, middleware_type: str, func: Callable) -> None: ...
    def apply_to_app(self, app: FastAPI) -> None: ...
```

### FileStorageProvider Protocol

```python
from jvspatial.api.protocols import FileStorageProvider

class FileStorageProvider(Protocol):
    async def save_file(self, path: str, content: bytes) -> None: ...
    async def get_file(self, path: str) -> bytes: ...
    async def get_file_url(self, path: str) -> str: ...
```

## Configuration

The API module can be configured through environment variables or programmatically:

```python
from jvspatial.api import Server, ServerConfig

config = ServerConfig(
    title="My API",
    description="API Description",
    version="1.0.0",
    debug=True,
    auth_enabled=True,
    cors_enabled=True,
    cors_origins=["http://localhost:3000"],
    file_storage_enabled=True
)

server = Server(config=config)
```

## Error Handling

The API provides standardized error handling through exception handlers:

```python
from jvspatial.api.exceptions import JVSpatialAPIException

class CustomError(JVSpatialAPIException):
    status_code = 400
    error_code = "custom_error"
```

Error responses are consistently formatted:

```json
{
    "error_code": "custom_error",
    "message": "Error description",
    "details": {
        "additional": "error context"
    }
}
```

## Lifecycle Management

Server lifecycle is managed through startup and shutdown hooks:

```python
@server.on_startup
async def startup():
    # Initialize resources
    ...

@server.on_shutdown
async def shutdown():
    # Cleanup resources
    ...
```

## Extensibility

The API architecture is designed for extensibility:

- Custom middleware
- Storage provider implementations
- Authentication schemes
- Error handlers
- Request/response processors