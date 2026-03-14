# Troubleshooting

## Common Issues

### Database Connection Errors
```bash
# Verify MongoDB is running
mongosh --eval "db.runCommand({ping: 1})"

# Check environment variables
echo $JVSPATIAL_MONGODB_URI
```

### Walker Execution Issues
```python
# Enable debug logging
import logging
logging.basicConfig(level=logging.DEBUG)

# Add walker lifecycle logging
class DebugWalker(Walker):
    @on_visit(Node)
    async def log_visit(self, here):
        print(f"Visiting {here.id} ({here.__class__.__name__})")

## Performance Issues

```python
# Enable query logging
from jvspatial.db import database
database.log_queries = True

# Check query execution times
DEBUG=true python your_script.py
```

## Common Error Messages

**"Node not found"**
- Verify node ID exists in database
- Check database connection settings

**Removing nodes whose class is no longer imported (ghost nodes)**

If you have records whose entity class module was removed (e.g. an action removed from agent configuration), use `Node.get(id)` followed by `node.delete(cascade=True)`. jvspatial falls back to returning a base `Node` instance for such records so you can delete them through the standard interface, ensuring edges and dependent nodes are properly cleaned up. See [Entity Reference - Class-Aware Retrieval](entity-reference.md#class-aware-retrieval-and-ghost-node-fallback).

**"Invalid edge direction"**
- Use only 'in', 'out', or 'both'
- Verify edge creation parameters

## Database Migration Tips
1. Stop all write operations
2. Export data: `python -m jvspatial.db.export --format json`
3. Update configuration
4. Import data: `python -m jvspatial.db.import --file backup.json`

## Memory Management
```python
# Batch large operations
async with database.batch_mode():
    for item in large_dataset:
        await process_item(item)
```

## See Also

- [GraphContext & Database Management](graph-context.md) - Database configuration and setup
- [Examples](examples.md) - Working examples and best practices
- [Entity Reference](entity-reference.md) - Complete API reference
- [MongoDB-Style Query Interface](mongodb-query-interface.md) - Query troubleshooting
- [REST API Integration](rest-api.md) - API troubleshooting

---

**[← Back to README](../../README.md)** | **[Contributing →](contributing.md)**
