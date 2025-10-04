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