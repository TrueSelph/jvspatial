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
    async def nodes(direction: str = "both") -> "NodeQuery"
    @classmethod
    async def all() -> List["Node"]
```

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