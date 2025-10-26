# JVspatial Decorator Reference

**Date**: 2025-10-20
**Version**: 0.2.0

This document provides a comprehensive reference for all decorators available in the JVspatial library, organized by category and use case.

---

## 📋 **Decorator Categories**

| Category | Purpose | Location | Count |
|----------|---------|----------|-------|
| **Graph Decorators** | Graph traversal hooks | `core/decorators.py` | 2 |
| **API Decorators** | Route and field configuration | `api/decorators/` | 6 |
| **Auth Decorators** | Authentication and authorization | `api/auth/decorators.py` | 2 |
| **Integration Decorators** | External service integration | `api/integrations/` | 3 |
| **Total** | | | **13** |

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

### Route Decorators

#### `@endpoint(path, methods=None, **kwargs)`

**Purpose**: Create basic API endpoints.

**Parameters**:
- `path`: URL path for the endpoint
- `methods`: HTTP methods (default: ["POST"])
- `**kwargs`: Additional FastAPI route parameters

**Examples**:
```python
from jvspatial.api.decorators import endpoint

@endpoint("/api/users", methods=["GET", "POST"])
class UserWalker(Walker):
    """Handle user operations."""
    pass

@endpoint("/api/health", methods=["GET"])
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}
```

#### `@auth_endpoint(path, roles=None, permissions=None, **kwargs)`

**Purpose**: Create authenticated endpoints.

**Parameters**:
- `path`: URL path for the endpoint
- `roles`: Required user roles
- `permissions`: Required permissions
- `**kwargs`: Additional route parameters

**Examples**:
```python
from jvspatial.api.decorators import auth_endpoint

@auth_endpoint("/api/admin", roles=["admin"])
class AdminWalker(Walker):
    """Admin-only operations."""
    pass

@auth_endpoint("/api/profile", permissions=["read:profile"])
async def get_profile():
    """Get user profile."""
    return {"user": "profile_data"}
```

#### `@webhook_endpoint(path, **kwargs)`

**Purpose**: Create webhook endpoints.

**Examples**:
```python
from jvspatial.api.decorators import webhook_endpoint

@webhook_endpoint("/webhooks/github")
class GitHubWebhook(Walker):
    """Handle GitHub webhook events."""
    pass
```

#### `@admin_endpoint(path, **kwargs)`

**Purpose**: Create admin-only endpoints.

**Examples**:
```python
from jvspatial.api.decorators import admin_endpoint

@admin_endpoint("/api/system")
class SystemWalker(Walker):
    """System administration."""
    pass
```

### Field Decorators

#### `@endpoint_field(**kwargs)`

**Purpose**: Configure Pydantic model fields for API endpoints.

**Parameters**:
- `description`: Field description for OpenAPI
- `endpoint_required`: Whether field is required in API
- `exclude_endpoint`: Hide field from API
- `endpoint_name`: Custom name for API field

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

## 🔐 **Auth Decorators**

**Location**: `jvspatial.api.auth.decorators`
**Purpose**: Authentication and authorization

### `@auth_endpoint`

**Purpose**: Require authentication for endpoints.

**Examples**:
```python
from jvspatial.api.auth.decorators import auth_endpoint

@auth_endpoint("/api/protected")
class ProtectedWalker(Walker):
    """Requires authentication."""
    pass
```

### `@admin_endpoint`

**Purpose**: Require admin privileges for endpoints.

**Examples**:
```python
from jvspatial.api.auth.decorators import admin_endpoint

@admin_endpoint("/api/admin")
class AdminWalker(Walker):
    """Requires admin privileges."""
    pass
```

---

## 🔗 **Integration Decorators**

**Location**: `jvspatial.api.integrations`
**Purpose**: External service integration

### Webhook Decorators

#### `@webhook_endpoint`

**Purpose**: Create webhook endpoints with HMAC verification.

**Examples**:
```python
from jvspatial.api.integrations.webhooks.decorators import webhook_endpoint

@webhook_endpoint("/webhooks/stripe")
class StripeWebhook(Walker):
    """Handle Stripe webhook events."""
    pass
```

### Scheduler Decorators

#### `@on_schedule(schedule, **kwargs)`

**Purpose**: Schedule functions for periodic execution.

**Parameters**:
- `schedule`: Schedule specification (e.g., "every 5 minutes")
- `task_id`: Unique identifier for the task
- `enabled`: Whether task is enabled
- `max_concurrent`: Maximum concurrent executions
- `timeout_seconds`: Execution timeout
- `retry_count`: Number of retries on failure
- `description`: Human-readable description

**Examples**:
```python
from jvspatial.api.integrations.scheduler.decorators import on_schedule

@on_schedule("every 30 minutes", description="Clean up temp files")
def cleanup_temp_files():
    """Clean up temporary files."""
    pass

@on_schedule("daily at 02:00", task_id="daily_backup")
async def backup_database():
    """Daily database backup."""
    pass

@on_schedule("every 1 hour", max_concurrent=3, timeout_seconds=300)
def process_queue():
    """Process background queue."""
    pass
```

**Schedule Syntax**:
- `"every 5 minutes"` - Every 5 minutes
- `"daily at 14:30"` - Daily at 2:30 PM
- `"weekly on monday at 09:00"` - Weekly on Monday at 9 AM
- `"monthly on 1st at 00:00"` - Monthly on the 1st at midnight

---

## 🛠️ **Decorator Discovery Helper**

### Finding Decorators

```python
from jvspatial.api.integrations.scheduler.decorators import (
    get_scheduled_tasks,
    is_scheduled,
    get_schedule_info
)

# Get all scheduled tasks
tasks = get_scheduled_tasks()
print(f"Found {len(tasks)} scheduled tasks")

# Check if function is scheduled
if is_scheduled(my_function):
    print("Function is scheduled")

# Get schedule information
info = get_schedule_info(my_function)
if info:
    print(f"Schedule: {info['schedule']}")
    print(f"Task ID: {info['task_id']}")
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
from jvspatial.api.decorators import auth_endpoint, endpoint_field
from pydantic import BaseModel

class UserModel(BaseModel):
    name: str = endpoint_field(description="User name")
    email: str = endpoint_field(description="User email")

@auth_endpoint("/api/users", roles=["user"])
class UserWalker(Walker):
    """Authenticated user operations."""
    pass
```

#### 3. **Scheduled Background Tasks**
```python
from jvspatial.api.integrations.scheduler.decorators import on_schedule

@on_schedule("every 1 hour", description="Process pending orders")
async def process_orders():
    """Process pending orders every hour."""
    # Implementation
    pass
```

#### 4. **Webhook Integration**
```python
from jvspatial.api.decorators import webhook_endpoint

@webhook_endpoint("/webhooks/payment")
class PaymentWebhook(Walker):
    """Handle payment webhook events."""
    pass
```

---

## 🔧 **Advanced Usage**

### Custom Decorator Registration

```python
from jvspatial.api.integrations.scheduler.decorators import (
    set_default_scheduler,
    register_scheduled_tasks
)

# Set up scheduler
scheduler = SchedulerService()
set_default_scheduler(scheduler)

# Register all decorated tasks
register_scheduled_tasks(scheduler)
```

### Decorator Metadata Access

```python
# Check if function has decorator metadata
if hasattr(my_function, '_is_scheduled'):
    print("Function is scheduled")

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
# ❌ Wrong - missing import
@on_visit  # NameError: name 'on_visit' is not defined

# ✅ Correct - proper import
from jvspatial.core import on_visit
@on_visit
```

### 2. **Decorator Order**
```python
# ❌ Wrong - decorator order matters
@on_exit
@on_visit
def my_function():  # This won't work as expected
    pass

# ✅ Correct - proper order
@on_visit
@on_exit
def my_function():
    pass
```

### 3. **Async/Sync Mismatch**
```python
# ❌ Wrong - mixing async and sync
@on_schedule("every 1 hour")
def sync_function():  # Won't work with async scheduler
    pass

# ✅ Correct - match decorator with function type
@on_schedule("every 1 hour")
async def async_function():
    pass
```

---

## 📝 **Migration Guide**

### From v0.1 to v0.2

**Old imports**:
```python
# v0.1
from jvspatial.api.endpoints.decorators import endpoint_field
from jvspatial.api.routing.decorators import endpoint
```

**New imports**:
```python
# v0.2
from jvspatial.api.decorators import endpoint, endpoint_field
```

**Changes**:
- All API decorators moved to `api/decorators/`
- Route and field decorators consolidated
- Integration decorators organized by service

---

## 🔗 **Related Documentation**

- [API Documentation](api-architecture.md)
- [Graph Traversal Guide](graph-traversal.md)
- [Authentication Guide](authentication.md)
- [Scheduler Documentation](scheduler.md)
- [Webhook Integration](webhook-architecture.md)

---

**Last Updated**: 2025-10-20
**Version**: 0.2.0
**Maintainer**: JVspatial Team
