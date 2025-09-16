# Advanced Usage

## Complex Traversal Patterns
```python
class InventoryWalker(Walker):
    @on_visit("StorageRoom")
    async def scan_storage(self, here):
        items = await (await here.nodes()).filter(node="InventoryItem")
        await self.visit(items)

    @on_visit("InventoryItem")
    async def check_stock(self, here):
        if here.quantity < here.min_stock:
            await self.reorder_item(here)

## Performance Optimization
- Use `NodeQuery.filter()` for batch operations
- Enable MongoDB indexing for frequent queries
- Implement walker result caching