# Graph Traversal Guide

## Overview

jvspatial provides powerful graph traversal capabilities through its Walker system. This guide covers traversal patterns, optimization techniques, and best practices for efficient graph navigation.

## Table of Contents

- [Basic Traversal](#basic-traversal)
- [Walker Types](#walker-types)
- [Traversal Patterns](#traversal-patterns)
- [Performance Optimization](#performance-optimization)
- [Safety and Protection](#safety-and-protection)

## Basic Traversal

### Simple Node Walking

```python
from jvspatial.core import Walker

class SimpleWalker(Walker):
    async def visit_node(self, node):
        print(f"Visiting node: {node.id}")

        # Get connected nodes
        neighbors = await node.get_neighbors()

        # Continue traversal
        for neighbor in neighbors:
            await self.walk(neighbor)

# Use the walker
walker = SimpleWalker()
await walker.walk(start_node)
```

### Filtered Traversal

```python
from jvspatial.core import Walker
from jvspatial.core.entities import on_visit

class UserWalker(Walker):
    @on_visit(User)
    async def handle_user(self, user: User):
        # Only processes User nodes
        print(f"Found user: {user.name}")

    @on_visit(Product)
    async def handle_product(self, product: Product):
        # Only processes Product nodes
        print(f"Found product: {product.name}")
```

## Walker Types

### Breadth-First Walker

```python
from jvspatial.walkers import BFSWalker

class BreadthFirstWalker(BFSWalker):
    async def visit_node(self, node):
        # Process nodes level by level
        level = self.current_level()
        print(f"Node {node.id} at level {level}")
```

### Depth-First Walker

```python
from jvspatial.walkers import DFSWalker

class DepthFirstWalker(DFSWalker):
    async def visit_node(self, node):
        # Process nodes depth-first
        depth = self.current_depth()
        print(f"Node {node.id} at depth {depth}")
```

### Path-Finding Walker

```python
from jvspatial.walkers import PathWalker

class ShortestPathWalker(PathWalker):
    def __init__(self, target_id: str):
        super().__init__()
        self.target_id = target_id
        self.found_path = None

    async def visit_node(self, node):
        if node.id == self.target_id:
            self.found_path = self.current_path()
            return self.STOP_TRAVERSAL
```

## Traversal Patterns

### Edge-Type Filtering

```python
class RelationshipWalker(Walker):
    async def visit_node(self, node):
        # Only follow specific edge types
        followers = await node.get_neighbors(
            edge_type=Follows,
            direction="incoming"
        )

        friends = await node.get_neighbors(
            edge_type=Friendship,
            direction="both"
        )
```

### Conditional Traversal

```python
class ConditionalWalker(Walker):
    async def should_visit(self, node) -> bool:
        # Skip inactive nodes
        if hasattr(node, "active") and not node.active:
            return False
        return True

    async def should_traverse_edge(self, edge) -> bool:
        # Only traverse recent relationships
        if edge.created_at < self.cutoff_date:
            return False
        return True
```

### Data Collection

```python
class DataCollector(Walker):
    def __init__(self):
        super().__init__()
        self.collected_data = []

    async def visit_node(self, node):
        if isinstance(node, DataNode):
            self.collected_data.append({
                "id": node.id,
                "type": node.__class__.__name__,
                "data": await node.get_data()
            })
```

## Performance Optimization

### Parallel Processing

```python
from jvspatial.walkers import ParallelWalker

class FastWalker(ParallelWalker):
    max_workers = 4

    async def process_node(self, node):
        # Nodes processed in parallel
        result = await self.heavy_computation(node)
        await self.store_result(result)
```

### Caching Support

```python
from jvspatial.cache import cached_walk

class CachedWalker(Walker):
    @cached_walk(ttl=3600)  # Cache for 1 hour
    async def visit_node(self, node):
        result = await self.expensive_operation(node)
        return result
```

### Batch Processing

```python
class BatchWalker(Walker):
    def __init__(self, batch_size=100):
        super().__init__()
        self.batch = []
        self.batch_size = batch_size

    async def visit_node(self, node):
        self.batch.append(node)

        if len(self.batch) >= self.batch_size:
            await self.process_batch()
            self.batch = []

    async def process_batch(self):
        await self.db.bulk_operation(self.batch)
```

## Safety and Protection

### Cycle Detection

```python
class SafeWalker(Walker):
    def __init__(self):
        super().__init__()
        self.visited = set()

    async def visit_node(self, node):
        if node.id in self.visited:
            return self.SKIP_NODE

        self.visited.add(node.id)
        await self.process_node(node)
```

### Depth Limiting

```python
class DepthLimitedWalker(Walker):
    max_depth = 5

    async def should_continue(self) -> bool:
        if self.current_depth() > self.max_depth:
            return False
        return True
```

### Resource Management

```python
class ResourceAwareWalker(Walker):
    async def __aenter__(self):
        await self.acquire_resources()
        return self

    async def __aexit__(self, *args):
        await self.release_resources()

    async def visit_node(self, node):
        async with self.resource_lock:
            await self.process_node(node)
```

## Best Practices

1. Always implement cycle detection for unknown graphs
2. Use appropriate walker type for your traversal pattern
3. Implement depth limits for safety
4. Cache expensive operations
5. Use parallel processing for independent operations
6. Batch process when possible
7. Monitor and limit resource usage
8. Implement proper error handling and recovery
9. Use type-specific handlers for cleaner code
10. Consider edge conditions in traversal logic