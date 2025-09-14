# jvspatial: An Asynchronous Object-Spatial Python Library

## Introduction
jvspatial is an object-spatial Python library that combines graph-based data modeling with spatial awareness and asynchronous operations. Inspired by Jaseci's Object-Spatial paradigm, it enables developers to build complex AI applications with:

- Automatic persistence and object lifecycle management
- Type-safe nodes and edges with Pydantic validation
- Async-first architecture for high performance
- Decorator-based visitor pattern for traversal logic
- Pluggable database backends (MongoDB/JSON)
- REST API endpoints via FastAPI integration

### Key Concepts

#### Nodes
Nodes represent entities in your spatial graph (e.g., cities, users, devices). They can store spatial coordinates and properties. Nodes can connect to other nodes via edges.

#### Edges
Edges represent relationships between nodes. They can be directional (outbound/inbound) or bidirectional. Edges can store relationship-specific properties (e.g., distance, connection type).

#### Walkers
Walkers traverse the graph, visiting nodes and executing logic at each stop. They implement the visitor pattern through decorators:
- `@on_visit` defines logic when a walker visits a node
- `@on_exit` defines cleanup logic after traversal

#### Spatial Queries
Nodes can be queried based on their spatial properties (latitude/longitude) using MongoDB's geospatial queries or JSONDB's coordinate filtering.

#### Root Node
The singleton RootNode serves as the global entry point for all graph traversals. All nodes connect to the root node for discoverability.

## API Reference

### Core Classes

#### `Object`
Base class for all persistent objects
- `id`: Unique identifier
- `save()`: Persist object to database
- `get(id)`: Retrieve object by ID
- `destroy()`: Delete object

#### `Node(Object)`
Represents graph nodes
- `connect(other, edge)`: Create connection to another node
- `edges(direction)`: Get connected edges
- `nodes(direction)`: Get connected nodes

#### `Edge(Object)`
Represents graph edges
- `source`: Source node ID
- `target`: Target node ID
- `direction`: Edge direction (out/in/both)

#### `Walker`
Graph traversal agent
- `spawn(start)`: Start traversal from node
- `visit(nodes)`: Add nodes to traversal queue
- `@on_visit`: Decorator for visit hooks
- `@on_exit`: Decorator for exit hooks

#### `RootNode(Node)`
Singleton root node for graph access
- `get()`: Retrieve root node instance

### Decorators

#### `@on_visit(target_type=None)`
Registers a method to be called when a Walker visits a Node or when a Node is visited by a Walker. The target_type parameter specifies the type of object to trigger the visit.

#### `@on_exit`
Registers a method to be called when a Walker completes its traversal.

### REST API

The `GraphAPI` class provides REST endpoints for Walker execution:

```python
api = GraphAPI()
api.router  # Expose this with FastAPI
```

Endpoint format:
```python
@endpoint("/path", methods=["POST"])
class MyWalker(Walker):
    ...
```

## FastAPI Server Setup

To expose your graph via REST API:

1. Create `main.py`:
```python
from fastapi import FastAPI
from jvspatial.api.api import GraphAPI

app = FastAPI()
api = GraphAPI()

# Register walkers as API endpoints
@api.endpoint("/tourist")
class Tourist(Walker):
    ...

app.include_router(api.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

2. Run the server:
```bash
uvicorn main:app --reload
```

3. Call endpoints:
```bash
curl -X POST http://localhost:8000/tourist -d '{"start_node": "n:City:123"}'
```

## Setup

### Installation
```bash
pip install jvspatial
```

### Dependencies
#### Required:
- Python 3.8+
- FastAPI (for the web interface)
- uvicorn (for running the server)
- python-multipart (for handling file uploads)

#### Optional (for database support):
- pymongo (for MongoDB support) - install with `pip install pymongo`

## Configuration
1. Create a `.env` file in your project root:
```bash
cp jvspatial/.env.example .env
```

2. Update the `.env` file with your preferred database settings:
```bash
# For MongoDB:
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://localhost:27017
JVSPATIAL_MONGODB_DB_NAME=jvspatial

# OR For JSON Database:
JVSPATIAL_DB_TYPE=json
JVSPATIAL_JSONDB_PATH=./data/jsondb.json
```

3. Set proper permissions for the `.env` file:
```bash
chmod 600 .env
```

## Database Setup
1. For MongoDB:
   - Install MongoDB
   - Create a database named `jvspatial` (or use the name you set in JVSPATIAL_MONGODB_DB_NAME)

2. For JSON Database:
   - Create a `data` directory in your project root (or adjust path in JVSPATIAL_JSONDB_PATH)
   - The JSONDB will be stored at the specified path

## Basic Usage
Creating nodes and edges with spatial data:

```python
from jvspatial.models import City, Highway, Railroad
from jvspatial.walker import Tourist

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

### Walkers
Traversing with Walker interface:

```python
from jvspatial.walker import Tourist

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

## Contributing
Contributions are welcome! Please fork the repository and submit pull requests.

## License
MIT License

For a comprehensive understanding of the library, please refer to the full documentation.