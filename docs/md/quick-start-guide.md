# Quick Start Guide

**Version**: 0.0.1
**Date**: 2025-10-20

Get started with jvspatial in 5 minutes! This guide covers installation, basic concepts, and your first application.

---

## 📦 **Installation**

```bash
# Install jvspatial
pip install jvspatial

# Install with optional dependencies
pip install jvspatial[redis]  # For Redis cache
pip install jvspatial[s3]     # For S3 storage
pip install jvspatial[all]    # All optional deps
```

---

## 🎯 **Core Concepts**

jvspatial is built on three key concepts:

### **1. Graph Entities**
- **Nodes**: Data points in your graph
- **Edges**: Relationships between nodes
- **Root**: Entry point to your graph

### **2. Walkers**
- Traverse the graph
- Execute business logic
- Return results

### **3. Context**
- Manages database connections
- Handles configuration
- Provides lifecycle management

---

## 🚀 **Your First Application**

### **Step 1: Define Your Nodes**

```python
from jvspatial import Node
from pydantic import Field

class User(Node):
    """A user in the system."""
    name: str = Field(description="User's name")
    email: str = Field(description="User's email")
    age: int = Field(ge=0, description="User's age")

class Post(Node):
    """A blog post."""
    title: str
    content: str
    author_id: str  # Links to User
```

### **Step 2: Create a Walker**

```python
from jvspatial import Walker
from jvspatial.core import on_visit

class UserWalker(Walker):
    """Walks through users and their posts."""

    @on_visit
    async def visit_user(self, node: User):
        """Called when visiting a User node."""
        return {
            "user": node.name,
            "email": node.email,
        }

    @on_visit
    async def visit_post(self, node: Post):
        """Called when visiting a Post node."""
        return {
            "title": node.title,
            "preview": node.content[:100],
        }
```

### **Step 3: Create API Endpoints**

> **💡 Standard Examples**: For production-ready implementations with authentication, CRUD operations, and pagination, see:
> - **Authenticated API**: [`examples/api/authenticated_endpoints_example.py`](../../examples/api/authenticated_endpoints_example.py)
> - **Unauthenticated API**: [`examples/api/unauthenticated_endpoints_example.py`](../../examples/api/unauthenticated_endpoints_example.py)

```python
from jvspatial.api import Server, endpoint
from jvspatial.core import Node

# Create server (entity-centric operations are automatically available)
server = Server(
    title="My API",
    description="API description",
    version="1.0.0",
    db_type="json",
    db_path="./jvdb",
    auth_enabled=False  # Set to True to enable authentication
)

@endpoint("/users/{user_id}", methods=["GET"])
async def get_user(user_id: str):
    """Get a user by ID."""
    user = await User.get(user_id)  # Entity-centric operation
    if not user:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="User not found")
    return {"user": user.export()}
```

### **Step 4: Start the Server**

```python
import asyncio

async def main():
    # Create server
    server = Server(
        config=ServerConfig(
            host="0.0.0.0",
            port=8000,
            title="My First jvspatial App",
        )
    )

    # Start server
    await server.start()

if __name__ == "__main__":
    asyncio.run(main())
```

### **Step 5: Run It!**

```bash
python app.py
```

Visit: `http://localhost:8000/docs` for interactive API documentation!

---

## 📖 **Common Patterns**

### **Pattern 1: Creating Nodes**

```python
from jvspatial import Node
from jvspatial.core import GraphContext

# Create a node
async with GraphContext() as ctx:
    user = User(
        name="Alice",
        email="alice@example.com",
        age=30
    )
    await user.save(ctx=ctx)

    print(f"Created user: {user.id}")
```

### **Pattern 2: Querying Nodes**

```python
# Get by ID (returns None if not found)
user = await User.get("user_id_here")
if user is None:
    raise EntityNotFoundError(message="User not found", entity_type="User", entity_id="user_id_here")

# Query with MongoDB-style filters
users = await User.find({
    "context.age": {"$gt": 18},
    "context.name": {"$regex": "^A", "$options": "i"}
})
```

### **Pattern 3: Creating Relationships**

```python
from jvspatial import Edge

async with GraphContext() as ctx:
    # Create an edge (relationship)
    edge = Edge(
        source=user.id,
        target=post.id,
        relationship="authored"
    )
    await edge.save(ctx=ctx)
```

### **Pattern 4: Authenticated Endpoints**

```python
from jvspatial.api import endpoint

@endpoint("/admin/users", methods=["GET"], auth=True, roles=["admin"])
async def list_all_users():
    """Admin-only endpoint."""
    users = await User.find({})
    return {"users": [u.export() for u in users]}
```

### **Pattern 5: Caching**

```python
from jvspatial.utils import memoize

@memoize(maxsize=100, ttl=300)  # Cache for 5 minutes
async def expensive_calculation(n: int):
    """Expensive function that benefits from caching."""
    # ... complex computation ...
    return result
```

---

## 🔧 **Configuration**

### **Environment Variables**

Create a `.env` file:

```bash
# Database
DATABASE_BACKEND=jsondb
DATABASE_PATH=./data

# Cache
CACHE_BACKEND=memory
CACHE_TTL=300

# Server
SERVER_HOST=0.0.0.0
SERVER_PORT=8000

# Authentication
JWT_SECRET_KEY=your-secret-key-here
JWT_ALGORITHM=HS256
JWT_EXPIRATION=3600
```

### **Programmatic Configuration**

```python
from jvspatial.api import Server, ServerConfig

config = ServerConfig(
    host="0.0.0.0",
    port=8000,
    title="My API",
    description="Built with jvspatial",
    version="1.0.0",

    # CORS
    cors_enabled=True,
    cors_origins=["http://localhost:3000"],

    # Database
    database_backend="jsondb",
    database_path="./data",

    # Cache
    cache_backend="redis",
    redis_url="redis://localhost:6379",
)

server = Server(config=config)
```

---

## 🧪 **Testing Your Code**

### **Unit Test Example**

```python
import pytest
from jvspatial import Node
from jvspatial.core import GraphContext

@pytest.mark.asyncio
async def test_user_creation():
    """Test creating a user node."""
    async with GraphContext() as ctx:
        user = User(
            name="Test User",
            email="test@example.com",
            age=25
        )
        await user.save(ctx=ctx)

        # Verify
        retrieved = await User.get(user.id, ctx=ctx)
        assert retrieved.name == "Test User"
        assert retrieved.email == "test@example.com"
```

### **API Test Example**

```python
import pytest
from httpx import AsyncClient
from jvspatial.api import Server

@pytest.mark.asyncio
async def test_get_user_endpoint():
    """Test the get user endpoint."""
    server = Server()

    async with AsyncClient(app=server.app, base_url="http://test") as client:
        response = await client.get("/users/test_id")
        assert response.status_code == 200
        data = response.json()
        assert "user" in data
```

---

## 📚 **Next Steps**

### **Learn More**

1. **[Module Organization](module-responsibility-matrix.md)** - Understand the library structure
2. **[Import Patterns](import-patterns.md)** - Learn best practices for imports
3. **[API Architecture](api-architecture.md)** - Deep dive into API design
4. **[Graph Traversal](graph-traversal.md)** - Master the Walker pattern
5. **[Decorator Reference](decorator-reference.md)** - Learn all decorators

### **Explore Examples**

```bash
cd examples/
ls -la

# Run examples
python core/cities.py
python server/server_demo.py
python walkers/walker_traversal_demo.py
```

### **Join the Community**

- 📖 **Documentation**: [docs/](../README.md)
- 💬 **Discussions**: GitHub Discussions
- 🐛 **Issues**: GitHub Issues
- 📧 **Email**: support@jvspatial.com

---

## 🎓 **Common Gotchas**

### **1. Forgetting Context**

```python
# ❌ Wrong: No context
user = await User.get(user_id)

# ✅ Correct: With context
async with GraphContext() as ctx:
    user = await User.get(user_id, ctx=ctx)
```

### **2. Blocking Operations**

```python
# ❌ Wrong: Blocking call
import time
time.sleep(5)  # Blocks the entire async loop!

# ✅ Correct: Async sleep
import asyncio
await asyncio.sleep(5)
```

### **3. Not Awaiting Async Functions**

```python
# ❌ Wrong: Forgot await
user = User.get(user_id, ctx=ctx)  # Returns coroutine!

# ✅ Correct: With await
user = await User.get(user_id, ctx=ctx)
```

### **4. Importing from Internal Modules**

```python
# ❌ Wrong: Internal import
from jvspatial.core.walker.event_system import EventManager

# ✅ Correct: Public API
from jvspatial.core import Walker
```

---

## 🎉 **Congratulations!**

You now know the basics of jvspatial! Start building your graph-based applications and explore the advanced features as you grow.

**Happy coding!** 🚀

---

**Last Updated**: 2025-10-20
**Version**: 0.0.1
**Maintainer**: JVspatial Team

