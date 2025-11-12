# Walker Queue Utility Operations

The `Walker` class now includes comprehensive queue manipulation methods for fine-grained control over traversal order and queue management. These operations are designed to be safe, robust, and efficient.

## Available Operations

### 1. `dequeue(nodes: Union[Node, List[Node]]) -> List[Node]`

Removes specified node(s) from the walker's queue.

**Parameters:**
- `nodes`: Node or list of nodes to remove from queue

**Returns:**
- List of nodes that were successfully removed from the queue

**Behavior:**
- Removes all occurrences of specified nodes from the queue
- Returns only nodes that were actually found and removed
- Safe to call with nodes not in the queue (they are simply ignored)

**Example:**
```python
walker = Walker()
walker.append([node_a, node_b, node_c])
removed = walker.dequeue([node_a, node_c])
# Queue now contains: [node_b]
# removed contains: [node_a, node_c]
```

### 2. `prepend(nodes: Union[Node, List[Node]]) -> List[Node]`

Adds node(s) to the head of the queue (will be processed first).

**Parameters:**
- `nodes`: Node or list of nodes to add to the beginning of the queue

**Returns:**
- List of nodes added to the queue

**Behavior:**
- Maintains relative order of nodes in the list
- Nodes are processed in the order they appear in the input list

**Example:**
```python
walker = Walker()
walker.append([node_a, node_b])
walker.prepend([node_c, node_d])
# Queue order: [node_c, node_d, node_a, node_b]
```

### 3. `append(nodes: Union[Node, List[Node]]) -> List[Node]`

Adds node(s) to the end of the queue (will be processed last).

**Parameters:**
- `nodes`: Node or list of nodes to add to the end of the queue

**Returns:**
- List of nodes added to the queue

**Behavior:**
- Equivalent to the existing `visit()` method but synchronous
- Maintains relative order of nodes in the input list

**Example:**
```python
walker = Walker()
walker.append([node_a, node_b])
walker.append(node_c)
# Queue order: [node_a, node_b, node_c]
```

### 4. `add_next(nodes: Union[Node, List[Node]]) -> List[Node]`

Adds node(s) next in the queue (will be processed immediately after current traversal step).

**Parameters:**
- `nodes`: Node or list of nodes to add next in queue

**Returns:**
- List of nodes added to the queue

**Behavior:**
- If queue is empty, adds to the queue normally
- If queue has items, adds to the front (next to be processed)
- Useful for priority processing or dynamic traversal modification

**Example:**
```python
walker = Walker()
walker.append([node_a, node_b])
walker.add_next(node_c)
# Queue order: [node_c, node_a, node_b]
# node_c will be processed next
```

### 5. `get_queue() -> List[Node]`

Returns the entire queue as a list.

**Returns:**
- List of all nodes currently in the queue

**Behavior:**
- Returns a copy of the queue as a list
- Does not modify the queue
- Safe for inspection and debugging

**Example:**
```python
walker = Walker()
walker.append([node_a, node_b])
current_queue = walker.get_queue()
print(f"Queue contains: {[n.name for n in current_queue]}")
```

### 6. `clear_queue() -> None`

Clears the queue of all nodes.

**Behavior:**
- Removes all nodes from the queue
- Resets queue to empty state
- Safe to call on empty queue

**Example:**
```python
walker = Walker()
walker.append([node_a, node_b, node_c])
walker.clear_queue()
# Queue is now empty
assert len(walker.get_queue()) == 0
```

### 7. `insert_after(target_node: Node, nodes: Union[Node, List[Node]]) -> List[Node]`

Inserts node(s) after the specified target node in the queue.

**Parameters:**
- `target_node`: Node after which to insert the new nodes
- `nodes`: Node or list of nodes to insert

**Returns:**
- List of nodes that were successfully inserted

**Raises:**
- `ValueError`: If target_node is not found in the queue

**Behavior:**
- Maintains relative order of inserted nodes
- Inserts immediately after the first occurrence of target_node

**Example:**
```python
walker = Walker()
walker.append([node_a, node_b, node_c])
walker.insert_after(node_a, [node_x, node_y])
# Queue order: [node_a, node_x, node_y, node_b, node_c]
```

### 8. `insert_before(target_node: Node, nodes: Union[Node, List[Node]]) -> List[Node]`

Inserts node(s) before the specified target node in the queue.

**Parameters:**
- `target_node`: Node before which to insert the new nodes
- `nodes`: Node or list of nodes to insert

**Returns:**
- List of nodes that were successfully inserted

**Raises:**
- `ValueError`: If target_node is not found in the queue

**Behavior:**
- Maintains relative order of inserted nodes
- Inserts immediately before the first occurrence of target_node

**Example:**
```python
walker = Walker()
walker.append([node_a, node_b, node_c])
walker.insert_before(node_b, [node_x, node_y])
# Queue order: [node_a, node_x, node_y, node_b, node_c]
```

### 9. `is_queued(node: Node) -> bool`

Checks if the specified node is in the walker's queue.

**Parameters:**
- `node`: Node to check for in the queue

**Returns:**
- `True` if the node is in the queue, `False` otherwise

**Behavior:**
- Uses efficient containment check
- Safe to call with any node
- Useful for conditional queue operations

**Example:**
```python
walker = Walker()
walker.append(node_a)

if not walker.is_queued(node_b):
    walker.append(node_b)
```

## Usage Patterns

### Dynamic Traversal Control

```python
class SmartWalker(Walker):
    @on_visit(Node)
    async def handle_node(self, here):
        # Dynamically add related nodes based on current node
        related_nodes = await here.connected_nodes(SomeNodeType)

        # Add high-priority nodes next
        priority_nodes = [n for n in related_nodes if n.priority == 'high']
        if priority_nodes:
            self.add_next(priority_nodes)

        # Add normal nodes to end
        normal_nodes = [n for n in related_nodes if n.priority == 'normal']
        if normal_nodes:
            self.append(normal_nodes)

        # Skip already processed nodes
        unprocessed = [n for n in related_nodes if not self.is_queued(n)]
        self.append(unprocessed)
```

### Conditional Processing

```python
class ConditionalWalker(Walker):
    def process_batch(self, nodes, condition_func):
        # Only queue nodes that meet the condition
        valid_nodes = [n for n in nodes if condition_func(n)]
        self.append(valid_nodes)

        # Remove nodes that no longer meet criteria
        current_queue = self.get_queue()
        invalid_nodes = [n for n in current_queue if not condition_func(n)]
        if invalid_nodes:
            self.dequeue(invalid_nodes)
```

### Queue Reorganization

```python
class PriorityWalker(Walker):
    def reorganize_by_priority(self):
        # Get current queue and clear it
        current_nodes = self.get_queue()
        self.clear_queue()

        # Sort by priority and rebuild queue
        high_priority = [n for n in current_nodes if n.priority == 'high']
        medium_priority = [n for n in current_nodes if n.priority == 'medium']
        low_priority = [n for n in current_nodes if n.priority == 'low']

        self.append(high_priority)
        self.append(medium_priority)
        self.append(low_priority)
```

## Thread Safety and Concurrency

All queue operations are designed to be safe for single-threaded use within async contexts. When modifying queues during traversal (within visit hooks), the operations are atomic and will not interfere with the ongoing traversal process.

## Performance Considerations

- `get_queue()` creates a copy of the internal deque, so avoid calling frequently in performance-critical code
- `insert_after()` and `insert_before()` convert the deque to a list temporarily, making them O(n) operations
- `is_queued()`, `append()`, `prepend()`, and `add_next()` are O(1) or O(k) where k is the number of nodes being added
- `dequeue()` is O(n*m) where n is queue size and m is number of nodes to remove

## Error Handling

The queue operations are designed to be robust:

- Operations with empty lists are no-ops (safe to call)
- `dequeue()` ignores nodes not in the queue (safe to call)
- `insert_after()` and `insert_before()` raise `ValueError` for missing target nodes
- All operations maintain queue integrity and never leave the queue in an invalid state

## Integration with Existing Code

These operations integrate seamlessly with existing Walker functionality:

- The `visit()` method works with queue operations
- Queue operations can be used within visit hooks during traversal
- All operations work with the same internal queue used by `spawn()` and traversal logic
- Queue operations integrate seamlessly with Walker behavior

## See Also

- [Entity Reference](entity-reference.md) - Complete Walker API reference
- [Examples](examples.md) - Walker usage examples and patterns
- [MongoDB-Style Query Interface](mongodb-query-interface.md) - Query capabilities in walker hooks
- [GraphContext & Database Management](graph-context.md) - Database integration
- [REST API Integration](rest-api.md) - Using walkers in API endpoints

---

**[← Back to README](../../README.md)** | **[Entity Reference →](entity-reference.md)**
