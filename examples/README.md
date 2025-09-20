# JVSpatial Examples

This directory contains examples demonstrating both the original API (which continues to work unchanged) and the new **GraphContext dependency injection pattern** that eliminates scattered database selection.

## 🎯 Quick Start

If you're **new to JVSpatial**, start with the original API examples. They work exactly as before:

```python
# Original API - Still works exactly the same!
city = await City.create(name="Chicago", population=2700000)
highway = await Highway.create(left=city1, right=city2, distance_km=200)
retrieved = await City.get(city.id)
```

If you want **advanced control** over database connections (testing, multiple databases, etc.), check out the GraphContext examples.

## 📁 Example Files

### Core Examples

#### 🚀 [`graphcontext_demo.py`](./graphcontext_demo.py) **⭐ START HERE**
**Complete demonstration of GraphContext dependency injection patterns**

Shows 5 patterns from simple to advanced:
1. **Original API** - No changes needed, works exactly as before
2. **Explicit GraphContext** - Advanced control over database connections
3. **Multiple Contexts** - Different databases for different purposes
4. **Testing Pattern** - Isolated test databases and mocking
5. **Backwards Compatibility** - Proves all existing code still works

```bash
python examples/graphcontext_demo.py
```

#### 🗺️ [`travel_graph.py`](./travel_graph.py)
**Updated travel/spatial example with GraphContext additions**

Original travel graph example enhanced to show:
- Basic node/edge creation (unchanged)
- Walker traversal patterns (unchanged)
- Spatial queries (unchanged)
- GraphContext for advanced scenarios (new)

```bash
python examples/travel_graph.py
```

#### 🤖 [`agent_graph.py`](./agent_graph.py)
**Hierarchical agent system with both API patterns**

Demonstrates:
- Building complex node hierarchies
- API endpoint integration
- Original API approach vs GraphContext approach
- Agent management with geographic properties

```bash
python examples/agent_graph.py
```

### Testing Examples

#### 🧪 [`testing_with_graphcontext.py`](./testing_with_graphcontext.py) **⭐ IMPORTANT FOR TESTING**
**Complete testing patterns with GraphContext**

Shows how GraphContext makes testing much easier:
- **Test Isolation** - Each test gets its own database
- **Mock Injection** - Unit testing with mock databases
- **Integration Testing** - Real database testing with isolation
- **Setup/Teardown** - Proper test lifecycle management
- **Legacy Compatibility** - Existing test code still works

```bash
python examples/testing_with_graphcontext.py
```

### API/Server Examples

#### 🌐 [`server_demo.py`](./server_demo.py)
FastAPI server integration (original API)

#### 🔄 [`dynamic_server_demo.py`](./dynamic_server_demo.py)
Dynamic endpoint management

#### 📡 [`endpoint_decorator_demo.py`](./endpoint_decorator_demo.py)
Endpoint decorators and routing

## 🔄 Migration Guide

### For Existing Users

**Good news: No changes required!** All your existing code continues to work:

```python
# This code works exactly the same before and after the refactor
node = await MyNode.create(name="Test", value=42)
node.data['extra'] = 'info'
await node.save()

retrieved = await MyNode.get(node.id)
edge = await MyEdge.create(left=node1, right=node2)

class MyWalker(Walker):
    @on_visit(MyNode)
    async def visit_node(self, here):
        print(f"Visiting {here.name}")

walker = MyWalker()
await walker.spawn(start=node)
```

### For Advanced Use Cases

If you want the benefits of GraphContext (testing, multiple databases, etc.), you can optionally use:

```python
from jvspatial.core.context import GraphContext
from jvspatial.db.factory import get_database

# Create custom context
ctx = GraphContext(database=get_database(db_type="json", base_path="/custom/path"))

# Use context for operations
node = await ctx.create_node(MyNode, name="Test")
retrieved = await ctx.get_node(node.id, MyNode)

# Original API still works with context-created entities
node.name = "Updated"
await node.save()  # Uses the entity's context automatically
```

## 🔍 Key Benefits Demonstrated

### ✅ Clean Architecture
- **Before**: `cls.db = get_database() if cls.db is None else cls.db` scattered everywhere
- **After**: Clean dependency injection with GraphContext

### ✅ Easy Testing
- **Before**: Shared global database state caused test interference
- **After**: Isolated databases per test, easy mocking

### ✅ Multiple Databases
- **Before**: One global database connection
- **After**: Multiple contexts for different purposes (main data, analytics, etc.)

### ✅ 100% Backwards Compatibility
- **Before**: Existing code
- **After**: Existing code works exactly the same + new capabilities available

## 🚀 Running Examples

All examples are self-contained and can be run directly:

```bash
# Run the main GraphContext demo
python examples/graphcontext_demo.py

# Run testing patterns demo
python examples/testing_with_graphcontext.py

# Run travel graph example
python examples/travel_graph.py

# Run agent hierarchy example
python examples/agent_graph.py
```

## 📚 Learning Path

1. **Start**: Run `graphcontext_demo.py` to see all patterns
2. **Learn**: Study `travel_graph.py` for practical usage
3. **Test**: Explore `testing_with_graphcontext.py` for testing approaches
4. **Build**: Use `agent_graph.py` as a template for hierarchical systems

## 🎯 When to Use What

### Use Original API When:
- Getting started with JVSpatial
- Simple applications with one database
- Migrating existing code (works unchanged)
- You want the simplest approach

### Use GraphContext When:
- Writing tests (isolation and mocking)
- Multiple database scenarios
- Advanced dependency injection needs
- You want explicit control over database connections

## 💡 Tips

1. **Start Simple**: The original API is perfect for learning and simple use cases
2. **Test with Context**: GraphContext makes testing much easier and more reliable
3. **Mix Approaches**: You can use both patterns in the same application
4. **No Breaking Changes**: All existing code continues to work unchanged

## 🔗 Related Documentation

- [GraphContext Reference](../jvspatial/core/context.py)
- [Database Factory](../jvspatial/db/factory.py)
- [Entity Classes](../jvspatial/core/entities.py)
- [Test Suite](../tests/) - Shows both old and new patterns in action