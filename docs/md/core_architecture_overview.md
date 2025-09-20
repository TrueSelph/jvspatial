# jvspatial Core Architecture Overview

## Introduction

The jvspatial core module provides a complete object-spatial ORM (Object-Relational Mapping) library designed for graph-based data persistence and traversal. It consists of four fundamental components plus advanced pagination capabilities that work together to create a powerful yet simple system for managing connected data at any scale.

## Architecture Components

### 1. Objects
**Simple units of information stored in the database**

Objects are the foundation - basic data containers with persistence capabilities:

```python
from jvspatial.core import Object

class Document(Object):
    title: str = Field(default="")
    content: str = Field(default="")
    created_at: str = Field(default="")

# Simple usage
doc = Document(title="My Document", content="Hello World")
await doc.save()
```

**Key Features:**
- Automatic ID generation
- Database persistence
- Type-safe with Pydantic
- Supports custom fields and validation

### 2. Nodes
**Modified objects designed to be connected by edges and visited by walkers**

Nodes extend Objects with connection capabilities:

```python
from jvspatial.core import Node

class City(Node):
    name: str = Field(default="")
    population: int = Field(default=0)

# Nodes can be connected
city_a = City(name="New York", population=8000000)
city_b = City(name="Chicago", population=2700000)

# Simple connection syntax
await city_a.connect(city_b)
```

**Key Features:**
- All Object capabilities
- Connection management (`connect()`, `disconnect()`, `is_connected_to()`)
- Traversal methods (`neighbors()`, `outgoing()`, `incoming()`)
- Designed to be visited by walkers
- Edge ordering preservation

### 3. Edges
**Connect nodes together**

Edges define relationships between nodes:

```python
from jvspatial.core import Edge

class Highway(Edge):
    distance: float = Field(default=0.0)
    lanes: int = Field(default=2)
    speed_limit: int = Field(default=65)

# Edges with metadata
highway = await city_a.connect(city_b, Highway, distance=790.0, lanes=4)
```

**Key Features:**
- Rich metadata support
- Directional (`in`, `out`, `both`)
- Type-safe edge properties
- Automatic persistence

### 4. Walkers
**Traverse nodes along edges for graph analysis and operations**

Walkers provide the traversal mechanism:

```python
from jvspatial.core import Walker, on_visit

class AnalysisWalker(Walker):
    nodes_visited: int = Field(default=0)

    @on_visit(City)
    async def analyze_city(self, here: City):
        print(f"Analyzing {here.name}")
        self.nodes_visited += 1

        # Continue traversal
        neighbors = await here.neighbors()
        await self.visit(neighbors)

# Walker usage
walker = AnalysisWalker()
await walker.spawn(start=city_a)  # Start traversal
```

**Key Features:**
- Visit hooks with `@on_visit` decorator
- State management during traversal
- Queue-based traversal control
- Cycle detection
- Multiple walker types on same graph
- Efficient pagination for large graph traversals

## Core Design Principles

### Semantic Simplicity
Operations read like natural language:
```python
# Creating and connecting is intuitive
city = City(name="Boston")
await city.connect(other_city)

# Walker traversal is clear
walker = TravelWalker()
await walker.spawn(start=city)
```

### Proper Separation of Concerns
Each component has a distinct role:
- **Objects**: Data storage
- **Nodes**: Connection points
- **Edges**: Relationships
- **Walkers**: Traversal logic

### Object Pagination
**Efficiently handle large graphs and datasets with database-level pagination**

The ObjectPager provides scalable access to large object collections:

```python
from jvspatial.core import ObjectPager, paginate_objects

# Simple pagination
cities = await paginate_objects(City, page=1, page_size=50)

# Advanced pagination with filtering
pager = ObjectPager(
    City,
    page_size=100,
    filters={"population": {"$gt": 1000000}},
    order_by="population",
    order_direction="desc"
)

large_cities = await pager.get_page()
```

**Key Features:**
- Database-level filtering and ordering
- Memory-efficient processing of large datasets
- Type-safe node returns
- Integration with walker traversal
- Helper functions for common use cases

### Performance Optimization
- Database-level queries and pagination
- Batch operations
- Edge ordering preservation
- Efficient traversal algorithms
- Memory-conscious large graph processing

## Usage Patterns

### Basic Graph Operations
```python
# 1. Create nodes
node_a = Node()
node_b = Node()

# 2. Connect them
await node_a.connect(node_b)

# 3. Traverse with walker
walker = Walker()
await walker.spawn(start=node_a)
```

### Custom Entity Types
```python
class Person(Node):
    name: str = Field(default="")
    age: int = Field(default=0)

class Friendship(Edge):
    since: str = Field(default="")
    strength: float = Field(default=1.0)

class SocialWalker(Walker):
    @on_visit(Person)
    async def meet_person(self, here: Person):
        print(f"Met {here.name}, age {here.age}")
```

### Complex Analysis
```python
class NetworkAnalyzer(Walker):
    network_stats: dict = Field(default_factory=dict)

    @on_visit(Person)
    async def analyze_person(self, here: Person):
        # Analyze social connections
        friends = await here.neighbors()
        self.network_stats[here.name] = {
            'friend_count': len(friends),
            'avg_friend_age': sum(f.age for f in friends) / len(friends)
        }
```

## Integration Examples

### FastAPI Integration
```python
from fastapi import FastAPI
from jvspatial.core import Node, Walker

app = FastAPI()

@app.post("/analyze/{node_id}")
async def analyze_network(node_id: str):
    node = await Node.get(node_id)
    walker = AnalysisWalker()
    await walker.spawn(start=node)
    return {"stats": walker.network_stats}
```

### Data Processing Pipeline
```python
async def process_social_network():
    # Load all people
    people = await Person.all()

    # Analyze each person's network
    for person in people:
        analyzer = NetworkAnalyzer()
        await analyzer.spawn(start=person)

        # Store analysis results
        person.network_metrics = analyzer.network_stats
        await person.save()
```

## Performance Features

### Database Optimization
- Queries pushed to database level
- Batch entity retrieval
- Index utilization
- Connection pooling

### Memory Efficiency
- Lazy loading of connections
- Built-in pagination for large datasets
- Garbage collection friendly
- Efficient cycle detection
- Database-level result limiting

### Scalability
- Handles large graphs (millions of nodes)
- Concurrent walker execution
- Distributed database support
- Performance monitoring

## Best Practices

### 1. Use Semantic Operations
```python
# Good: Clear intent
neighbors = await node.neighbors()
await walker.spawn(start=node)

# Avoid: Complex internal calls
query = await node.nodes()
results = await query.filter()
```

### 2. Design Walker Hierarchy
```python
# Base walker for common behavior
class BaseAnalyzer(Walker):
    @on_visit(Node)
    async def track_visit(self, here: Node):
        # Common tracking logic
        pass

# Specialized walkers
class SecurityScanner(BaseAnalyzer): pass
class PerformanceAnalyzer(BaseAnalyzer): pass
```

### 3. Efficient Traversal and Pagination
```python
# Use limits to control memory
neighbors = await node.neighbors(limit=100)

# Database-level filtering
large_cities = await City.find_by(population={"$gt": 1000000})

# Paginate large result sets
cities_page = await paginate_objects(City, page=1, page_size=50)

# Process large graphs efficiently
pager = ObjectPager(City, page_size=100)
while True:
    cities = await pager.next_page()
    if not cities:
        break
    await process_cities(cities)
```

### 4. Walker State Management
```python
class StatefulWalker(Walker):
    visited_types: dict = Field(default_factory=dict)

    @on_visit(Node)
    async def track_type(self, here: Node):
        node_type = here.__class__.__name__
        self.visited_types[node_type] = self.visited_types.get(node_type, 0) + 1
```

## Summary

The jvspatial core architecture provides:

- **Objects**: Simple data persistence
- **Nodes**: Connected data points that can be visited
- **Edges**: Rich relationship modeling
- **Walkers**: Powerful graph traversal and analysis
- **ObjectPager**: Efficient pagination for large graphs and datasets

This architecture enables developers to build sophisticated graph applications while maintaining semantic simplicity. The system scales from simple connections to complex network analysis, all with the same intuitive interface:

```python
# Always this simple
node = Node()
walker = Walker()
await walker.spawn(start=node)
```

The power lies not in complexity, but in the elegant composition of these four fundamental components working together.