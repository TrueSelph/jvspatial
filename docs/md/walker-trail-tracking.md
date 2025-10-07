# Walker Trail Tracking

The Walker trail tracking system provides comprehensive monitoring and recording of the path taken during graph traversal. This powerful feature enables debugging, analytics, audit trails, and complex traversal optimization strategies.

## Overview

Trail tracking automatically records every node visited by a walker, along with connecting edge information and custom metadata. This creates a complete audit trail of the walker's journey through the graph.

### Key Features

- **Automatic Recording**: Trails are recorded automatically when enabled
- **Edge Tracking**: Records edges used to traverse between nodes
- **Metadata Support**: Store custom metadata for each step
- **Memory Management**: Configurable maximum trail length to prevent memory issues
- **Rich API**: Multiple methods to access trail data in different formats
- **Performance Optimized**: Minimal overhead when disabled
- **Data Integrity**: Trail data is read-only externally to maintain integrity of the traversal log

## Quick Start

### Basic Trail Tracking

```python
from jvspatial.core import Walker, on_visit

class SimpleTrackingWalker(Walker):
    def __init__(self):
        super().__init__()
        # Enable trail tracking
        self.trail_enabled = True
        self.max_trail_length = 100  # Keep last 100 steps

    @on_visit('User')
    async def visit_user(self, here):
        print(f"Visiting user: {here.name}")

        # Check current trail
        current_trail = self.get_trail()
        print(f"Trail length: {len(current_trail)}")

        # Continue traversal
        friends = await here.nodes(node=['User'], relationship='friend')
        await self.visit(friends)

# Usage
walker = SimpleTrackingWalker()
root = await Root.get()
await walker.spawn(root)

# Access final trail
final_trail = walker.get_trail()
print(f"Visited {len(final_trail)} nodes: {final_trail}")
```

## Trail Configuration

### Enabling Trail Tracking

Trail tracking is controlled by the `trail_enabled` property:

```python
class ConfigurableWalker(Walker):
    def __init__(self, enable_tracking=True):
        super().__init__()
        self.trail_enabled = enable_tracking  # Configurable

        # Optional: Set maximum trail length
        self.max_trail_length = 50  # 0 = unlimited (default), configurable
```

### Trail Data Integrity

The trail data itself (`trail`, `trail_edges`, `trail_metadata`) is **read-only** from external code to maintain the integrity of the traversal log:

```python
# ALLOWED: Configure trail settings
walker.trail_enabled = True
walker.max_trail_length = 100

# ALLOWED: Read trail data
current_trail = walker.trail  # Returns a copy
trail_length = walker.get_trail_length()

# NOT ALLOWED: Direct modification of trail data
# walker.trail = ['some', 'custom', 'trail']  # No setter available
# walker.trail_edges = [None, 'edge1']        # No setter available
# walker.trail_metadata = [{}]                # No setter available

# ALLOWED: Clear trail through provided method
walker.clear_trail()  # Only way to modify trail externally
```

### Memory Management

Use `max_trail_length` to prevent memory issues in long-running walkers:

```python
class MemoryEfficientWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True

        # Keep only the last 20 steps
        self.max_trail_length = 20  # Oldest steps are automatically removed
```

## Trail API Reference

### Trail Properties

**Configurable Settings (Read/Write):**
- `trail_enabled: bool` - Enable/disable trail tracking
- `max_trail_length: int` - Maximum trail length (0 = unlimited)

**Trail Data (Read-Only Properties):**
- `trail: List[str]` - List of visited node IDs (returns copy)
- `trail_edges: List[Optional[str]]` - Edge IDs between nodes (returns copy)
- `trail_metadata: List[Dict[str, Any]]` - Metadata per step (returns deep copy)

### Basic Trail Access

#### `get_trail() -> List[str]`

Returns the trail as a list of node IDs in visit order.

```python
class BasicTrailWalker(Walker):
    @on_exit
    async def report_trail(self):
        trail = self.get_trail()
        print(f"Visited nodes: {trail}")
        # Example output: ['n:Root:root', 'n:User:user1', 'n:User:user2']

        # Alternative: Use the property (both return copies)
        trail_property = self.trail
        assert trail == trail_property  # Same data
```

#### `get_trail_length() -> int`

Returns the current number of steps in the trail.

```python
@on_visit('User')
async def check_trail_size(self, here):
    steps = self.get_trail_length()
    if steps > 10:
        print("Trail is getting long, consider optimization")
```

#### `clear_trail() -> None`

Clears the entire trail history.

```python
@on_visit('Checkpoint')
async def reset_at_checkpoint(self, here):
    # Start fresh trail from checkpoint
    self.clear_trail()
    print("Trail cleared at checkpoint")
```

### Advanced Trail Access

#### `get_trail_nodes() -> List[Node]`

Returns actual Node objects from the trail (async database lookups).

```python
class DetailedReportWalker(Walker):
    @on_exit
    async def detailed_report(self):
        trail_nodes = await self.get_trail_nodes()

        for i, node in enumerate(trail_nodes):
            print(f"Step {i+1}: {node.__class__.__name__} - {node.name}")
```

#### `get_trail_path() -> List[Tuple[Node, Optional[Edge]]]`

Returns the complete path with nodes and connecting edges.

```python
class PathAnalysisWalker(Walker):
    @on_exit
    async def analyze_path(self):
        trail_path = await self.get_trail_path()

        for i, (node, edge) in enumerate(trail_path):
            if edge:
                print(f"Step {i+1}: Traversed {edge.edge_type} to reach {node.name}")
            else:
                print(f"Step {i+1}: Started at {node.name}")
```

#### `get_recent_trail(count: int = 5) -> List[str]`

Returns the most recent N steps from the trail.

```python
@on_visit('User')
async def check_recent_visits(self, here):
    recent = self.get_recent_trail(count=3)
    print(f"Last 3 nodes visited: {recent}")

    # Avoid revisiting recently visited nodes
    if here.id in recent[:-1]:  # Exclude current node
        print("Recently visited this node, skipping deeper traversal")
        self.skip()
```

#### `get_trail_metadata(step: int = -1) -> Dict[str, Any]`

Returns metadata for a specific trail step.

```python
@on_visit('User')
async def check_previous_step_metadata(self, here):
    # Get metadata from previous step (-2 = two steps back)
    prev_metadata = self.get_trail_metadata(step=-2)

    if prev_metadata.get('node_type') == 'User':
        print("Previous node was also a User")
```

## Metadata and Custom Data

### Automatic Metadata

The trail system automatically records metadata for each step:

```python
# Automatic metadata includes:
{
    "timestamp": 1234567890.123,      # Unix timestamp
    "node_type": "User",              # Node class name
    "queue_length": 5                 # Queue size at visit time
}
```

### Custom Metadata

You can add custom metadata during traversal:

```python
class MetadataWalker(Walker):
    @on_visit('User')
    async def visit_with_metadata(self, here):
        # Get current step metadata
        current_metadata = self.get_trail_metadata()

        # Add custom metadata (this is read-only access)
        # Custom metadata should be added via the visiting context
        # or by extending the _record_trail_step method

        print(f"Processing user {here.name} at {current_metadata.get('timestamp')}")
```

### Advanced Metadata Usage

```python
class AdvancedMetadataWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True
        self.performance_metrics = []

    @on_visit('User')
    async def performance_tracking(self, here):
        import time
        start_time = time.time()

        # Perform user processing
        await self.process_user_data(here)

        # Record performance in our custom metrics
        processing_time = time.time() - start_time
        self.performance_metrics.append({
            'node_id': here.id,
            'processing_time': processing_time,
            'step_number': self.get_trail_length()
        })

    @on_exit
    async def performance_report(self):
        # Combine trail data with performance metrics
        trail = self.get_trail()

        for i, (node_id, metric) in enumerate(zip(trail, self.performance_metrics)):
            print(f"Step {i+1}: {node_id} took {metric['processing_time']:.2f}s")

    async def process_user_data(self, user):
        # Simulate processing time
        import asyncio
        await asyncio.sleep(0.1)
```

## Advanced Use Cases

### Cycle Detection

Use trail data to detect and handle cycles in graph traversal:

```python
class CycleDetectionWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True
        self.max_trail_length = 1000
        self.visited_nodes = set()

    @on_visit('Node')
    async def detect_cycles(self, here):
        if here.id in self.visited_nodes:
            print(f"Cycle detected! Already visited {here.id}")

            # Find where we first visited this node
            trail = self.get_trail()
            first_visit = trail.index(here.id)
            cycle_length = len(trail) - first_visit - 1

            print(f"Cycle length: {cycle_length} steps")
            self.response['cycle_detected'] = {
                'node_id': here.id,
                'cycle_length': cycle_length,
                'trail_position': first_visit
            }

            # Stop traversal to avoid infinite loop
            await self.disengage()
            return

        self.visited_nodes.add(here.id)

        # Continue normal traversal
        connected = await here.nodes()
        await self.visit(connected)
```

### Path Optimization Analysis

Analyze trails to optimize future traversals:

```python
class OptimizationAnalysisWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True
        self.edge_usage_count = {}

    @on_exit
    async def analyze_path_efficiency(self):
        trail_path = await self.get_trail_path()

        # Count edge usage
        for node, edge in trail_path:
            if edge:
                edge_id = edge.id
                self.edge_usage_count[edge_id] = self.edge_usage_count.get(edge_id, 0) + 1

        # Find most used edges (potential bottlenecks)
        most_used_edges = sorted(
            self.edge_usage_count.items(),
            key=lambda x: x[1],
            reverse=True
        )[:5]

        self.response['path_analysis'] = {
            'total_steps': len(trail_path),
            'unique_edges_used': len(self.edge_usage_count),
            'most_used_edges': [
                {'edge_id': edge_id, 'usage_count': count}
                for edge_id, count in most_used_edges
            ],
            'path_efficiency': len(set(self.get_trail())) / len(self.get_trail())  # unique/total ratio
        }
```

### Audit Trail Generation

Create comprehensive audit trails for compliance:

```python
class AuditTrailWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True
        self.max_trail_length = 0  # Keep unlimited history for audit
        self.audit_actions = []

    @on_visit('User')
    async def audit_user_access(self, here):
        # Record access in audit log
        metadata = self.get_trail_metadata()

        audit_entry = {
            'timestamp': metadata.get('timestamp'),
            'action': 'USER_ACCESSED',
            'user_id': here.id,
            'user_name': here.name,
            'trail_position': self.get_trail_length(),
            'access_method': 'walker_traversal'
        }

        self.audit_actions.append(audit_entry)

        # Process user data
        await self.process_sensitive_data(here)

    @on_visit('Document')
    async def audit_document_access(self, here):
        metadata = self.get_trail_metadata()

        audit_entry = {
            'timestamp': metadata.get('timestamp'),
            'action': 'DOCUMENT_ACCESSED',
            'document_id': here.id,
            'document_title': getattr(here, 'title', 'Unknown'),
            'trail_position': self.get_trail_length(),
            'classification': getattr(here, 'classification', 'unclassified')
        }

        self.audit_actions.append(audit_entry)

    @on_exit
    async def generate_audit_report(self):
        trail_path = await self.get_trail_path()

        # Create comprehensive audit report
        audit_report = {
            'walker_id': id(self),
            'start_time': min(action['timestamp'] for action in self.audit_actions),
            'end_time': max(action['timestamp'] for action in self.audit_actions),
            'total_steps': len(trail_path),
            'nodes_visited': {
                'users': len([a for a in self.audit_actions if a['action'] == 'USER_ACCESSED']),
                'documents': len([a for a in self.audit_actions if a['action'] == 'DOCUMENT_ACCESSED'])
            },
            'full_trail': self.get_trail(),
            'audit_actions': self.audit_actions
        }

        self.response['audit_report'] = audit_report

    async def process_sensitive_data(self, user):
        # Simulate sensitive data processing
        pass
```

## Performance Considerations

### Memory Usage

Trail tracking has minimal memory overhead, but consider these factors:

```python
class PerformanceAwareWalker(Walker):
    def __init__(self):
        super().__init__()

        # For short traversals: unlimited trail
        if self.expected_traversal_size() < 1000:
            self.trail_enabled = True
            self.max_trail_length = 0  # Unlimited

        # For long traversals: limit trail size
        else:
            self.trail_enabled = True
            self.max_trail_length = 100  # Keep last 100 steps only

    def expected_traversal_size(self):
        # Your logic to estimate traversal size
        return 500
```

### Trail Access Performance

Different trail access methods have different performance characteristics:

```python
# O(1) - Very fast
trail_length = self.get_trail_length()
recent_steps = self.get_recent_trail(5)

# O(1) - Fast (returns copy of internal list)
trail_ids = self.get_trail()

# O(n) - Slower (database lookups for each node)
trail_nodes = await self.get_trail_nodes()

# O(n+m) - Slowest (database lookups for nodes and edges)
trail_path = await self.get_trail_path()
```

### Best Practices for Performance

```python
class OptimizedTrailWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True
        self.max_trail_length = 50

        # Cache frequently accessed data
        self._trail_cache = {}

    @on_visit('User')
    async def optimized_processing(self, here):
        # Use lightweight trail access during traversal
        trail_length = self.get_trail_length()  # O(1)
        recent = self.get_recent_trail(3)       # O(1)

        # Avoid expensive operations during traversal
        # Save heavy trail analysis for @on_exit

        if trail_length > 40:
            print("Approaching trail limit, optimizing...")

    @on_exit
    async def comprehensive_analysis(self):
        # Perform expensive trail operations once at the end
        trail_nodes = await self.get_trail_nodes()
        trail_path = await self.get_trail_path()

        # Generate final report
        self.response['trail_summary'] = {
            'node_count': len(trail_nodes),
            'path_complexity': len(trail_path)
        }
```

## Debugging and Troubleshooting

### Trail Debugging Utilities

```python
class DebuggingWalker(Walker):
    def __init__(self, debug=False):
        super().__init__()
        self.trail_enabled = True
        self.debug_mode = debug

    @on_visit('Node')
    async def debug_visit(self, here):
        if self.debug_mode:
            trail = self.get_trail()
            print(f"Step {len(trail)}: Visiting {here.__class__.__name__}:{here.id}")
            print(f"Current trail: {trail[-5:]}")  # Last 5 steps

    def print_trail_summary(self):
        """Utility method for debugging trail state."""
        trail = self.get_trail()
        print(f"Trail Summary:")
        print(f"  - Length: {len(trail)}")
        print(f"  - First 3: {trail[:3]}")
        print(f"  - Last 3: {trail[-3:]}")
        print(f"  - Enabled: {self.trail_enabled}")
        print(f"  - Max length: {self.max_trail_length}")
```

### Common Issues and Solutions

#### Issue: Trail Not Recording
```python
# Check if trail is enabled
if not self.trail_enabled:
    print("Trail tracking is disabled")
    self.trail_enabled = True

# Check if max_trail_length is too restrictive
if self.max_trail_length == 1:
    print("Trail length limit too small")
    self.max_trail_length = 100
```

#### Issue: Cannot Modify Trail Data
```python
# ❌ WRONG: Attempting to modify trail data directly
# walker.trail = ['custom', 'trail']  # AttributeError: no setter
# walker.trail.append('node_id')      # Modifies copy, not original

# ✅ CORRECT: Trail is read-only by design for data integrity
# Use provided methods to interact with trail:
walker.clear_trail()  # Clear trail if needed
current_trail = walker.get_trail()  # Get current trail

# If you need custom trail manipulation, consider:
# 1. Extending Walker class with custom trail methods
# 2. Using separate tracking variables alongside the trail
# 3. Processing trail data after traversal completion
```

#### Issue: Memory Usage Too High
```python
# Implement periodic trail clearing
@on_visit('Checkpoint')
async def manage_trail_memory(self, here):
    if self.get_trail_length() > 1000:
        # Keep only recent history
        recent_trail = self.get_recent_trail(50)
        self.clear_trail()
        print("Trail cleared to manage memory usage")
```

#### Issue: Performance Degradation
```python
# Avoid expensive trail operations in visit hooks
@on_visit('User')
async def efficient_processing(self, here):
    # Good: Use lightweight operations
    trail_length = self.get_trail_length()

    # Bad: Avoid in visit hooks
    # trail_nodes = await self.get_trail_nodes()  # Database lookups!

    # Save expensive operations for @on_exit
```

## Integration with Other Walker Features

### Trail + Queue Operations

```python
class SmartTraversalWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True

    @on_visit('User')
    async def smart_traversal(self, here):
        # Use trail to avoid revisiting nodes
        trail = self.get_trail()

        # Get potential next nodes
        candidates = await here.nodes(node=['User'])

        # Filter out recently visited nodes
        unvisited = [node for node in candidates if node.id not in trail]

        if unvisited:
            # Add unvisited nodes to queue
            self.append(unvisited)
        else:
            # All candidates visited, try different direction
            print("All immediate candidates visited, exploring alternatives")
            alternatives = await here.nodes(direction="in")
            unvisited_alternatives = [n for n in alternatives if n.id not in trail]
            self.append(unvisited_alternatives)
```

### Trail + Pause/Resume

```python
class PersistentTrailWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True
        self.max_trail_length = 0  # Keep full history

    @on_visit('LargeDataset')
    async def process_large_dataset(self, here):
        # Process in batches with pausing
        print(f"Processing large dataset, trail length: {self.get_trail_length()}")

        # Pause after processing to avoid overwhelming system
        self.pause("Batch processing pause")

    def save_trail_state(self, filepath):
        """Save trail state for persistence across sessions."""
        import json
        trail_data = {
            'trail': self.get_trail(),
            'trail_length': self.get_trail_length(),
            'enabled': self.trail_enabled,
            'max_length': self.max_trail_length
        }

        with open(filepath, 'w') as f:
            json.dump(trail_data, f)

    def load_trail_state(self, filepath):
        """Load previously saved trail state."""
        import json
        try:
            with open(filepath, 'r') as f:
                trail_data = json.load(f)

            # Note: This is conceptual - actual implementation would
            # need to restore internal trail state
            self.trail_enabled = trail_data['enabled']
            self.max_trail_length = trail_data['max_length']
            print(f"Loaded trail state: {len(trail_data['trail'])} steps")

        except FileNotFoundError:
            print("No saved trail state found")
```

## API Testing

### Unit Testing Trail Functionality

```python
import pytest
from jvspatial.core import Walker, Node, on_visit

class TestTrailWalker(Walker):
    def __init__(self):
        super().__init__()
        self.trail_enabled = True
        self.max_trail_length = 10

@pytest.mark.asyncio
async def test_basic_trail_tracking():
    """Test basic trail tracking functionality."""
    walker = TestTrailWalker()

    # Initially empty trail
    assert walker.get_trail_length() == 0
    assert walker.get_trail() == []

    # After spawning, should have trail
    root = await Root.get()
    await walker.spawn(root)

    assert walker.get_trail_length() > 0
    assert root.id in walker.get_trail()

@pytest.mark.asyncio
async def test_trail_length_limit():
    """Test max_trail_length enforcement."""
    walker = TestTrailWalker()
    walker.max_trail_length = 3

    # Create test nodes
    nodes = []
    for i in range(5):
        node = await Node.create(name=f"test_node_{i}")
        nodes.append(node)

    # Visit all nodes
    for node in nodes:
        walker._record_trail_step(node)

    # Should only keep last 3
    trail = walker.get_trail()
    assert len(trail) == 3
    assert trail == [nodes[2].id, nodes[3].id, nodes[4].id]

@pytest.mark.asyncio
async def test_trail_metadata():
    """Test trail metadata functionality."""
    walker = TestTrailWalker()

    # Record a step with metadata
    node = await Node.create(name="test_node")
    test_metadata = {"custom_data": "test_value", "priority": 5}
    walker._record_trail_step(node, metadata=test_metadata)

    # Check metadata retrieval
    retrieved_metadata = walker.get_trail_metadata()
    assert "custom_data" in retrieved_metadata
    assert retrieved_metadata["custom_data"] == "test_value"
    assert retrieved_metadata["priority"] == 5
```

## See Also

- [Walker Queue Operations](walker-queue-operations.md) - Advanced queue manipulation
- [Entity Reference](entity-reference.md) - Complete Walker API reference
- [Examples](examples.md) - More trail tracking examples
- [Troubleshooting](troubleshooting.md) - Common issues and solutions

---

**[← Back to README](../../README.md)** | **[Walker Queue Operations →](walker-queue-operations.md)**