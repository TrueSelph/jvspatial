# jvspatial Examples

This document showcases key examples that demonstrate the range of capabilities and features of the jvspatial library - a powerful object-spatial ORM for building connected graph applications with spatial awareness.

## 🎯 **Standard Implementation Examples** (Recommended Starting Point)

These examples serve as the **standard reference implementation** for building custom jvspatial APIs:

### 1. **Authenticated API Example** (Complete CRUD with Authentication)
**File**: [`examples/api/authenticated_endpoints_example.py`](../../examples/api/authenticated_endpoints_example.py)

**What it demonstrates**:
- ✅ Complete CRUD operations (Create, Read, Update, Delete)
- ✅ JWT-based authentication and authorization
- ✅ Permission and role-based access control
- ✅ Entity-centric database operations (`UserNode.get()`, `ProductNode.create()`, etc.)
- ✅ Pagination with `ObjectPager`
- ✅ Response schemas with examples
- ✅ Walker-based analytics endpoints
- ✅ Automatic authentication endpoint registration (login, register, logout)

**Key Features**:
```python
# Server with authentication enabled
server = Server(
    title="Authenticated CRUD API Example",
    auth_enabled=True,
    jwt_auth_enabled=True,
    db_type="json",
    db_path="./jvdb"
)

# Protected endpoint with permissions
@endpoint("/users", methods=["GET"], auth=True, permissions=["read_users"])
async def list_users(page: int = 1, per_page: int = 10):
    pager = ObjectPager(UserNode, page_size=per_page)
    users = await pager.get_page(page=page)
    return {"users": [user.export() for user in users], ...}

# Entity-centric CRUD operations
user = await UserNode.create(name="John", email="john@example.com")
await user.save()
await user.delete()
```

**Use this example when**: You need a full-featured API with authentication, CRUD operations, and role-based access control.

### 2. **Unauthenticated API Example** (Public Read-Only API)
**File**: [`examples/api/unauthenticated_endpoints_example.py`](../../examples/api/unauthenticated_endpoints_example.py)

**What it demonstrates**:
- ✅ Public endpoints (no authentication required)
- ✅ Read-only operations (GET endpoints)
- ✅ Listing with pagination and filtering
- ✅ Entity-centric retrieval operations
- ✅ Response schemas with examples
- ✅ **No authentication endpoints** (login/register/logout are NOT registered)

**Key Features**:
```python
# Server without authentication
server = Server(
    title="Public API Example",
    auth_enabled=False,  # No auth endpoints will be registered
    db_type="json",
    db_path="./jvdb_public"
)

# Public endpoint with pagination
@endpoint("/articles", methods=["GET"])
async def list_articles(page: int = 1, per_page: int = 10, category: Optional[str] = None):
    pager = ObjectPager(ArticleNode, page_size=per_page)
    articles = await pager.get_page(page=page, additional_filters={"category": category} if category else {})
    return {"articles": [article.export() for article in articles], ...}
```

**Use this example when**: You need a public API for reading data, content delivery, or read-only services.

---

## Table of Contents

**Standard Examples** (Start Here):
1. [Authenticated API Example](#1-authenticated-api-example-complete-crud-with-authentication) ⭐
2. [Unauthenticated API Example](#2-unauthenticated-api-example-public-read-only-api) ⭐

**Additional Examples**:
3. [Graph Visualization](#graph-visualization) - Export graphs in DOT/Mermaid formats
4. [Core ORM Demo](#core-orm-demo) - Basic object-spatial ORM concepts
5. [Travel Graph](#travel-graph) - Spatial operations and walker patterns
6. [Agent Graph](#agent-graph) - Hierarchical systems with API endpoints
7. [Authentication Demo](#authentication-demo) - JWT tokens, API keys, and RBAC
8. [Dynamic Server](#dynamic-server) - Runtime endpoint registration
9. [GraphContext Demo](#graphcontext-demo) - Database dependency injection
10. [Semantic Filtering](#semantic-filtering) - Advanced query capabilities

---

## Graph Visualization

**File**: [`examples/core/graph_visualization_example.py`](../../examples/core/graph_visualization_example.py)

**What it demonstrates**:
- ✅ Creating interconnected graph structures
- ✅ Exporting graphs in DOT (Graphviz) format
- ✅ Exporting graphs in Mermaid format
- ✅ Custom filtering and styling
- ✅ Multiple layout options
- ✅ File output and return value patterns

**Key Features**:
```python
from jvspatial.core.graph import generate_graph_dot, generate_graph_mermaid

# Generate DOT format (returns value, optionally saves to file)
dot_graph = await generate_graph_dot(
    context,
    graph_name="company_graph",
    rankdir="LR",
    node_shape="box",
    include_attributes=True,
    output_file="graph.dot"  # Optional: saves to file
)

# Generate Mermaid format
mermaid_graph = await generate_graph_mermaid(
    context,
    graph_type="flowchart",
    direction="LR",
    include_attributes=True,
    output_file="graph.mermaid"  # Optional: saves to file
)

# Using GraphContext convenience method
graph = await context.export_graph(
    format="dot",
    output_file="graph.dot",
    rankdir="LR"
)
```

**Use this example when**: You need to visualize your graph structure for documentation, debugging, or analysis.

**See also**: [Graph Visualization Guide](../graph-visualization.md) - Complete documentation


# Usage
walker = TravelWalker()
await walker.spawn(start=city)
report = walker.get_report()  # List of reported items
visited = walker.cities_visited  # Internal state
```

---

## Travel Graph

**File**: [`examples/travel_graph.py`](examples/travel_graph.py)

**What it demonstrates**:
- Spatial calculations and geographic data
- Complex walker patterns with state management
- MongoDB-style spatial queries
- Edge-typed graph traversal

### Key Features Shown

**Spatial Queries**:
```python path=examples/travel_graph.py start=69
bounded_cities = await City.find({
    "$and": [
        {"context.latitude": {"$gte": min_lat, "$lte": max_lat}},
        {"context.longitude": {"$gte": min_lon, "$lte": max_lon}},
    ]
})
```

**Haversine Distance Calculation**:
```python path=examples/travel_graph.py start=31
def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two coordinates using Haversine formula."""
    earth_radius = 6371  # Earth's radius in kilometers
    # ... mathematical calculation
```

**Edge-Type Filtering**:
```python path=examples/travel_graph.py start=140
highway_neighbors = await here.nodes(direction="out", edge=[Highway])
```

**Stateful Walker with Cargo Management**:
```python path=examples/travel_graph.py start=162
class FreightTrain(Walker):
    max_cargo_capacity: int = 5000  # tons
    current_cargo_weight: int = 0

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.route_cities = []  # Track visited cities
        self.cargo_list = []  # Track cargo loaded

    @on_visit(City)
    async def load_cargo(self, here: City):
        self.route_cities.append(here.name)
        # Complex cargo loading logic
        self.report({"cargo_loaded": {...}})  # Report each cargo operation
```

---

## Agent Graph

**File**: [`examples/agent_graph.py`](examples/agent_graph.py)

**What it demonstrates**:
- Hierarchical agent systems
- API endpoint integration with walker patterns
- Entity-centric CRUD operations
- Type annotations and validation

### Key Features Shown

**Hierarchical Structure**: Root → App → Agents → MyAgent → Actions

**API Endpoint Integration with Semantic Responses**:
```python path=examples/agent_graph.py start=116
from jvspatial.api.endpoint.router import EndpointField

@endpoint("/api/agents/interact", methods=["POST"])
class InteractWalker(Walker):
    target_agent_name: str = EndpointField(
        default="",
        description="Name of specific agent to target (optional)",
        examples=["ProductionAgent", "TestAgent"],
    )

    @on_visit(Node)
    async def process(self, here: Node):
        # Use endpoint semantic responses for API endpoints
        return self.endpoint.success(
            data={"result": "processed"},
            message="Processing complete"
        )
```

**Entity-Centric CRUD**:
```python path=examples/agent_graph.py start=147
app_nodes = await App.find({"context.status": "active"})
```

**Complex Query Building**:
```python path=examples/agent_graph.py start=193
query_filters: Dict[str, Any] = {"context.published": True}
if not self.include_inactive:
    query_filters["context.status"] = "active"
```

**Spatial Properties in Agents**:
```python path=examples/agent_graph.py start=53
class MyAgent(Node):
    name: str = ""
    published: bool = True
    latitude: float = 0.0
    longitude: float = 0.0
    capabilities: List[str] = Field(default_factory=list)
```

---

## Authentication Demo

**File**: [`examples/auth_demo.py`](examples/auth_demo.py)

**What it demonstrates**:
- Complete JWT token authentication system
- API key authentication for services
- Role-based access control (RBAC)
- Spatial region and node type permissions
- Multi-level endpoint protection
- User management and session handling
- Rate limiting and security middleware

### Key Features Shown

**Authentication Configuration**:
```python path=examples/auth_demo.py start=81
configure_auth(
    # JWT Configuration
    jwt_secret_key=jwt_secret,
    jwt_algorithm="HS256",
    jwt_expiration_hours=24,
    jwt_refresh_expiration_days=7,  # Shorter for demo

    # API Key Configuration
    api_key_header="X-API-Key",
    api_key_query_param="api_key",

    # Rate Limiting
    rate_limit_enabled=True,
    default_rate_limit_per_hour=100,  # Lower for demo

    # Security (relaxed for demo)
    require_https=False,
    session_cookie_secure=False,
    session_cookie_httponly=True
)
```

**User Creation with Spatial Permissions**:
```python path=examples/auth_demo.py start=175
# 3. Regional Analyst with Spatial Restrictions
regional_user = await User.create(
    email="regional_user@example.com",
    password_hash=User.hash_password("regional123"),
    is_admin=False,
    is_active=True,
    roles=["analyst", "regional_viewer"],
    permissions=["read_spatial_data", "analyze_data", "export_reports"],
    allowed_regions=["north_america"],  # Only North America
    allowed_node_types=["City", "Highway"],  # No POIs
    max_traversal_depth=15,
    rate_limit_per_hour=2000
)
```

**Multi-Level Endpoint Protection**:
```python path=examples/auth_demo.py start=366
@endpoint("/public/info", methods=["GET"])
async def public_info():
    """Public endpoint - no authentication required."""
    return {
        "message": "This is public information",
        "service": "jvspatial Authentication Demo",
        "version": "1.0.0",
        "authentication": "Not required for this endpoint",
        "timestamp": datetime.now().isoformat()
    }

@auth_endpoint("/protected/data", methods=["GET"])
async def protected_data(request: Request):
    """Protected endpoint requiring authentication."""
    current_user = get_current_user(request)

    return {
        "message": "This is protected data",
        "authentication": "Required - JWT token",
        "user": {
            "email": current_user.email,
            "roles": current_user.roles,
            "permissions": current_user.permissions
        },
        "timestamp": datetime.now().isoformat()
    }

@admin_endpoint("/admin/users", methods=["GET"])
async def admin_list_users(request: Request):
    """Admin endpoint to list all users."""
    current_user = get_current_user(request)

    all_users = await User.all()
    return {
        "message": "User management - Admin access only",
        "authentication": "JWT token + admin role required",
        "admin_user": current_user.email,
        "total_users": len(all_users),
        "users": [user.export() for user in all_users]
    }
```

**Spatial Access Control in Walker Endpoints**:
```python path=examples/auth_demo.py start=483
@auth_endpoint(
    "/protected/spatial-query",
    methods=["POST"],
    permissions=["read_spatial_data"]
)
class ProtectedSpatialQuery(Walker):
    """Protected spatial query walker with region-based access control."""

    region: str = EndpointField(
        description="Target region to query",
        examples=["north_america", "europe", "asia"]
    )

    @on_visit(Node)
    async def spatial_query(self, here: Node):
        current_user = get_current_user(self.request)

        # Check if user can access this region
        if not current_user.can_access_region(self.region):
            return self.endpoint.forbidden(
                message="Access denied to region",
                details={
                    "region": self.region,
                    "user_allowed_regions": current_user.allowed_regions
                }
            )
```

**API Key Authentication**:
```python path=examples/auth_demo.py start=705
@endpoint("/api/export/cities", methods=["GET"])
async def api_key_export_cities(request: Request):
    """Endpoint accessible via API key (demonstrates service authentication)."""

    # This endpoint will be accessible via API key due to middleware
    # Check if authenticated via API key
    api_key_user = getattr(request.state, 'api_key_user', None)
    jwt_user = getattr(request.state, 'current_user', None)

    auth_method = "Unknown"
    user_info = {}

    if api_key_user:
        auth_method = "API Key"
        user_info = {
            "api_key_name": api_key_user.get("name", "Unknown"),
            "key_id": api_key_user.get("key_id", "Unknown")
        }
    elif jwt_user:
        auth_method = "JWT Token"
        user_info = {
            "username": jwt_user.username,
            "roles": jwt_user.roles
        }
```

**Demo Accounts and Usage**:
```python path=examples/auth_demo.py start=334
"demo_accounts": {
    "admin": {
        "username": "demo_admin",
        "password": "admin123",
        "permissions": "Full admin access"
    },
    "user": {
        "username": "demo_user",
        "password": "user123",
        "permissions": "Read access to North America and Europe"
    },
    "regional": {
        "username": "regional_user",
        "password": "regional123",
        "permissions": "Analyst access limited to North America"
    }
}
```

### Running the Authentication Demo

```bash
cd examples/
python auth_demo.py
```

Then visit:
- **Dashboard**: http://localhost:8000/auth-demo - Demo overview and instructions
- **API Docs**: http://localhost:8000/docs - Interactive API documentation
- **Login**: POST /auth/login - Authenticate to get JWT tokens
- **Public**: GET /public/* - No authentication required
- **Protected**: GET /protected/* - JWT token required
- **Admin**: GET /admin/* - Admin role required

### Authentication Flow Examples

**1. User Registration:**
```bash
curl -X POST "http://localhost:8000/auth/register" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "newuser",
    "email": "user@example.com",
    "password": "password123",
    "confirm_password": "password123"
  }'
```

**2. User Login:**
```bash
curl -X POST "http://localhost:8000/auth/login" \
  -H "Content-Type: application/json" \
  -d '{
    "username": "demo_user",
    "password": "user123"
  }'
```

**3. Access Protected Endpoint:**
```bash
# Use token from login response
TOKEN="eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."

curl -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/protected/data"
```

**4. API Key Usage:**
```bash
curl -H "X-API-Key: demo-export-key-12345" \
  "http://localhost:8000/api/export/cities"
```

**5. Spatial Query with Permissions:**
```bash
curl -X POST "http://localhost:8000/protected/spatial-query" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "region": "north_america",
    "node_type": "City"
  }'
```

---

## Dynamic Server

**File**: [`examples/dynamic_server_demo.py`](examples/dynamic_server_demo.py)

**What it demonstrates**:
- Runtime endpoint registration
- Package discovery patterns
- Shared server instances
- Startup hooks and initialization

### Key Features Shown

**Server Creation with Enhanced Config**:
```python path=examples/dynamic_server_demo.py start=59
server = create_server(
    title="Dynamic Task Management API",
    description="Advanced task management with dynamic endpoint registration",
    version="2.0.0",
    debug=True,
    db_type="json",
    db_path="jvdb/dynamic_demo",
)
```

**Package Discovery**:
```python path=examples/dynamic_server_demo.py start=75
server.enable_package_discovery(
    enabled=True, patterns=["*_tasks", "*_workflows", "task_*", "demo_*"]
)
```

**Startup Hooks**:
```python path=examples/dynamic_server_demo.py start=83
@server.on_startup
async def initialize_sample_tasks():
    """Create sample data on startup."""
    tasks = [
        await Task.create(
            title="System Analysis",
            description="Analyze current system architecture",
            priority="high",
        ),
        # ... more tasks
    ]
```

**Dynamic Walker Registration**:
```python path=examples/dynamic_server_demo.py start=140
@endpoint("/tasks/create")
class CreateTask(Walker):
    title: str = EndpointField(
        description="Task title",
        examples=["Fix login bug", "Update documentation"],
        min_length=3,
        max_length=200,
    )
```

---

## GraphContext Demo

**File**: [`examples/graphcontext_demo.py`](examples/graphcontext_demo.py)

**What it demonstrates**:
- Database dependency injection
- Multiple database contexts
- Testing patterns with isolation
- Clean API design

### Key Features Shown

**Standard API**:
```python path=examples/graphcontext_demo.py start=65
# Standard entity creation syntax
chicago = await City.create(
    name="Chicago", population=2700000, latitude=41.88, longitude=-87.63
)
```

**Explicit GraphContext**:
```python path=examples/graphcontext_demo.py start=102
ctx = GraphContext(database=custom_db)

seattle = await ctx.create_node(
    City, name="Seattle", population=750000, latitude=47.61, longitude=-122.33
)
```

**Multiple Database Contexts**:
```python path=examples/graphcontext_demo.py start=141
# Main database for application data
main_ctx = GraphContext(database=main_db)

# Analytics database for logging/metrics
analytics_ctx = GraphContext(database=analytics_db)
```

**Multi-Database Support with Prime Database**:
For managing multiple databases with a prime database for core persistence, see [`examples/database/multi_database_example.py`](../../examples/database/multi_database_example.py):
```python
from jvspatial.db import create_database, get_database_manager, switch_database, unregister_database

# Prime database is automatically created for auth/sessions
manager = get_database_manager()
prime_db = manager.get_prime_database()

# Create and register additional databases
app_db = create_database("json", base_path="./app_data", register=True, name="app")

# Switch between databases
switch_database("app")  # For application data
switch_database("prime")  # Back to prime

# Remove a database
unregister_database("app")
```

**Testing Pattern**:
```python path=examples/graphcontext_demo.py start=194
# Create isolated test database
test_db = get_database(db_type="json", base_path=test_db_path)
test_ctx = GraphContext(database=test_db)
```

---

## Semantic Filtering

**File**: [`examples/semantic_filtering.py`](examples/semantic_filtering.py)

**What it demonstrates**:
- Advanced query capabilities with MongoDB-style operators
- Database-level optimization
- Complex filtering combining nodes and edges
- Performance-oriented query patterns

### Key Features Shown

**Simple Type Filtering**:
```python path=examples/semantic_filtering.py start=155
cities = await new_york.nodes(node="City")
```

**Property Filtering via kwargs**:
```python path=examples/semantic_filtering.py start=160
ma_connections = await new_york.nodes(state="MA")
```

**Complex Node Filtering with MongoDB Operators**:
```python path=examples/semantic_filtering.py start=169
large_cities = await new_york.nodes(
    node=[{"City": {"context.population": {"$gte": 1_000_000}}}]
)
```

**Complex Edge Filtering**:
```python path=examples/semantic_filtering.py start=189
fast_highways = await new_york.nodes(
    edge=[{"Highway": {"context.speed_limit": {"$gte": 65}}}]
)
```

**Combined Filters**:
```python path=examples/semantic_filtering.py start=195
good_free_roads = await new_york.nodes(
    edge=[{
        "Highway": {
            "context.condition": {"$ne": "poor"},
            "context.toll_road": False,
        }
    }]
)
```

---

## Additional Examples

The `examples/` directory contains many more specialized examples:

### Core Examples (All Passing)
- **`walker_traversal_demo.py`** - Walker traversal patterns
- **`walker_events_demo.py`** - Walker event communication system
- **`walker_reporting_demo.py`** - Walker reporting system with `report()` pattern
- **`database/multi_database_example.py`** - **Multi-database support with prime database** - Managing multiple databases, switching, and removing non-prime databases
- **`database_switching_example.py`** - Multiple database backends
- **`multi_target_hooks_demo.py`** - Advanced walker hooks with `@on_visit(TypeA, TypeB)`
- **`object_pagination_demo.py`** - Pagination and performance
- **`testing_with_graphcontext.py`** - Testing strategies with database isolation
- **`semantic_filtering.py`** - Advanced MongoDB-style queries
- **`enhanced_nodes_filtering.py`** - Enhanced filtering capabilities
- **`unified_query_interface_example.py`** - Advanced query interfaces
- **`exception_handling_demo.py`** - Error handling patterns

### Server Examples
- **`simple_dynamic_example.py`** - Dynamic endpoint registration patterns
- **`server_demo.py`** - Comprehensive server features
- **`auth_demo.py`** - JWT and API key authentication (runs indefinitely)
- **`scheduler_example.py`** - Scheduled tasks (runs indefinitely)
- **`dynamic_server_demo.py`** - Advanced dynamic endpoints
- **`endpoint_decorator_demo.py`** - Endpoint decorator patterns
- **`fastapi_server.py`** - FastAPI integration

## Running the Examples

Each example can be run independently:

```bash
cd examples/
python walker_traversal_demo.py
python travel_graph.py
python agent_graph.py
# ... etc
```

Some examples (like `dynamic_server_demo.py`) start web servers and should be accessed via HTTP endpoints.

## Key Architectural Concepts

1. **Objects**: Simple data storage units
2. **Nodes**: Connected objects that can be visited by walkers
3. **Edges**: Typed connections between nodes with their own properties
4. **Walkers**: Traverse nodes along edges, implementing business logic
5. **GraphContext**: Dependency injection for database connections
6. **Spatial Awareness**: Built-in support for geographic data and calculations

The examples demonstrate how these concepts work together to create powerful, maintainable graph applications with spatial capabilities.

## See Also

- **[Authentication System Documentation](authentication.md)** - Complete authentication guide with JWT, API keys, and RBAC
- **[Authentication Quickstart](auth-quickstart.md)** - Get authentication working in 5 minutes
- **[REST API with Authentication](rest-api.md#authentication-integration)** - Securing your API endpoints
- **[Server API Guide](server-api.md)** - Complete server configuration and setup
