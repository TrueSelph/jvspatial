# Design Decisions

This document explains the key architectural decisions and patterns used in jvspatial, providing context for why certain approaches were chosen over alternatives.

## Table of Contents

- [Object-Spatial Model](#object-spatial-model)
- [Walker Pattern](#walker-pattern)
- [Node & Edge Design](#node--edge-design)
- [Storage Architecture](#storage-architecture)
- [API Design](#api-design)

## Object-Spatial Model

### Why Object-Spatial?

Traditional approaches to handling spatial data often fall into two categories:
1. Relational databases with spatial extensions (PostGIS)
2. Pure graph databases (Neo4j)

The object-spatial model combines the best of both:
- **Object-oriented**: Clean, intuitive APIs with proper encapsulation
- **Graph structure**: Natural representation of relationships
- **Spatial awareness**: Built-in support for geographic operations
- **Type safety**: Strong typing with Pydantic validation

### Comparison with Alternatives

#### vs. Pure ORM (SQLAlchemy)
- **ORM**: Tables with foreign keys, requires complex joins
- **jvspatial**: Direct object relationships, natural traversal

#### vs. Graph DB (Neo4j)
- **Neo4j**: Low-level graph operations, separate spatial plugin
- **jvspatial**: High-level objects with built-in spatial features

#### vs. Spatial DB (PostGIS)
- **PostGIS**: Powerful but complex SQL queries
- **jvspatial**: Simple Python API with semantic filtering

## Walker Pattern

### Why Walkers?

The Walker pattern was chosen over alternatives for several reasons:

1. **Natural Problem Solving**
   - Matches how humans think about traversing relationships
   - Makes complex graph operations intuitive

2. **State Management**
   - Walkers can maintain state during traversal
   - Perfect for collecting data or managing resources

3. **Business Logic**
   - Clear separation of traversal and processing logic
   - Easy to extend and modify behavior

### Alternative Patterns Considered

#### Iterator Pattern
```python
# Iterator approach - limited state, harder to manage
for node in graph.iter_nodes():
    if isinstance(node, City):
        process_city(node)
    for neighbor in node.neighbors():
        process_neighbor(neighbor)
```

#### Visitor Pattern
```python
# Traditional visitor - rigid, less intuitive
class CityVisitor:
    def visit_city(self, city): pass
    def visit_road(self, road): pass
graph.accept(visitor)
```

#### Walker Pattern (Chosen)
```python
class CityAnalyzer(Walker):
    @on_visit(City)
    async def analyze_city(self, here: City):
        self.population_sum += here.population
        nearby = await here.nodes(
            node=City,
            distance={"$lte": 100}
        )
        await self.visit(nearby)  # Natural traversal
```

### Benefits of Walkers

1. **State Management**
   - Track visited nodes
   - Maintain analysis state
   - Handle resource allocation

2. **Control Flow**
   - Skip irrelevant nodes
   - Pause/resume traversal
   - Limit depth/breadth

3. **Event System**
   - Emit events during traversal
   - Coordinate between walkers
   - Build reactive systems

## Node & Edge Design

### Why Separate Node & Edge Classes?

1. **Clear Semantics**
   - Nodes represent entities
   - Edges represent relationships
   - Each can have their own properties

2. **Type Safety**
   ```python
   class City(Node):
       name: str
       population: int

   class Highway(Edge):
       distance: float
       lanes: int
   ```

3. **Query Optimization**
   - Efficient filtering by type
   - Better index utilization
   - Clearer query patterns

### Alternative Approaches Considered

#### Universal Objects
```python
# Less clear, harder to optimize
class GraphObject:
    type: str  # "node" or "edge"
    properties: Dict[str, Any]
```

#### Property-Only Edges
```python
# Limited relationship modeling
edge = (node1, node2, {"type": "highway", "distance": 100})
```

## Storage Architecture

### Multi-Backend Support

The storage architecture was designed to support multiple backends while maintaining a consistent API:

```python
# Same API, different backends
await City.find({"population": {"$gt": 1000000}})  # Works with JSON
await City.find({"population": {"$gt": 1000000}})  # Works with MongoDB
```

### Why MongoDB-Style Queries?

1. **Familiarity**: Many developers know MongoDB query syntax
2. **Expressiveness**: Powerful query capabilities
3. **Consistency**: Works the same across all backends

### JSON Backend

Included for:
1. Development simplicity
2. No external dependencies
3. Easy testing
4. Simple deployments

### MongoDB Backend

Optimized for:
1. Production workloads
2. Horizontal scaling
3. Complex queries
4. Large datasets

## API Design

### FastAPI Integration

FastAPI was chosen for:
1. Modern async support
2. Automatic OpenAPI docs
3. Type safety with Pydantic
4. High performance

### Walker Endpoints

The Walker endpoint pattern combines REST APIs with graph traversal:

```python
@endpoint("/api/cities/nearby")
class NearbyCities(Walker):
    latitude: float
    longitude: float
    radius: float = 10.0

    @on_visit(City)
    async def find_nearby(self, here: City):
        if within_radius(here, self.latitude, self.longitude, self.radius):
            self.report({"city": here.name})
```

Benefits:
1. Clean endpoint definition
2. Automatic request validation
3. Graph traversal capabilities
4. Built-in documentation

## Migration Considerations

### From Traditional ORM

```python
# SQLAlchemy approach
cities = (
    db.query(City)
    .filter(City.population > 1000000)
    .join(Highway)
    .filter(Highway.lanes >= 4)
    .all()
)

# jvspatial approach
cities = await City.find({
    "context.population": {"$gt": 1000000},
    "edge": [{
        "Highway": {"context.lanes": {"$gte": 4}}
    }]
})
```

### From Graph Database

```python
# Neo4j Cypher
MATCH (c:City)-[r:HIGHWAY]->(n:City)
WHERE c.population > 1000000
AND r.lanes >= 4
RETURN c, r, n

# jvspatial
@on_visit(City)
async def analyze(self, here: City):
    if here.population > 1000000:
        connected = await here.nodes(
            node=City,
            edge=Highway,
            lanes={"$gte": 4}
        )
```

## See Also

- [Core Concepts](core-concepts.md)
- [Entity Reference](entity-reference.md)
- [Walker Patterns](walker-patterns.md)
- [API Integration](rest-api.md)