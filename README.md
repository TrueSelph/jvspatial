# jvspatial: An Asynchronous Object-Spatial Python Library

![GitHub release (latest by date)](https://img.shields.io/github/v/release/TrueSelph/jvspatial)
![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/TrueSelph/jvspatial/test-jvspatial.yaml)
![GitHub issues](https://img.shields.io/github/issues/TrueSelph/jvspatial)
![GitHub pull requests](https://img.shields.io/github/issues-pr/TrueSelph/jvspatial)
![GitHub](https://img.shields.io/github/license/TrueSelph/jvspatial)

## Quick Start

```python
import asyncio
from jvspatial.core.entities import Node, Walker, Root, on_visit, on_exit

class MyAgent(Node):
    """Agent with spatial properties"""
    published: bool = True
    latitude: float = 0.0
    longitude: float = 0.0

class AgentWalker(Walker):
    @on_visit(Root)
    async def on_root(self, here):
        # Create and connect an agent
        agent = MyAgent(latitude=40.7128, longitude=-74.0060)
        await here.connect(agent)
        await self.visit(agent)

    @on_visit(MyAgent)
    async def on_agent(self, here):
        print(f"Visiting agent at {here.latitude}, {here.longitude}")

    @on_exit
    async def respond(self):
        self.response["status"] = "completed"

async def main():
    root = await Root.get()
    walker = AgentWalker()
    result = await walker.spawn(root)
    print(f"Result: {result.response}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Table of Contents

- [Introduction](#introduction)
- [Installation](#installation)
- [Core Concepts](#core-concepts)
- [Getting Started](#getting-started)
- [Examples](#examples)
- [API Reference](#api-reference)
- [Database Configuration](#database-configuration)
- [REST API Integration](#rest-api-integration)
- [Advanced Features](#advanced-features)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)

## Introduction

**jvspatial** is an asynchronous, object-spatial Python library designed for building robust persistence and business logic layers. Inspired by Jaseci's graph-based paradigm and leveraging Python's async capabilities, jvspatial empowers developers to model complex relationships, traverse object graphs, and implement agent-based architectures that scale with modern cloud-native concurrency requirements.

### Key Features

- **Async-First Design**: Built with native async/await support throughout
- **Type-Driven Entities**: Pydantic models for node/edge definitions
- **Flexible Persistence**: Multiple database backends (JSON, MongoDB)
- **Imperative Walkers**: Explicit traversal control with visit/exit hooks
- **REST Endpoint Mixins**: Combine walkers with FastAPI routes
- **Explicit Connections via Edges**: Manual relationship management between nodes
- **Object Lifecycle**: Manual save/load operations for granular control

## Installation

### Basic Installation
```bash
pip install jvspatial
```

### Development Installation
```bash
git clone https://github.com/TrueSelph/jvspatial
cd jvspatial
pip install -e .[dev]
```

### Dependencies
```bash
# Core dependencies
pip install pydantic>=2.0 asyncio

# For REST API examples:
pip install fastapi uvicorn

# Optional MongoDB support:
pip install motor pymongo
```

## Core Concepts

### Nodes
Nodes represent entities in your object-spatial graph. They can store any data and have operations which may be triggered by visiting Walkers.

```python
from jvspatial.core.entities import Node

class City(Node):
    name: str
    population: int
    latitude: float
    longitude: float

# Create a city
chicago = await City.create(
    name="Chicago",
    population=2697000,
    latitude=41.8781,
    longitude=-87.6298
)
```

### Edges
Edges represent relationships between nodes with optional properties.

```python
from jvspatial.core.entities import Edge

class Highway(Edge):
    lanes: int = 4
    speed_limit: int = 65

# Connect cities with a highway
highway = await chicago.connect(detroit, Highway, lanes=6, speed_limit=70)
```

### Walkers
Walkers traverse the object-spatial graph and execute logic at each node they visit.

```python
from jvspatial.core.entities import Walker, on_visit, on_exit

class Tourist(Walker):
    @on_visit(City)
    async def visit_city(self, here):
        print(f"Visiting {here.name}")

        # Find connected cities and visit them
        connected_cities = await (await here.nodes()).filter(node='City')
        await self.visit(connected_cities)

    @on_exit
    async def trip_complete(self):
        self.response["message"] = "Trip completed!"
```

### Root Node
The singleton Root serves as the entry point for all graph operations.

```python
from jvspatial.core.entities import Root

# Get the root node (creates it if it doesn't exist)
root = await Root.get()
```

## Getting Started

### 1. Basic Node Creation and Connection

```python
import asyncio
from jvspatial.core.entities import Node, Root

class Person(Node):
    name: str
    age: int

async def basic_example():
    # Get root node
    root = await Root.get()

    # Create nodes
    alice = await Person.create(name="Alice", age=30)
    bob = await Person.create(name="Bob", age=25)

    # Connect nodes
    await root.connect(alice)
    await root.connect(bob)
    await alice.connect(bob)

    # Query connections
    alice_connections = await alice.nodes()
    print(f"Alice is connected to: {[node.name for node in alice_connections]}")

asyncio.run(basic_example())
```

### 2. Walker Traversal

```python
import asyncio
from jvspatial.core.entities import Node, Walker, Root, on_visit

class Person(Node):
    name: str
    visited: bool = False

class NetworkExplorer(Walker):
    @on_visit(Person)
    async def visit_person(self, here):
        here.visited = True
        await here.save()
        print(f"Visited {here.name}")

        # Visit unvisited neighbors
        neighbors = await (await here.nodes()).filter(node='Person')
        unvisited = [n for n in neighbors if not n.visited]
        await self.visit(unvisited)

async def traversal_example():
    root = await Root.get()

    # Create a network
    alice = await Person.create(name="Alice")
    bob = await Person.create(name="Bob")
    charlie = await Person.create(name="Charlie")

    await root.connect(alice)
    await alice.connect(bob)
    await bob.connect(charlie)

    # Traverse the network
    explorer = NetworkExplorer()
    await explorer.spawn(alice)

asyncio.run(traversal_example())
```


## Examples

The `examples/` directory contains complete working examples:

### Agent Graph Example
A comprehensive agent management system demonstrating hierarchical organization:

```bash
cd jvspatial
python examples/agent_graph.py
```

This example shows:
- App → Agents → MyAgent → Actions hierarchy
- Spatial agent properties (latitude/longitude)
- Walker hooks for each node type
- Database persistence

### Travel Graph Example
A travel planning system with cities and transportation:

```bash
cd jvspatial
python examples/travel_graph.py
```

## API Reference

### Core Classes

#### `Object`
Base class for all persistent objects.

```python
class Object(BaseModel):
    id: str = Field(default="")

    async def save() -> "Object"
    @classmethod
    async def get(cls, id: str) -> Optional["Object"]
    @classmethod
    async def create(cls, **kwargs) -> "Object"
    async def destroy(cascade: bool = True) -> None
    def export() -> dict
```

#### `Node(Object)`
Represents graph nodes with connection capabilities.

```python
class Node(Object):
    edge_ids: List[str] = Field(default_factory=list)

    async def connect(other: "Node", edge: Type["Edge"] = Edge,
                     direction: str = "out", **kwargs) -> "Edge"
    async def edges(direction: str = "") -> List["Edge"]
    async def nodes(direction: str = "both") -> "NodeQuery"

    async def filter_nodes(self, *,
                          node_type: Optional[str] = None,
                          direction: str = "out") -> List["Node"]
```

#### `Edge(Object)`
Represents connections between nodes.

```python
class Edge(Object):
    source: str  # Source node ID
    target: str  # Target node ID
    direction: str = "both"  # "in", "out", or "both"
```

#### `Walker`
Graph traversal agent with hook-based logic.

```python
class Walker(BaseModel):
    response: dict = Field(default_factory=dict)

    async def spawn(start: Optional[Node] = None) -> "Walker"
    async def visit(nodes: Union[Node, List[Node]]) -> list
    async def disengage() -> "Walker"
        """Permanently halt walk and remove walker from graph"""
```

#### `Walker.disengage()`
The `disengage` method permanently halts a walker's traversal and removes it from the graph. This is a terminal operation that cannot be undone.

**Behavior**:
- Removes the walker from its current node (if present)
- Clears the current node reference
- Sets the `paused` flag to `True`
- Walker cannot be resumed after disengagement

**Returns**:
The walker instance in its disengaged state for inspection

**Example Usage**:
```python
# Start traversal
walker = CustomWalker()
await walker.spawn(root_node)

# ... during walk when permanent stop needed ...

# Disengage the walker (permanent halt)
await walker.disengage()

# Walker is now off the graph
print(f"Walker current node: {walker.here}")  # None
print(f"Walker paused state: {walker.paused}")  # True

# Attempting to resume will not work
# await walker.resume()  # Would have no effect
```



#### `NodeQuery`
Query builder for filtering connected nodes.

```python
class NodeQuery:
    async def filter(*, node: Optional[Union[str, List[str]]] = None,
                    edge: Optional[Union[str, Type["Edge"], List[...]]] = None,
                    direction: str = "both", **kwargs) -> List["Node"]
```

### Decorators

#### `@on_visit(target_type=None)`
Register methods to execute when visiting nodes.

```python
# Walker visiting specific node types
@on_visit(City)
async def visit_city(self, here: City): ...

# Walker visiting any node
@on_visit()
async def visit_any(self, here: Node): ...

# Node being visited by specific walker
@on_visit(Tourist)  # On Node class
async def handle_tourist(self, visitor: Tourist): ...
```

#### `@on_exit`
Register cleanup methods after traversal completion.

```python
@on_exit
async def cleanup(self):
    self.response["completed_at"] = datetime.now()
```

## Database Configuration

jvspatial supports multiple database backends configured via environment variables.

### JSON Database (Default)
Perfect for development and small applications.

```bash
# .env file
JVSPATIAL_DB_TYPE=json
JVSPATIAL_JSONDB_PATH=jvdb
```

Data is stored in `jvdb/` with separate directories for nodes and edges:
```
jvdb/
├── node/
│   ├── n:Root:root.json
│   ├── n:City:123abc.json
│   └── ...
└── edge/
    ├── e:Edge:456def.json
    └── ...
```

### MongoDB
For production applications requiring scalability.

```bash
# .env file
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://localhost:27017
JVSPATIAL_MONGODB_DB_NAME=jvspatial
```

### Custom Database
Implement the `Database` abstract class for custom backends:

```python
from jvspatial.db.database import Database

class MyDatabase(Database):
    async def save(self, collection: str, data: dict) -> dict: ...
    async def get(self, collection: str, id: str) -> Optional[dict]: ...
    async def delete(self, collection: str, id: str) -> None: ...
    async def find(self, collection: str, query: dict) -> List[dict]: ...
```

## REST API Integration

jvspatial provides seamless FastAPI integration for exposing walkers as REST endpoints with powerful field-based parameter control.

### Enhanced Field-Based Parameter Control

The new `EndpointField` system provides rich control over API parameter generation, replacing the legacy comment-based approach with a type-safe, feature-rich solution.

#### Basic Usage

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

#### Advanced Parameter Control

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

## Advanced Features

### Complex Node Filtering

```python
# Get nodes connected via specific edge types with properties
connected = await (await node.nodes(direction="out")).filter(
    node=['City', 'Town'],
    edge=[Highway, Railroad],
    speed_limit=65  # Filter by edge property
)
```

### Walker Execution Flow

```python
class InventoryWalker(Walker):
    def __init__(self):
        self.found_items = []

    @on_visit(Root)
    async def start_inventory(self, here):
        print("Starting inventory check")
        # Find all storage rooms connected to root
        storage_rooms = await (await here.nodes()).filter(node="StorageRoom")
        if storage_rooms:
            await self.visit(storage_rooms[0])
        else:
            print("No storage rooms found")
            self.response["error"] = "No storage facilities available"

    @on_visit("StorageRoom")
    async def check_storage(self, here):
        print(f"Checking storage room: {here.id}")
        # Find all inventory items in this storage
        items = await (await here.nodes()).filter(node="InventoryItem")
        self.found_items.extend(items)

        # Visit each item to scan details
        await self.visit(items)

    @on_visit("InventoryItem")
    async def record_item(self, here):
        print(f"Scanning item: {here.name} ({here.serial_number})")
        self.response.setdefault("items", []).append({
            "id": here.id,
            "name": here.name,
            "location": here.storage_location
        })

    @on_exit
    async def final_report(self):
        self.response["total_items"] = len(self.found_items)
        self.response["unique_categories"] = len({item.category for item in self.found_items})
        print(f"Inventory check complete. Found {self.response['total_items']} items.")
```

### Database Configuration

```python
from pydantic import validator

class Highway(Edge):
    lanes: int
    speed_limit: int
    toll_road: bool = False

    @validator('lanes')
    def validate_lanes(cls, v):
        if v < 1 or v > 12:
            raise ValueError('Lanes must be between 1 and 12')
        return v

    @validator('speed_limit')
    def validate_speed(cls, v):
        if v < 25 or v > 85:
            raise ValueError('Speed limit must be between 25 and 85 mph')
        return v
```

## Project Structure

```
jvspatial/
├── jvspatial/           # Core library
│   ├── __init__.py
│   ├── api/             # REST API components
│   │   ├── __init__.py
│   │   └── api.py       # EndpointRouter class
│   ├── core/            # Core entities and logic
│   │   ├── __init__.py
│   │   ├── entities.py  # Node, Edge, Walker classes
│   │   └── lib.py       # Utility functions
│   └── db/              # Database backends
│       ├── __init__.py
│       ├── database.py  # Abstract Database class
│       ├── factory.py   # Database factory
│       ├── jsondb.py    # JSON database implementation
│       └── mongodb.py   # MongoDB implementation
├── examples/            # Working examples
│   ├── agent_graph.py   # Agent management system
│   └── travel_graph.py  # Travel planning system
├── tests/               # Test suite
│   ├── integration/
│   └── unit/
├── db/                  # Default JSON database location
│   └── json/
├── setup.py             # Package setup
├── README.md            # This file
└── .env.example         # Environment configuration template
```

## Troubleshooting

### Common Issues

#### "Pydantic validation error"
```python
# ❌ Missing required fields
class MyAgent(Node):
    latitude: float  # Required field
    longitude: float  # Required field

# ✅ Provide defaults or make optional
class MyAgent(Node):
    latitude: float = 0.0
    longitude: float = 0.0
```

#### "Node has no attribute 'latitude'"
```python
# ❌ Assuming spatial attributes exist
async def get_coordinates(node):
    return (node.latitude, node.longitude)

# ✅ Check attributes first
async def get_coordinates(node):
    if hasattr(node, 'latitude') and hasattr(node, 'longitude'):
        return (node.latitude, node.longitude)
    return None

```python
@on_visit(Root)
async def on_root(self, here):
    # Check for existing App nodes first
    existing_apps = await (await here.nodes()).filter(node='App')
    if existing_apps:
        await self.visit(existing_apps[0])  # Use existing
    else:
        # Create new one
        app = App()
        await here.connect(app)
        await self.visit(app)
```

#### Database connection issues
```bash
# Check environment variables
echo $JVSPATIAL_DB_TYPE
echo $JVSPATIAL_JSONDB_PATH

# Verify database directory exists and is writable
ls -la jvdb/
```

### Performance Tips

1. **Use batch operations** when creating many nodes
2. **Implement connection pooling** for MongoDB in production
3. **Consider pagination** for large node queries
4. **Use specific node type filters** to reduce query overhead

### Debug Mode

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Enable detailed walker logging
class DebugWalker(Walker):
    @on_visit(Node)
    async def log_visit(self, here):
        print(f"Visiting {here.__class__.__name__} {here.id}")
        print(f"Connections: {await here.nodes()}")
```

## Contributing

We welcome contributions! Here's how to get started:

### Development Setup

```bash
# Clone the repository
git clone https://github.com/TrueSelph/jvspatial
cd jvspatial

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in development mode
pip install -e .
pip install -r requirements-dev.txt
```

### Running Tests

```bash
# Run all tests
python -m pytest

# Run with coverage
python -m pytest --cov=jvspatial

# Run specific test file
python -m pytest tests/unit/test_node.py
```

### Contribution Guidelines

1. **Fork** the repository
2. **Create** a feature branch: `git checkout -b feature/amazing-feature`
3. **Write tests** for your changes
4. **Ensure tests pass**: `python -m pytest`
5. **Update documentation** if needed
6. **Commit** your changes: `git commit -m 'Add amazing feature'`
7. **Push** to your fork: `git push origin feature/amazing-feature`
8. **Create** a Pull Request

### Code Style

We use:
- **Black** for code formatting
- **isort** for import sorting
- **flake8** for linting
- **mypy** for type checking

```bash
# Format code
black jvspatial/
isort jvspatial/

# Check style
flake8 jvspatial/
mypy jvspatial/
```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Inspired by [Jaseci](https://github.com/Jaseci-Labs/jaseci) and its Object-Spatial paradigm
- Built with [Pydantic](https://pydantic-docs.helpmanual.io/) for data validation
- REST API powered by [FastAPI](https://fastapi.tiangolo.com/)

---

## Support

- **Documentation**: [Full Documentation](https://github.com/TrueSelph/jvspatial/wiki)
- **Issues**: [GitHub Issues](https://github.com/TrueSelph/jvspatial/issues)
- **Discussions**: [GitHub Discussions](https://github.com/TrueSelph/jvspatial/discussions)

---
## Contributors

<p align="center">
    <a href="https://github.com/TrueSelph/jvspatial/graphs/contributors">
        <img src="https://contrib.rocks/image?repo=TrueSelph/jvspatial" />
    </a>
</p>