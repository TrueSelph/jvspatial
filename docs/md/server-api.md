# jvspatial Server API

The jvspatial Server class provides a powerful, object-oriented abstraction for building FastAPI applications with spatial data management capabilities. It simplifies the process of creating robust APIs while leveraging the full power of the jvspatial framework.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Server Class Overview](#server-class-overview)
3. [Configuration](#configuration)
4. [Walker Endpoints](#walker-endpoints)
5. [Dynamic Registration](#dynamic-registration)
6. [Package Development](#package-development)
7. [Custom Routes](#custom-routes)
8. [Middleware](#middleware)
9. [Lifecycle Hooks](#lifecycle-hooks)
10. [Exception Handling](#exception-handling)
11. [Database Configuration](#database-configuration)
12. [Examples](#examples)
13. [API Reference](#api-reference)

## 🎯 **Standard Implementation Examples**

**We strongly recommend starting with these standard examples** as they demonstrate best practices and complete patterns:

### **Authenticated API Example** (Full CRUD with Auth)
📁 **File**: [`examples/api/authenticated_endpoints_example.py`](../../examples/api/authenticated_endpoints_example.py)

**Complete example** showing:
- Server setup with authentication (`auth_enabled=True`)
- CRUD operations (Create, Read, Update, Delete)
- Entity-centric database operations
- Pagination with `ObjectPager`
- Permission-based access control
- Response schemas with examples
- Automatic auth endpoints registration

### **Unauthenticated API Example** (Public Read-Only)
📁 **File**: [`examples/api/unauthenticated_endpoints_example.py`](../../examples/api/unauthenticated_endpoints_example.py)

**Complete example** showing:
- Server setup without authentication (`auth_enabled=False`)
- Public read-only endpoints
- Pagination and filtering
- No authentication endpoints (login/register/logout are NOT registered)

**Use these examples as templates** when building your custom jvspatial APIs!

### When to Use Which Example

- **Use Authenticated API Example** when:
  - You need user authentication
  - You need CRUD operations
  - You need access control (permissions/roles)
  - You're building a private or protected API

- **Use Unauthenticated API Example** when:
  - You're building a public API
  - You only need read operations
  - You're serving public content
  - Authentication is handled externally or not needed

---

## Quick Start

Here's a minimal example to get started quickly. For production-ready implementations, see the [standard examples](#-standard-implementation-examples) above.

```python
from jvspatial.api import Server, endpoint
from jvspatial.api import Server, endpoint
from jvspatial.api.decorators import EndpointField
from jvspatial.core import Walker, Node, on_visit

# Create a server instance
server = Server(
    title="My Spatial API",
    description="A spatial data management API",
    version="1.0.0",
    debug=True,
    db_type="json",
    db_path="./jvdb",
    auth_enabled=False  # Set to True to enable authentication
)

# Define a Walker endpoint
@endpoint("/process", methods=["POST"])
class ProcessData(Walker):
    data: str = EndpointField(description="Data to process")

    @on_visit(Node)
    async def process(self, here):
        self.response["result"] = self.data.upper()

# Run the server
if __name__ == "__main__":
    server.run()
```

## Server Class Overview

The `Server` class is the main entry point for creating jvspatial-powered APIs. It provides:

- **Automatic FastAPI setup** with sensible defaults
- **Database integration** with automatic initialization
- **Walker endpoint registration** using decorators
- **Lifecycle management** with startup/shutdown hooks
- **Middleware support** for request/response processing
- **Configuration management** through ServerConfig
- **Exception handling** with custom handlers

### Key Features

- **Zero-configuration database setup** - just specify the type
- **Declarative API definition** using decorators
- **Automatic OpenAPI documentation** generation
- **Health checks** and monitoring endpoints
- **CORS support** with configurable policies
- **Development-friendly** with hot reload support

## Configuration

### Basic Configuration

```python
from jvspatial.api.server import Server

server = Server(
    title="My API",
    description="API description",
    version="1.0.0",
    host="0.0.0.0",
    port=8000,
    debug=False
)
```

### ServerConfig Model

The `ServerConfig` model provides comprehensive configuration options:

```python
from jvspatial.api.server import Server, ServerConfig

config = ServerConfig(
    # API Configuration
    title="Spatial Management API",
    description="Advanced spatial data management",
    version="2.0.0",
    debug=True,

    # Server Configuration
    host="127.0.0.1",
    port=8080,
    docs_url="/docs",
    redoc_url="/redoc",

    # CORS Configuration
    cors_enabled=True,
    cors_origins=["https://myapp.com"],
    cors_methods=["GET", "POST"],
    cors_headers=["*"],

    # Database Configuration
    db_type="json",
    db_path="jvdb/production",

    # Logging
    log_level="info"
)

server = Server(config=config)
```

### Configuration Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `title` | str | "jvspatial API" | API title |
| `description` | str | "API built with jvspatial framework" | API description |
| `version` | str | "1.0.0" | API version |
| `debug` | bool | False | Enable debug mode |
| `host` | str | "0.0.0.0" | Server host |
| `port` | int | 8000 | Server port |
| `docs_url` | str | "/docs" | OpenAPI docs URL |
| `redoc_url` | str | "/redoc" | ReDoc URL |
| `cors_enabled` | bool | True | Enable CORS |
| `cors_origins` | List[str] | ["*"] | Allowed origins |
| `cors_methods` | List[str] | ["*"] | Allowed methods |
| `cors_headers` | List[str] | ["*"] | Allowed headers |
| `db_type` | str | None | Database type |
| `db_path` | str | None | Database path |
| `log_level` | str | "info" | Logging level |

## Walker Endpoints

Walker endpoints are the primary way to define business logic in jvspatial APIs. They combine the power of jvspatial's graph traversal with FastAPI's parameter validation.

### Basic Walker

```python
@endpoint("/tasks/create")
class CreateTask(Walker):
ame: str = EndpointField(description="User name", min_length=2)
    email: str = EndpointField(description="User email")

    @on_visit(Root)
    async def create_user(self, here):
        user = await User.create(name=self.name, email=self.email)
        await here.connect(user)
        self.response["user_id"] = user.id
```

### Advanced Walker with Field Groups

```python
@endpoint("/locations/search")
class SearchLocations(Walker):
    # Search center coordinates (grouped)
    latitude: float = EndpointField(
        endpoint_group="center",
        description="Search center latitude",
        ge=-90.0, le=90.0
    )
    longitude: float = EndpointField(
        endpoint_group="center",
        description="Search center longitude",
        ge=-180.0, le=180.0
    )

    # Search parameters (grouped)
    radius_km: float = EndpointField(
        endpoint_group="search",
        default=10.0,
        description="Search radius",
        gt=0.0
    )
    location_type: Optional[str] = EndpointField(
        endpoint_group="search",
        default=None,
        description="Filter by type"
    )

    @on_visit(Root)
    async def search(self, here):
        # Implementation here
        pass
```

### Walker Methods

Walker endpoints support all standard HTTP methods:

```python
# POST (default)
@endpoint("/data", methods=["POST"])
class ProcessData(Walker):
    pass

# GET endpoint
@endpoint("/status", methods=["GET"])
class GetStatus(Walker):
    pass

# Multiple methods
@endpoint("/resource", methods=["GET", "POST", "PUT"])
class ResourceEndpoint(Walker):
    pass
```

## Dynamic Registration

**NEW**: The jvspatial Server class now supports dynamic endpoint registration, allowing walkers to be registered and discovered at runtime. This enables package-based development and hot-reloading of endpoints without server restart.

### Runtime Registration

Register endpoints programmatically while the server is running:

```python
from jvspatial.api import Server, endpoint

server = Server(title="Dynamic API", db_type="json", db_path="./jvdb")

# Start server
server.run()  # In production, this would be running

# Later, in another module or after package installation:
from jvspatial.api import endpoint
from jvspatial.api.decorators import EndpointField

@endpoint("/new-endpoint", methods=["POST"])
class NewWalker(Walker):
    data: str = EndpointField(description="Data to process")

    @on_visit(Root)
    async def process(self, here):
        self.response["result"] = self.data

# The @endpoint decorator automatically registers with the current server
```

### Shared Server Instances

Use shared server instances across modules:

```python
# main.py
from jvspatial.api import Server

server = Server(title="Shared API", db_type="json", db_path="./jvdb")  # Becomes default server

# other_module.py
from jvspatial.api import endpoint

@endpoint("/module-endpoint", methods=["POST"])
class ModuleWalker(Walker):
    # Walker implementation
    pass
```

### Server State Management

The server tracks its runtime state for dynamic operations:

- `server._is_running` - Whether the server is currently running
- `server._registered_walker_classes` - Set of registered walker classes
- `server._package_discovery_enabled` - Package discovery status
- `server._discovery_patterns` - Package name patterns for discovery

## Package Development

Develop installable walker packages that can be discovered at runtime:

### Package Structure

```
my_walkers/
    __init__.py          # Export walkers
    walkers.py           # Walker implementations
    models.py            # Node models (optional)
    setup.py             # Package configuration
```

### Walker Package Example

```python
# my_walkers/walkers.py
from jvspatial.api import register_walker_to_default
from jvspatial.api.endpoint.router import EndpointField
from jvspatial.core import Walker, Root, on_visit

@register_walker_to_default("/my-package/process")
class MyPackageWalker(Walker):
    """Walker from installable package."""

    input_data: str = EndpointField(
        description="Data to process",
        examples=["hello", "world"]
    )

    @on_visit(Root)
    async def process_data(self, here):
        # Package-specific processing logic
        self.response = {
            "processed": self.input_data.upper(),
            "package": "my_walkers",
            "version": "1.0.0"
        }
```

```python
# my_walkers/__init__.py
from .walkers import MyPackageWalker

__all__ = ["MyPackageWalker"]
__version__ = "1.0.0"
```

### Package Installation and Discovery

1. **Install the package**:
   ```bash
   pip install my_walkers
   ```

2. **Server discovers automatically** (if patterns match):
   ```python
   server.enable_package_discovery(patterns=['*_walkers'])
   # my_walkers will be discovered and registered
   ```

3. **Manual discovery trigger**:
   ```python
   # Force discovery of new packages
   count = server.discover_and_register_packages()
   ```

## Enhanced Endpoint Unregistration

**NEW**: The jvspatial Server class now provides comprehensive endpoint unregistration capabilities that properly handle both walker classes and function endpoints, with automatic FastAPI app rebuilding when the server is running.

### Enhanced Walker Removal

The `unregister_walker_class()` method now properly removes walker endpoints and triggers FastAPI app rebuilding:

```python
# Remove a specific walker class
success = server.unregister_walker_class(MyWalker)
if success:
    print("Walker removed successfully")
    # FastAPI app is automatically rebuilt if server is running
else:
    print("Failed to remove walker")

# Remove all walkers from a specific path
removed_walkers = server.unregister_walker_endpoint("/my-endpoint")
print(f"Removed {len(removed_walkers)} walkers")
```

### Function Endpoint Removal

**NEW**: Remove function endpoints registered with `@server.route()` or `@endpoint`:

```python
# Function endpoint
@endpoint("/status", methods=["GET"])
def get_status():
    return {"status": "ok"}

# Later, remove the function endpoint
success = await server.unregister_endpoint(get_status)
if success:
    print("Function endpoint removed")

# Remove by path
success = server.unregister_endpoint("/status")
if success:
    print("Endpoint at /status removed")

# Remove package-style function endpoints
@endpoint("/package-function")
def package_func():
    return {"message": "Package function"}

# Remove using current server
from jvspatial.api import get_current_server
current_server = get_current_server()
if current_server:
    success = await current_server.unregister_endpoint(package_func)
```

### Comprehensive Path-Based Removal

**NEW**: Remove all endpoints (both walkers and functions) from a specific path:

```python
# Remove everything at a path
removed_count = server.unregister_endpoint_by_path("/api/admin")
print(f"Removed {removed_count} endpoints from /api/admin")

# This removes:
# - All walker classes registered at that path
# - All function endpoints at that path
# - Triggers app rebuild if server is running
```

### Enhanced Endpoint Listing

**NEW**: Comprehensive endpoint listing methods:

```python
# List all walker endpoints
walker_info = server.list_walker_endpoints()
for name, info in walker_info.items():
    print(f"Walker {name}: {info['path']} {info['methods']}")

# List all function endpoints
function_info = server.list_function_endpoints()
for name, info in function_info.items():
    print(f"Function {name}: {info['path']} {info['methods']}")

# List all endpoints (walkers and functions)
all_endpoints = server.list_all_endpoints()
print(f"Total: {len(all_endpoints['walkers'])} walkers, {len(all_endpoints['functions'])} functions")
```

### Runtime App Rebuilding

When endpoints are removed from a running server, the FastAPI app is automatically rebuilt:

```python
# Start server
server.run(host="0.0.0.0", port=8000)

# In another context (e.g., admin endpoint, background task)
server.unregister_walker_class(MyWalker)  # App rebuilds automatically
server.unregister_endpoint("/deprecated")  # App rebuilds automatically
```

**Key Benefits:**
- **Complete removal**: Endpoints are truly inaccessible after removal
- **Automatic rebuilding**: FastAPI app rebuilds when server is running
- **Flexible removal**: By class, function reference, or path
- **Comprehensive tracking**: All endpoint types are properly tracked and removed

**Performance Note**: App rebuilding has a performance cost but ensures proper endpoint removal. Multiple removals are processed individually but could be batched in future versions.

### Testing Enhanced Unregistration

The enhanced unregistration functionality includes comprehensive tests located in `tests/api/`:

```bash
# Run basic unregistration tests
python -m pytest tests/api/test_unregister.py -v

# Run comprehensive unregistration tests
python -m pytest tests/api/test_unregister_comprehensive.py -v

# Run all API tests
python -m pytest tests/api/ -v
```

**Test Coverage:**
- Static server unregistration
- Running server simulation with app rebuilding
- Package-style endpoint support
- Error condition handling
- Path-based comprehensive removal
- Function endpoint removal by reference and path
- Enhanced endpoint listing methods

**Live Demonstration:**

See `examples/dynamic_endpoint_removal.py` for a live demonstration of endpoint removal with a running server.

### Function Endpoints

Register regular functions as endpoints using `@endpoint`:

```python
from jvspatial.api import endpoint

@endpoint("/users/count", methods=["GET"])
async def get_user_count():
    """Simple function endpoint - no Walker needed."""
    users = await User.all()
    return {"count": len(users)}

@endpoint("/users/{user_id}", methods=["GET"])
async def get_user(user_id: str):
    """Function endpoint with path parameters."""
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user.export()}

# Function endpoints support all FastAPI features
@endpoint("/upload", methods=["POST"], tags=["files"])
async def upload_file(file: UploadFile = File(...)):
    """Function endpoint with file upload."""
    return {"filename": file.filename, "size": len(await file.read())}
```

### Global Server Functions

Access server instances from anywhere:

```python
from jvspatial.api import endpoint, get_current_server

# Get the current server from context
server = get_current_server()
if server:
    print(f"Current server: {server.config.title}")

# Endpoints automatically register with the current server
@endpoint("/global-function", methods=["GET"])
async def global_function():
    return {"message": "Hello from global function"}

@endpoint("/global-walker", methods=["POST"])
class GlobalWalker(Walker):
    pass
```

## Custom Routes

For simple endpoints that don't require graph traversal, use custom routes:

```python
@endpoint("/health", methods=["GET"])
async def health_check():
    return {"status": "healthy"}

@endpoint("/stats", methods=["GET"])
async def get_stats():
    users = await User.all()
    return {"user_count": len(users)}

# Route with parameters
@endpoint("/users/{user_id}", methods=["GET"])
async def get_user(user_id: str):
    user = await User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user.export()}
```

## Middleware

Add custom middleware for request/response processing:

```python
@server.middleware("http")
async def log_requests(request, call_next):
    start_time = datetime.now()
    response = await call_next(request)
    duration = (datetime.now() - start_time).total_seconds()
    print(f"{request.method} {request.url} - {duration:.3f}s")
    return response

@server.middleware("http")
async def add_security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    return response
```

## Lifecycle Hooks

Manage application startup and shutdown with hooks:

### Startup Hooks

```python
@server.on_startup
async def initialize_database():
    """Initialize database with sample data."""
    print("Setting up database...")
    root = await Root.get()  # type: ignore
    if not root:
        root = await Root.create()
    print("Database ready!")

@server.on_startup
def setup_logging():
    """Configure logging (synchronous function)."""
    logging.basicConfig(level=logging.INFO)
    print("Logging configured")
```

### Shutdown Hooks

```python
@server.on_shutdown
async def cleanup():
    """Cleanup resources on shutdown."""
    print("Cleaning up...")

@server.on_shutdown
def save_metrics():
    """Save metrics (synchronous function)."""
    print("Saving metrics...")
```

## Exception Handling

Add custom exception handlers:

```python
@server.exception_handler(404)
async def not_found_handler(request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "error": "Resource not found",
            "path": str(request.url)
        }
    )

@server.exception_handler(ValueError)
async def value_error_handler(request, exc):
    return JSONResponse(
        status_code=400,
        content={"error": str(exc)}
    )

# Handle custom exceptions
class BusinessLogicError(Exception):
    pass

@server.exception_handler(BusinessLogicError)
async def business_error_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={"error": "Business logic error", "detail": str(exc)}
    )
```

## Serverless Deployment (AWS Lambda)

jvspatial supports serverless deployment to AWS Lambda using Mangum, an ASGI adapter for serverless platforms. The Lambda handler can be automatically configured when creating the Server instance, making deployment transparent and straightforward.

### Installation

Install Mangum for serverless support:

```bash
pip install mangum>=0.17.0
# Or install optional dependencies:
pip install jvspatial[serverless]
```

### Automatic Serverless Setup (Recommended)

Enable serverless mode when creating the Server instance. The Lambda handler will be automatically created and configured:

```python
from jvspatial.api import Server, endpoint

# Create server with serverless mode enabled
server = Server(
    title="Lambda API",
    description="jvspatial API on AWS Lambda",
    serverless_mode=True,  # Enable automatic handler setup
    serverless_lifespan="auto",  # Enable startup/shutdown events
    # serverless_api_gateway_base_path="/prod",  # Optional: API Gateway base path
    db_type="json",
    db_path="/tmp/jvdb",  # Lambda /tmp directory (ephemeral)
)

@endpoint("/hello", methods=["GET"])
async def hello():
    return {"message": "Hello from Lambda!"}

# Handler is automatically created - access it via property or method
handler = server.lambda_handler  # Direct property access
# Or: handler = server.get_lambda_handler()  # Method access
```

### Manual Handler Creation

You can also create the handler manually if you prefer more control:

```python
from jvspatial.api import Server, endpoint

server = Server(title="My Lambda API")

@endpoint("/products", methods=["GET"])
async def list_products():
    products = await ProductNode.find()
    return {"products": [p.export() for p in products]}

# Create handler manually with custom configuration
handler = server.get_lambda_handler(
    lifespan="auto",  # Enable startup/shutdown events
    api_gateway_base_path="/prod",  # If using API Gateway base path
)
```

### Serverless Configuration Options

When using `serverless_mode=True`, you can configure the handler via ServerConfig:

- `serverless_mode`: Enable automatic Lambda handler creation (default: `False`)
- `serverless_lifespan`: Mangum lifespan mode - `"auto"`, `"on"`, or `"off"` (default: `"auto"`)
- `serverless_api_gateway_base_path`: Optional API Gateway base path (e.g., `"/prod"`, `"/v1"`)

### Lambda Deployment Steps

1. **Package your application**:
   ```bash
   # Create deployment package
   pip install -r requirements.txt -t .
   zip -r lambda_function.zip .
   ```

2. **Set Lambda handler**: Set the handler to your module and handler variable:
   - Handler: `lambda_example.handler` (if your file is `lambda_example.py`)

3. **Configure API Gateway**: Set up an API Gateway trigger for your Lambda function

4. **Environment Variables**: Configure database and other settings via Lambda environment variables:
   - `JVSPATIAL_DB_TYPE`: Database type (e.g., "dynamodb", "json", "mongodb")
   - **For DynamoDB** (recommended):
     - `JVSPATIAL_DYNAMODB_TABLE_NAME`: DynamoDB table name (default: "jvspatial")
     - `JVSPATIAL_DYNAMODB_REGION`: AWS region (default: "us-east-1")
     - `AWS_ACCESS_KEY_ID`: AWS access key (or use IAM role)
     - `AWS_SECRET_ACCESS_KEY`: AWS secret key (or use IAM role)
   - **For JSON** (ephemeral):
     - `JVSPATIAL_DB_PATH`: Database path (use `/tmp/jvdb` for Lambda)
   - **For MongoDB**:
     - `JVSPATIAL_DB_CONNECTION_STRING`: MongoDB connection string

### Lambda-Specific Considerations

**Database Configuration**:
- **DynamoDB (Recommended)**: Native AWS service, perfect for Lambda deployments
  ```python
  server = Server(
      serverless_mode=True,
      db_type="dynamodb",
      dynamodb_table_name="myapp",
      dynamodb_region="us-east-1",
  )
  ```
- **JSON**: Use `/tmp/jvdb` for ephemeral storage (data lost on cold start)
- **MongoDB**: Use connection string in environment variables for persistent storage

**Cold Starts**:
- Lifespan events (startup/shutdown) are supported via Mangum
- Consider using provisioned concurrency for production workloads
- Keep dependencies minimal to reduce cold start time

**Example Lambda Configuration**:
```python
import os
from jvspatial.api import Server, endpoint

# Configure from environment variables with serverless mode enabled
server = Server(
    title="Lambda API",
    serverless_mode=True,  # Automatic handler setup
    serverless_lifespan="auto",
    # Use DynamoDB for persistent storage (recommended)
    db_type=os.getenv("JVSPATIAL_DB_TYPE", "dynamodb"),
    dynamodb_table_name=os.getenv("JVSPATIAL_DYNAMODB_TABLE_NAME", "jvspatial"),
    dynamodb_region=os.getenv("JVSPATIAL_DYNAMODB_REGION", "us-east-1"),
    # Or use JSON for ephemeral storage
    # db_type=os.getenv("JVSPATIAL_DB_TYPE", "json"),
    # db_path=os.getenv("JVSPATIAL_DB_PATH", "/tmp/jvdb"),
)

@endpoint("/health", methods=["GET"])
async def health():
    return {"status": "healthy", "environment": "lambda"}

# Handler is automatically available
handler = server.lambda_handler
```

### Complete Example

See the complete Lambda deployment example:
📁 **File**: [`examples/api/lambda_example.py`](../../examples/api/lambda_example.py)

This example demonstrates:
- Full Lambda handler setup
- Database configuration for Lambda
- Multiple endpoint types
- Local testing vs. Lambda deployment

## Database Configuration

### JSON Database

```python
server.configure_database("json", path="jvdb/my_app")

# Or during initialization
server = Server(db_type="json", db_path="jvdb/my_app")
```

### MongoDB Database

```python
server.configure_database(
    "mongodb",
    uri="mongodb://localhost:27017",
    database="my_spatial_db"
)

# Or during initialization
server = Server(
    db_type="mongodb",
    mongodb_uri="mongodb://localhost:27017",
    mongodb_database="my_spatial_db"
)
```

### Environment Variables

The server automatically sets these environment variables:

- `JVSPATIAL_DB_TYPE` - Database type
- `JVSPATIAL_JSONDB_PATH` - JSON database path
- `JVSPATIAL_SQLITE_PATH` - SQLite database file path
- `JVSPATIAL_MONGODB_URI` - MongoDB connection URI
- `JVSPATIAL_MONGODB_DATABASE` - MongoDB database name

## Examples

### Simple CRUD API

```python
from jvspatial.api.server import create_server
from jvspatial.core import Node, Root, Walker, on_visit
from jvspatial.api.endpoint.router import EndpointField

server = create_server(title="CRUD API", version="1.0.0")

class Item(Node):
    name: str
    description: str
    price: float

@endpoint("/items/create", methods=["POST"])
class CreateItem(Walker):
    name: str = EndpointField(min_length=1, max_length=100)
    description: str = EndpointField(default="")
    price: float = EndpointField(gt=0.0)

    @on_visit(Root)
    async def create_item(self, here):
        item = await Item.create(
            name=self.name,
            description=self.description,
            price=self.price
        )
        await here.connect(item)
        self.response = {"item_id": item.id, "status": "created"}

@endpoint("/items", methods=["GET"])
async def list_items():
    items = await Item.all()
    return {"items": [item.export() for item in items]}

if __name__ == "__main__":
    server.run()
```

### Spatial Data API

```python
from jvspatial.api.server import create_server
from jvspatial.core import Node, Root, Walker, on_visit
import math

server = create_server(title="Spatial API", db_type="json")

class Location(Node):
    name: str
    latitude: float
    longitude: float

def calculate_distance(lat1, lon1, lat2, lon2):
    # Haversine formula implementation
    R = 6371
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

@endpoint("/locations/nearby", methods=["POST"])
class FindNearbyLocations(Walker):
    latitude: float = EndpointField(ge=-90.0, le=90.0)
    longitude: float = EndpointField(ge=-180.0, le=180.0)
    radius_km: float = EndpointField(default=10.0, gt=0.0)

    @on_visit(Root)
    async def find_nearby(self, here):
        all_locations = await Location.all()
        nearby = []

        for loc in all_locations:
            distance = calculate_distance(
                self.latitude, self.longitude,
                loc.latitude, loc.longitude
            )
            if distance <= self.radius_km:
                nearby.append({
                    "id": loc.id,
                    "name": loc.name,
                    "distance_km": round(distance, 2)
                })

        nearby.sort(key=lambda x: x["distance_km"])
        self.response = {"locations": nearby}

if __name__ == "__main__":
    server.run()
```

## API Reference

### Server Class

```python
class Server:
    def __init__(
        self,
        config: Optional[Union[ServerConfig, Dict[str, Any]]] = None,
        **kwargs: Any
    )
```

#### Methods

**Core Registration Methods:**

- `walker(path: str, methods: List[str] = None, **kwargs) -> Decorator`
  - Register a Walker class as an API endpoint

- `route(path: str, methods: List[str] = None, **kwargs) -> Decorator`
  - Register a custom route handler

**Dynamic Registration Methods:**

- `register_walker_class(walker_class: Type[Walker], path: str, methods: List[str] = None, **kwargs)`
  - Programmatically register a Walker class (supports runtime registration)

- `discover_and_register_packages(package_patterns: List[str] = None) -> int`
  - Discover and register walker endpoints from installed packages

- `refresh_endpoints() -> int`
  - Refresh and discover new endpoints from packages

- `enable_package_discovery(enabled: bool = True, patterns: List[str] = None)`
  - Enable or disable automatic package discovery

**Enhanced Endpoint Unregistration Methods:**

- `register_walker_class(walker_class: Type[Walker], path: str, methods: Optional[List[str]] = None, **kwargs) -> None`
  - Programmatically register a walker class as an endpoint

- `async unregister_walker_class(walker_class: Type[Walker]) -> bool`
  - Remove a walker class and its endpoint from the server

- `async unregister_walker_endpoint(path: str) -> List[Type[Walker]]`
  - Remove all walkers registered to a specific path

- `async unregister_endpoint(endpoint: Union[str, Callable]) -> bool`
  - Remove a function endpoint by path string or function reference

- `async unregister_endpoint_by_path(path: str) -> int`
  - Remove all endpoints (both walkers and functions) from a specific path

**Endpoint Listing Methods:**

- `list_walker_endpoints() -> Dict[str, Dict[str, Any]]`
  - Get information about all registered walkers

- `async list_function_endpoints() -> Dict[str, Dict[str, Any]]`
  - Get information about all registered function endpoints

- `list_all_endpoints() -> Dict[str, Any]`
  - Get comprehensive information about all endpoints (walkers and functions)

- `enable_package_discovery(enabled: bool = True, patterns: Optional[List[str]] = None) -> None`
  - Enable or disable automatic package discovery

- `refresh_endpoints() -> int`
  - Refresh and discover new endpoints from packages (server must be running)

**Server Management Methods:**

- `middleware(middleware_type: str = "http") -> Decorator`
  - Add middleware to the application

- `exception_handler(exc_class_or_status_code) -> Decorator`
  - Add exception handler

- `on_startup(func: Callable) -> Callable`
  - Register startup task

- `on_shutdown(func: Callable) -> Callable`
  - Register shutdown task

**Server Execution Methods:**

- `run(host: str = None, port: int = None, reload: bool = None, **kwargs)`
  - Run the server using uvicorn

- `run_async(host: str = None, port: int = None, **kwargs)`
  - Run the server asynchronously

- `get_app() -> FastAPI`
  - Get the FastAPI application instance

**Configuration Methods:**

- `configure_database(db_type: str, **db_config)`
  - Configure database settings

- `add_node_type(node_class: Type[Node])`
  - Register a Node type (for documentation)

### Helper Functions

```python
from jvspatial.api import create_server, get_current_server

# Create a Server instance with common configuration
def create_server(
    title: str = "jvspatial API",
    description: str = "API built with jvspatial framework",
    version: str = "1.0.0",
    **config_kwargs: Any
) -> Server
```
Creates a Server instance and automatically sets it as the current server.

```python
# Get the current server from context
def get_current_server() -> Optional[Server]
```
The current server is automatically set when a Server is instantiated. The `@endpoint` decorator uses the current server for registration.

### Built-in Endpoints

Every server automatically includes:

- `GET /` - API information
- `GET /health` - Health check endpoint
- `POST /api/*` - Walker endpoints (under /api prefix)

### Default Middleware

- **CORS middleware** - Configurable cross-origin support
- **Exception handling** - Global exception handler with optional debug info

### Environment Variables

The Server class respects these environment variables:

- `JVSPATIAL_DB_TYPE` - Database type override
- `JVSPATIAL_JSONDB_PATH` - JSON database path
- `JVSPATIAL_SQLITE_PATH` - SQLite database file path
- `JVSPATIAL_MONGODB_URI` - MongoDB connection string
- `JVSPATIAL_MONGODB_DATABASE` - MongoDB database name

## Best Practices

### 1. Use Configuration Objects

```python
# Good
config = ServerConfig(
    title="My API",
    debug=False,
    db_type="mongodb",
    cors_origins=["https://myapp.com"]
)
server = Server(config=config)

# Also good - using create_server helper
from jvspatial.api import create_server

server = create_server(
    title="My API",
    debug=False,
    db_type="mongodb",
    db_path="./jvdb",
    cors_origins=["https://myapp.com"]
)
```

### 2. Organize Walker Endpoints

```python
# Group related endpoints
@endpoint("/users/create", methods=["POST"])
class CreateUser(Walker):
    pass

@endpoint("/users/update", methods=["PUT"])
class UpdateUser(Walker):
    pass

@endpoint("/users/search", methods=["POST"])
class SearchUsers(Walker):
    pass
```

### 3. Use EndpointField for Validation

```python
# Good - with validation and documentation
@endpoint("/items/create", methods=["POST"])
class CreateItem(Walker):
    name: str = EndpointField(
        description="Item name",
        min_length=1,
        max_length=100,
        examples=["Widget", "Gadget"]
    )
    price: float = EndpointField(
        description="Item price in USD",
        gt=0.0,
        examples=[9.99, 149.99]
    )
```

### 4. Handle Errors Gracefully

```python
@server.walker("/process")
class ProcessData(Walker):
    data: str

    @on_visit(Root)
    async def process(self, here):
        try:
            # Process data
            result = complex_processing(self.data)
            self.response = {"result": result}
        except ValueError as e:
            self.response = {
                "status": "error",
                "error": f"Invalid data: {str(e)}"
            }
        except Exception as e:
            self.response = {
                "status": "error",
                "error": "Processing failed"
            }
```

### 5. Use Startup Hooks for Initialization

```python
@server.on_startup
async def initialize_data():
    """Initialize database with required data."""
    # Check if admin user exists
    admin = await User.get("admin")
    if not admin:
        admin = await User.create(
            id="admin",
            name="Administrator",
            role="admin"
        )
        print("Created admin user")
```

## Server Class Benefits

The `Server` class provides a cleaner, more maintainable approach for building jvspatial APIs:

```python
from jvspatial.api import Server, endpoint

server = Server(
    title="My API",
    db_type="json",
    db_path="./jvdb"
)

@endpoint("/process", methods=["POST"])
class ProcessData(Walker):
    # Walker implementation
    pass

if __name__ == "__main__":
    server.run()
```

**Key Benefits:**
- Automatic database setup and context management
- Built-in authentication and middleware support
- Automatic OpenAPI documentation generation
- Lifecycle management with startup/shutdown hooks
- Entity-centric operations out of the box

## See Also

- [REST API Integration](rest-api.md) - Walker endpoints and API patterns
- [Entity Reference](entity-reference.md) - Complete API reference
- [MongoDB-Style Query Interface](mongodb-query-interface.md) - Query capabilities in endpoints
- [Object Pagination Guide](pagination.md) - Paginating server responses
- [Examples](examples.md) - Server usage examples
- [GraphContext & Database Management](graph-context.md) - Database integration

---

**[← Back to README](../../README.md)** | **[REST API Integration ←](rest-api.md)**
