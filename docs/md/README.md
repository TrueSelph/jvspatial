# jvspatial Documentation

## Getting Started

- [Installation and Setup](../../README.md#installation)
- [Quick Start](../../README.md#quick-start)
- [Core Concepts](core-concepts.md)
- [Design Decisions](design-decisions.md)

## Fundamentals

### Entity Management
- [Entity Reference](entity-reference.md) - Node and Edge operations
- [Entity Attributes](attribute-annotations.md) - Field annotations and validation
- [MongoDB Query Interface](mongodb-query-interface.md) - Query capabilities
- [Object Pagination](pagination.md) - Efficient data access

### Graph Operations
- [Graph Traversal](graph-traversal.md) - Walker patterns and algorithms
- [Walker Queue Operations](walker-queue-operations.md) - Queue management
- [Walker Trail Tracking](walker-trail-tracking.md) - Path recording
- [Walker Reporting & Events](walker-reporting-events.md) - Data collection

## Integration

### API & Server
- [REST API Guide](rest-api.md) - FastAPI integration
- [Server API](server-api.md) - Server configuration
- [Environment Configuration](environment-configuration.md) - Setup options

### Storage & Security
- [File Storage Guide](file-storage-usage.md) - Multi-backend storage
- [File Storage Architecture](file-storage-architecture.md) - Technical details
- [Authentication Guide](authentication.md) - Security and access control
- [Authentication Quickstart](auth-quickstart.md) - 5-minute setup

### Advanced Features
- [Webhook Architecture](webhook-architecture.md) - Event handling
- [Webhooks Quickstart](webhooks-quickstart.md) - Basic setup
- [Scheduler Guide](scheduler.md) - Background tasks
- [Caching System](caching.md) - Performance optimization

## Development

### Best Practices
- [Migration Guide](migration.md) - Moving from other systems
- [Error Handling](error-handling.md) - Exception patterns
- [Infinite Walk Protection](infinite-walk-protection.md) - Safety limits
- [Node Operations](node-operations.md) - Working with nodes

### Project Info
- [Contributing Guide](contributing.md)
- [Examples](examples.md)
- [Troubleshooting](troubleshooting.md)
- [License](license.md)

## Migration Checklist

When migrating to jvspatial from another system:

1. **Assessment**
   - [ ] Identify current data models and relationships
   - [ ] Map existing queries to jvspatial patterns
   - [ ] List required integrations (auth, storage, etc.)

2. **Core Setup**
   - [ ] Install jvspatial and dependencies
   - [ ] Configure database backend
   - [ ] Set up environment variables

3. **Data Migration**
   - [ ] Convert models to Node/Edge classes
   - [ ] Create data migration scripts
   - [ ] Validate data integrity

4. **Integration**
   - [ ] Set up authentication if needed
   - [ ] Configure file storage if needed
   - [ ] Integrate with existing services

5. **Testing**
   - [ ] Run migration on test data
   - [ ] Verify query results
   - [ ] Test performance
   - [ ] Validate relationships

6. **Deployment**
   - [ ] Plan deployment strategy
   - [ ] Set up monitoring
   - [ ] Create rollback plan
   - [ ] Document changes

See the [Migration Guide](migration.md) for detailed instructions.

## Common Tasks

### Working with Entities

```python
from jvspatial.core import Node, Edge

# Create entities
user = await User.create(name="Alice", email="alice@example.com")
post = await Post.create(title="Hello", content="World")
author = await AuthorEdge.create(src=user, dst=post)

# Query entities
active_users = await User.find({
    "context.active": True,
    "context.last_login": {"$gte": last_week}
})

# Graph traversal
posts = await user.nodes(
    node=Post,
    edge=AuthorEdge,
    status="published"
)
```

### REST API Integration

```python
from jvspatial.api import Server, walker_endpoint

server = Server(title="My API")

@walker_endpoint("/api/users/{user_id}/posts")
class UserPostsWalker(Walker):
    @on_visit(User)
    async def get_posts(self, here: User):
        posts = await here.nodes(
            node=Post,
            edge=AuthorEdge
        )
        self.report({"posts": [post.export() for post in posts]})

server.run()
```

### Authentication

```python
from jvspatial.api.auth import configure_auth, auth_endpoint

configure_auth(jwt_secret_key="your-secret-key")

@auth_endpoint("/api/protected", permissions=["read_data"])
async def protected_endpoint():
    return {"message": "Authenticated access"}
```

### File Storage

```python
from jvspatial.storage import get_file_interface

storage = get_file_interface()

# Save file
await storage.save_file("path/to/file.pdf", content)

# Create temporary URL
url = await storage.get_signed_url(
    "path/to/file.pdf",
    expires_in=3600
)
```

See individual guides for more detailed documentation on each topic.