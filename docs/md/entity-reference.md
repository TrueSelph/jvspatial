# Entity Reference

## Library Reference

### Core Classes

#### `Object`
Base class for all persistent objects.

```python
class Object(BaseModel):
    id: str = Field(default="")

    async def save() -> "Object"
    @classmethod
    async def get(cls, id: str) -> Optional["Object"]
    @classmethod
    async def create(cls, **kwargs) -> "Object"
    async def destroy(cascade: bool = True) -> None
    def export() -> dict
```

#### `Node(Object)`
Represents graph nodes with connection capabilities.

```python
class Node(Object):
    edge_ids: List[str] = Field(default_factory=list)

    async def connect(other: "Node", edge: Type["Edge"] = Edge,
                     direction: str = "out", **kwargs) -> "Edge"
    async def edges(direction: str = "") -> List["Edge"]
    async def nodes(direction: str = "both", node: Optional[...] = None,
                   edge: Optional[...] = None, **kwargs) -> List["Node"]
    async def node(direction: str = "out", node: Optional[...] = None,
                  edge: Optional[...] = None, **kwargs) -> Optional["Node"]
    @classmethod
    async def all() -> List["Node"]
```

**Key Methods:**

- **`nodes()`**: Returns a list of connected nodes with filtering options
- **`node()`**: Returns a single connected node (first match) or None - convenience method when you expect only one result

#### `Edge(Object)`
Represents connections between nodes.

```python
class Edge(Object):
    source: str  # Source node ID
    target: str  # Target node ID
    direction: str = "both"  # "in", "out", or "both"
```

#### `Walker`
Graph traversal agent with hook-based logic.

```python
class Walker(BaseModel):
    response: dict = Field(default_factory=dict)
    current_node: Optional[Node] = None
    paused: bool = False

    async def spawn(start: Optional[Node] = None) -> "Walker"
    async def visit(nodes: Union[Node, List[Node]]) -> list
    async def resume() -> "Walker"
    async def disengage() -> "Walker"
        """Halt the walk and remove walker from graph"""
    def skip() -> None
        """Skip processing of current node and proceed to next"""

    # Queue Management Operations
    def dequeue(nodes: Union[Node, List[Node]]) -> List[Node]
    def prepend(nodes: Union[Node, List[Node]]) -> List[Node]
    def append(nodes: Union[Node, List[Node]]) -> List[Node]
    def add_next(nodes: Union[Node, List[Node]]) -> List[Node]
    def get_queue() -> List[Node]
    def clear_queue() -> None
    def insert_after(target_node: Node, nodes: Union[Node, List[Node]]) -> List[Node]
    def insert_before(target_node: Node, nodes: Union[Node, List[Node]]) -> List[Node]
    def is_queued(node: Node) -> bool

    # Properties
    @property
    def here() -> Optional[Node]  # Current node being visited
    @property
    def visitor() -> Optional["Walker"]  # Walker instance itself
```

#### `Walker.disengage()`
The `disengage` method permanently halts a walker's traversal and removes it from the graph. This is a terminal operation that cannot be undone.

**Behavior**:
- Removes the walker from its current node (if present)
- Clears the current node reference
- Sets the `paused` flag to `True`
- Walker cannot be resumed after disengagement

**Returns**:
The walker instance in its disengaged state for inspection

**Example Usage**:
```python
# Start traversal
walker = CustomWalker()
await walker.spawn(root_node)

# ... during walk when permanent stop needed ...

# Disengage the walker (permanent halt)
await walker.disengage()

# Walker is now off the graph
print(f"Walker current node: {walker.here}")  # None
print(f"Walker paused state: {walker.paused}")  # True

# Attempting to resume will not work
# await walker.resume()  # Would have no effect
```



#### `NodeQuery`
Query builder for filtering connected nodes.

```python
class NodeQuery:
    async def filter(*, node: Optional[Union[str, List[str]]] = None,
                    edge: Optional[Union[str, Type["Edge"], List[...]]] = None,
                    direction: str = "both", **kwargs) -> List["Node"]
```

#### `ObjectPager`
Database-level pagination for efficient handling of large object collections.

```python
class ObjectPager:
    def __init__(self, object_type: Type[Object], page_size: int = 20,
                 filters: Optional[dict] = None, order_by: Optional[str] = None,
                 order_direction: str = "asc")

    async def get_page(self, page: int = 1) -> List[Object]
    async def next_page() -> List[Object]
    async def previous_page() -> List[Object]

    # Properties
    @property
    def current_page() -> int
    @property
    def has_next_page() -> bool
    @property
    def has_previous_page() -> bool
    @property
    def is_cached() -> bool
```

**Usage Examples:**

```python
from jvspatial.core import ObjectPager, paginate_objects, paginate_by_field, City

# Simple pagination helper
cities = await paginate_objects(City, page=1, page_size=50)

# Field-based pagination helper
top_cities = await paginate_by_field(
    City, field="population", order="desc", page_size=25
)

# Full-featured pager with filtering
pager = ObjectPager(
    City,
    page_size=100,
    filters={"population": {"$gt": 1000000}},
    order_by="name",
    order_direction="asc"
)

# Navigate through pages
first_page = await pager.get_page(1)
second_page = await pager.next_page()
back_to_first = await pager.previous_page()

# Process all pages efficiently
while True:
    nodes = await pager.next_page()
    if not nodes:
        break
    await process_nodes(nodes)
```

### Pagination Helpers

#### `paginate_objects(object_type, page=1, page_size=20, filters=None)`
Simple helper for paginating objects with optional filtering.

```python
async def paginate_objects(
    object_type: Type[Object],
    page: int = 1,
    page_size: int = 20,
    filters: Optional[dict] = None
) -> List[Object]
```

#### `paginate_by_field(object_type, field, page=1, page_size=20, order="asc", filters=None)`
Field-based pagination with ordering.

```python
async def paginate_by_field(
    object_type: Type[Object],
    field: str,
    page: int = 1,
    page_size: int = 20,
    order: str = "asc",
    filters: Optional[dict] = None
) -> List[Object]
```

### Decorators

#### `@on_visit(target_type=None)`
Register methods to execute when visiting nodes.

```python
# Walker visiting specific node types
@on_visit(City)
async def visit_city(self, here: City): ...

# Walker visiting any node
@on_visit()
async def visit_any(self, here: Node): ...

# Node being visited by specific walker
@on_visit(Tourist)  # On Node class
async def handle_tourist(self, visitor: Tourist): ...
```

#### `@on_exit`
Register cleanup methods after traversal completion.

```python
@on_exit
async def cleanup(self):
    self.response["completed_at"] = datetime.now()
```

## See Also

- [MongoDB-Style Query Interface](mongodb-query-interface.md) - Advanced querying capabilities
- [Object Pagination Guide](pagination.md) - Detailed pagination documentation
- [Walker Queue Operations](walker-queue-operations.md) - Walker queue management
- [Examples](examples.md) - Practical usage examples
- [GraphContext & Database Management](graph-context.md) - Database integration

---

**[← Back to README](../../README.md)** | **[Examples →](examples.md)**
