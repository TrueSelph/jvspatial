# jvspatial: Asynchronous Object-Spatial Python Library

![GitHub release (latest by date)](https://img.shields.io/github/v/release/TrueSelph/jvspatial)
![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/TrueSelph/jvspatial/test-jvspatial.yaml)
![GitHub issues](https://img.shields.io/github/issues/TrueSelph/jvspatial)
![GitHub pull requests](https://img.shields.io/github/issues-pr/TrueSelph/jvspatial)
![GitHub](https://img.shields.io/github/license/TrueSelph/jvspatial)

## Overview

**jvspatial** is an asynchronous, object-spatial Python library designed for building robust persistence and business logic application layers. Inspired by Jaseci's object-spatial paradigm and leveraging Python's async capabilities, jvspatial empowers developers to model complex relationships, traverse object graphs, and implement agent-based architectures that scale with modern cloud-native concurrency requirements.

### Key Features

- **Entity-Centric Design**: Clean, MongoDB-style query interface that works across different backends
- **Attribute Annotations**: `@protected` and `@transient` decorators for immutable fields and runtime-only data
- **Pluggable Cache System**: In-memory, Redis, and layered caching strategies for high-performance deployments
- **Object Pagination**: Efficient database-level pagination with `ObjectPager` for handling large datasets
- **FastAPI Server Integration**: Built-in REST API endpoints with automatic OpenAPI documentation
- **Enterprise Authentication**: JWT tokens, API keys, RBAC, and spatial permissions system
- **Advanced Webhook System**: Secure webhook endpoints with HMAC verification, idempotency handling, path-based authentication, asynchronous processing, and automatic payload injection
- **Async/await Architecture**: Native async support throughout the library
- **Multi-backend Persistence**: JSON and MongoDB backends with extensible database interface
- **Graph Traversal**: Precise control over walker-based graph traversal with semantic filtering
- **Walker Reporting System**: Simple, direct data collection and aggregation during traversal
- **Inter-Walker Communication**: Event-driven coordination between concurrent walkers
- **Infinite Walk Protection**: Comprehensive safeguards against infinite loops with configurable limits
- **Type Safety**: Pydantic-based modeling for nodes, edges, and walkers


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

### Version Compatibility
**Supported Environments**:
- Python 3.9+
- MongoDB 5.0+ (optional)
- FastAPI 0.88+ (for REST features)

## Environment Configuration

jvspatial uses environment variables for database configuration and library setup. These variables provide flexible configuration without requiring code changes.

### Core Database Configuration

| Variable | Description | Default Value | Required |
|----------|-------------|---------------|-----------|
| `JVSPATIAL_DB_TYPE` | Database backend to use (`json` or `mongodb`) | `json` | No |
| `JVSPATIAL_JSONDB_PATH` | Base path for JSON database files | `jvdb` | No |
| `JVSPATIAL_MONGODB_URI` | MongoDB connection URI | `mongodb://localhost:27017` | No |
| `JVSPATIAL_MONGODB_DB_NAME` | MongoDB database name | `jvdb` | No |

### Walker Infinite Walk Protection

| Variable | Description | Default Value | Required |
|----------|-------------|---------------|-----------|
| `JVSPATIAL_WALKER_PROTECTION_ENABLED` | Enable/disable walker protection mechanisms | `true` | No |
| `JVSPATIAL_WALKER_MAX_STEPS` | Maximum steps before auto-halt | `10000` | No |
| `JVSPATIAL_WALKER_MAX_VISITS_PER_NODE` | Maximum visits per node before auto-halt | `100` | No |
| `JVSPATIAL_WALKER_MAX_EXECUTION_TIME` | Maximum execution time in seconds | `300.0` | No |
| `JVSPATIAL_WALKER_MAX_QUEUE_SIZE` | Maximum queue size before limiting additions | `1000` | No |

### Environment Setup Examples

#### JSON Database (Default)
```bash
# Use default JSON database with custom path
export JVSPATIAL_DB_TYPE=json
export JVSPATIAL_JSONDB_PATH=/path/to/database
```

#### MongoDB Configuration
```bash
# Use MongoDB with custom connection
export JVSPATIAL_DB_TYPE=mongodb
export JVSPATIAL_MONGODB_URI=mongodb://user:password@localhost:27017
export JVSPATIAL_MONGODB_DB_NAME=production_spatial_db
```

#### Production MongoDB with Authentication
```bash
# Production MongoDB setup with authentication
export JVSPATIAL_DB_TYPE=mongodb
export JVSPATIAL_MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
export JVSPATIAL_MONGODB_DB_NAME=jvspatial_production
```

### Using .env Files

Create a `.env` file in your project root:

```env
# Database Configuration
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://localhost:27017
JVSPATIAL_MONGODB_DB_NAME=jvspatial_dev

# Optional: JSON Database Path (if using JSON backend)
JVSPATIAL_JSONDB_PATH=./jvdb

# Caching Configuration (optional)
JVSPATIAL_CACHE_BACKEND=memory
JVSPATIAL_CACHE_SIZE=1000

# Walker Protection Configuration
JVSPATIAL_WALKER_PROTECTION_ENABLED=true
JVSPATIAL_WALKER_MAX_STEPS=10000
JVSPATIAL_WALKER_MAX_VISITS_PER_NODE=100
JVSPATIAL_WALKER_MAX_EXECUTION_TIME=300.0
JVSPATIAL_WALKER_MAX_QUEUE_SIZE=1000
```

Then load it in your application:

```python
from dotenv import load_dotenv
load_dotenv()  # Load .env file

# jvspatial will automatically use the environment variables
from jvspatial.core import GraphContext
ctx = GraphContext()  # Uses environment configuration
```

## Exception Handling

jvspatial provides a comprehensive exception hierarchy for robust error handling and graceful degradation.

### Exception Hierarchy

All jvspatial exceptions inherit from `JVSpatialError`:

```python
from jvspatial.exceptions import (
    JVSpatialError,         # Base exception
    ValidationError,        # Data validation errors
    EntityNotFoundError,    # Entity lookup failures
    NodeNotFoundError,      # Node-specific not found
    EdgeNotFoundError,      # Edge-specific not found
    DatabaseError,          # Database operation failures
    ConnectionError,        # Database connection issues
    GraphError,             # Graph structure problems
    WalkerExecutionError,   # Walker runtime errors
    ConfigurationError,     # Configuration problems
)
```

### Basic Exception Handling

```python
import asyncio
from jvspatial.core import Node
from jvspatial.exceptions import JVSpatialError, EntityNotFoundError, ValidationError

class User(Node):
    name: str = ""
    email: str = ""

async def handle_user_operations():
    try:
        # Entity operations that might fail
        user = await User.create(name="Alice", email="alice@example.com")
        retrieved = await User.get("invalid_id")

    except EntityNotFoundError as e:
        print(f"Entity not found: {e.message}")
        print(f"Entity type: {e.entity_type}, ID: {e.entity_id}")

    except ValidationError as e:
        print(f"Validation failed: {e.message}")
        if e.field_errors:
            for field, error in e.field_errors.items():
                print(f"  {field}: {error}")

    except JVSpatialError as e:
        # Catch-all for any jvspatial error
        print(f"jvspatial error: {e.message}")
        if e.details:
            print(f"Details: {e.details}")

    except Exception as e:
        # Handle unexpected errors
        print(f"Unexpected error: {e}")

async def main():
    await handle_user_operations()

if __name__ == "__main__":
    asyncio.run(main())
```

### Database Exception Handling

```python
from jvspatial.exceptions import DatabaseError, ConnectionError, QueryError
from jvspatial.core import GraphContext

async def robust_database_operations():
    try:
        ctx = GraphContext()
        users = await User.find({"context.active": True})

    except ConnectionError as e:
        print(f"Database connection failed: {e.message}")
        print(f"Database type: {e.database_type}")
        # Implement retry logic or fallback

    except QueryError as e:
        print(f"Query failed: {e.message}")
        print(f"Query: {e.query}")
        # Log query for debugging

    except DatabaseError as e:
        print(f"Database operation failed: {e.message}")
        # Handle database-level errors
```

### Walker Exception Handling

```python
from jvspatial.exceptions import WalkerExecutionError, WalkerTimeoutError
from jvspatial.core import Walker, on_visit

class SafeWalker(Walker):
    @on_visit(User)
    async def process_user(self, here: User):
        try:
            # Potentially risky operations
            result = await some_external_service(here)
            self.report(result)
        except Exception as e:
            # Log error and continue traversal
            self.report({"error": str(e), "user_id": here.id})

async def safe_traversal():
    try:
        walker = SafeWalker()
        result = await walker.spawn(start_node)

    except WalkerTimeoutError as e:
        print(f"Walker timed out after {e.timeout_seconds} seconds")
        # Access partial results
        partial_report = walker.get_report()

    except WalkerExecutionError as e:
        print(f"Walker execution failed: {e.message}")
        print(f"Walker class: {e.walker_class}")
```

### Configuration Exception Handling

```python
from jvspatial.exceptions import ConfigurationError, InvalidConfigurationError
from jvspatial.db.factory import get_database

def setup_database_with_fallback():
    try:
        # Try preferred database
        db = get_database("mongodb")

    except InvalidConfigurationError as e:
        print(f"MongoDB configuration invalid: {e.message}")
        print(f"Config key: {e.config_key}, Value: {e.config_value}")

        # Fall back to JSON database
        try:
            db = get_database("json")
            print("Falling back to JSON database")
        except ConfigurationError:
            raise ConfigurationError("No database backend available")

    return db
```

## Quick Start

### Entity-Centric CRUD Operations
```python
import asyncio
from jvspatial.core import Node, Walker, on_visit

class User(Node):
    name: str = ""
    email: str = ""
    active: bool = True

class UserProcessor(Walker):
    @on_visit(User)
    async def process_user(self, here: User):
        print(f"Processing user: {here.name} ({here.email})")

        # Use the new reporting system to collect data
        self.report({
            "user_processed": {
                "name": here.name,
                "email": here.email,
                "active": here.active
            }
        })

        # Use MongoDB-style queries for connected users
        active_users = await User.find({"context.active": True})
        self.report(f"Found {len(active_users)} active users")

async def main():
    # Entity-centric CRUD (automatic database setup)
    user = await User.create(name="Alice", email="alice@company.com")

    # MongoDB-style queries work across all backends
    users = await User.find({"context.active": True})
    senior_users = await User.find({"context.name": {"$regex": "^A", "$options": "i"}})

    # Walker traversal with new reporting system
    walker = UserProcessor()
    result_walker = await walker.spawn(user)  # spawn() returns the walker

    # Get collected data as a simple list
    report = result_walker.get_report()
    print(f"Collected {len(report)} items:")
    for item in report:
        print(f"  - {item}")

if __name__ == "__main__":
    asyncio.run(main())
```

### FastAPI Server Integration
```python
from jvspatial.api import Server, walker_endpoint
from jvspatial.api.endpoint.router import EndpointField
from jvspatial.core import Walker, Node, on_visit

# Create server with automatic database setup
server = Server(
    title="My Spatial API",
    description="Graph-based data management API",
    version="1.0.0"
)

@walker_endpoint("/api/users/process", methods=["POST"])
class ProcessUser(Walker):
    user_name: str = EndpointField(
        description="Name of user to process",
        examples=["Alice", "Bob"],
        min_length=2
    )

    @on_visit(Node)
    async def process(self, here: Node):
        users = await User.find({"context.name": self.user_name})
        self.report({"found_users": len(users)})

if __name__ == "__main__":
    server.run()  # API available at http://localhost:8000/docs
```

### Scheduler Integration

jvspatial includes optional scheduler support for background task automation using the `@on_schedule` decorator:

```python
from jvspatial.api import Server
from jvspatial.api.scheduler import on_schedule
from jvspatial.core import Object
from datetime import datetime

# Define entity for job tracking
class ScheduledJob(Object):
    job_name: str = ""
    execution_time: datetime = datetime.now()
    status: str = "pending"
    duration_seconds: float = 0.0

# Create scheduled function
@on_schedule("every 30 minutes", description="System cleanup")
async def cleanup_system():
    """Automated cleanup with job tracking."""
    start_time = datetime.now()

    # Perform cleanup work
    cleanup_count = perform_cleanup_work()

    # Create job record
    await ScheduledJob.create(
        job_name="system_cleanup",
        execution_time=start_time,
        status="completed",
        duration_seconds=(datetime.now() - start_time).total_seconds()
    )
    print(f"✅ Cleaned up {cleanup_count} items")

# Create server with scheduler enabled
server = Server(
    title="Scheduled App",
    scheduler_enabled=True,  # Enable scheduler
    scheduler_interval=1,    # Check every second
)

if __name__ == "__main__":
    server.run()  # Scheduler runs automatically
```

**Installation:**
```bash
pip install jvspatial[scheduler]
```

**📖 For comprehensive scheduler documentation:** [Scheduler Integration Guide](docs/md/scheduler.md)

## Table of Contents

### Getting Started
- [Installation](#installation)
- [Quick Start](#quick-start)
- [Core Concepts](#core-concepts)

### Core Features
- [Entity-Centric CRUD Operations](#entity-centric-crud-operations)
- [MongoDB-Style Query Interface](#mongodb-style-query-interface)
- [Object Pagination](#object-pagination)
- [Walker Traversal Patterns](#walker-traversal-patterns)
- [Walker Trail Tracking](#walker-trail-tracking)
- [FastAPI Server Integration](#fastapi-server-integration)
- [Scheduler Integration](#scheduler-integration)
- [Webhook Integration](#webhook-integration)

### Advanced Topics
- [GraphContext & Database Management](docs/md/graph-context.md)
- [Environment Configuration](docs/md/environment-configuration.md)
- [Caching System](docs/md/caching.md)
- [Infinite Walk Protection](docs/md/infinite-walk-protection.md)
- [REST API Integration](docs/md/rest-api.md)
- [Scheduler Integration](docs/md/scheduler.md)
- [Webhook Architecture](docs/md/webhook-architecture.md)
- [MongoDB-Style Query Interface](docs/md/mongodb-query-interface.md)
- [Object Pagination Guide](docs/md/pagination.md)
- [Entity Reference](docs/md/entity-reference.md)
- [Walker Queue Operations](docs/md/walker-queue-operations.md)
- [Walker Trail Tracking](docs/md/walker-trail-tracking.md)

### Resources
- [Examples](docs/md/examples.md)
- [Troubleshooting](docs/md/troubleshooting.md)
- [Contributing](docs/md/contributing.md)
- [License](docs/md/license.md)
- [Project Structure](#project-structure)

## Core Concepts

### Entity-Centric Architecture

jvspatial follows an **entity-centric design** philosophy that emphasizes clean, intuitive APIs for working with graph data:

```python
# Entity creation - simple and direct
user = await User.create(name="Alice", email="alice@company.com")

# MongoDB-style queries - work across all database backends
active_users = await User.find({"context.active": True})
senior_users = await User.find({"context.age": {"$gte": 35}})

# Semantic filtering during traversal
engineering_colleagues = await user.nodes(
    node=['User'],
    department="engineering",
    active=True
)
```

### Key Entities

1. **Node** - Graph nodes representing entities (users, cities, documents, etc.)
2. **Edge** - Relationships between nodes with optional properties
3. **Walker** - Graph traversal agents that implement business logic
4. **ObjectPager** - Efficient pagination for large datasets
5. **Server** - FastAPI integration for REST API endpoints

## Entity-Centric CRUD Operations

jvspatial's entity-centric design provides a clean, consistent interface for all database operations:

```python
from jvspatial.core import Node

class User(Node):
    name: str = ""
    email: str = ""
    department: str = ""
    active: bool = True

# Create entities
user = await User.create(name="Alice", email="alice@company.com")

# Retrieve by ID
user = await User.get(user_id)

# Simple filtering
users = await User.find_by(active=True)

# Update entities
user.name = "Alice Johnson"
await user.save()

# Delete entities
await user.delete()

# Count and aggregation
count = await User.count({"context.department": "engineering"})
departments = await User.distinct("department")
```

## MongoDB-Style Query Interface

jvspatial provides a unified MongoDB-style query interface that works across all database backends:

```python
# Comparison operators
senior_users = await User.find({"context.age": {"$gte": 35}})
young_users = await User.find({"context.age": {"$lt": 30}})
non_admin_users = await User.find({"context.role": {"$ne": "admin"}})

# Logical operators
engineers = await User.find({
    "$and": [
        {"context.department": "engineering"},
        {"context.active": True}
    ]
})

# Array operations
tech_users = await User.find({"context.skills": {"$in": ["python", "javascript"]}})

# Regular expressions
johnson_family = await User.find({
    "context.name": {"$regex": "Johnson", "$options": "i"}
})

# Complex nested queries
active_senior_engineers = await User.find({
    "$and": [
        {"context.department": "engineering"},
        {"context.age": {"$gte": 35}},
        {"context.active": True},
        {"context.skills": {"$in": ["python", "go", "rust"]}}
    ]
})
```

## Walker Traversal Patterns

Walkers implement graph traversal logic using the `nodes()` and `node()` methods for semantic filtering:

```python
from jvspatial.core import Walker, on_visit

class DataCollector(Walker):
    def __init__(self):
        super().__init__()
        self.collected_data = []

    @on_visit(User)
    async def collect_user_data(self, here: User):
        """Process user nodes with semantic filtering."""
        self.collected_data.append(here.name)

        # Get multiple connected nodes
        engineering_users = await here.nodes(
            node=['User'],  # Only User nodes
            department="engineering",  # Simple filtering
            active=True  # Multiple filters
        )
        await self.visit(engineering_users)

        # Get a single connected node (when you expect only one)
        profile = await here.node(node='Profile')
        if profile:
            self.collected_data.append(profile.bio)

    @on_visit(City)
    async def process_city(self, here: City):
        """Process city nodes with control flow."""
        # Skip small cities
        if here.population < 10000:
            self.skip()  # Skip to next node
            return

        # Find large nearby cities
        large_cities = await here.nodes(
            node=[{'City': {"context.population": {"$gte": 500_000}}}],
            direction="out"
        )
        await self.visit(large_cities)

# Walker control methods
# - skip(): Skip current node, continue to next
# - pause()/resume(): Temporarily pause walker
# - disengage(): Permanently halt walker
```

## Walker Trail Tracking

jvspatial walkers include built-in trail tracking capabilities to monitor and record the path taken during graph traversal:

```python
from jvspatial.core import Walker, on_visit

class TrackingWalker(Walker):
    def __init__(self):
        super().__init__()
        # Enable trail tracking with maximum 50 steps
        self.trail_enabled = True
        self.max_trail_length = 50

    @on_visit(User)
    async def visit_user(self, here: User):
        print(f"Visited user: {here.name}")

        # Get current trail
        trail = self.get_trail()  # List of node IDs
        print(f"Current trail length: {len(trail)}")

        # Get recent trail steps
        recent_steps = self.get_recent_trail(count=3)
        print(f"Recent steps: {recent_steps}")

        # Continue traversal
        colleagues = await here.nodes(node=['User'], department=here.department)
        await self.visit(colleagues)

    @on_exit
    async def generate_trail_report(self):
        """Generate a comprehensive trail report."""
        # Get full trail with node objects
        trail_nodes = await self.get_trail_nodes()

        # Get trail with connecting edges
        trail_path = await self.get_trail_path()

        # Use report() method to collect trail data
        self.report({
            "trail_report": {
                "total_steps": self.get_trail_length(),
                "visited_nodes": [node.name for node in trail_nodes],
                "path_details": [
                    {
                        "node": node.name,
                        "edge": edge.edge_type if edge else "start"
                    }
                    for node, edge in trail_path
                ]
            }
        })

# Usage
walker = TrackingWalker()
root = await Root.get()
await walker.spawn(root)

# Access trail information from walker's report
report = walker.get_report()
trail_reports = [item for item in report if isinstance(item, dict) and 'trail_report' in item]
trail_report = trail_reports[0]['trail_report'] if trail_reports else None
print(f"Final trail: {trail_report}")
```

### Trail API Reference

**Configuration (read/write):**
- `trail_enabled` - Enable/disable trail tracking
- `max_trail_length` - Maximum number of steps to retain (0 = unlimited)

**Trail Data (read-only properties):**
- `trail` - List of visited node IDs (returns copy to prevent modification)
- `trail_edges` - List of edge IDs traversed between nodes (read-only)
- `trail_metadata` - Metadata for each trail step (read-only)

**Trail Access Methods:**
- `get_trail()` - Get list of visited node IDs
- `get_trail_nodes()` - Get actual Node objects from trail
- `get_trail_path()` - Get trail with connecting edges
- `get_trail_length()` - Get current trail length
- `get_trail_metadata(step)` - Get metadata for specific step
- `get_recent_trail(count)` - Get recent N steps
- `clear_trail()` - Clear entire trail history (only way to modify trail)

## FastAPI Server Integration

The jvspatial Server class provides seamless FastAPI integration with automatic OpenAPI documentation:

### Server Setup

```python
from jvspatial.api import Server, walker_endpoint
from jvspatial.api.endpoint.router import EndpointField
from jvspatial.core import Walker, Node, on_visit

# Create server with automatic database setup
server = Server(
    title="Spatial Data API",
    description="Graph-based data management",
    version="1.0.0",
    debug=True
)

@walker_endpoint("/api/users/analyze", methods=["POST"])
class AnalyzeUser(Walker):
    user_name: str = EndpointField(
        description="Name of user to analyze",
        examples=["Alice", "Bob"],
        min_length=2,
        max_length=100
    )

    department: str = EndpointField(
        default="general",
        description="User department filter",
        examples=["engineering", "marketing"]
    )

    @on_visit(Node)
    async def analyze_user(self, here: Node):
        # Find user and analyze connections
        users = await User.find({"context.name": self.user_name})

        if users:
            user = users[0]
            colleagues = await user.nodes(
                node=['User'],
                department=self.department,
                active=True
            )

            # Use report() method to collect analysis results
            self.report({
                "user_analysis": {
                    "user": {"name": user.name, "email": user.email},
                    "colleagues": len(colleagues),
                    "department": self.department
                }
            })
        else:
            self.report({"error": "User not found"})

if __name__ == "__main__":
    server.run()  # Available at http://localhost:8000/docs
```

### Enhanced Response Handling

The `@walker_endpoint` and `@endpoint` decorators now automatically inject semantic response helpers for clean, flexible HTTP responses:

```python
@walker_endpoint("/api/users/profile", methods=["POST"])
class UserProfileWalker(Walker):
    user_id: str = EndpointField(description="User ID to retrieve")

    @on_visit(User)
    async def get_profile(self, here: User):
        if here.id != self.user_id:
            return  # Continue traversal

        # Clean, semantic error responses
        if not here.data:
            return self.endpoint.not_found(
                message="User not found",
                details={"user_id": self.user_id}
            )

        # Successful response with proper status
        return self.endpoint.success(
            data={"id": here.id, "name": here.name},
            message="User profile retrieved"
        )

@endpoint("/api/health", methods=["GET"])
async def health_check(endpoint):
    """Function endpoint with semantic responses."""
    return endpoint.success(
        data={"status": "healthy", "version": "1.0.0"},
        message="Service is running"
    )
```

**Available Response Methods:**
- `endpoint.success()` - 200 OK responses
- `endpoint.created()` - 201 Created responses
- `endpoint.not_found()` - 404 Not Found errors
- `endpoint.bad_request()` - 400 Bad Request errors
- `endpoint.unauthorized()` - 401 Unauthorized errors
- `endpoint.response()` - Flexible custom responses

### API Usage

```bash
# Call the endpoint
curl -X POST "http://localhost:8000/api/users/analyze" \
  -H "Content-Type: application/json" \
  -d '{
    "user_name": "Alice",
    "department": "engineering"
  }'
```

## Advanced Webhook System

JVspatial provides a powerful, production-ready webhook system with enterprise-grade security, reliability, and developer experience features:

### Modern Webhook Decorators

```python
from jvspatial.api.auth.decorators import webhook_endpoint, webhook_walker_endpoint
from jvspatial.core.entities import Walker, Node, on_visit

# Simple webhook with automatic payload injection
@webhook_endpoint("/webhook/payment")
async def payment_webhook(payload: dict, endpoint):
    """Process payment webhooks with automatic JSON parsing."""
    payment_id = payload.get("payment_id")
    amount = payload.get("amount")

    # Process payment...

    return endpoint.response(
        content={
            "status": "processed",
            "message": f"Payment {payment_id} processed: ${amount}"
        }
    )

# Advanced webhook with security features
@webhook_endpoint(
    "/webhook/stripe/{key}",
    path_key_auth=True,                    # API key in URL path
    hmac_secret="stripe-webhook-secret",   # HMAC signature verification
    idempotency_ttl_hours=48,              # Duplicate handling for 48h
    permissions=["process_payments"]
)
async def stripe_webhook(raw_body: bytes, content_type: str, endpoint):
    """Stripe webhook with path-based auth and HMAC verification."""
    import json

    if content_type == "application/json":
        payload = json.loads(raw_body.decode('utf-8'))
        event_type = payload.get("type", "unknown")

        # Process different Stripe events
        if event_type == "payment_intent.succeeded":
            return endpoint.response(
                content={
                    "status": "processed",
                    "event_type": event_type,
                    "message": "Payment successful"
                }
            )

    return endpoint.response(content={"status": "received"})

# Walker-based webhook for graph operations
@webhook_walker_endpoint("/webhook/location-update")
class LocationUpdateWalker(Walker):
    """Update spatial data based on webhook events."""

    def __init__(self, payload: dict):
        super().__init__()
        self.payload = payload
        # Use report() method for data collection during traversal

    @on_visit(Node)
    async def update_location_data(self, here: Node):
        # Access webhook payload data
        locations = self.payload.get("locations", [])

        for location_data in locations:
            # Update graph nodes with webhook data
            location_id = location_data.get("id")
            coordinates = location_data.get("coordinates")

            if location_id and coordinates:
                here.coordinates = coordinates
                await here.save()

                self.report({
                    "location_updated": {
                        "id": location_id,
                        "coordinates": coordinates
                    }
                })
```

### Enterprise Security Features

- **🔐 Path-Based Authentication**: API keys embedded in URLs for services that support it
- **🔏 HMAC Signature Verification**: Per-endpoint secrets with automatic verification
- **🚫 Idempotency Protection**: Database-backed duplicate request handling with configurable TTL
- **⚡ Asynchronous Processing**: Queue webhooks for background processing
- **🛡️ HTTPS Enforcement**: Configurable HTTPS-only webhook processing
- **📏 Payload Limits**: Configurable size limits with support for raw/JSON/XML payloads
- **🎯 Permission-Based Access**: Full RBAC integration
- **📊 Event Tracking**: Complete audit trail with GraphContext database entities

### Automatic Server Integration

```python
from jvspatial.api import Server

# Webhook middleware is automatically added when webhook endpoints are detected
server = Server(
    title="My Webhook API",
    description="API with advanced webhook processing"
)

# Webhook endpoints registered via decorators are automatically discovered
# Security middleware is automatically configured
# Database entities for tracking are automatically created

server.run()  # Webhooks ready at /webhook/* paths
```

### Environment Configuration

```bash
# Global webhook settings
JVSPATIAL_WEBHOOK_HMAC_SECRET=your-global-hmac-secret
JVSPATIAL_WEBHOOK_MAX_PAYLOAD_SIZE=5242880  # 5MB
JVSPATIAL_WEBHOOK_IDEMPOTENCY_TTL=3600      # 1 hour
JVSPATIAL_WEBHOOK_HTTPS_REQUIRED=true
```

### Testing & Development

```bash
# Simple webhook test
curl -X POST "http://localhost:8000/webhook/payment" \
  -H "Content-Type: application/json" \
  -d '{"payment_id": "pay_123", "amount": 99.99}'

# Webhook with path-based auth
curl -X POST "http://localhost:8000/webhook/stripe/key123:secret456" \
  -H "Content-Type: application/json" \
  -H "X-Signature: sha256=abc123..." \
  -d '{"type": "payment_intent.succeeded"}'

# With idempotency key
curl -X POST "http://localhost:8000/webhook/payment" \
  -H "Content-Type: application/json" \
  -H "X-Idempotency-Key: unique-123" \
  -d '{"payment_id": "pay_124"}'
```

### Key Benefits

1. **🚀 Developer Experience**: Automatic payload injection, standardized responses, comprehensive error handling
2. **🏢 Enterprise Ready**: Database persistence, retry mechanisms, audit trails
3. **🔒 Security First**: Multiple authentication methods, signature verification, HTTPS enforcement
4. **⚡ High Performance**: Asynchronous processing, efficient idempotency checking
5. **🔧 Flexible**: Support for JSON, XML, binary payloads and custom processing
6. **📈 Scalable**: Database-backed state management, configurable limits

> **📖 Complete webhook documentation:** [Webhook Architecture Guide](docs/md/webhook-architecture.md) | [Webhook Quickstart](docs/md/webhooks-quickstart.md)

## Object Pagination

Handle large datasets efficiently with built-in database-level pagination:

### Simple Pagination

```python
from jvspatial.core.pager import paginate_objects, City

# Get first page of cities (default: 20 per page)
cities = await paginate_objects(City, page=1, page_size=20)

# Paginate with filters
large_cities = await paginate_objects(
    City,
    page=1,
    page_size=10,
    filters={"context.population": {"$gt": 1_000_000}}
)
```

### Advanced Pagination with ObjectPager

```python
from jvspatial.core.pager import ObjectPager

# Create pager with filters and ordering
pager = ObjectPager(
    City,
    page_size=25,
    filters={"context.population": {"$gte": 100_000}},
    order_by="population",
    order_direction="desc"
)

# Navigate through pages
large_cities = await pager.get_page(1)
if pager.has_next_page():
    more_cities = await pager.next_page()

# Process all pages efficiently
while True:
    cities = await pager.next_page()
    if not cities:
        break
    # Process batch
    await process_cities(cities)
```

## Complex Traversal Example
````markdown
```python
# From traversal_demo.py (simplified)
class DeliveryWalker(Walker):
    @on_visit(City)
    async def deliver_package(self, here: City):
        # Highlight 1: Conditional delivery logic
        if here.is_hub and random.random() < 0.75:
            self.packages_delivered += 1

        # Highlight 2: Probabilistic path selection
        connections = await here.edges(edge_type=Highway)
        if connections:
            next_city = random.choice([c.target_node for c in connections])
            await self.visit(next_city)

    @on_exit
    async def final_report(self):
        # Highlight 3: Built-in metrics collection using report()
        self.report({
            "delivery_summary": {
                "delivered": self.packages_delivered,
                "visited": len(self.visited_nodes)
            }
        })
```
Key Features Demonstrated:
- Conditional node processing
- Edge-based traversal decisions
- Automatic metric collection
- Context-managed database sessions
````

## @on_visit Decorator

**NEW**: The `@on_visit` decorator supports powerful multi-target and edge traversal capabilities:

### Multi-Target Hooks
Handle multiple entity types with a single hook function:

```python
class LogisticsWalker(Walker):
    @on_visit(Warehouse, Port, Factory)  # Triggers for ANY of these types
    async def handle_facility(self, here):
        facility_type = here.__class__.__name__
        print(f"Processing {facility_type}: {here.name}")

        # Business logic that applies to all facility types
        await self.process_inventory(here)
```

### Catch-All Hooks
Create universal hooks that respond to any entity type:

```python
class InspectionWalker(Walker):
    @on_visit()  # No parameters = catch-all
    async def inspect_anything(self, here):
        # This runs for EVERY node and edge visited
        self.report({
            "inspected_item": {
                "type": here.__class__.__name__,
                "id": here.id
            }
        })
```

### Transparent Edge Traversal
Walkers automatically traverse edges when moving between connected nodes:

```python
class TransportWalker(Walker):
    @on_visit(City)
    async def visit_city(self, here):
        print(f"Arrived in {here.name}")

        # Find connected cities and queue them for visits
        connected_cities = await (await here.nodes()).filter(node='City')
        await self.visit(connected_cities)  # Edges will be traversed automatically!

    @on_visit(Highway, Railroad)  # Handle different transport types
    async def use_transport(self, here):
        # This hook is triggered automatically during traversal between cities
        transport_cost = self.calculate_cost(here)
        print(f"Using {here.name}, cost: ${transport_cost}")
        # Walker automatically moves to the connected city after processing
```

### Smart Entity Responses
Nodes and Edges can respond differently to specific Walker types:

```python
# Smart node that responds to different walker types
class SmartWarehouse(Warehouse):
    @on_visit(LogisticsWalker, InspectionWalker)  # Multi-target response
    async def handle_authorized_access(self, visitor):
        if isinstance(visitor, LogisticsWalker):
            visitor.report({"inventory_access": "GRANTED"})
        elif isinstance(visitor, InspectionWalker):
            visitor.report({"compliance_report": self.get_compliance_data()})

# Smart edge with walker-specific behavior
class SmartHighway(Highway):
    @on_visit(LogisticsWalker)
    async def commercial_vehicle_access(self, visitor):
        # Give commercial vehicles priority lane access
        visitor.report({"priority_lane": True})
        visitor.report({"toll_discount": 0.15})
```

### Type Validation
The decorator enforces proper targeting:
- **Walkers** can only target `Node` and `Edge` types
- **Nodes** and **Edges** can only target `Walker` types
- Invalid targeting raises `TypeError` at class definition time

```python
# ✅ Valid - Walker targeting Node types
class MyWalker(Walker):
    @on_visit(City, Warehouse)  # Valid
    async def handle_locations(self, here): pass

# ❌ Invalid - Walker cannot target other Walkers
class BadWalker(Walker):
    @on_visit(LogisticsWalker)  # TypeError!
    async def invalid_hook(self, here): pass
```

## Walker Reporting and Event Systems

### Simple Data Collection with `report()`

The reporting system allows walkers to collect any data during traversal using a simple, direct approach:

```python
from jvspatial.core import Walker, on_visit, on_exit

class DataCollector(Walker):
    @on_visit(User)
    async def collect_user_data(self, here: User):
        # Report any data - dicts, strings, numbers, lists
        self.report({
            "user": {
                "id": here.id,
                "name": here.name,
                "department": here.department
            }
        })

        # Report simple values
        self.report(f"Processed: {here.name}")

    @on_exit
    async def generate_summary(self):
        current_data = self.get_report()
        self.report({"total_items": len(current_data)})

# Usage - get data as a simple list
walker = DataCollector()
result_walker = await walker.spawn()
report = result_walker.get_report()  # Direct list access

for item in report:
    print(f"Collected: {item}")
```

### Inter-Walker Communication with Events

Walkers can communicate in real-time using the event system:

```python
from jvspatial.core.events import on_emit
import asyncio

class AlertWalker(Walker):
    """Walker that detects issues and emits alerts."""

    @on_visit('ServerNode')
    async def monitor_server(self, here: Node):
        if here.cpu_usage > 90:
            # Emit event to other walkers
            await self.emit("high_cpu_alert", {
                "server_id": here.id,
                "cpu_usage": here.cpu_usage,
                "severity": "critical"
            })
            self.report({"alert_sent": here.id})

class ResponseWalker(Walker):
    """Walker that responds to alerts from other walkers."""

    @on_emit("high_cpu_alert")
    async def handle_cpu_alert(self, event_data):
        server_id = event_data.get("server_id")
        self.report({
            "alert_handled": {
                "server": server_id,
                "action": "cleanup_initiated"
            }
        })

# Run walkers concurrently - they'll communicate automatically
alert_walker = AlertWalker()
response_walker = ResponseWalker()

# Both walkers run and communicate via events
results = await asyncio.gather(
    alert_walker.spawn(),
    response_walker.spawn()
)
```

### Key Benefits

**Reporting System:**
- **Simple**: `walker.report(any_data)` and `walker.get_report()`
- **Direct Access**: No nested structures - get a plain list of your data
- **Flexible**: Report strings, dicts, numbers, lists - any data type
- **Aggregation**: Perfect for collecting analytics and generating summaries

**Event System:**
- **Real-time**: Walkers communicate during traversal
- **Decoupled**: Walkers don't need to know about each other
- **Concurrent**: Multiple walkers can run and coordinate simultaneously
- **Event-Driven**: Build complex workflows with event chains

**[📖 Complete Guide: Walker Reporting & Events](./docs/md/walker-reporting-events.md)**

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
            self.report({"error": "No storage facilities available"})

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
        self.report({
            "inventory_item": {
                "id": here.id,
                "name": here.name,
                "location": here.storage_location
            }
        })

    @on_exit
    async def final_report(self):
        # Report final inventory summary
        total_items = len(self.found_items)
        unique_categories = len({item.category for item in self.found_items})

        self.report({
            "inventory_summary": {
                "total_items": total_items,
                "unique_categories": unique_categories
            }
        })
        print(f"Inventory check complete. Found {total_items} items.")
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

## Optimization Insights

### Database Performance Benchmarks

| Feature              | JSONDB Implementation      | MongoDB Implementation     |
|----------------------|----------------------------|----------------------------|
| Version Storage      | `_version` field in docs   | Atomic `findOneAndUpdate`  |
| Conflict Detection   | Pre-update version check   | Built-in atomic operations |
| Performance (10k ops)| 2.1s ±0.3s                 | 1.4s ±0.2s                |
| Best For             | Single-node deployments    | Distributed systems        |
| Migration Strategy   | Batch version field adds   | Schema versioning          |

## License

This project is licensed under the MIT License - see the [LICENSE](docs/md/license.md) file for details.

## Acknowledgments

- Inspired by [Jaseci](https://github.com/Jaseci-Labs/jaseci) and its Object-Spatial paradigm
- Built with [Pydantic](https://pydantic-docs.helpmanual.io/) for data validation
- REST API powered by [FastAPI](https://fastapi.tiangolo.com/)

---

## Documentation & Support

### Core Documentation
- **[Full Documentation](./docs/md/)** - Complete guide to jvspatial
- **[API Reference](./docs/md/rest-api.md)** - REST API integration guide
- **[Walker Reporting & Events](./docs/md/walker-reporting-events.md)** - Data collection and inter-walker communication
- **[Examples](./docs/md/examples.md)** - Working examples and patterns

### Authentication & Security
- **[Authentication System](./docs/md/authentication.md)** - JWT, API keys, and RBAC
- **[Authentication Quickstart](./docs/md/auth-quickstart.md)** - Get secured in 5 minutes
- **[Authentication Demo](./examples/auth_demo.py)** - Complete working example

### Support
- **Issues**: [GitHub Issues](https://github.com/TrueSelph/jvspatial/issues)
- **Discussions**: [GitHub Discussions](https://github.com/TrueSelph/jvspatial/discussions)

---
## Contributors

<p align="center">
    <a href="https://github.com/TrueSelph/jvspatial/graphs/contributors">
        <img src="https://contrib.rocks/image?repo=TrueSelph/jvspatial" />
    </a>
</p>