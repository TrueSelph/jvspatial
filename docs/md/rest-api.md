# REST API Integration

jvspatial provides seamless **FastAPI integration** with automatic OpenAPI documentation generation, enabling you to quickly build production-ready APIs for your graph data. The library emphasizes two modern approaches:

1. **Server Class (Recommended)** - Complete API server with automatic database setup and configuration
2. **Walker Endpoint Decorators** - Direct endpoint registration for maximum flexibility

Both approaches leverage the current **entity-centric design** with MongoDB-style queries and support the library's core features like ObjectPager and semantic filtering.

## Quick Start with Server Class

The recommended approach uses the modern `Server` class with entity-centric operations:

```python
from jvspatial.api import Server, endpoint
from jvspatial.api.endpoint import EndpointField
from jvspatial.core import Walker, Node, on_visit

# Define your entity
class User(Node):
    name: str = ""
    email: str = ""
    department: str = ""
    active: bool = True

# Create server with automatic configuration
server = Server(
    title="User Management API",
    description="Entity-centric user management with graph capabilities",
    version="1.0.0",
    debug=True
)

@endpoint("/api/users/search", methods=["POST"])
class SearchUsers(Walker):
    """Search users with MongoDB-style queries and semantic filtering."""

    name_pattern: str = EndpointField(
        description="Name pattern to search (supports regex)",
        examples=["Alice", "John", "^A.*"],
        min_length=1
    )

    department: str = EndpointField(
        default="",
        description="Department filter",
        examples=["engineering", "marketing", "sales"]
    )

    include_inactive: bool = EndpointField(
        default=False,
        description="Include inactive users in search"
    )

    @on_visit(Node)
    async def search_users(self, here: Node):
        # Build MongoDB-style query
        query = {
            "context.name": {"$regex": self.name_pattern, "$options": "i"}
        }

        if self.department:
            query["context.department"] = self.department

        if not self.include_inactive:
            query["context.active"] = True

        # Execute entity-centric search
        users = await User.find(query)

        self.response = {
            "users": [
                {
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "department": user.department,
                    "active": user.active
                } for user in users
            ],
            "total_found": len(users),
            "query_used": query
        }

if __name__ == "__main__":
    server.run()  # API available at http://localhost:8000/docs
```

**Benefits of Modern Server Class:**
- **Zero-configuration**: Automatic database setup with sensible defaults
- **Entity-centric**: Direct integration with Node.find(), User.create(), etc.
- **MongoDB-style queries**: Unified query interface across all database backends
- **Automatic OpenAPI docs**: Rich documentation with examples and validation
- **Object pagination**: Built-in support for efficient large dataset handling
- **Semantic filtering**: Advanced graph traversal capabilities in endpoints
- **Production-ready**: Built-in CORS, health checks, and middleware support

📖 **[See complete Server Class documentation →](server-api.md)**

---

## Walker Endpoint Decorators

For maximum flexibility, use the modern `@endpoint` decorator (works for both functions and Walker classes):

### Walker Endpoints with Entity Operations

```python
from jvspatial.api import walker_endpoint, endpoint
from jvspatial.api.endpoint.router import EndpointField
from jvspatial.core import Walker, Node, on_visit
from fastapi import HTTPException
from typing import List, Optional

class Product(Node):
    name: str = ""
    price: float = 0.0
    category: str = ""
    in_stock: bool = True
    description: str = ""

@endpoint("/api/products/create", methods=["POST"])
class CreateProduct(Walker):
    """Create a new product with entity-centric operations."""

    name: str = EndpointField(
        description="Product name",
        examples=["Laptop Pro", "Gaming Mouse"],
        min_length=1,
        max_length=200
    )

    price: float = EndpointField(
        description="Product price in USD",
        examples=[299.99, 1499.99],
        gt=0.0
    )

    category: str = EndpointField(
        description="Product category",
        examples=["electronics", "books", "clothing"]
    )

    description: str = EndpointField(
        default="",
        description="Product description",
        max_length=1000
    )

    @on_visit(Node)
    async def create_product(self, here: Node):
        # Check for existing product
        existing = await Product.find_one({
            "context.name": self.name,
            "context.category": self.category
        })

        if existing:
            self.response = {
                "error": "Product with this name already exists in category",
                "existing_product_id": existing.id
            }
            return

        # Create new product using entity-centric approach
        product = await Product.create(
            name=self.name,
            price=self.price,
            category=self.category,
            description=self.description,
            in_stock=True
        )

        self.response = {
            "product": {
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "category": product.category
            },
            "status": "created"
        }
```

## Enhanced Response Handling with endpoint.response()

The `@walker_endpoint` and `@endpoint` decorators now automatically inject semantic response helpers for clean, flexible HTTP responses:

### Walker Endpoints with Semantic Responses

```python
@endpoint("/api/products/details", methods=["POST"])
class ProductDetails(Walker):
    """Get product details with enhanced response handling."""

    product_id: str = EndpointField(
        description="Product ID to retrieve",
        examples=["p:Product:12345"],
        min_length=1
    )

    include_reviews: bool = EndpointField(
        default=False,
        description="Include product reviews in response"
    )

    @on_visit(Product)
    async def get_product_details(self, here: Product):
        if here.id != self.product_id:
            return  # Continue traversal

        # Product not found
        if not here.data:
            return self.endpoint.not_found(
                message="Product not found",
                details={"product_id": self.product_id}
            )

        # Out of stock check
        if not here.in_stock:
            return self.endpoint.response(
                content={
                    "message": "Product is currently out of stock",
                    "product": {"id": here.id, "name": here.name},
                    "estimated_restock": "2-3 weeks"
                },
                status_code=200,
                headers={"X-Stock-Status": "out-of-stock"}
            )

        # Build product response
        product_data = {
            "id": here.id,
            "name": here.name,
            "price": here.price,
            "category": here.category,
            "description": here.description,
            "in_stock": here.in_stock
        }

        if self.include_reviews:
            # Find connected review nodes
            reviews = await here.nodes(node=['Review'])
            product_data["reviews"] = [
                {"rating": r.rating, "comment": r.comment}
                for r in reviews[:5]  # Limit to 5 recent reviews
            ]

        # Success response with proper headers
        return self.endpoint.success(
            data=product_data,
            message="Product details retrieved successfully",
            headers={"X-Product-Category": here.category}
        )

@endpoint("/api/products/create-advanced", methods=["POST"])
class CreateProductAdvanced(Walker):
    """Create product with comprehensive validation and response handling."""

    name: str = EndpointField(description="Product name", min_length=1)
    price: float = EndpointField(description="Product price", gt=0.0)
    category: str = EndpointField(description="Product category")

    @on_visit(Node)
    async def create_product(self, here: Node):
        # Validation with specific error responses
        if self.price > 10000:
            return self.endpoint.unprocessable_entity(
                message="Product price exceeds maximum allowed",
                details={"price": self.price, "max_allowed": 10000}
            )

        # Check for conflicts
        existing = await Product.find_one({
            "context.name": self.name,
            "context.category": self.category
        })

        if existing:
            return self.endpoint.conflict(
                message="Product already exists in this category",
                details={
                    "name": self.name,
                    "category": self.category,
                    "existing_id": existing.id
                }
            )

        # Create product
        product = await Product.create(
            name=self.name,
            price=self.price,
            category=self.category
        )

        # Return 201 Created with location header
        return self.endpoint.created(
            data={
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "category": product.category
            },
            message="Product created successfully",
            headers={"Location": f"/api/products/{product.id}"}
        )
```

### Function Endpoints with Enhanced Responses

```python
@endpoint("/api/health", methods=["GET"])
async def enhanced_health_check(endpoint):
    """Health check with semantic response handling."""
    try:
        # Test database connectivity
        product_count = await Product.count()

        return endpoint.success(
            data={
                "status": "healthy",
                "version": "1.0.0",
                "database": "connected",
                "total_products": product_count
            },
            message="System is operating normally"
        )
    except Exception as e:
        return endpoint.error(
            message="Health check failed",
            status_code=503,  # Service Unavailable
            details={"error": str(e)}
        )

@endpoint("/api/products/{product_id}/status", methods=["PUT"])
async def update_product_status(product_id: str, in_stock: bool, endpoint):
    """Update product stock status with validation."""

    # Find product
    product = await Product.get(product_id)
    if not product:
        return endpoint.not_found(
            message="Product not found",
            details={"product_id": product_id}
        )

    # Update status
    product.in_stock = in_stock
    await product.save()

    # Return success with updated data
    return endpoint.success(
        data={
            "id": product.id,
            "name": product.name,
            "in_stock": product.in_stock,
            "updated_at": "2025-09-21T06:32:18Z"
        },
        message=f"Product status updated to {'in stock' if in_stock else 'out of stock'}"
    )

@endpoint("/api/export/products", methods=["GET"])
async def export_products(format: str, endpoint):
    """Export products with flexible response formatting."""

    # Validate format
    supported_formats = ["json", "csv", "xml"]
    if format not in supported_formats:
        return endpoint.bad_request(
            message="Unsupported export format",
            details={
                "requested": format,
                "supported": supported_formats
            }
        )

    # Generate export data
    products = await Product.all()
    export_data = {
        "format": format,
        "total_products": len(products),
        "export_id": "exp_20250921_063218",
        "download_url": f"/downloads/products.{format}"
    }

    # Custom response with export-specific headers
    return endpoint.response(
        content={
            "data": export_data,
            "message": f"Export prepared in {format} format"
        },
        status_code=202,  # Accepted - export is being processed
        headers={
            "X-Export-Format": format,
            "X-Export-Count": str(len(products)),
            "X-Processing-Time": "estimated 30 seconds"
        }
    )
```

### Available Response Methods

The injected `endpoint` helper provides semantic methods for common HTTP responses:

**Success Responses:**
- `endpoint.success(data=result, message="Success")` → 200 OK
- `endpoint.created(data=new_item, message="Created")` → 201 Created
- `endpoint.no_content(headers={})` → 204 No Content

**Error Responses:**
- `endpoint.bad_request(message="Invalid input")` → 400 Bad Request
- `endpoint.unauthorized(message="Auth required")` → 401 Unauthorized
- `endpoint.forbidden(message="Access denied")` → 403 Forbidden
- `endpoint.not_found(message="Not found")` → 404 Not Found
- `endpoint.conflict(message="Resource exists")` → 409 Conflict
- `endpoint.unprocessable_entity(message="Validation failed")` → 422 Unprocessable Entity
- `endpoint.error(message="Custom error", status_code=500)` → Custom status

**Flexible Response:**
- `endpoint.response(content=data, status_code=202, headers={})` → Full control

All methods support:
- `data`: Response payload data
- `message`: Human-readable message
- `details`: Additional error/context information
- `headers`: Custom HTTP headers

### Migration from Manual Response Building

**Before (manual response building):**
```python
@endpoint("/api/example")
class ExampleWalker(Walker):
    async def process(self, here):
        if error_condition:
            self.response = {
                "error": "Something went wrong",
                "status": 400
            }
        else:
            self.response = {
                "data": result,
                "message": "Success"
            }
```

**After (semantic responses):**
```python
@endpoint("/api/example")
class ExampleWalker(Walker):
    async def process(self, here):
        if error_condition:
            return self.endpoint.bad_request(
                message="Something went wrong",
                details={"reason": "validation_failed"}
            )

        return self.endpoint.success(
            data=result,
            message="Success"
        )
```

### Function Endpoints for Simple Operations

```python
@endpoint("/api/products/count", methods=["GET"])
async def get_product_count():
    """Get total product count - simple function endpoint."""
    total = await Product.count()
    active = await Product.count({"context.in_stock": True})

    return {
        "total_products": total,
        "in_stock": active,
        "out_of_stock": total - active
    }

@endpoint("/api/products/{product_id}", methods=["GET"])
async def get_product(product_id: str):
    """Get product by ID with entity-centric retrieval."""
    product = await Product.get(product_id)

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    return {
        "product": {
            "id": product.id,
            "name": product.name,
            "price": product.price,
            "category": product.category,
            "description": product.description,
            "in_stock": product.in_stock
        }
    }

@endpoint("/api/products/{product_id}", methods=["DELETE"])
async def delete_product(product_id: str):
    """Delete product using entity-centric operations."""
    product = await Product.get(product_id)

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    await product.delete()

    return {"message": "Product deleted successfully", "deleted_id": product_id}
```

## Advanced MongoDB-Style Query Endpoints

```python
@endpoint("/api/products/advanced-search", methods=["POST"])
class AdvancedProductSearch(Walker):
    """Advanced product search with MongoDB-style queries and pagination."""

    # Search filters (grouped)
    category: Optional[str] = EndpointField(
        default=None,
        endpoint_group="filters",
        description="Product category filter",
        examples=["electronics", "books", "clothing"]
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

    name_pattern: Optional[str] = EndpointField(
        default=None,
        endpoint_group="filters",
        description="Name pattern (supports regex)",
        examples=["laptop", "^Gaming", "mouse$"]
    )

    # Pagination (grouped)
    page: int = EndpointField(
        default=1,
        endpoint_group="pagination",
        ge=1,
        description="Page number"
    )

    page_size: int = EndpointField(
        default=20,
        endpoint_group="pagination",
        ge=1,
        le=100,
        description="Items per page"
    )

    # Sorting
    sort_by: str = EndpointField(
        default="name",
        description="Field to sort by",
        examples=["name", "price", "category"]
    )

    sort_order: str = EndpointField(
        default="asc",
        description="Sort order",
        examples=["asc", "desc"]
    )

    @on_visit(Node)
    async def advanced_search(self, here: Node):
        # Build MongoDB-style query
        query = {"context.in_stock": True}  # Only in-stock products

        # Add filters
        if self.category:
            query["context.category"] = self.category

        if self.min_price is not None or self.max_price is not None:
            price_filter = {}
            if self.min_price is not None:
                price_filter["$gte"] = self.min_price
            if self.max_price is not None:
                price_filter["$lte"] = self.max_price
            query["context.price"] = price_filter

        if self.name_pattern:
            query["context.name"] = {
                "$regex": self.name_pattern,
                "$options": "i"
            }

        # Use ObjectPager for efficient pagination
        from jvspatial.core.pager import ObjectPager

        pager = ObjectPager(
            Product,
            page_size=self.page_size,
            filters=query,
            order_by=self.sort_by,
            order_direction=self.sort_order
        )

        products = await pager.get_page(self.page)
        pagination_info = pager.to_dict()

        self.response = {
            "products": [
                {
                    "id": p.id,
                    "name": p.name,
                    "price": p.price,
                    "category": p.category,
                    "description": p.description[:100] + "..." if len(p.description) > 100 else p.description
                } for p in products
            ],
            "pagination": pagination_info,
            "query_applied": query
        }
```

**Generated API Request Structure:**
```json
{
  "filters": {
    "category": "electronics",
    "min_price": 100.0,
    "max_price": 1000.0,
    "name_pattern": "laptop"
  },
  "pagination": {
    "page": 1,
    "page_size": 20
  },
  "sort_by": "price",
  "sort_order": "asc"
}
```

## Real-World Example: User Management with Graph Traversal

```python
from jvspatial.core import Node, Edge, Walker, on_visit
from jvspatial.api import walker_endpoint, Server
from jvspatial.api.endpoint.router import EndpointField
from typing import List, Optional

# Entity definitions
class User(Node):
    name: str = ""
    email: str = ""
    department: str = ""
    role: str = "user"
    active: bool = True
    skills: List[str] = []

class Collaboration(Edge):
    project: str = ""
    start_date: str = ""
    status: str = "active"

# Create server
server = Server(
    title="User Management API",
    description="Advanced user management with graph relationships",
    version="2.0.0"
)

@endpoint("/api/users/network-analysis", methods=["POST"])
class NetworkAnalysis(Walker):
    """Analyze user collaboration networks using graph traversal."""

    user_id: str = EndpointField(
        description="User ID to analyze",
        examples=["user123", "alice-smith"]
    )

    max_depth: int = EndpointField(
        default=2,
        description="Maximum traversal depth",
        ge=1,
        le=5
    )

    include_departments: List[str] = EndpointField(
        default_factory=list,
        description="Departments to include (empty = all)",
        examples=[["engineering", "product"], ["marketing"]]
    )

    active_only: bool = EndpointField(
        default=True,
        description="Only include active users"
    )

    @on_visit(User)
    async def analyze_network(self, here: User):
        """Analyze collaboration network using semantic filtering."""
        if here.id == self.user_id:
            # This is our target user - start analysis
            self.response["target_user"] = {
                "id": here.id,
                "name": here.name,
                "department": here.department,
                "role": here.role
            }

            # Find direct collaborators using semantic filtering
            collaborator_filters = {"active": True} if self.active_only else {}
            if self.include_departments:
                # Use MongoDB-style query for department filtering
                direct_collaborators = await here.nodes(
                    node=[{
                        'User': {
                            "context.department": {"$in": self.include_departments},
                            "context.active": True if self.active_only else {"$exists": True}
                        }
                    }],
                    direction="both"
                )
            else:
                direct_collaborators = await here.nodes(
                    node=['User'],
                    **collaborator_filters
                )

            self.response["direct_collaborators"] = [
                {
                    "id": user.id,
                    "name": user.name,
                    "department": user.department,
                    "shared_skills": list(set(here.skills) & set(user.skills))
                } for user in direct_collaborators
            ]

            # Continue traversal if depth allows
            if self.max_depth > 1:
                self.max_depth -= 1
                await self.visit(direct_collaborators)
        else:
            # Secondary user - add to extended network
            if "extended_network" not in self.response:
                self.response["extended_network"] = []

            self.response["extended_network"].append({
                "id": here.id,
                "name": here.name,
                "department": here.department
            })

@endpoint("/api/users/skill-matching", methods=["POST"])
class SkillMatching(Walker):
    """Find users with matching skills using MongoDB-style queries."""

    required_skills: List[str] = EndpointField(
        description="Required skills to match",
        examples=[["python", "javascript"], ["design", "figma"]]
    )

    department_filter: Optional[str] = EndpointField(
        default=None,
        description="Filter by department",
        examples=["engineering", "design", "product"]
    )

    min_skill_match: int = EndpointField(
        default=1,
        description="Minimum number of skills that must match",
        ge=1
    )

    @on_visit(Node)
    async def find_matching_users(self, here: Node):
        # Build complex MongoDB-style query
        query = {
            "$and": [
                {"context.active": True},
                {"context.skills": {"$in": self.required_skills}}
            ]
        }

        if self.department_filter:
            query["$and"].append({"context.department": self.department_filter})

        # Find matching users
        matching_users = await User.find(query)

        # Filter by minimum skill match count
        filtered_users = []
        for user in matching_users:
            match_count = len(set(user.skills) & set(self.required_skills))
            if match_count >= self.min_skill_match:
                filtered_users.append({
                    "id": user.id,
                    "name": user.name,
                    "email": user.email,
                    "department": user.department,
                    "matching_skills": list(set(user.skills) & set(self.required_skills)),
                    "match_score": match_count / len(self.required_skills)
                })

        # Sort by match score (highest first)
        filtered_users.sort(key=lambda x: x["match_score"], reverse=True)

        self.response = {
            "required_skills": self.required_skills,
            "department_filter": self.department_filter,
            "min_skill_match": self.min_skill_match,
            "matching_users": filtered_users,
            "total_matches": len(filtered_users)
        }

if __name__ == "__main__":
    server.run()
```

**API Usage Examples:**
```bash
# Network analysis
curl -X POST "http://localhost:8000/api/users/network-analysis" \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "alice-123",
    "max_depth": 2,
    "include_departments": ["engineering", "product"],
    "active_only": true
  }'

# Skill matching
curl -X POST "http://localhost:8000/api/users/skill-matching" \
  -H "Content-Type: application/json" \
  -d '{
    "required_skills": ["python", "javascript", "react"],
    "department_filter": "engineering",
    "min_skill_match": 2
  }'
```

## EndpointField Parameter Reference

The `EndpointField` provides comprehensive parameter control for API endpoints:

```python
from jvspatial.api.endpoint.router import EndpointField
from typing import Optional, List

class ExampleWalker(Walker):
    # Basic field with validation
    name: str = EndpointField(
        description="User name",
        examples=["Alice", "Bob"],
        min_length=1,
        max_length=100
    )

    # Numeric field with constraints
    age: int = EndpointField(
        description="User age",
        ge=0,
        le=150,
        examples=[25, 30, 45]
    )

    # Optional field with custom API name
    user_id: Optional[str] = EndpointField(
        default=None,
        endpoint_name="userId",  # Shows as "userId" in API
        description="Unique user identifier",
        pattern=r"^[a-zA-Z0-9_-]+$"
    )

    # Grouped parameters (create nested objects in API)
    min_price: Optional[float] = EndpointField(
        default=None,
        endpoint_group="filters",  # Groups under "filters" object
        ge=0.0,
        description="Minimum price filter"
    )

    max_price: Optional[float] = EndpointField(
        default=None,
        endpoint_group="filters",  # Groups under "filters" object
        ge=0.0,
        description="Maximum price filter"
    )

    # Hidden field (not in API docs but still accessible)
    api_key: str = EndpointField(
        default="default_key",
        endpoint_hidden=True,  # Hidden from OpenAPI documentation
        description="Internal API key"
    )

    # Excluded field (not exposed in API at all)
    internal_cache: dict = EndpointField(
        default_factory=dict,
        exclude_endpoint=True  # Completely excluded from endpoint
    )

    # Deprecated field with migration guidance
    old_parameter: Optional[str] = EndpointField(
        default=None,
        endpoint_deprecated=True,  # Marked as deprecated in docs
        description="DEPRECATED: Use 'userId' instead"
    )
```

### Complete Parameter Options

```python
EndpointField(
    default=...,                    # Field default value
    default_factory=...,            # Factory function for default

    # Standard Pydantic validation
    title="Field Title",            # OpenAPI title override
    description="Field description", # OpenAPI description
    examples=["example1", "example2"], # OpenAPI examples

    # Numeric constraints
    gt=0,                          # Greater than
    ge=0,                          # Greater than or equal
    lt=100,                        # Less than
    le=100,                        # Less than or equal
    multiple_of=5,                 # Must be multiple of value

    # String constraints
    min_length=1,                  # Minimum string length
    max_length=50,                 # Maximum string length
    pattern=r"^[a-zA-Z]+$",        # Regex pattern validation

    # Array/List constraints
    min_items=1,                   # Minimum array length
    max_items=10,                  # Maximum array length

    # Endpoint-specific configuration
    exclude_endpoint=False,         # Exclude from endpoint entirely
    endpoint_name="customName",     # Custom parameter name in API
    endpoint_required=None,         # Override required status (True/False/None)
    endpoint_hidden=False,          # Hide from OpenAPI docs
    endpoint_deprecated=False,      # Mark as deprecated
    endpoint_group="groupName",     # Group related parameters
    endpoint_constraints={          # Additional OpenAPI constraints
        "format": "email",
        "pattern": r"^[A-Z]{2}-\d{4}$"
    }
)
```

## Integration Patterns

### Startup Data Initialization

```python
@server.on_startup
async def initialize_sample_data():
    """Initialize sample data on server startup."""
    # Check if we already have data
    user_count = await User.count()
    if user_count > 0:
        print(f"Found {user_count} existing users, skipping initialization")
        return

    # Create sample users
    sample_users = [
        {"name": "Alice Johnson", "email": "alice@company.com", "department": "engineering", "skills": ["python", "javascript"]},
        {"name": "Bob Smith", "email": "bob@company.com", "department": "product", "skills": ["design", "figma"]},
        {"name": "Carol Davis", "email": "carol@company.com", "department": "engineering", "skills": ["python", "go"]}
    ]

    created_users = []
    for user_data in sample_users:
        user = await User.create(**user_data)
        created_users.append(user)

    # Create some collaborations
    if len(created_users) >= 2:
        collab = await Collaboration.create(
            source=created_users[0],
            target=created_users[2],
            project="API Development",
            start_date="2024-01-15"
        )
        await created_users[0].connect(created_users[2], edge=Collaboration)

    print(f"Initialized {len(created_users)} sample users with collaborations")

@server.on_shutdown
async def cleanup():
    """Cleanup tasks on shutdown."""
    print("API server shutting down...")
```

### Error Handling and Validation

```python
from fastapi import HTTPException

@endpoint("/api/users/update", methods=["PUT"])
class UpdateUser(Walker):
    user_id: str = EndpointField(description="User ID to update")
    name: Optional[str] = EndpointField(default=None, min_length=1, max_length=100)
    email: Optional[str] = EndpointField(default=None, pattern=r'^[^@]+@[^@]+\.[^@]+$')
    department: Optional[str] = EndpointField(default=None)
    skills: Optional[List[str]] = EndpointField(default=None)

    @on_visit(Node)
    async def update_user(self, here: Node):
        # Validate user exists
        user = await User.get(self.user_id)
        if not user:
            self.response = {"error": "User not found", "status": 404}
            return

        # Validate email uniqueness if provided
        if self.email and self.email != user.email:
            existing = await User.find_one({"context.email": self.email})
            if existing:
                self.response = {"error": "Email already in use", "status": 400}
                return

        # Update fields
        update_data = {}
        if self.name is not None:
            update_data["name"] = self.name
        if self.email is not None:
            update_data["email"] = self.email
        if self.department is not None:
            update_data["department"] = self.department
        if self.skills is not None:
            update_data["skills"] = self.skills

        # Apply updates
        for field, value in update_data.items():
            setattr(user, field, value)

        await user.save()

        self.response = {
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "department": user.department,
                "skills": user.skills
            },
            "updated_fields": list(update_data.keys()),
            "status": "updated"
        }
```

## Best Practices and Patterns

### 1. Entity-Centric Design

```python
# Good: Use entity-centric operations
@endpoint("/api/users/search")
class SearchUsers(Walker):
    @on_visit(Node)
    async def search(self, here: Node):
        # Direct entity operations
        users = await User.find({"context.active": True})
        total = await User.count()

# Bad: Direct database access
class OldSearchUsers(Walker):
    @on_visit(Node)
    async def search(self, here: Node):
        # Don't do this - bypasses entity layer
        db = get_database()
        users = await db.find("user", {"active": True})
```

### 2. MongoDB-Style Queries

```python
# Good: Use MongoDB-style queries for complex filtering
@endpoint("/api/products/advanced-search")
class AdvancedSearch(Walker):
    @on_visit(Node)
    async def search(self, here: Node):
        query = {
            "$and": [
                {"context.category": "electronics"},
                {"context.price": {"$gte": 100, "$lte": 1000}},
                {"context.name": {"$regex": "laptop", "$options": "i"}}
            ]
        }
        products = await Product.find(query)

# Bad: Python-level filtering
class BadSearch(Walker):
    @on_visit(Node)
    async def search(self, here: Node):
        all_products = await Product.all()  # Loads everything
        filtered = [p for p in all_products if p.price >= 100]  # Inefficient
```

### 3. Use Object Pagination for Large Datasets

```python
# Good: Use ObjectPager for efficient pagination
@endpoint("/api/users/list")
class ListUsers(Walker):
    page: int = EndpointField(default=1, ge=1)
    page_size: int = EndpointField(default=20, ge=1, le=100)

    @on_visit(Node)
    async def list_users(self, here: Node):
        from jvspatial.core.pager import ObjectPager

        pager = ObjectPager(
            User,
            page_size=self.page_size,
            filters={"context.active": True},
            order_by="name"
        )

        users = await pager.get_page(self.page)
        pagination_info = pager.to_dict()

        self.response = {
            "users": [user.export() for user in users],
            "pagination": pagination_info
        }
```

### 4. Semantic Filtering in Graph Traversal

```python
# Good: Use semantic filtering with nodes() method
@endpoint("/api/users/connections")
class UserConnections(Walker):
    user_id: str = EndpointField(description="User ID to analyze")

    @on_visit(User)
    async def analyze_connections(self, here: User):
        if here.id == self.user_id:
            # Use semantic filtering for connected users
            colleagues = await here.nodes(
                node=['User'],
                department=here.department,  # Simple filtering
                active=True
            )

            # Advanced filtering with MongoDB-style queries
            skilled_colleagues = await here.nodes(
                node=[{
                    'User': {
                        "context.skills": {"$in": ["python", "javascript"]},
                        "context.active": True
                    }
                }]
            )

            self.response = {
                "user": {"id": here.id, "name": here.name},
                "colleagues": [u.export() for u in colleagues],
                "skilled_colleagues": [u.export() for u in skilled_colleagues]
            }
```

### 5. Error Handling and Validation

```python
# Good: Comprehensive error handling
@endpoint("/api/users/create")
class CreateUser(Walker):
    name: str = EndpointField(min_length=1, max_length=100)
    email: str = EndpointField(pattern=r'^[^@]+@[^@]+\.[^@]+$')
    department: str = EndpointField()

    @on_visit(Node)
    async def create_user(self, here: Node):
        try:
            # Check for existing user
            existing = await User.find_one({"context.email": self.email})
            if existing:
                self.response = {
                    "error": "Email already exists",
                    "status": "conflict",
                    "code": 409
                }
                return

            # Create new user
            user = await User.create(
                name=self.name,
                email=self.email,
                department=self.department
            )

            self.response = {
                "user": user.export(),
                "status": "created",
                "code": 201
            }

        except ValidationError as e:
            self.response = {
                "error": "Validation failed",
                "details": str(e),
                "status": "validation_error",
                "code": 400
            }
        except Exception as e:
            self.response = {
                "error": "Internal server error",
                "status": "error",
                "code": 500
            }
```

### 6. Proper API Documentation

```python
# Good: Rich documentation with examples
@endpoint("/api/products/search", methods=["POST"])
class ProductSearch(Walker):
    """Search products with advanced filtering and pagination.

    This endpoint allows searching products using various filters including
    category, price range, and text search. Results are paginated for
    efficient handling of large product catalogs.
    """

    query: str = EndpointField(
        description="Search query for product names and descriptions",
        examples=["laptop", "gaming mouse", "wireless headphones"],
        min_length=1,
        max_length=100
    )

    category: Optional[str] = EndpointField(
        default=None,
        description="Filter by product category",
        examples=["electronics", "books", "clothing", "home"]
    )

    price_range: Optional[dict] = EndpointField(
        default=None,
        description="Price range filter with min/max values",
        examples=[{"min": 10.0, "max": 100.0}, {"min": 50.0}]
    )
```

## Authentication Integration

The jvspatial REST API includes comprehensive authentication support with JWT tokens, API keys, and role-based access control:

### Quick Authentication Setup

```python
from jvspatial.api import create_server
from jvspatial.api.auth import configure_auth, AuthenticationMiddleware

# Configure authentication
configure_auth(
    jwt_secret_key="your-secret-key",
    jwt_expiration_hours=24,
    rate_limit_enabled=True
)

# Create server with authentication
server = create_server(title="Authenticated API")
server.app.add_middleware(AuthenticationMiddleware)
```

### Endpoint Protection Levels

```python
from jvspatial.api import endpoint  # Public endpoints
from jvspatial.api.auth import auth_endpoint, admin_endpoint

# 1. Public endpoints - no authentication required
@endpoint("/public/data")
async def public_data():
    return {"message": "Anyone can access"}

@endpoint("/public/search")
class PublicSearch(Walker):
    @on_visit(Node)
    async def search(self, here: Node):
        # Public search logic
        pass

# 2. Authenticated endpoints - login required
@auth_endpoint("/protected/user-data")
async def user_data():
    return {"message": "Must be logged in"}

@auth_endpoint("/protected/spatial-query")
class ProtectedSpatialQuery(Walker):
    @on_visit(Node)
    async def query(self, here: Node):
        # Protected spatial operations
        pass

# 3. Permission-based endpoints
@auth_endpoint("/reports/generate", permissions=["generate_reports"])
async def generate_report():
    return {"message": "Requires generate_reports permission"}

# 4. Role-based endpoints
@auth_endpoint("/admin/settings", roles=["admin"])
async def admin_settings():
    return {"message": "Admin role required"}

# 5. Admin-only endpoints (shortcut)
@admin_endpoint("/admin/users")
async def manage_users():
    return {"message": "Admin access only"}
```

### Authentication in Walker Endpoints

```python
from jvspatial.api.auth import auth_walker_endpoint, get_current_user

@auth_endpoint(
    "/spatial/analysis",
    permissions=["analyze_spatial_data"],
    roles=["analyst", "admin"]
)
class SpatialAnalysis(Walker):
    region: str = EndpointField(description="Target region")

    @on_visit(City)
    async def analyze_cities(self, here: City):
        current_user = get_current_user(self.request)

        # Check spatial permissions
        if not current_user.can_access_region(self.region):
            self.response = {"error": "Access denied to region"}
            return

        if not current_user.can_access_node_type("City"):
            return  # Skip inaccessible node types

        # Perform analysis for authorized user
        self.response = {
            "analysis": f"Spatial analysis of {here.name}",
            "user": current_user.username,
            "permissions": current_user.permissions
        }
```

### Built-in Authentication Endpoints

All authentication endpoints are automatically registered:

**Public Authentication:**
- `POST /auth/register` - User registration
- `POST /auth/login` - User login with JWT tokens
- `POST /auth/refresh` - Token refresh
- `POST /auth/logout` - User logout

**Authenticated User Management:**
- `GET /auth/profile` - Get user profile
- `PUT /auth/profile` - Update user profile
- `POST /auth/api-keys` - Create API key
- `GET /auth/api-keys` - List user's API keys
- `DELETE /auth/api-keys/{key_id}` - Revoke API key

**Admin User Management:**
- `GET /auth/admin/users` - List all users
- `PUT /auth/admin/users/{user_id}` - Update user
- `DELETE /auth/admin/users/{user_id}` - Delete user
- `GET /auth/admin/sessions` - List active sessions

### API Key Authentication

```python
# Create API key endpoint
@auth_endpoint("/create-service-key", methods=["POST"])
async def create_service_key(request: Request):
    from jvspatial.api.auth import APIKey, get_current_user

    user = get_current_user(request)
    api_key = await APIKey.create(
        name="Data Export Service",
        key_id="export-service-1",
        key_hash=APIKey.hash_key("secret-key-123"),
        user_id=user.id,
        allowed_endpoints=["/api/export/*"],
        rate_limit_per_hour=5000
    )

    return {
        "key_id": api_key.key_id,
        "secret": "secret-key-123",  # Only shown once
        "allowed_endpoints": api_key.allowed_endpoints
    }

# Use API key in requests:
# curl -H "X-API-Key: secret-key-123" http://localhost:8000/api/export/data
```

### Spatial Permissions

Users can be restricted to specific regions and node types:

```python
@auth_endpoint("/geo/query", permissions=["read_spatial"])
class GeoQuery(Walker):
    target_region: str = EndpointField(examples=["north_america", "europe"])

    @on_visit(Node)
    async def geo_search(self, here: Node):
        current_user = get_current_user(self.request)

        # Spatial region access control
        if hasattr(here, 'region') and not current_user.can_access_region(here.region):
            return  # Skip inaccessible regions

        # Node type access control
        if not current_user.can_access_node_type(here.__class__.__name__):
            return  # Skip inaccessible node types

        # Process accessible nodes
        if "results" not in self.response:
            self.response = {"results": [], "user_permissions": {
                "allowed_regions": current_user.allowed_regions,
                "allowed_node_types": current_user.allowed_node_types
            }}

        self.response["results"].append(here.export())
```

### Rate Limiting

Automatic rate limiting per user:

```python
# Configure global rate limits
configure_auth(
    rate_limit_enabled=True,
    default_rate_limit_per_hour=1000
)

# Per-user rate limits
user.rate_limit_per_hour = 5000  # Premium user
await user.save()
```

### Enhanced Response Handling with Authentication

```python
@auth_endpoint("/secure/process", permissions=["process_data"])
class SecureProcessor(Walker):
    @on_visit(Node)
    async def secure_process(self, here: Node):
        current_user = get_current_user(self.request)

        # Authentication-aware error handling
        if not current_user.has_permission("advanced_processing"):
            return self.endpoint.forbidden(
                message="Advanced processing requires additional permissions",
                details={"required_permission": "advanced_processing"}
            )

        # Rate limit check
        if self._is_rate_limited(current_user):
            return self.endpoint.error(
                message="Rate limit exceeded",
                status_code=429,
                headers={"Retry-After": "3600"}
            )

        # Process with user context
        result = await self._process_with_user_permissions(here, current_user)

        return self.endpoint.success(
            data=result,
            message="Processing completed",
            headers={"X-User-ID": current_user.id}
        )
```

📖 **[Complete Authentication Guide →](authentication.md)**

## Benefits of Current Approach

1. **Entity-Centric**: Direct integration with Node.find(), User.create(), etc.
2. **MongoDB Queries**: Familiar, powerful query syntax across all backends
3. **Type Safety**: Full IDE support and static analysis with Pydantic
4. **Rich Documentation**: Automatic OpenAPI generation with examples
5. **Object Pagination**: Efficient handling of large datasets
6. **Semantic Filtering**: Advanced graph traversal capabilities
7. **Performance**: Database-level operations for optimal speed
8. **Maintainability**: Clean, readable code with proper separation of concerns
9. **Security**: Enterprise-grade authentication with JWT and API keys
10. **Spatial Permissions**: Region and node type access control

## Migration from Legacy Patterns

If migrating from older REST API patterns:

### Before (Legacy)
```python
# Old pattern - manual FastAPI setup
from fastapi import FastAPI
app = FastAPI()

@app.post("/search")
async def search_products(query: str):
    # Manual database operations
    db = get_database()
    results = await db.find("products", {"name": query})
    return results
```

### After (Current)
```python
# New pattern - entity-centric with server class
from jvspatial.api import Server, endpoint

server = Server(title="Product API")

@endpoint("/api/products/search")
class SearchProducts(Walker):
    query: str = EndpointField(description="Search query")

    @on_visit(Node)
    async def search(self, here: Node):
        # Entity-centric operations
        products = await Product.find({
            "context.name": {"$regex": self.query, "$options": "i"}
        })
        self.response = {"products": [p.export() for p in products]}
```

## See Also

- [Server API Documentation](server-api.md) - Complete Server class reference
- [Entity Reference](entity-reference.md) - API reference for entities
- [MongoDB-Style Query Interface](mongodb-query-interface.md) - Query syntax for endpoints
- [Object Pagination Guide](pagination.md) - Paginating API results
- [Examples](examples.md) - API examples and patterns
- [GraphContext & Database Management](graph-context.md) - Database integration

---

**[← Back to README](../../README.md)** | **[Server API →](server-api.md)**
