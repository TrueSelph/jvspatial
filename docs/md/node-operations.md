## Node Connection Management

### connect()
`async connect(other: Node, edge: Optional[Type[Edge]] = None, direction: str = "out", **kwargs: Any) -> Edge`

Connect this node to another node.

**Parameters:**
- `other`: Target node to connect to
- `edge`: Edge class to use for connection (defaults to base Edge)
- `direction`: Connection direction ('out', 'in', 'both')
- `**kwargs`: Additional edge properties

**Returns:**
Created edge instance

### disconnect()
`async disconnect(other: Node, edge_type: Optional[Type[Edge]] = None) -> bool`

Removes connections between the current node and another node.

**Parameters:**
- `other`: Target node to disconnect from
- `edge_type`: Specific edge type to remove (optional)

**Returns:**
True if disconnection was successful, False otherwise

**Example:**
```python
# Basic disconnection
success = await user_node.disconnect(company_node)

# Disconnect specific edge type
success = await user_node.disconnect(company_node, edge_type=EmploymentEdge)
```

## Node Traversal Methods

### nodes()
`async nodes(direction: str = "out", node: Optional[...] = None, edge: Optional[...] = None, limit: Optional[int] = None, **kwargs) -> List[Node]`

Get all nodes connected to this node with optional filtering.

**Parameters:**
- `direction`: Connection direction ('out', 'in', 'both')
- `node`: Node type filtering (string, list, or dict with MongoDB-style queries)
- `edge`: Edge type filtering (string, type, list, or dict with MongoDB-style queries)
- `limit`: Maximum number of nodes to retrieve
- `**kwargs`: Simple property filters for connected nodes

**Returns:**
List of connected nodes matching criteria

**Examples:**
```python
# Get all connected nodes
all_nodes = await node.nodes()

# Filter by node type
cities = await node.nodes(node='City')

# Multiple node types
locations = await node.nodes(node=['City', 'Town'])

# Property filtering
ny_cities = await node.nodes(node='City', state="NY")

# Complex MongoDB-style filtering
large_cities = await node.nodes(
    node=[{'City': {"context.population": {"$gte": 500000}}}]
)
```

### node()
`async node(direction: str = "out", node: Optional[...] = None, edge: Optional[...] = None, **kwargs) -> Optional[Node]`

Get a single node connected to this node. This is a convenience method that returns the first matching node, eliminating the need for list indexing when you expect only one result.

**Parameters:**
- `direction`: Connection direction ('out', 'in', 'both')
- `node`: Node type filtering (same formats as `nodes()` method)
- `edge`: Edge type filtering (same formats as `nodes()` method)
- `**kwargs`: Simple property filters for connected nodes

**Returns:**
First connected node matching criteria, or None if no nodes found

**Key Benefits:**
- Eliminates need for list indexing with `nodes()[0]`
- Returns `None` instead of empty list for cleaner code
- Optimized with `limit=1` for better performance
- Safer - no IndexError if no nodes exist

**Examples:**
```python
# Before (using nodes())
nodes = await agent.nodes(node=['Memory'])
if nodes:
    memory = nodes[0]
    # use memory

# After (using node())
memory = await agent.node(node='Memory')
if memory:
    # use memory directly
    pass

# Find specific node
user_profile = await user.node(node='Profile')

# With property filtering
active_session = await user.node(node='Session', status="active")

# With direction
parent_node = await child.node(direction="in")

# Complex filtering
premium_city = await state.node(
    node=[{'City': {"context.population": {"$gte": 1000000}}}]
)
```

**When to Use:**
- When you expect exactly one connected node
- When you want the first matching node from multiple results
- When you need cleaner, more readable code without list indexing
- When you want to avoid potential IndexError exceptions
