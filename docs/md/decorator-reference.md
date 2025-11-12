# JVspatial Decorator Reference

**Date**: 2025-10-20
**Version**: 0.0.1

This document provides a comprehensive reference for all decorators available in the JVspatial library, organized by category and use case.

---

## 📋 **Decorator Categories**

| Category | Purpose | Location | Count |
|----------|---------|----------|-------|
| **Graph Decorators** | Graph traversal hooks | `core/decorators.py` | 2 |
| **API Decorators** | Route and field configuration | `api/decorators/` | 2 |
| **Total** | | | **4** |

---

## 🌐 **Graph Decorators**

**Location**: `jvspatial.core.decorators`
**Purpose**: Control graph traversal behavior

### `@on_visit(*target_types)`

**Purpose**: Register a visit hook for specific node/edge types during graph traversal.

**Parameters**:
- `*target_types`: One or more target types (Node, Edge, Walker subclasses, or string names)

**Examples**:
```python
from jvspatial.core import on_visit, Node, Edge

# Visit specific node types
@on_visit(UserNode, AdminNode)
def handle_user_nodes(walker, node):
    print(f"Visiting user node: {node}")

# Visit any edge type
@on_visit(Edge)
def handle_all_edges(walker, edge):
    print(f"Traversing edge: {edge}")

# Visit with string names (forward references)
@on_visit("WebhookEvent", "Notification")
def handle_events(walker, node):
    print(f"Processing event: {node}")

# Visit any valid type (no parameters)
@on_visit
def handle_any_node(walker, node):
    print(f"Visiting: {node}")
```

**Use Cases**:
- Logging specific node types
- Data transformation during traversal
- Conditional logic based on node types
- Metrics collection

---

### `@on_exit`

**Purpose**: Execute code when walker completes traversal.

**Examples**:
```python
from jvspatial.core import on_exit

@on_exit
def cleanup_resources(walker):
    """Clean up resources after traversal."""
    walker.cleanup_temp_files()
    walker.close_connections()

@on_exit
async def send_completion_notification(walker):
    """Send notification when traversal completes."""
    await walker.notify_completion()
```

**Use Cases**:
- Resource cleanup
- Completion notifications
- Final data processing
- Metrics reporting

---

## 🚀 **API Decorators**

**Location**: `jvspatial.api.decorators`
**Purpose**: Configure API endpoints and fields

### `@endpoint`

**Purpose**: Unified decorator for registering both function and Walker class endpoints. This is the only endpoint decorator in jvspatial - all endpoint types (public, authenticated, admin, webhook) are created using this single decorator with different parameters.

**Location**: `jvspatial.api.decorators` or `jvspatial.api`

**Parameters**:
- `path` (str): URL path for the endpoint
- `methods` (List[str], optional): HTTP methods (default: `["GET"]` for functions, `["POST"]` for Walkers)
- `auth` (bool, optional): Require authentication (default: `False`)
- `roles` (List[str], optional): Required user roles (e.g., `["admin"]`)
- `permissions` (List[str], optional): Required permissions (e.g., `["read:users"]`)
- `webhook` (bool, optional): Configure as webhook endpoint (default: `False`)
- `signature_required` (bool, optional): Require webhook signature verification (default: `False`)
- `response` (ResponseSchema, optional): Response schema definition (see [Response Schema Definition](rest-api.md#response-schema-definition))
- `**kwargs`: Additional FastAPI route parameters (tags, summary, description, etc.)

**Examples**:

**Basic Public Endpoint**:
```python
from jvspatial.api import endpoint

@endpoint("/api/health", methods=["GET"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
```

**Authenticated Endpoint**:
```python
@endpoint("/api/profile", methods=["GET"], auth=True)
async def get_profile():
    """Get user profile - requires authentication."""
    return {"user": "profile_data"}
```

**Role-Based Endpoint**:
```python
@endpoint("/api/admin", methods=["GET"], auth=True, roles=["admin"])
async def admin_panel():
    """Admin-only endpoint."""
    return {"admin": "dashboard"}
```

**Permission-Based Endpoint**:
```python
@endpoint("/api/users", methods=["GET"], auth=True, permissions=["read:users"])
async def list_users():
    """List users - requires read:users permission."""
    return {"users": []}
```

**Walker Endpoint**:
```python
from jvspatial.core import Walker

@endpoint("/api/process", methods=["POST"])
class ProcessData(Walker):
    """Process data using graph traversal."""
    data: str

    async def process(self):
        return {"result": self.data.upper()}
```

**Endpoint with Response Schema**:
```python
from jvspatial.api.endpoints.response import ResponseField, success_response

@endpoint(
    "/api/users",
    methods=["GET"],
    response=success_response(
        data={
            "users": ResponseField(
                field_type=list,
                description="List of users",
                example=[{"id": "1", "name": "John"}]
            ),
            "count": ResponseField(
                field_type=int,
                description="Total count",
                example=1
            )
        }
    )
)
async def get_users():
    return {"users": [], "count": 0}
```

**Webhook Endpoint**:
```python
@endpoint("/webhooks/github", webhook=True, signature_required=True)
async def github_webhook():
    """Handle GitHub webhook events."""
    return {"status": "ok"}
```

For detailed information on response schemas, see the [Response Schema Definition](rest-api.md#response-schema-definition) section in the REST API documentation.

### Field Configuration

#### `EndpointField`

**Purpose**: Configure fields in Walker classes for API endpoints. Used as a type annotation for Walker class attributes.

**Location**: `jvspatial.api.decorators.EndpointField`

**Parameters**:
- `default`: Default value for the field
- `description`: Field description for OpenAPI documentation
- `examples`: Example values (list or single value)
- `min_length`, `max_length`: String length constraints
- `ge`, `le`, `gt`, `lt`: Numeric constraints (greater/less than or equal)
- `pattern`: Regex pattern for string validation
- `**kwargs`: Additional Pydantic Field arguments

**Examples**:
```python
from jvspatial.api.decorators import EndpointField
from jvspatial.core import Walker

@endpoint("/api/users/search", methods=["POST"])
class SearchUsers(Walker):
    name: str = EndpointField(
        description="Name pattern to search",
        examples=["Alice", "John"],
        min_length=1,
        max_length=100
    )

    age: int = EndpointField(
        default=0,
        description="Minimum age",
        ge=0,
        le=150,
        examples=[25, 30, 45]
    )

    include_inactive: bool = EndpointField(
        default=False,
        description="Include inactive users in results"
    )
```

#### `endpoint_field()`

**Purpose**: Configure Pydantic model fields for API endpoints. Used with Pydantic BaseModel classes.

**Location**: `jvspatial.api.decorators.endpoint_field`

**Parameters**:
- `description`: Field description for OpenAPI
- `endpoint_required`: Whether field is required in API
- `exclude_endpoint`: Hide field from API
- `endpoint_name`: Custom name for API field
- `**kwargs`: Additional Pydantic Field arguments

**Examples**:
```python
from jvspatial.api.decorators import endpoint_field
from pydantic import BaseModel

class UserModel(BaseModel):
    name: str = endpoint_field(
        description="User's full name",
        endpoint_required=True
    )

    password: str = endpoint_field(
        exclude_endpoint=True  # Hide from API
    )

    email: str = endpoint_field(
        endpoint_name="email_address",
        description="User's email address"
    )
```

---

## 📚 **Usage Patterns**

### Common Patterns

#### 1. **Graph Traversal with Hooks**
```python
from jvspatial.core import Walker, on_visit, on_exit

class DataProcessor(Walker):
    @on_visit(UserNode)
    def process_user(self, walker, node):
        # Process user data
        pass

    @on_exit
    def finalize_processing(self, walker):
        # Clean up and finalize
        pass
```

#### 2. **API Endpoint with Authentication**
```python
from jvspatial.api import endpoint
from jvspatial.api.decorators import EndpointField

@endpoint("/api/users", methods=["GET"], auth=True, roles=["user"])
class UserWalker(Walker):
    """Authenticated user operations."""
    name: str = EndpointField(description="User name")
    email: str = EndpointField(description="User email")
```

#### 3. **Permission-Based Endpoint**
```python
from jvspatial.api import endpoint

@endpoint("/api/admin", methods=["GET"], auth=True, permissions=["admin:read"])
async def admin_panel():
    """Admin operations requiring specific permissions."""
    return {"admin": "dashboard"}
```

#### 4. **Webhook Integration**
```python
from jvspatial.api import endpoint

@endpoint("/webhooks/payment", webhook=True, signature_required=True)
async def payment_webhook():
    """Handle payment webhook events."""
    return {"status": "received"}
```

---

## 🔧 **Advanced Usage**

### Decorator Metadata Access

```python
# Check if function/class has endpoint configuration
if hasattr(my_function, '_jvspatial_endpoint_config'):
    config = my_function._jvspatial_endpoint_config
    print(f"Endpoint path: {config['path']}")
    print(f"Methods: {config['methods']}")
    print(f"Auth required: {config.get('auth_required', False)}")

# Check if function is a visit hook
if hasattr(my_function, '_is_visit_hook'):
    print("Function is a visit hook")
```

---

## 📖 **Best Practices**

### 1. **Decorator Organization**
- Use graph decorators for traversal logic
- Use API decorators for endpoint configuration
- Use integration decorators for external services

### 2. **Naming Conventions**
- Use descriptive function names
- Follow the pattern: `@decorator_name`
- Group related decorators together

### 3. **Error Handling**
- Always handle exceptions in decorated functions
- Use appropriate logging levels
- Provide meaningful error messages

### 4. **Performance Considerations**
- Avoid heavy computation in decorators
- Use async decorators for I/O operations
- Consider decorator overhead in hot paths

---

## 🚨 **Common Pitfalls**

### 1. **Import Errors**
```python
# Wrong - missing import
@on_visit  # NameError: name 'on_visit' is not defined

# Correct - proper import
from jvspatial.core import on_visit
@on_visit
```

### 2. **Decorator Order**
```python
# Wrong - decorator order matters
@on_exit
@on_visit
def my_function():  # This won't work as expected
    pass

# Correct - proper order
@on_visit
@on_exit
def my_function():
    pass
```

### 3. **Async/Sync Mismatch**
```python
# Wrong - mixing async and sync
@on_schedule("every 1 hour")
def sync_function():  # Won't work with async scheduler
    pass

# Correct - match decorator with function type
@on_schedule("every 1 hour")
async def async_function():
    pass
```

---

## 📝 **Import Reference**

### Recommended Imports

```python
# Main endpoint decorator
from jvspatial.api import endpoint  # Recommended
# or
from jvspatial.api.decorators import endpoint

# Field configuration for Walker classes
from jvspatial.api.decorators import EndpointField

# Field configuration for Pydantic models
from jvspatial.api.decorators import endpoint_field

# Response schema helpers
from jvspatial.api.endpoints.response import (
    ResponseField,
    ResponseSchema,
    success_response,
    error_response
)
```

---

## 🔗 **Related Documentation**

- [API Documentation](api-architecture.md)
- [Graph Traversal Guide](graph-traversal.md)
- [Authentication Guide](authentication.md)
- [Scheduler Documentation](scheduler.md)
- [Webhook Integration](webhook-architecture.md)

---

**Last Updated**: 2025-10-20
**Version**: 0.0.1
**Maintainer**: JVspatial Team

