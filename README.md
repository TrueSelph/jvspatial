# jvspatial: Asynchronous Object-Spatial Python Library

![GitHub release (latest by date)](https://img.shields.io/github/v/release/TrueSelph/jvspatial)
![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/TrueSelph/jvspatial/test-jvspatial.yaml)
![GitHub issues](https://img.shields.io/github/issues/TrueSelph/jvspatial)
![GitHub pull requests](https://img.shields.io/github/issues-pr/TrueSelph/jvspatial)
![GitHub](https://img.shields.io/github/license/TrueSelph/jvspatial)

## Overview

**jvspatial** is an asynchronous, object-spatial Python library designed for building robust persistence and business logic application layers. Inspired by Jaseci's object-spatial paradigm and leveraging Python's async capabilities, jvspatial empowers developers to model complex relationships, traverse object graphs, and implement agent-based architectures that scale with modern cloud-native concurrency requirements. Key capabilities:

- Typed node/edge modeling via Pydantic
- Precise control over graph traversal
- Multi-backend persistence (JSON/MongoDB)
- Integrated REST API endpoints
- Async/await architecture


## Installation

```bash
# Basic installation
pip install jvspatial

# Development setup
git clone https://github.com/TrueSelph/jvspatial
cd jvspatial
pip install -e .[dev]
```

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
- [Examples](docs/md/examples.md)
- [Entity Reference](docs/md/entity-reference.md)
- [Walker Queue Operations](docs/md/walker-queue-operations.md)
- [Walker Skip Operation](docs/md/walker-skip.md)
- [Database Configuration](docs/md/database-config.md)
- [REST API Integration](docs/md/rest-api.md)
- [Advanced Features](docs/md/advanced-usage.md)
- [Project Structure](#project-structure)
- [Troubleshooting](docs/md/troubleshooting.md)
- [Contributing](docs/md/contributing.md)

## Introduction

**jvspatial** is an asynchronous, object-spatial Python library designed for building robust persistence and business logic layers. Inspired by Jaseci's object-spatial paradigm and leveraging Python's async capabilities, jvspatial empowers developers to model complex relationships, traverse object graphs, and implement agent-based architectures that scale with modern cloud-native concurrency requirements.

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
highway = await chicago.connect(detroit, edge=Highway, lanes=6, speed_limit=70)
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

### Pydantic Validation

```python
from pydantic import field_validator

class Highway(Edge):
    lanes: int
    speed_limit: int
    toll_road: bool = False

    @field_validator('lanes')
    @classmethod
    def validate_lanes(cls, v):
        if v < 1 or v > 12:
            raise ValueError('Lanes must be between 1 and 12')
        return v

    @field_validator('speed_limit')
    @classmethod
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
│   │   └── endpoint_router.py  # EndpointRouter class
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
│   ├── fastapi_server.py# FastAPI server example
│   └── travel_graph.py  # Travel planning system
├── tests/               # Test suite
│   ├── api/             # API tests
│   ├── database/        # Database tests
│   ├── integration/     # Integration tests
│   └── unit/            # Unit tests
├── docs/                # Documentation
│   └── md/              # Markdown documentation files
├── setup.py             # Package setup
├── LICENSE              # MIT License
├── README.md            # This file
└── .env.example         # Environment configuration template
```

## License

This project is licensed under the MIT License - see the [LICENSE](docs/md/license.md) file for details.

## Acknowledgments

- Inspired by [Jaseci](https://github.com/Jaseci-Labs/jaseci) and its Object-Spatial paradigm
- Built with [Pydantic](https://pydantic-docs.helpmanual.io/) for data validation
- REST API powered by [FastAPI](https://fastapi.tiangolo.com/)

---

## Support

- **Documentation**: [Full Documentation](./docs/md/)
- **Issues**: [GitHub Issues](https://github.com/TrueSelph/jvspatial/issues)
- **Discussions**: [GitHub Discussions](https://github.com/TrueSelph/jvspatial/discussions)

---
## Contributors

<p align="center">
    <a href="https://github.com/TrueSelph/jvspatial/graphs/contributors">
        <img src="https://contrib.rocks/image?repo=TrueSelph/jvspatial" />
    </a>
</p>