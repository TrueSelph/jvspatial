# Walker `skip()` Functionality

The Walker class now includes a `skip()` method that works similar to the `continue` statement in typical loops. When called during node traversal (within visit hooks), it immediately halts execution of the current node's hooks and proceeds to the next node in the queue.

## Overview

The `skip()` function provides precise control over graph traversal by allowing walkers to bypass processing of specific nodes based on dynamic conditions. This is particularly useful for:

- **Conditional Processing**: Skip nodes that don't meet certain criteria
- **Performance Optimization**: Avoid expensive operations on nodes that don't need processing
- **Flow Control**: Implement complex traversal logic with early exits
- **Error Handling**: Skip nodes that are in invalid states

## Usage

### Basic Usage

```python
from jvspatial.core.entities import Walker, Node, on_visit

class ConditionalWalker(Walker):
    @on_visit(Node)
    async def process_node(self, here):
        # Check if node should be skipped
        if here.should_skip:
            self.skip()  # Skip to next node
            return  # This line won't be reached

        # Process the node normally
        await self.do_processing(here)
```

### Skip with Conditions

```python
class FilteringWalker(Walker):
    @on_visit(Node)
    async def filter_nodes(self, here):
        # Skip nodes based on multiple conditions
        if here.status == "inactive":
            self.response.setdefault("skipped", []).append(here.id)
            self.skip()

        if not hasattr(here, "priority") or here.priority == "low":
            self.skip()

        # Only high/medium priority active nodes reach here
        await self.process_important_node(here)
```

### Skip with Queue Manipulation

```python
class SmartWalker(Walker):
    @on_visit(Node)
    async def smart_processing(self, here):
        # Add related nodes to queue
        if here.node_type == "hub":
            related = await here.connected_nodes(Node)
            self.add_next(related)

        # Skip temporary or cache nodes
        if here.name.startswith("temp_") or here.is_cache:
            self.skip()

        # Process normal nodes
        await self.handle_node(here)
```

## Method Signature

```python
def skip(self) -> None:
    """Skip processing of the current node and proceed to the next node in the queue.

    This function works similar to 'continue' in typical loops. When called during
    node traversal (within a visit hook), it immediately halts execution of the
    current node's hooks and proceeds to the next node in the queue.

    Can only be called from within visit hooks during active traversal.

    Raises:
        TraversalSkipped: Internal exception used to control traversal flow

    Example:
        @on_visit(Node)
        async def process_node(self, here):
            if here.should_be_skipped:
                self.skip()  # Skip to next node
                return  # This line won't be reached

            # Process the node normally
            await self.do_heavy_processing(here)
    """
```

## Behavior Details

### Execution Flow

1. **Normal Processing**: When a walker visits a node, all applicable visit hooks are executed sequentially
2. **Skip Called**: When `skip()` is called within a hook, a `TraversalSkipped` exception is raised
3. **Hook Interruption**: The exception immediately halts execution of the current hook and any remaining hooks for that node
4. **Next Node**: The walker continues to the next node in the queue
5. **No Side Effects**: The skip operation doesn't affect the queue or other walker state

### Code After `skip()`

Any code after a `skip()` call **will not be executed**:

```python
@on_visit(Node)
async def example_hook(self, here):
    if some_condition:
        self.skip()
        print("This will NOT be printed")  # Unreachable code
        return "This will NOT be returned"  # Unreachable code

    print("This WILL be printed for non-skipped nodes")
```

### Multiple Hooks

If a walker has multiple hooks for the same node type, `skip()` halts execution of all remaining hooks for that node:

```python
class MultiHookWalker(Walker):
    @on_visit(Node)
    async def first_hook(self, here):
        print("First hook executing")
        if here.should_skip:
            self.skip()
            print("Won't print this")  # Unreachable

    @on_visit(Node)
    async def second_hook(self, here):
        print("Second hook executing")  # Won't execute if skip() called in first_hook

    @on_visit(Node)
    async def third_hook(self, here):
        print("Third hook executing")   # Won't execute if skip() called in first_hook
```

## Integration with Queue Operations

The `skip()` function works seamlessly with all queue manipulation methods:

```python
class AdvancedWalker(Walker):
    @on_visit(Node)
    async def advanced_processing(self, here):
        # Add nodes to queue based on current node
        if here.type == "branch_point":
            children = await here.connected_nodes(ChildNode)
            self.append(children)

        # Insert priority nodes next
        if hasattr(here, "urgent_related"):
            urgent = await here.get_urgent_related()
            self.add_next(urgent)

        # Skip nodes that are already processed
        if here.processed:
            self.response.setdefault("already_processed", []).append(here.id)
            self.skip()

        # Skip nodes pending external validation
        if here.needs_external_validation and not here.validated:
            # Re-queue for later processing
            self.append(here)
            self.skip()

        # Process the node
        await self.do_processing(here)
```

## Error Handling and Safety

### Exception Safety

The `skip()` function is implemented using a custom `TraversalSkipped` exception that is caught and handled internally by the Walker traversal engine. This ensures:

- **No Memory Leaks**: Resources are properly cleaned up
- **State Consistency**: Walker state remains consistent
- **Continuation**: Traversal continues normally with the next node

### Try/Catch Blocks

You can safely use `skip()` within try/catch blocks:

```python
@on_visit(Node)
async def safe_processing(self, here):
    try:
        # Attempt some operation
        result = await self.risky_operation(here)

        if result.should_skip:
            self.skip()  # Safe to call within try block

    except SomeException as e:
        # Handle the exception
        self.response.setdefault("errors", []).append(str(e))
        self.skip()  # Safe to call within except block

    # This only executes if no skip() was called
    await self.finalize_processing(here)
```

### Best Practices

1. **Early Skip**: Call `skip()` as early as possible to avoid unnecessary processing
2. **Clear Conditions**: Make skip conditions explicit and well-documented
3. **Logging**: Log skip events for debugging and monitoring
4. **Response Tracking**: Track skipped nodes in the walker response for analysis

```python
class BestPracticeWalker(Walker):
    @on_visit(Node)
    async def process_with_best_practices(self, here):
        # Early validation and skip
        if not self.should_process_node(here):
            self.log_skip(here, "failed_validation")
            self.skip()

        if here.is_blacklisted:
            self.log_skip(here, "blacklisted")
            self.skip()

        # Normal processing for valid nodes
        await self.process_valid_node(here)

    def should_process_node(self, node):
        """Clear, testable condition logic."""
        return (
            node.status == "active" and
            node.has_required_fields() and
            not node.is_duplicate()
        )

    def log_skip(self, node, reason):
        """Centralized skip logging."""
        self.response.setdefault("skipped_nodes", []).append({
            "node_id": node.id,
            "reason": reason,
            "timestamp": datetime.now().isoformat()
        })
```

## Performance Considerations

- **Efficient**: `skip()` has minimal overhead - it simply raises an exception that's caught by the traversal engine
- **No Queue Impact**: Skipping doesn't modify the queue structure or order
- **Memory Safe**: Skipped nodes are not held in memory beyond normal garbage collection
- **Scalable**: Works efficiently even with large numbers of skipped nodes

## Use Cases

### 1. Data Filtering

```python
class DataFilterWalker(Walker):
    def __init__(self, filter_criteria, **kwargs):
        super().__init__(**kwargs)
        self.criteria = filter_criteria

    @on_visit(DataNode)
    async def filter_data(self, here):
        if not self.criteria.matches(here.data):
            self.skip()

        await self.process_matching_data(here)
```

### 2. Conditional Processing Pipelines

```python
class PipelineWalker(Walker):
    @on_visit(TaskNode)
    async def execute_pipeline_stage(self, here):
        # Skip if prerequisites not met
        if not await here.prerequisites_satisfied():
            # Re-queue for later
            self.append(here)
            self.skip()

        # Skip if already completed
        if here.status == "completed":
            self.skip()

        # Execute the task
        await here.execute()
```

### 3. Graph Pruning

```python
class PruningWalker(Walker):
    @on_visit(Node)
    async def prune_graph(self, here):
        # Skip nodes that don't meet threshold
        if here.importance_score < self.threshold:
            # Don't traverse children of unimportant nodes
            self.skip()

        # Add children of important nodes to queue
        children = await here.connected_nodes(Node)
        self.append(children)
```

### 4. Error Recovery

```python
class RobustWalker(Walker):
    @on_visit(Node)
    async def robust_processing(self, here):
        # Skip nodes in error state
        if here.has_errors():
            await self.log_error_node(here)
            self.skip()

        # Skip nodes that are locked by other processes
        if here.is_locked():
            # Try again later
            self.append(here)
            self.skip()

        # Process healthy nodes
        await self.process_healthy_node(here)
```

## Testing Skip Functionality

When testing walkers that use `skip()`, verify both the skip behavior and normal processing:

```python
import pytest
from jvspatial.core.entities import Walker, Node, Root, on_visit

class TestSkipWalker(Walker):
    @on_visit(TestNode)
    async def test_skip_logic(self, here):
        if "skip" not in self.response:
            self.response["skip"] = []
        if "process" not in self.response:
            self.response["process"] = []

        if here.should_skip:
            self.response["skip"].append(here.name)
            self.skip()
            # This should not execute
            self.response["process"].append(f"ERROR_{here.name}")

        self.response["process"].append(here.name)

@pytest.mark.asyncio
async def test_skip_behavior():
    # Setup nodes
    skip_node = await TestNode.create(name="SKIP", should_skip=True)
    process_node = await TestNode.create(name="PROCESS", should_skip=False)

    # Run walker
    walker = TestSkipWalker()
    walker.append([skip_node, process_node])
    result = await walker.spawn()

    # Verify results
    assert "SKIP" in result.response["skip"]
    assert "PROCESS" in result.response["process"]
    assert "ERROR_SKIP" not in result.response["process"]
```

## Conclusion

The `skip()` functionality provides powerful flow control for Walker traversals, enabling sophisticated graph processing patterns while maintaining simplicity and performance. Use it to implement conditional processing, filtering, error handling, and optimization strategies in your graph-based applications.