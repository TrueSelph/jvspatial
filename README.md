# jvspatial: An Asynchronous Object-Spatial Python Library

## Introduction
jvspatial is an object-spatial Python library inspired by Jaseci's Object-Spatial paradigm combined with Python's asynchronous programming paradigm for building asynchronous graph-based persistence and processing layers into your Python (AI) application. It enables developers to:
- Automatic persistence and object lifecycle management
- Type-safe nodes and edges with Pydantic validation
- Async-first architecture for high performance
- Decorator-based visitor pattern for traversal logic
- Pluggable database backends (JSON/MongoDB)
- REST API endpoints via FastAPI integration

## Core Concepts

### Nodes
Nodes represent entities in the graph. Below is an example of a City node:

```python
class City(Node):
    name: str
    population: int
    latitude: float
    longitude: float

    @on_visit
    def on_visited(self, visitor):
        print(f"Being visited by {visitor.id}")
```

### Edges
Edges define relationships between nodes with directional control:

```python
class Highway(Edge):
    length: float
    lanes: int = 4

class Railroad(Edge):
    electrified: bool
```

### Walkers
Walkers traverse graphs asynchronously with advanced capabilities. Below is an example of a Tourist walker:

```python
class Tourist(Walker):
    @on_visit(City)
    async def visit_city(self, visitor: City):
        """Track visited cities and explore connections"""
        if 'visited' not in self.response:
            self.response['visited'] = []
        self.response['visited'].append(visitor.name)
        print(f"Tourist visiting {visitor.name} (pop: {visitor.population})")
        
        # Get connected cities via highways
        neighbors = await (await visitor.nodes(direction="out")).filter(edge=Highway)
        await self.visit([n for n in neighbors if n.name not in self.response["visited"]])
```

## Basic Usage
Creating nodes and edges with spatial data:

```python
# Create cities with coordinates
chicago = await City(
    name="Chicago",
    population=2697000,
    latitude=41.8781,
    longitude=-87.6298
)

st_louis = await City(
    name="St. Louis",
    population=300576,
    latitude=38.6270,
    longitude=-90.1994
)

# Create multiple connection types
highway = await chicago.connect(st_louis, Highway, length=297, lanes=4)
railroad = await chicago.connect(st_louis, Railroad, electrified=True)
```

Traversing with Walker interface:

```python
tourist = Tourist()
await tourist.traverse(chicago)
```

## Advanced Features
### Hook Decorators
The `@on_visit` decorator intelligently handles context based on its usage:

- When applied to Walker methods:
  - Can only accept Node, Edge, or None as a parameter
  - Receives visited Node/Edge as a parameter
  - Example: `@on_visit(City) async def visit_city(self, city)`

- When applied to Node/Edge methods:
  - Can only accept Walker or None as a parameter
  - Receives visiting Walker as a parameter
  - Example: `@on_visit(Tourist) async def on_tourist(self, visitor)`

- When no parameter is specified:
  - Automatically passes the appropriate context
  - For Walkers: passes current Node/Edge
  - For Nodes/Edges: passes visiting Walker

### RootNode
Global entry point for traversals (stored in 'node' collection):

```python
# Create root node
root = await RootNode.get()
```

For a comprehensive understanding of the library, please refer to the full documentation.