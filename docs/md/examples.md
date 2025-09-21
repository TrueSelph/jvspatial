# jvspatial Examples

This document showcases key examples that demonstrate the range of capabilities and features of the jvspatial library - a powerful object-spatial ORM for building connected graph applications with spatial awareness.

## Table of Contents

1. [Core ORM Demo](#core-orm-demo) - Basic object-spatial ORM concepts
2. [Travel Graph](#travel-graph) - Spatial operations and walker patterns
3. [Agent Graph](#agent-graph) - Hierarchical systems with API endpoints
4. [Dynamic Server](#dynamic-server) - Runtime endpoint registration
5. [GraphContext Demo](#graphcontext-demo) - Database dependency injection
6. [Semantic Filtering](#semantic-filtering) - Advanced query capabilities

---

## Core ORM Demo

**File**: [`examples/orm_demo.py`](examples/orm_demo.py)

**What it demonstrates**:
- Basic Node and Edge creation
- Semantic connection syntax
- Walker-based traversal
- Database-optimized queries

### Key Features Shown

```python path=examples/orm_demo.py start=15
class City(Node):
    """Example city node."""
    name: str = Field(default="")
    population: int = Field(default=0)

class Highway(Edge):
    """Example highway edge."""
    distance: float = Field(default=0.0)
    lanes: int = Field(default=2)
```

**Elegant Connection Interface**:
```python path=examples/orm_demo.py start=71
highway1 = await new_york.connect(chicago, Highway, distance=790.0, lanes=4)
```

**Database-Optimized Queries**:
```python path=examples/orm_demo.py start=119
# MongoDB-style queries with context prefix
large_cities = await City.find({"context.population": {"$gt": 5000000}})
```

**Walker Traversal**:
```python path=examples/orm_demo.py start=29
class TravelWalker(Walker):
    @on_visit(City)
    async def visit_city(self, here: City):
        print(f"🚶 Visiting {here.name} (pop: {here.population:,})")
        self.cities_visited.append(here.name)
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

    @on_visit(City)
    async def load_cargo(self, here: City):
        # Complex cargo loading logic based on city characteristics
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

**API Endpoint Integration**:
```python path=examples/agent_graph.py start=116
@walker_endpoint("/api/agents/interact", methods=["POST"])
class InteractWalker(Walker):
    target_agent_name: str = EndpointField(
        default="",
        description="Name of specific agent to target (optional)",
        examples=["ProductionAgent", "TestAgent"],
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
@server.walker("/tasks/create")
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
- Backward compatibility with original API

### Key Features Shown

**Original API (No Changes Needed)**:
```python path=examples/graphcontext_demo.py start=65
# All original syntax works exactly the same!
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

- **`crud_demo.py`** - Basic CRUD operations
- **`database_switching_example.py`** - Multiple database backends
- **`endpoint_decorator_demo.py`** - API endpoint patterns
- **`multi_target_hooks_demo.py`** - Advanced walker hooks
- **`object_pagination_demo.py`** - Pagination and performance
- **`testing_with_graphcontext.py`** - Testing strategies
- **`traversal_demo.py`** - Graph traversal patterns
- **`unified_query_interface_example.py`** - Advanced query interfaces

## Running the Examples

Each example can be run independently:

```bash
cd examples/
python orm_demo.py
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