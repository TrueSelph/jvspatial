# Examples

This document showcases practical examples demonstrating jvspatial's GraphContext architecture and core features.

## Example Directory

The `examples/` directory contains working demonstrations:

### [Basic Usage (`basic_usage.py`)](../../examples/basic_usage.py)
**Simple node creation and walker traversal**

Demonstrates fundamental jvspatial patterns:
- Person nodes with automatic GraphContext management
- Walker traversal with @on_visit decorators
- Basic graph connections and traversal

```python
class Person(Node):
    name: str
    age: int = 0

class FriendWalker(Walker):
    @on_visit(Person)
    async def visit_person(self, here):
        print(f"Visiting {here.name} (age {here.age})")

# Usage with automatic GraphContext
person = await Person.create(name="Alice", age=30)
walker = FriendWalker()
result = await walker.spawn(person)
```

### [GraphContext Demo (`graphcontext_demo.py`)](../../examples/graphcontext_demo.py)
**Advanced database management and dependency injection**

Shows explicit GraphContext usage:
- Manual GraphContext creation and configuration
- Database isolation for testing
- Multiple context management
- Entity creation through context methods

```python
from jvspatial.core.context import GraphContext
from jvspatial.db.factory import get_database

# Create GraphContext with specific database
db = get_database(db_type="json", base_path="./my_data")
ctx = GraphContext(database=db)

# Create entities through context
city = await ctx.create_node(City, name="Chicago", population=2700000)
```

### [Social Network (`social_network.py`)](../../examples/social_network.py)
**Complete social graph with relationships**

Builds a comprehensive social network:
- User nodes with profiles and interests
- Friendship edges with strength attributes
- Content nodes (posts, comments) with relationships
- Walker patterns for social graph traversal

```python
class User(Node):
    username: str
    email: str
    interests: list[str] = []

class Friendship(Edge):
    strength: float = 1.0
    since: str = ""

class Post(Node):
    content: str
    timestamp: str = ""
```

## Core Patterns

### Simple GraphContext Usage (Recommended)

For most applications, use the automatic GraphContext approach:

```python
import asyncio
from jvspatial.core.entities import Node, Walker, on_visit

class Document(Node):
    title: str
    content: str = ""

class DocumentWalker(Walker):
    @on_visit(Document)
    async def visit_document(self, here):
        print(f"Document: {here.title}")

async def main():
    # Automatic GraphContext with default JSON database
    doc = await Document.create(title="My Doc", content="Hello World")

    walker = DocumentWalker()
    await walker.spawn(doc)

if __name__ == "__main__":
    asyncio.run(main())
```

### Advanced GraphContext Configuration

For complex applications needing explicit database control:

```python
import asyncio
from jvspatial.core.entities import Node, Edge
from jvspatial.core.context import GraphContext
from jvspatial.db.factory import get_database

class Organization(Node):
    name: str
    department: str = ""

class Manages(Edge):
    since: str = ""
    level: int = 1

async def main():
    # Custom database configuration
    db = get_database(
        db_type="json",
        base_path="./org_data",
        auto_create=True
    )
    ctx = GraphContext(database=db)

    # Create entities through context
    ceo = await ctx.create_node(Organization, name="Alice", department="Executive")
    cto = await ctx.create_node(Organization, name="Bob", department="Technology")

    # Create relationship
    manages = await ctx.create_edge(
        Manages,
        source=ceo,
        target=cto,
        since="2023-01",
        level=1
    )

    # Access through standard API
    retrieved_ceo = await Organization.get(ceo.id)
    print(f"CEO: {retrieved_ceo.name}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Testing with GraphContext

GraphContext enables isolated testing environments:

```python
import pytest
from jvspatial.core.context import GraphContext
from jvspatial.db.factory import get_database

@pytest.fixture
async def test_context():
    # Create isolated test database
    db = get_database(db_type="json", base_path=":memory:")
    ctx = GraphContext(database=db)
    yield ctx
    # Cleanup is automatic

async def test_user_creation(test_context):
    user = await test_context.create_node(
        User,
        username="testuser",
        email="test@example.com"
    )
    assert user.username == "testuser"

    # Verify persistence
    retrieved = await test_context.get_node(User, user.id)
    assert retrieved.email == "test@example.com"
```

## Running Examples

```bash
# Run basic usage example
cd jvspatial
python examples/basic_usage.py

# Run GraphContext demo
python examples/graphcontext_demo.py

# Run social network example
python examples/social_network.py
```

## Key Benefits of GraphContext

1. **Clean Dependency Injection**: No scattered database connections across classes
2. **Testing Isolation**: Easy to create isolated test environments
3. **Configuration Flexibility**: Switch databases without changing entity code
4. **Backward Compatibility**: Existing API (`Node.create()`, `Edge.create()`) works unchanged
5. **Explicit Control**: When needed, full control over database operations

For more details, see [GraphContext Documentation](./graph-context.md).
