# REST API Integration

jvspatial provides seamless FastAPI integration through two approaches:

1. **Server Class (Recommended)** - High-level, object-oriented API server with automatic configuration
2. **Direct EndpointRouter** - Lower-level integration for custom FastAPI applications

Both approaches use the enhanced `EndpointField` system for precise API parameter control.

## Quick Start with Server Class

The recommended approach uses the `Server` class for simplified setup:

```python
from jvspatial.api.server import create_server
from jvspatial.core.entities import Walker, Root, on_visit
from jvspatial.api.endpoint_router import EndpointField

# Create server with automatic configuration
server = create_server(
    title="My Spatial API",
    description="Spatial data management API",
    version="1.0.0",
    db_type="json",
    db_path="jvdb/my_app"
)

@server.walker("/greet")
class GreetingWalker(Walker):
    name: str = EndpointField(
        default="World",
        description="Name to greet",
        examples=["Alice", "Bob"]
    )

    @on_visit(Root)
    async def greet(self, here):
        self.response["message"] = f"Hello, {self.name}!"

if __name__ == "__main__":
    server.run()  # Automatic database setup, docs at /docs
```

**Benefits of Server Class:**
- Zero-configuration database setup
- Automatic health checks and monitoring
- Built-in CORS and security middleware
- Lifecycle management with startup/shutdown hooks
- Simplified deployment with `server.run()`

📖 **[See complete Server Class documentation →](server-api.md)**

---

## Direct EndpointRouter Usage

For advanced use cases or custom FastAPI applications, you can use the EndpointRouter directly:

### Basic Usage

```python
from fastapi import FastAPI
from jvspatial.api.endpoint_router import EndpointRouter, EndpointField
from jvspatial.core.entities import Walker, Root, on_visit, on_exit

app = FastAPI(title="My Spatial API")
router = EndpointRouter()

@router.endpoint("/greet", methods=["POST"])
class GreetingWalker(Walker):
    # Basic field with description and examples
    name: str = EndpointField(
        default="World",
        description="Name to greet",
        examples=["Alice", "Bob", "Charlie"]
    )

    # Field with validation constraints
    age: int = EndpointField(
        default=25,
        ge=0,
        le=150,
        description="Age of the person"
    )

    # Excluded field (not exposed in API)
    internal_state: dict = EndpointField(
        default_factory=dict,
        exclude_endpoint=True
    )

    @on_visit(Root)
    async def greet(self, here):
        self.response["message"] = f"Hello, {self.name}! You are {self.age} years old."

    @on_exit
    async def finish(self):
        self.response["status"] = "success"

app.include_router(router.router)
```

## Advanced Parameter Control

```python
@router.endpoint("/user-search", methods=["POST"])
class UserSearchWalker(Walker):
    # Custom parameter name in API
    user_id: str = EndpointField(
        endpoint_name="userId",
        description="Unique user identifier",
        pattern=r"^[a-zA-Z0-9_]+$",
        examples=["john_doe", "alice123"]
    )

    # Grouped authentication parameters
    username: str = EndpointField(
        endpoint_group="auth",
        description="Username for authentication",
        min_length=3,
        max_length=50
    )

    password: str = EndpointField(
        endpoint_group="auth",
        endpoint_hidden=True,  # Hidden from OpenAPI docs
        description="User password"
    )

    # Optional field made required for endpoint
    config: Optional[dict] = EndpointField(
        default=None,
        endpoint_required=True,
        description="Required configuration for API"
    )

    # Deprecated parameter with migration guidance
    old_param: Optional[str] = EndpointField(
        default=None,
        endpoint_deprecated=True,
        description="DEPRECATED: Use 'userId' instead"
    )

    # Internal processing fields (excluded)
    _search_cache: dict = EndpointField(
        default_factory=dict,
        exclude_endpoint=True
    )

    @on_visit(Root)
    async def search_user(self, here):
        # Access grouped auth parameters
        auth_success = self.authenticate(self.username, self.password)
        if auth_success:
            user = await self.find_user(self.user_id)
            self.response["user"] = user
        else:
            self.response["error"] = "Authentication failed"
```

**Generated API Request Structure:**
```json
{
  "userId": "john_doe",
  "auth": {
    "username": "john",
    "password": "secret123"
  },
  "config": {"theme": "dark"},
  "start_node": "n:Root:root"
}
```

### Real-World Example: E-commerce Product Search

```python
@router.endpoint("/products/search", methods=["POST"])
class ProductSearchWalker(Walker):
    # Basic search parameter
    query: str = EndpointField(
        description="Product search query",
        examples=["laptop", "smartphone", "headphones"],
        min_length=1,
        max_length=100
    )

    # Grouped filter parameters
    category: Optional[str] = EndpointField(
        default=None,
        endpoint_group="filters",
        endpoint_name="categoryId",
        description="Product category filter",
        examples=["electronics", "clothing", "books"]
    )

    min_price: Optional[float] = EndpointField(
        default=None,
        endpoint_group="filters",
        ge=0.0,
        description="Minimum price filter"
    )

    max_price: Optional[float] = EndpointField(
        default=None,
        endpoint_group="filters",
        ge=0.0,
        description="Maximum price filter"
    )

    # Grouped pagination parameters
    page: int = EndpointField(
        default=1,
        endpoint_group="pagination",
        ge=1,
        description="Page number"
    )

    limit: int = EndpointField(
        default=20,
        endpoint_group="pagination",
        ge=1,
        le=100,
        description="Items per page"
    )

    # API key (hidden from documentation)
    api_key: str = EndpointField(
        default="default_key",
        endpoint_hidden=True,
        description="Internal API authentication key"
    )

    # Internal state (excluded from API)
    search_cache: dict = EndpointField(
        default_factory=dict,
        exclude_endpoint=True
    )

    @on_visit(Root)
    async def search_products(self, here):
        products = await self.perform_search(
            query=self.query,
            category=self.category,
            min_price=self.min_price,
            max_price=self.max_price,
            page=self.page,
            limit=self.limit
        )

        self.response["products"] = products
        self.response["total"] = len(products)
        self.response["page"] = self.page
```

**API Request:**
```json
{
  "query": "laptop",
  "filters": {
    "categoryId": "electronics",
    "min_price": 500.0,
    "max_price": 2000.0
  },
  "pagination": {
    "page": 1,
    "limit": 25
  }
}
```

### EndpointField Parameter Reference

```python
EndpointField(
    default=...,                    # Field default value

    # Standard Pydantic validation
    title="Field Title",            # OpenAPI title
    description="Field description", # OpenAPI description
    examples=["example1", "example2"], # OpenAPI examples
    gt=0, ge=0, lt=100, le=100,    # Numeric constraints
    min_length=1, max_length=50,    # String length constraints
    pattern=r"^[a-zA-Z]+$",        # String pattern validation

    # Endpoint-specific configuration
    exclude_endpoint=False,         # Exclude from endpoint entirely
    endpoint_name="customName",     # Custom parameter name in API
    endpoint_required=True,         # Override required status for endpoint
    endpoint_hidden=False,          # Hide from OpenAPI docs
    endpoint_deprecated=False,      # Mark as deprecated in OpenAPI
    endpoint_group="groupName",     # Group related parameters
    endpoint_constraints={          # Additional OpenAPI constraints
        "multipleOf": 10,
        "pattern": r"^[A-Z]{2}-\d{4}$"
    }
)
```

### API Usage Examples

```bash
# Start the server
python main.py

# Simple greeting
curl -X POST http://localhost:8000/greet \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "age": 30}'

# Product search with filters
curl -X POST http://localhost:8000/products/search \
  -H "Content-Type: application/json" \
  -d '{
    "query": "gaming laptop",
    "filters": {
      "categoryId": "electronics",
      "min_price": 800,
      "max_price": 3000
    },
    "pagination": {
      "page": 1,
      "limit": 10
    }
  }'

# User search with authentication
curl -X POST http://localhost:8000/user-search \
  -H "Content-Type: application/json" \
  -d '{
    "userId": "john_doe",
    "auth": {
      "username": "john",
      "password": "secret123"
    },
    "config": {"includePrivateData": true}
  }'
```

### Alternative Comment-Based Approach

For convenience, the library also supports the comment-based approach:

**Convenient, comment-based approach:**
```python
class MyWalker(Walker):
    public_field: str = "default"
    private_field: str  # endpoint: ignore
```

The formal approach is recommended, however, it provides:
- **Better Performance**: 2-5x faster than AST parsing
- **Type Safety**: Full IDE support and static analysis
- **Rich Features**: Parameter grouping, custom naming, validation
- **Reliability**: Works in all Python environments

### Benefits of Enhanced Field Control

1. **Type Safety**: Full IDE support and static analysis
2. **Rich Documentation**: Automatic OpenAPI generation with descriptions and examples
3. **Flexible Validation**: Support for all Pydantic validation constraints
4. **Parameter Grouping**: Organize related parameters into nested objects
5. **Custom Naming**: API-friendly parameter names different from internal field names
6. **Performance**: 2-5x faster than comment-based approach
7. **Maintainability**: No AST parsing complexity
8. **Extensibility**: Easy to add new endpoint-specific features