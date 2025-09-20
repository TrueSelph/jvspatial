# @on_visit Decorator - Multiple Entity Support

The `@on_visit` decorator in jvspatial provides powerful multi-entity targeting capabilities, allowing you to create flexible hooks that respond to multiple entity types with a single function.

## Overview

The `@on_visit` decorator supports three main patterns:

1. **Single Target**: Target a specific entity type
2. **Multi-Target**: Target multiple entity types with one hook
3. **Catch-All**: Target any entity type

## Single Target Hooks

Target a specific entity type:

```python
class MyWalker(Walker):
    @on_visit(CityNode)
    async def visit_city(self, here):
        print(f"Visiting city: {here.name}")
```

## Multi-Target Hooks

Handle multiple entity types with a single hook function:

```python
class LogisticsWalker(Walker):
    @on_visit(Warehouse, Port, Factory)  # Triggers for ANY of these types
    async def handle_facility(self, here):
        facility_type = here.__class__.__name__
        print(f"Processing {facility_type}: {here.name}")

        # Shared business logic for all facility types
        await self.process_inventory(here)

        # Type-specific logic
        if isinstance(here, Warehouse):
            await self.handle_warehouse_specific(here)
        elif isinstance(here, Port):
            await self.handle_port_specific(here)
```

## Catch-All Hooks

Create universal hooks that respond to any entity type:

```python
class InspectionWalker(Walker):
    @on_visit()  # No parameters = catch-all
    async def inspect_anything(self, here):
        # This runs for EVERY node and edge visited
        entity_type = here.__class__.__name__
        self.response.setdefault("inspected", []).append({
            "type": entity_type,
            "id": here.id,
            "timestamp": datetime.now().isoformat()
        })
```

## Entity-Specific Responses

Nodes and Edges can also use multi-target hooks to respond differently to various Walker types:

```python
class SmartWarehouse(Warehouse):
    @on_visit(LogisticsWalker, InspectionWalker)  # Multi-target response
    async def handle_authorized_access(self, visitor):
        # Different behavior based on visitor type
        if isinstance(visitor, LogisticsWalker):
            visitor.response["inventory_access"] = "GRANTED"
            visitor.response["current_stock"] = self.current_stock
        elif isinstance(visitor, InspectionWalker):
            visitor.response["compliance_report"] = await self.generate_compliance_data()
            visitor.response["last_inspection"] = self.last_inspection_date

class SmartHighway(Highway):
    @on_visit(LogisticsWalker, EmergencyWalker)
    async def provide_special_access(self, visitor):
        if isinstance(visitor, LogisticsWalker):
            # Commercial vehicle benefits
            visitor.response["priority_lane"] = True
            visitor.response["toll_discount"] = 0.15
        elif isinstance(visitor, EmergencyWalker):
            # Emergency vehicle access
            visitor.response["emergency_clearance"] = True
            visitor.response["fastest_route"] = await self.get_emergency_route()
```

## Type Validation

The decorator enforces proper targeting rules:

- **Walkers** can only target `Node` and `Edge` types
- **Nodes** and **Edges** can only target `Walker` types
- Invalid targeting raises `TypeError` at class definition time

```python
# ✅ Valid Examples
class ValidWalker(Walker):
    @on_visit(City, Highway)  # Walker targeting Node/Edge types
    async def handle_entities(self, here): pass

class ValidNode(Node):
    @on_visit(LogisticsWalker, InspectionWalker)  # Node targeting Walker types
    async def handle_visitors(self, visitor): pass

# ❌ Invalid Examples - These will raise TypeError
class InvalidWalker(Walker):
    @on_visit(LogisticsWalker)  # Walker cannot target other Walkers
    async def invalid_hook(self, here): pass

class InvalidNode(Node):
    @on_visit(CityNode)  # Node cannot target other Nodes
    async def invalid_hook(self, visitor): pass
```

## Transparent Edge Traversal

Walkers automatically traverse edges when moving between connected nodes. Edge hooks are triggered transparently during this traversal:

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

## Best Practices

### 1. Use Multi-Target for Shared Logic
When multiple entity types need similar processing:

```python
@on_visit(Warehouse, Factory, StorageUnit)
async def handle_storage_facility(self, here):
    # Shared inventory management logic
    await self.update_inventory_count(here)
    await self.check_capacity(here)
```

### 2. Combine with Type Checking
Use `isinstance()` for type-specific behavior within multi-target hooks:

```python
@on_visit(Highway, Railroad, ShippingRoute)
async def use_transportation(self, here):
    base_cost = 10.0

    if isinstance(here, Highway):
        cost = base_cost + here.toll_cost
    elif isinstance(here, Railroad):
        cost = base_cost * (2.0 if here.electrified else 1.5)
    elif isinstance(here, ShippingRoute):
        cost = base_cost * here.distance_km * 0.1

    self.total_cost += cost
```

### 3. Use Catch-All for Logging/Monitoring
Catch-all hooks are perfect for cross-cutting concerns:

```python
@on_visit()  # Catches everything
async def monitor_activity(self, here):
    # Universal monitoring logic
    self.activity_log.append({
        "entity_type": here.__class__.__name__,
        "entity_id": here.id,
        "timestamp": datetime.now(),
        "walker_id": self.id
    })
```

## Hook Execution Order

When multiple hooks target the same entity:
1. Specific type hooks execute first
2. Multi-target hooks execute next
3. Catch-all hooks execute last

This allows for layered processing where specific behavior runs before general behavior.

## Performance Considerations

- Multi-target hooks are registered efficiently at class definition time
- Hook lookup is O(1) for specific types, O(n) for multi-target matching
- Catch-all hooks have minimal overhead as they're checked last
- Entity responses are processed only when walker types match

The `@on_visit` decorator's multi-entity support provides a powerful and flexible way to handle complex entity interactions while maintaining clean, readable code.