# Using Objects, Nodes, Edges and Walkers

This document describes how to work with the jvspatial core module for graph operations, focusing on semantic simplicity and performance optimization.

## Architecture Overview

The jvspatial object-spatial ORM consists of four core components:

- **Objects**: Simple units of information stored in the database
- **Nodes**: Modified objects designed to be connected by edges and visited by walkers
- **Edges**: Connect nodes together
- **Walkers**: Traverse nodes along edges for graph analysis and operations

## Design Principles

- **Semantic Simplicity**: `node = Node()` and `node.connect(node_b)` work intuitively
- **Walker-Based Traversal**: `walker.spawn(start_node)` and `walker.visit(nodes)` for graph traversal
- **Abstracted Complexity**: Database operations handled automatically
- **Performance Optimized**: Queries performed at database level for efficiency
- **Ordered Traversals**: Maintains "add order" for graph traversals
- **Scalable**: Handles large graphs efficiently

## Basic Usage

### Creating Nodes

Creating nodes is straightforward:

```python
from jvspatial.core import Node

# Simple node creation
node_a = Node()
node_b = Node()

print(f"Created nodes: {node_a.id}, {node_b.id}")
```

### Connecting Nodes

Use the semantic `.connect()` method:

```python
# Connect two nodes
connection = await node_a.connect(node_b)

# Connection is bidirectional by default
print(f"Connection count: {node_a.connection_count}")  # 1
```

### Traversing Connections

Navigate the graph naturally:

```python
# Get all neighboring nodes
neighbors = await node_a.neighbors()

# Get nodes by direction
outgoing = await node_a.outgoing()
incoming = await node_a.incoming()

# Check if nodes are connected
is_connected = await node_a.is_connected_to(node_b)
```

## Custom Entity Types

Define your own node and edge types using Pydantic fields:

```python
from jvspatial.core import Node, Edge
from pydantic import Field

class City(Node):
    name: str = Field(default="")
    population: int = Field(default=0)
    latitude: float = Field(default=0.0)
    longitude: float = Field(default=0.0)

class Highway(Edge):
    distance: float = Field(default=0.0)
    lanes: int = Field(default=2)
    speed_limit: int = Field(default=65)
```

### Using Custom Types

```python
# Create cities
new_york = City(
    name="New York",
    population=8000000,
    latitude=40.7128,
    longitude=-74.0060
)

chicago = City(
    name="Chicago",
    population=2700000,
    latitude=41.8781,
    longitude=-87.6298
)

# Connect with custom edge
highway = await new_york.connect(
    chicago,
    Highway,
    distance=790.0,
    lanes=4,
    speed_limit=75
)
```

## Database Queries

The system provides database-level query optimization for performance:

### Finding Nodes

```python
# Find nodes by properties (database-level filtering)
large_cities = await City.find_by(population={"$gt": 5000000})

# Complex queries with multiple criteria
eastern_cities = await City.find({
    "context.longitude": {"$gt": -100},
    "context.population": {"$gt": 1000000}
})

# Limit results for performance
recent_nodes = await City.find({}, limit=100)
```

### Connection Queries

```python
# Check specific connection types
has_highway = await city_a.is_connected_to(city_b, Highway)

# Find all connections of a type
highways = await city_a.edges(Highway)

# Efficient neighbor access with limits
nearby_cities = await city_a.neighbors(limit=10)
```

## Connection Management

### Creating Connections

```python
# Basic connection
await node_a.connect(node_b)

# Connection with custom edge type
await city_a.connect(city_b, Highway, distance=100.0)

# Connection with direction
await node_a.connect(node_b, direction="out")
```

### Removing Connections

```python
# Remove all connections between nodes
disconnected = await node_a.disconnect(node_b)

# Remove specific edge type
disconnected = await city_a.disconnect(city_b, Highway)
```

### Advanced Connection Operations

```python
# Create node and connect in one operation
denver = await City.create_and_connect(
    chicago,
    Highway,
    name="Denver",
    population=715000,
    distance=920.0,
    lanes=4
)

# Check connection count
print(f"Chicago now has {chicago.connection_count} connections")
```

## Performance Features

### Edge Ordering Preservation

The system maintains the order in which connections were created:

```python
city = City(name="Hub City")

# Connect to multiple cities
await city.connect(City(name="City A"))
await city.connect(City(name="City B"))
await city.connect(City(name="City C"))

# Neighbors returned in connection order
neighbors = await city.neighbors()
# Returns: [City A, City B, City C] in that order
```

### Pagination for Large Graphs

Handle large object collections efficiently with built-in pagination:

```python
from jvspatial.core import ObjectPager, paginate_objects, paginate_by_field

# Simple pagination
cities = await paginate_objects(City, page=1, page_size=50)
more_cities = await paginate_objects(City, page=2, page_size=50)

# Pagination with filters
large_cities = await paginate_objects(
    City,
    filters={"population": {"$gt": 1000000}},
    page_size=25
)

# Field-based pagination (ordered results)
top_cities_by_population = await paginate_by_field(
    City,
    field="population",
    order="desc",
    page_size=20
)

# Advanced pagination with ObjectPager
pager = ObjectPager(
    City,
    page_size=100,
    filters={"population": {"$gt": 500000}},
    order_by="name",
    order_direction="asc"
)

# Process pages efficiently
while True:
    cities = await pager.next_page()
    if not cities:
        break
    await process_city_batch(cities)
```

### Batch Operations

Efficient operations for large graphs:

```python
# Batch node retrieval
node_ids = ["id1", "id2", "id3", "id4", "id5"]
query = {"id": {"$in": node_ids}}
nodes = await Node.find(query)

# Efficient connection traversal
neighbors = await hub_node.neighbors(limit=50)

# Paginated processing
async def process_large_graph():
    pager = ObjectPager(Node, page_size=200)
    total_processed = 0

    while True:
        nodes = await pager.next_page()
        if not nodes:
            break

        for node in nodes:
            await process_node(node)

        total_processed += len(nodes)
        print(f"Processed {total_processed} nodes")
```

### Database-Level Filtering

Queries are pushed to the database for efficiency:

```python
# This query runs at database level, not in Python
wealthy_cities = await City.find_by(
    population={"$gt": 1000000},
    economic_status="wealthy"
)

# Complex spatial queries (example)
nearby_cities = await City.find({
    "context.latitude": {"$gte": 40.0, "$lte": 41.0},
    "context.longitude": {"$gte": -75.0, "$lte": -73.0}
})
```

## Performance Monitoring

Enable performance monitoring to optimize your application:

```python
from jvspatial.core.context import (
    enable_performance_monitoring,
    get_performance_stats
)

# Enable monitoring
enable_performance_monitoring()

# Perform operations
city = City(name="Test City")
await city.connect(other_city)

# Get performance statistics
stats = get_performance_stats()
print(f"Total operations: {stats['total_operations']}")
print(f"Average duration: {stats['average_duration']:.3f}s")
```

## Working with Large Graphs

### Efficient Pagination

Use built-in pagination instead of manual offset/limit:

```python
# ✅ Good: Use built-in pagination
pager = ObjectPager(Node, page_size=100)
while True:
    nodes = await pager.next_page()
    if not nodes:
        break

    for node in nodes:
        await process_node(node)

# ✅ Also good: Simple pagination helper
for page in range(1, 11):  # Process first 10 pages
    nodes = await paginate_objects(Node, page=page, page_size=100)
    for node in nodes:
        await process_node(node)

# ❌ Less efficient: Manual offset/limit
page_size = 100
offset = 0

while True:
    nodes = await Node.find({}, limit=page_size, offset=offset)
    if not nodes:
        break

    for node in nodes:
        await process_node(node)

    offset += page_size
```

### Memory Management

```python
# Use limits to control memory usage
neighbors = await hub_node.neighbors(limit=20)

# Process connections in batches
for i in range(0, hub_node.connection_count, 50):
    batch_neighbors = await hub_node.neighbors(limit=50, offset=i)
    await process_neighbors(batch_neighbors)
```

## Error Handling

### Connection Errors

```python
try:
    await node_a.connect(node_b)
except Exception as e:
    print(f"Connection failed: {e}")

# Safe disconnection
success = await node_a.disconnect(node_b)
if not success:
    print("Disconnection failed or nodes weren't connected")
```

### Query Errors

```python
try:
    results = await City.find_by(invalid_field="value")
except ValueError as e:
    print(f"Invalid query: {e}")
```

## Best Practices

### 1. Use Semantic Methods

```python
# Preferred: semantic and clear
neighbors = await node.neighbors()

# Less preferred: more complex
query = await node.nodes()
filtered = await query.filter()
```

### 2. Database-Level Queries

```python
# Efficient: database filtering
large_cities = await City.find_by(population={"$gt": 5000000})

# Inefficient: Python filtering
all_cities = await City.all()
large_cities = [c for c in all_cities if c.population > 5000000]
```

### 3. Connection Limits and Pagination

```python
# Good: controlled memory usage
neighbors = await hub_node.neighbors(limit=100)

# Good: paginate large result sets
large_cities = await paginate_objects(
    City,
    filters={"population": {"$gt": 1000000}},
    page_size=50
)

# Good: process all nodes efficiently
pager = ObjectPager(City, page_size=100)
while True:
    cities = await pager.next_page()
    if not cities:
        break
    await analyze_cities(cities)

# Potentially problematic: unlimited results
neighbors = await hub_node.neighbors()  # Could return millions
all_cities = await City.all()  # Loads everything into memory
```

### 4. Type-Safe Operations

```python
# Type-safe connection checking
has_highway = await city_a.is_connected_to(city_b, Highway)

# Specific disconnection
await city_a.disconnect(city_b, Highway)
```

### 5. Batch Operations

```python
# Efficient: single operation
denver = await City.create_and_connect(chicago, Highway, **kwargs)

# Less efficient: multiple operations
denver = await City.create(**kwargs)
await denver.connect(chicago, Highway)
```

## Pagination and Large Graphs

When working with large graphs (thousands to millions of nodes), pagination becomes essential for memory management and performance. jvspatial provides comprehensive pagination support that operates at the database level for maximum efficiency.

### Why Use Pagination?

- **Memory Management**: Avoid loading massive datasets into memory
- **Performance**: Database-level filtering and limiting
- **Scalability**: Handle graphs of any size
- **User Experience**: Responsive applications with large datasets

### Pagination Patterns

#### 1. Simple Page-Based Pagination

```python
from jvspatial.core import paginate_nodes, City

# Get specific pages
page_1 = await paginate_nodes(City, page=1, page_size=50)
page_2 = await paginate_nodes(City, page=2, page_size=50)

# With filtering
active_users = await paginate_nodes(
    User,
    page=1,
    page_size=100,
    filters={"status": "active"}
)
```

#### 2. Ordered Pagination by Field

```python
from jvspatial.core import paginate_by_field, Product

# Get top products by rating
top_products = await paginate_by_field(
    Product,
    field="rating",
    order="desc",
    page_size=25
)

# Get cheapest products in electronics
cheap_electronics = await paginate_by_field(
    Product,
    field="price",
    order="asc",
    page_size=50,
    filters={"category": "electronics"}
)
```

#### 3. Streaming Pagination

```python
from jvspatial.core import NodePager, Customer

async def process_all_customers():
    """Process all customers in efficient batches."""
    pager = NodePager(Customer, page_size=100)
    total_processed = 0

    while True:
        customers = await pager.next_page()
        if not customers:
            break

        # Process batch
        for customer in customers:
            await analyze_customer(customer)

        total_processed += len(customers)
        print(f"Progress: {total_processed} customers processed")

    print(f"Completed processing {total_processed} total customers")
```

### Pagination with Walker Traversal

Combine pagination with walker traversal for memory-efficient graph analysis:

```python
from jvspatial.core import NodePager, Walker, on_visit, City

class CityAnalyzer(Walker):
    """Analyzes cities using paginated traversal."""

    def __init__(self):
        super().__init__()
        self.total_analyzed = 0

    async def analyze_all_cities(self):
        """Analyze all cities in paginated batches."""
        pager = NodePager(City, page_size=50)

        while True:
            cities = await pager.next_page()
            if not cities:
                break

            # Visit each city in the batch
            await self.visit(cities)

    @on_visit(City)
    async def analyze_city(self, here: City):
        """Analyze individual city."""
        self.total_analyzed += 1

        # Get limited neighbors to avoid memory issues
        neighbors = await here.neighbors(limit=10)

        self.response[here.id] = {
            "name": here.name,
            "population": here.population,
            "neighbor_count": len(neighbors),
            "avg_neighbor_population": sum(n.population for n in neighbors) / len(neighbors) if neighbors else 0
        }

# Usage
analyzer = CityAnalyzer()
await analyzer.analyze_all_cities()
print(f"Analyzed {analyzer.total_analyzed} cities")
```

### Performance Best Practices

#### 1. Choose Appropriate Page Sizes

```python
# Interactive UI: Small pages for responsiveness
ui_products = await paginate_nodes(Product, page_size=20)

# Batch processing: Medium pages for efficiency
processing_orders = NodePager(Order, page_size=100)

# Bulk operations: Large pages for throughput
bulk_export = NodePager(LogEntry, page_size=500)
```

#### 2. Use Database-Level Filtering

```python
# ✅ Good: Filter at database level
large_cities = await paginate_nodes(
    City,
    filters={"population": {"$gt": 1000000}}
)

# ❌ Bad: Filter in Python after loading
all_cities = await City.all()
large_cities = [c for c in all_cities if c.population > 1000000]
```

#### 3. Monitor Memory Usage

```python
import gc
from jvspatial.core import NodePager

async def memory_conscious_processing():
    """Process large datasets with memory management."""
    pager = NodePager(LargeNode, page_size=50)
    page_count = 0

    while True:
        nodes = await pager.next_page()
        if not nodes:
            break

        # Process nodes
        await process_node_batch(nodes)

        page_count += 1

        # Periodic cleanup
        if page_count % 10 == 0:
            gc.collect()
            print(f"Processed {page_count} pages, memory cleanup performed")
```

## Working with Walkers

Walkers are the traversal mechanism in jvspatial - they visit nodes along edges to analyze or operate on the graph.

### Creating Walkers

```python
from jvspatial.core import Walker, on_visit

class AnalysisWalker(Walker):
    """Walker that analyzes node properties."""

    nodes_visited: int = Field(default=0)
    total_population: int = Field(default=0)

    @on_visit(City)
    async def analyze_city(self, here: City):
        """Called when walker visits a city."""
        print(f"Analyzing {here.name}")
        self.nodes_visited += 1
        self.total_population += here.population

        # Continue to neighbors
        neighbors = await here.neighbors(limit=2)
        await self.visit(neighbors)
```

### Walker Traversal

```python
# Create and spawn a walker
walker = AnalysisWalker()

# Start traversal from a specific node
await walker.spawn(start=my_node)

# Or spawn from root node (default)
await walker.spawn()

# Check results
print(f"Visited {walker.nodes_visited} nodes")
print(f"Total population: {walker.total_population}")
```

### Walker Visit Hooks

Walkers use the `@on_visit` decorator to define behavior when visiting nodes or edges:

```python
class DeliveryWalker(Walker):
    packages: int = Field(default=5)

    @on_visit(City)
    async def deliver_package(self, here: City):
        """Deliver package to city."""
        if self.packages > 0:
            self.packages -= 1
            print(f"Delivered package to {here.name}")

    @on_visit(Highway)
    async def traverse_highway(self, highway: Highway):
        """Called when traversing highway edges."""
        print(f"Traveling {highway.distance} miles")
```

### Multiple Walker Types

Different walker types can traverse the same graph for different purposes:

```python
# Analysis walker
analysis_walker = AnalysisWalker()
await analysis_walker.spawn(start=central_city)

# Delivery walker
delivery_walker = DeliveryWalker(packages=10)
await delivery_walker.spawn(start=depot_city)

# Security walker
security_walker = SecurityWalker()
await security_walker.spawn(start=checkpoint_city)
```

## Common Patterns

### Building Networks

```python
# Create a simple network
cities = []
for name in ["New York", "Chicago", "Los Angeles"]:
    city = await City.create(name=name)
    cities.append(city)

# Connect all cities to each other
for i, city_a in enumerate(cities):
    for city_b in cities[i+1:]:
        await city_a.connect(city_b, Highway)
```

### Network Analysis

```python
# Find highly connected nodes
hub_cities = []
all_cities = await City.all()

for city in all_cities:
    if city.connection_count > 10:
        hub_cities.append(city)

# Analyze connection patterns
for city in hub_cities:
    neighbors = await city.neighbors()
    print(f"{city.name} connected to: {[n.name for n in neighbors]}")
```

### Data Migration

```python
# Migrate data while preserving connections
old_nodes = await OldNodeType.all()

for old_node in old_nodes:
    # Create new node
    new_node = await NewNodeType.create(
        name=old_node.name,
        # ... other fields
    )

    # Preserve connections
    old_neighbors = await old_node.neighbors()
    for neighbor in old_neighbors:
        await new_node.connect(neighbor)
```

## Integration Examples

### With FastAPI

```python
from fastapi import FastAPI
from jvspatial.core import Node

app = FastAPI()

@app.post("/nodes/{node_id}/connect/{other_id}")
async def connect_nodes(node_id: str, other_id: str):
    node_a = await Node.get(node_id)
    node_b = await Node.get(other_id)

    if node_a and node_b:
        await node_a.connect(node_b)
        return {"connected": True}
    return {"connected": False}

@app.get("/nodes/{node_id}/neighbors")
async def get_neighbors(node_id: str, limit: int = 10):
    node = await Node.get(node_id)
    if node:
        neighbors = await node.neighbors(limit=limit)
        return [{"id": n.id, "type": n.__class__.__name__} for n in neighbors]
    return []
```

### With Data Processing

```python
import asyncio
from jvspatial.core import Node

async def process_graph_parallel():
    """Process large graphs in parallel."""
    all_nodes = await Node.find({}, limit=1000)

    # Process nodes in parallel batches
    batch_size = 50
    for i in range(0, len(all_nodes), batch_size):
        batch = all_nodes[i:i+batch_size]

        # Process batch in parallel
        tasks = [process_node(node) for node in batch]
        await asyncio.gather(*tasks)

async def process_node(node):
    """Process individual node and its connections."""
    neighbors = await node.neighbors(limit=5)
    # Perform analysis
    return analyze_connections(node, neighbors)
```

This documentation provides a comprehensive guide to using nodes and edges in jvspatial, focusing on practical usage patterns and performance optimization techniques.