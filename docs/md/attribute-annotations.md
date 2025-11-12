# Attribute Annotation System

The jvspatial framework provides an elegant annotation system for marking entity attributes with special behaviors using the `@attribute` decorator.

## Overview

- **`@attribute(protected=True)`**: Prevents modification after initial assignment during object construction
- **`@attribute(transient=True)`**: Excludes fields from serialization/export operations
- **`@attribute(private=True)`**: Marks fields as private/internal use only
- **Compound decorators**: Combine both annotations for fields that are both immutable and non-persistent

## Quick Example

```python
from pydantic import BaseModel, Field
from jvspatial.core.annotations import attribute, AttributeMixin

class MyEntity(AttributeMixin, BaseModel):
    # Protected - cannot be modified after initialization
    id: str = attribute(protected=True, description="Unique identifier")

    # Normal - can be freely modified
    name: str = "Default Name"

    # Transient - excluded from exports
    cache: dict = attribute(transient=True, default_factory=dict)

    # Both protected and transient
    internal_state: dict = attribute(protected=True, transient=True, default_factory=dict)
```

## Core Concepts

### Protected Attributes

Protected attributes can be set during object initialization but cannot be modified afterward. This is ideal for:

- **Identity fields** (id, uuid, etc.)
- **Immutable configuration** (foundation dates, creation timestamps)
- **Reference keys** that should never change

```python
entity = MyEntity(id="abc-123")
entity.id = "new-id"  # ✗ Raises AttributeProtectionError
```

### Transient Attributes

Transient attributes are excluded from export/serialization operations. Use these for:

- **Runtime caches and temporary data**
- **Processing state** that shouldn't be persisted
- **Derived values** that can be recalculated
- **Session-specific data**

```python
entity.cache["temp"] = "value"  # ✓ Works at runtime
data = entity.export()  # cache not included in export
```

### Compound Decorators

Combine both behaviors for internal state management:

```python
# Both immutable AND not exported
_state: dict = protected(transient(Field(default_factory=dict)))
```

## Usage Patterns

### Basic Protected Field

```python
class Entity(ProtectedAttributeMixin, BaseModel):
    id: str = protected("", description="Unique identifier")
```

### Transient with default_factory

Always use `Field()` when specifying `default_factory`:

```python
# ✓ Correct
cache: dict = transient(Field(default_factory=dict))
items: list = transient(Field(default_factory=list))

# ✗ Wrong - will not work
cache: dict = transient(default_factory=dict)
```

### With Field Arguments

Both decorators support all Pydantic Field arguments:

```python
score: int = protected(
    Field(default=0, ge=0, le=100),
    description="Score between 0-100"
)

tags: list = transient(
    Field(default_factory=list),
    description="Temporary tags"
)
```

### Compound Decorators

Use nested decorators in either order:

```python
# protected outside
state1: dict = protected(transient(Field(default_factory=dict)))

# transient outside
state2: dict = transient(protected(Field(default_factory=dict)))

# Both work identically
```

### Private Attribute Helper

Convenience function for protected + transient:

```python
from jvspatial.core.annotations import private_attr

_cache: dict = private_attr(default_factory=dict)
# Equivalent to: protected(transient(Field(default_factory=dict)))
```

## Integration with jvspatial Entities

All jvspatial core entities automatically support annotations:

### Object

```python
from jvspatial.core.entities import Object

class MyObject(Object):
    # id is already protected in Object base class
    data: str = ""
    temp: dict = transient(Field(default_factory=dict))
```

### Node

```python
from jvspatial.core.entities import Node

class City(Node):
    # id is already protected from Node
    population: int = 0
    founded: int = protected(0, description="Foundation year")
    visitors: int = transient(Field(default=0))
```

### Edge

```python
from jvspatial.core.entities import Edge

class Highway(Edge):
    # id, source, target are already protected from Edge
    lanes: int = protected(2, description="Number of lanes")
    traffic: int = transient(Field(default=0))
```

### Walker

```python
from jvspatial.core.entities import Walker

class MyWalker(Walker):
    # id is already protected from Walker
    max_depth: int = protected(10)
    current_depth: int = transient(Field(default=0))
```

## Inheritance

Annotations are inherited across the class hierarchy:

```python
class Parent(ProtectedAttributeMixin, BaseModel):
    parent_id: str = protected("")
    parent_cache: dict = transient(Field(default_factory=dict))

class Child(Parent):
    child_id: str = protected("")
    child_cache: dict = transient(Field(default_factory=dict))

# All four fields respect their annotations
child = Child(parent_id="p1", child_id="c1")
child.parent_id = "new"  # ✗ Protected
child.child_id = "new"   # ✗ Protected

data = child.export()  # Neither cache is exported
```

## Error Handling

### AttributeProtectionError

```python
from jvspatial.core.annotations import AttributeProtectionError

try:
    entity.id = "new-id"
except AttributeProtectionError as e:
    print(f"Cannot modify: {e.attr_name} on {e.cls_name}")
```

## Best Practices

### 1. Protect Identity Fields

```python
class Entity(ProtectedAttributeMixin, BaseModel):
    id: str = protected("")
    uuid: str = protected(Field(default_factory=lambda: str(uuid.uuid4())))
```

### 2. Mark Temporary Data as Transient

```python
class ProcessingEntity(ProtectedAttributeMixin, BaseModel):
    id: str = protected("")
    data: str = ""

    # Runtime only
    cache: dict = transient(Field(default_factory=dict))
    last_accessed: datetime = transient(Field(default_factory=datetime.now))
```

### 3. Use Compound for Internal State

```python
class StateMachine(ProtectedAttributeMixin, BaseModel):
    id: str = protected("")

    # Neither modifiable nor exportable
    _state_history: list = protected(transient(Field(default_factory=list)))
```

### 4. Always Use Field() for Complex Defaults

```python
# ✓ Correct
items: list = protected(Field(default_factory=list))

# ✗ Wrong
items: list = protected(default_factory=list)
```

## API Reference

### Decorators

#### `protected(field_def, **kwargs)`
Marks a field as protected - cannot be modified after initialization.

#### `transient(field_def, **kwargs)`
Marks a field as transient - excluded from exports.

#### `private_attr(default, **kwargs)`
Convenience for protected + transient fields.

### Classes

#### `ProtectedAttributeMixin`
Mixin providing annotation support. Must inherit before BaseModel.

#### `AttributeProtectionError(attr_name, cls_name)`
Exception raised when modifying protected attributes.

### Utility Functions

#### `is_protected(cls, attr_name) -> bool`
Check if attribute is protected.

#### `is_transient(cls, attr_name) -> bool`
Check if attribute is transient.

#### `get_protected_attrs(cls) -> Set[str]`
Get all protected attributes (includes inherited).

#### `get_transient_attrs(cls) -> Set[str]`
Get all transient attributes (includes inherited).

## Protected Attributes

The `id` field is automatically protected in all entities. You cannot modify IDs after object creation:

```python
# This will raise AttributeProtectionError
obj.id = "new-id"  # ✗ AttributeProtectionError

# Correct approach: Create a new object with the desired ID
new_obj = MyEntity(id="new-id", **other_attrs)
```

### Adding to Custom Classes

1. Inherit from `ProtectedAttributeMixin`
2. Apply decorators to fields
3. Use `Field()` for complex types

```python
# Before
class MyClass(BaseModel):
    id: str = ""

# After
class MyClass(ProtectedAttributeMixin, BaseModel):
    id: str = protected("")
```

## Performance

- **Protection checking**: O(1) cached lookup
- **Transient exclusion**: O(n) where n = transient fields
- **Auto-registration**: Once at class definition
- **Minimal overhead**: Only during `__setattr__` and `export()`

## See Also

- [Entity Reference](entity-reference.md) - Core entity types
- [Walker Trail Tracking](walker-trail-tracking.md) - Walker-specific features
- [Examples](examples.md) - More usage examples