# Infinite Walk Protection

This guide provides comprehensive information about jvspatial's infinite walk protection mechanisms that prevent walkers from engaging in infinite loops or runaway traversals.

## Table of Contents

- [Overview](#overview)
- [Protection Mechanisms](#protection-mechanisms)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [Usage Examples](#usage-examples)
- [Monitoring and Status](#monitoring-and-status)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## Overview

Infinite walk protection is a comprehensive system of safeguards designed to prevent walker traversals from running indefinitely or consuming excessive resources. The protection system operates through multiple layers of limits and automatic halting mechanisms.

### Why Protection is Needed

Graph traversal can lead to infinite loops in several scenarios:

- **Circular references**: Nodes that reference each other in cycles
- **Dynamic node creation**: Walkers that create new nodes during traversal
- **Recursive patterns**: Complex graph structures with multiple paths
- **Programming errors**: Bugs in walker logic that cause infinite loops
- **Resource exhaustion**: Runaway walkers consuming memory and CPU

### Key Benefits

- **Automatic Safety**: Protection is enabled by default with sensible limits
- **Resource Management**: Prevents memory overflow and CPU exhaustion
- **Configurable Limits**: Adjustable thresholds for different use cases
- **Detailed Reporting**: Comprehensive status and trigger information
- **Environment Support**: Configuration via environment variables
- **Production Ready**: Battle-tested limits for production deployments

## Protection Mechanisms

The infinite walk protection system consists of four main mechanisms:

### 1. Maximum Steps Protection

Limits the total number of steps (node visits) a walker can take during traversal.

**Default**: 10,000 steps
**Trigger**: When step count reaches or exceeds the limit
**Response**: Walker is automatically disengaged

```python
walker = MyWalker(max_steps=5000)
await walker.spawn(start_node)

if walker.response.get("protection_triggered") == "max_steps":
    print(f"Walker stopped after {walker.step_count} steps")
```

### 2. Node Visit Frequency Protection

Limits how many times a single node can be visited to prevent excessive cycling.

**Default**: 100 visits per node
**Trigger**: When any node is visited more than the limit
**Response**: Walker is automatically disengaged

```python
walker = MyWalker(max_visits_per_node=10)
await walker.spawn(start_node)

if walker.response.get("protection_triggered") == "max_visits_per_node":
    node_id = walker.response.get("node_id")
    count = walker.response.get("visit_count")
    print(f"Node {node_id} visited {count} times")
```

### 3. Timeout Protection

Limits the total execution time for walker traversal.

**Default**: 300 seconds (5 minutes)
**Trigger**: When execution time exceeds the limit
**Response**: Walker is automatically disengaged

```python
walker = MyWalker(max_execution_time=60.0)  # 1 minute limit
await walker.spawn(start_node)

if walker.response.get("protection_triggered") == "timeout":
    execution_time = walker.response.get("execution_time")
    print(f"Walker timed out after {execution_time:.2f} seconds")
```

### 4. Queue Size Protection

Limits the maximum number of nodes that can be queued for traversal.

**Default**: 1,000 nodes
**Trigger**: When attempting to add nodes would exceed the limit
**Response**: Additional nodes are silently dropped

```python
walker = MyWalker(max_queue_size=100)

# This will only add nodes up to the limit
nodes = [Node() for _ in range(200)]
added_nodes = await walker.visit(nodes)
print(f"Added {len(added_nodes)} of {len(nodes)} nodes")
```

## Configuration

### Constructor Configuration

Configure protection limits when creating walker instances:

```python
walker = MyWalker(
    max_steps=5000,                    # Maximum steps
    max_visits_per_node=50,           # Maximum visits per node
    max_execution_time=120.0,         # Maximum time in seconds
    max_queue_size=500,               # Maximum queue size
    protection_enabled=True           # Enable/disable protection
)
```

### Runtime Configuration

Modify protection settings during walker execution:

```python
walker = MyWalker()

# Adjust limits at runtime
walker.max_steps = 2000
walker.max_visits_per_node = 25
walker.max_execution_time = 60.0
walker.max_queue_size = 200

# Enable or disable protection
walker.protection_enabled = False
```

### Property Validation

Protection properties automatically validate values:

```python
walker = MyWalker()

# Negative values are converted to 0
walker.max_steps = -100        # Becomes 0
walker.max_execution_time = -30.0  # Becomes 0.0

# Values are constrained to reasonable ranges
print(walker.max_steps)        # 0
print(walker.max_execution_time)  # 0.0
```

## Environment Variables

Configure protection limits system-wide using environment variables:

### Available Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `JVSPATIAL_WALKER_PROTECTION_ENABLED` | Enable/disable protection | `true` |
| `JVSPATIAL_WALKER_MAX_STEPS` | Maximum steps before halt | `10000` |
| `JVSPATIAL_WALKER_MAX_VISITS_PER_NODE` | Maximum visits per node | `100` |
| `JVSPATIAL_WALKER_MAX_EXECUTION_TIME` | Maximum execution time (seconds) | `300.0` |
| `JVSPATIAL_WALKER_MAX_QUEUE_SIZE` | Maximum queue size | `1000` |

### Configuration Examples

**Development Environment** (.env file):
```env
JVSPATIAL_WALKER_PROTECTION_ENABLED=true
JVSPATIAL_WALKER_MAX_STEPS=50000
JVSPATIAL_WALKER_MAX_VISITS_PER_NODE=200
JVSPATIAL_WALKER_MAX_EXECUTION_TIME=600.0
JVSPATIAL_WALKER_MAX_QUEUE_SIZE=2000
```

**Testing Environment**:
```env
JVSPATIAL_WALKER_PROTECTION_ENABLED=true
JVSPATIAL_WALKER_MAX_STEPS=1000
JVSPATIAL_WALKER_MAX_VISITS_PER_NODE=10
JVSPATIAL_WALKER_MAX_EXECUTION_TIME=30.0
JVSPATIAL_WALKER_MAX_QUEUE_SIZE=100
```

**Production Environment**:
```env
JVSPATIAL_WALKER_PROTECTION_ENABLED=true
JVSPATIAL_WALKER_MAX_STEPS=10000
JVSPATIAL_WALKER_MAX_VISITS_PER_NODE=100
JVSPATIAL_WALKER_MAX_EXECUTION_TIME=300.0
JVSPATIAL_WALKER_MAX_QUEUE_SIZE=1000
```

### Loading Configuration

```python
from dotenv import load_dotenv
load_dotenv()  # Load environment variables

# Walker automatically uses environment configuration
walker = MyWalker()  # Uses environment defaults
print(f"Max steps: {walker.max_steps}")
print(f"Protection enabled: {walker.protection_enabled}")
```

## Usage Examples

### Basic Protection Example

```python
from jvspatial.core import Walker, Node, on_visit

class SafeWalker(Walker):
    @on_visit(Node)
    async def safe_traversal(self, here):
        print(f"Visiting: {here.id}")

        # Normal traversal logic
        connected_nodes = await here.nodes()
        await self.visit(connected_nodes)

# Create walker with custom protection
walker = SafeWalker(
    max_steps=1000,
    max_visits_per_node=5,
    max_execution_time=30.0
)

# Run traversal with automatic protection
await walker.spawn(start_node)

# Check if protection triggered
if "protection_triggered" in walker.response:
    protection_type = walker.response["protection_triggered"]
    print(f"Protection triggered: {protection_type}")
else:
    print("Traversal completed successfully")
```

### Monitoring During Traversal

```python
import asyncio
from jvspatial.core import Walker, Node, on_visit

class MonitoredWalker(Walker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.status_interval = 10  # Check status every 10 nodes

    @on_visit(Node)
    async def monitored_traversal(self, here):
        # Regular processing
        await self.process_node(here)

        # Periodic status monitoring
        if self.step_count % self.status_interval == 0:
            status = self.get_protection_status()
            print(f"Status at step {self.step_count}:")
            print(f"  Steps: {status['step_usage_percent']:.1f}% of limit")
            print(f"  Queue: {status['queue_usage_percent']:.1f}% of limit")
            print(f"  Time: {status['time_usage_percent']:.1f}% of limit")

        # Continue traversal
        connected_nodes = await here.nodes()
        await self.visit(connected_nodes[:5])  # Limit to prevent explosion

    async def process_node(self, node):
        """Custom node processing logic."""
        await asyncio.sleep(0.01)  # Simulate processing time

# Usage
walker = MonitoredWalker(max_steps=100)
await walker.spawn(start_node)
```

### Error Handling and Recovery

```python
from jvspatial.core import Walker, Node, on_visit

class RobustWalker(Walker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.retry_count = 0
        self.max_retries = 3

    @on_visit(Node)
    async def robust_traversal(self, here):
        try:
            # Risky processing that might cause loops
            await self.risky_processing(here)

        except Exception as e:
            print(f"Error processing {here.id}: {e}")
            # Continue to next node instead of failing

        # Safe traversal with limits
        connected_nodes = await here.nodes(limit=10)
        await self.visit(connected_nodes)

    async def risky_processing(self, node):
        """Simulate processing that might create cycles."""
        if hasattr(node, 'processed') and node.processed:
            # Already processed, might create cycle
            return

        node.processed = True
        await asyncio.sleep(0.01)

# Create walker with conservative limits
walker = RobustWalker(
    max_steps=500,
    max_visits_per_node=3,
    max_execution_time=60.0,
    protection_enabled=True
)

# Run with error handling
try:
    await walker.spawn(start_node)

    if walker.response.get("protection_triggered"):
        print(f"Protected halt: {walker.response['protection_triggered']}")

        # Optionally retry with adjusted limits
        if walker.retry_count < walker.max_retries:
            walker.retry_count += 1
            walker.max_steps *= 2  # Double the limit
            print(f"Retrying with increased limits (attempt {walker.retry_count})")
            walker.response.clear()
            await walker.spawn(start_node)

except Exception as e:
    print(f"Walker failed: {e}")
```

### Dynamic Protection Adjustment

```python
from jvspatial.core import Walker, Node, on_visit

class AdaptiveWalker(Walker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.complexity_factor = 1.0

    @on_visit(Node)
    async def adaptive_traversal(self, here):
        # Analyze graph complexity
        connected_count = len(await here.nodes())

        if connected_count > 50:  # High complexity
            self.complexity_factor = 2.0
            # Tighten protection for complex graphs
            self.max_visits_per_node = min(self.max_visits_per_node, 10)
            self.max_queue_size = min(self.max_queue_size, 200)

        elif connected_count < 5:  # Low complexity
            self.complexity_factor = 0.5
            # Relax protection for simple graphs
            self.max_visits_per_node = min(self.max_visits_per_node * 2, 200)

        # Continue traversal
        next_nodes = await here.nodes(limit=int(10 / self.complexity_factor))
        await self.visit(next_nodes)

# Usage
walker = AdaptiveWalker()
await walker.spawn(start_node)
```

## Monitoring and Status

### Protection Status API

Get comprehensive protection status information:

```python
walker = MyWalker()

# Get complete protection status
status = walker.get_protection_status()

print("Protection Status:")
print(f"  Enabled: {status['protection_enabled']}")
print(f"  Steps: {status['step_count']}/{status['max_steps']} ({status['step_usage_percent']:.1f}%)")
print(f"  Queue: {status['queue_size']}/{status['max_queue_size']} ({status['queue_usage_percent']:.1f}%)")
print(f"  Time: {status['elapsed_time']:.2f}s/{status['max_execution_time']}s ({status['time_usage_percent']:.1f}%)")

if status['most_visited_node']:
    print(f"  Most visited: {status['most_visited_node']} ({status['most_visited_count']} times)")
```

### Real-time Monitoring

```python
import asyncio
from jvspatial.core import Walker, Node, on_visit

class MonitoringWalker(Walker):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.monitoring_task = None

    async def spawn(self, start=None):
        # Start monitoring task
        self.monitoring_task = asyncio.create_task(self.monitor_protection())

        try:
            # Run normal traversal
            return await super().spawn(start)
        finally:
            # Stop monitoring
            if self.monitoring_task:
                self.monitoring_task.cancel()

    async def monitor_protection(self):
        """Monitor protection status during traversal."""
        while not self.paused:
            await asyncio.sleep(1.0)  # Check every second

            status = self.get_protection_status()

            # Warn when approaching limits
            if status['step_usage_percent'] > 80:
                print(f"⚠️  Step limit approaching: {status['step_usage_percent']:.1f}%")

            if status['time_usage_percent'] > 80:
                print(f"⚠️  Time limit approaching: {status['time_usage_percent']:.1f}%")

            if status['queue_usage_percent'] > 80:
                print(f"⚠️  Queue limit approaching: {status['queue_usage_percent']:.1f}%")

    @on_visit(Node)
    async def monitored_visit(self, here):
        # Normal processing
        connected_nodes = await here.nodes()
        await self.visit(connected_nodes[:5])

# Usage
walker = MonitoringWalker()
await walker.spawn(start_node)
```

### Status Properties

Access individual status values directly:

```python
walker = MyWalker()

# Read-only status properties
print(f"Current steps: {walker.step_count}")
print(f"Visit counts: {walker.node_visit_counts}")
print(f"Protection enabled: {walker.protection_enabled}")

# Configuration properties (read/write)
print(f"Max steps: {walker.max_steps}")
print(f"Max visits per node: {walker.max_visits_per_node}")
print(f"Max execution time: {walker.max_execution_time}")
print(f"Max queue size: {walker.max_queue_size}")
```

## Best Practices

### 1. Choose Appropriate Limits

**Development**:
- Higher limits for exploration and debugging
- Longer timeouts for complex analysis
- More permissive visit counts

```python
# Development walker
dev_walker = MyWalker(
    max_steps=50000,
    max_visits_per_node=200,
    max_execution_time=600.0,  # 10 minutes
    max_queue_size=2000
)
```

**Production**:
- Conservative limits to prevent resource exhaustion
- Shorter timeouts for responsive service
- Strict visit limits to prevent cycles

```python
# Production walker
prod_walker = MyWalker(
    max_steps=10000,
    max_visits_per_node=50,
    max_execution_time=120.0,  # 2 minutes
    max_queue_size=500
)
```

**Testing**:
- Very strict limits for fast test execution
- Low timeouts to catch issues quickly
- Small queue sizes to prevent test hangs

```python
# Test walker
test_walker = MyWalker(
    max_steps=100,
    max_visits_per_node=5,
    max_execution_time=10.0,  # 10 seconds
    max_queue_size=50
)
```

### 2. Monitor Protection Status

Implement monitoring to understand walker behavior:

```python
class InstrumentedWalker(Walker):
    @on_visit(Node)
    async def instrumented_visit(self, here):
        # Log protection status periodically
        if self.step_count % 100 == 0:
            status = self.get_protection_status()
            logger.info(f"Walker status: {status['step_usage_percent']:.1f}% steps used")

        # Regular processing
        await self.process_node(here)
```

### 3. Handle Protection Triggers Gracefully

```python
async def run_protected_walker(walker, start_node):
    """Run walker with proper protection handling."""
    await walker.spawn(start_node)

    if "protection_triggered" in walker.response:
        trigger_type = walker.response["protection_triggered"]

        if trigger_type == "max_steps":
            logger.warning(f"Walker halted after {walker.step_count} steps")

        elif trigger_type == "max_visits_per_node":
            node_id = walker.response["node_id"]
            count = walker.response["visit_count"]
            logger.warning(f"Walker halted: node {node_id} visited {count} times")

        elif trigger_type == "timeout":
            time_taken = walker.response["execution_time"]
            logger.warning(f"Walker timed out after {time_taken:.2f} seconds")

        # Handle the situation appropriately
        return False  # Indicate protection triggered

    return True  # Indicate successful completion
```

### 4. Use Environment Configuration

Set up environment-specific configurations:

```python
# config.py
import os

WALKER_PROTECTION_CONFIG = {
    'development': {
        'max_steps': int(os.getenv('JVSPATIAL_WALKER_MAX_STEPS', '50000')),
        'max_visits_per_node': int(os.getenv('JVSPATIAL_WALKER_MAX_VISITS_PER_NODE', '200')),
        'max_execution_time': float(os.getenv('JVSPATIAL_WALKER_MAX_EXECUTION_TIME', '600.0')),
    },
    'production': {
        'max_steps': int(os.getenv('JVSPATIAL_WALKER_MAX_STEPS', '10000')),
        'max_visits_per_node': int(os.getenv('JVSPATIAL_WALKER_MAX_VISITS_PER_NODE', '100')),
        'max_execution_time': float(os.getenv('JVSPATIAL_WALKER_MAX_EXECUTION_TIME', '300.0')),
    }
}

def create_walker_with_env_config(walker_class, environment='production'):
    """Create walker with environment-specific protection config."""
    config = WALKER_PROTECTION_CONFIG.get(environment, WALKER_PROTECTION_CONFIG['production'])
    return walker_class(**config)
```

### 5. Test Protection Mechanisms

Write tests to verify protection works:

```python
import pytest
from jvspatial.core import Walker, Node, on_visit

class TestProtectionWalker(Walker):
    @on_visit(Node)
    async def create_infinite_loop(self, here):
        # Intentionally create infinite loop for testing
        await self.visit([here])  # Visit same node repeatedly

@pytest.mark.asyncio
async def test_visit_protection():
    walker = TestProtectionWalker(max_visits_per_node=3)
    start_node = Node(name="test")

    await walker.spawn(start_node)

    # Protection should have triggered
    assert walker.response.get("protection_triggered") == "max_visits_per_node"
    assert walker.response.get("visit_count") > 3
```

## Troubleshooting

### Common Issues and Solutions

#### 1. Protection Triggering Too Early

**Symptoms**: Walker stops before completing expected work

**Causes**:
- Limits set too low for the use case
- Complex graph structure requiring more traversal
- Inefficient traversal patterns

**Solutions**:
```python
# Analyze actual requirements
status = walker.get_protection_status()
print(f"Walker used {status['step_count']} steps")
print(f"Peak queue size: {status['queue_size']}")

# Adjust limits based on analysis
walker.max_steps = walker.max_steps * 2
walker.max_execution_time = walker.max_execution_time * 1.5
```

#### 2. Protection Not Triggering

**Symptoms**: Walker continues indefinitely despite protection being enabled

**Causes**:
- Protection disabled in configuration
- Limits set too high
- Walker not actually in infinite loop

**Solutions**:
```python
# Verify protection is enabled
assert walker.protection_enabled == True

# Check current limits
status = walker.get_protection_status()
print(f"Current limits: {status}")

# Add monitoring to understand behavior
walker.max_steps = 1000  # Temporary lower limit for testing
```

#### 3. Environment Variables Not Loading

**Symptoms**: Walker uses default values despite environment variables being set

**Causes**:
- Environment variables not loaded
- Incorrect variable names
- Values overridden by constructor parameters

**Solutions**:
```python
import os
from dotenv import load_dotenv

# Ensure environment variables are loaded
load_dotenv()

# Verify variables are available
print(f"MAX_STEPS env: {os.getenv('JVSPATIAL_WALKER_MAX_STEPS')}")

# Create walker without overriding parameters
walker = MyWalker()  # Don't pass max_steps=... if you want env values
```

#### 4. Queue Size Protection Too Restrictive

**Symptoms**: Important nodes not being visited due to queue limits

**Causes**:
- Queue size limit too small for graph structure
- Walker adding too many nodes at once

**Solutions**:
```python
# Increase queue size limit
walker.max_queue_size = 5000

# Or implement prioritized queuing
class PriorityWalker(Walker):
    @on_visit(Node)
    async def priority_visit(self, here):
        # Get all connected nodes
        all_nodes = await here.nodes()

        # Add high-priority nodes first
        high_priority = [n for n in all_nodes if n.priority > 8]
        low_priority = [n for n in all_nodes if n.priority <= 8]

        await self.visit(high_priority)

        # Add low-priority nodes if space available
        if len(self.queue) < self.max_queue_size * 0.8:
            await self.visit(low_priority[:10])  # Limit low-priority additions
```

#### 5. Timeout Issues in Production

**Symptoms**: Walkers timing out in production but not in development

**Causes**:
- Production environment slower than development
- Network latency affecting database operations
- Resource contention in production

**Solutions**:
```python
# Environment-specific timeout configuration
import os

if os.getenv('ENVIRONMENT') == 'production':
    walker = MyWalker(max_execution_time=600.0)  # 10 minutes in production
else:
    walker = MyWalker(max_execution_time=300.0)  # 5 minutes elsewhere

# Add performance monitoring
class PerformanceWalker(Walker):
    @on_visit(Node)
    async def timed_visit(self, here):
        import time
        start = time.time()

        # Regular processing
        await self.process_node(here)

        duration = time.time() - start
        if duration > 1.0:  # Log slow operations
            logger.warning(f"Slow node processing: {duration:.2f}s for {here.id}")
```

### Debug Tools

#### Protection Status Debugging

```python
def debug_protection_status(walker):
    """Print detailed protection status for debugging."""
    status = walker.get_protection_status()

    print("=== Walker Protection Status ===")
    print(f"Protection Enabled: {status['protection_enabled']}")
    print(f"Steps: {status['step_count']:,} / {status['max_steps']:,} ({status['step_usage_percent']:.1f}%)")
    print(f"Queue: {status['queue_size']:,} / {status['max_queue_size']:,} ({status['queue_usage_percent']:.1f}%)")

    if status['elapsed_time'] is not None:
        print(f"Time: {status['elapsed_time']:.2f}s / {status['max_execution_time']:.1f}s ({status['time_usage_percent']:.1f}%)")
    else:
        print("Time: Not started")

    print(f"Unique nodes visited: {len(status['node_visit_counts'])}")

    if status['most_visited_node']:
        print(f"Most visited node: {status['most_visited_node']} ({status['most_visited_count']} times)")
        usage_pct = (status['most_visited_count'] / status['max_visits_per_node']) * 100
        print(f"Visit usage: {usage_pct:.1f}% of limit per node")

    print("================================")

# Usage during debugging
walker = MyWalker()
await walker.spawn(start_node)
debug_protection_status(walker)
```

#### Environment Configuration Verification

```python
def verify_environment_config():
    """Verify environment variable configuration."""
    import os

    vars_to_check = [
        'JVSPATIAL_WALKER_PROTECTION_ENABLED',
        'JVSPATIAL_WALKER_MAX_STEPS',
        'JVSPATIAL_WALKER_MAX_VISITS_PER_NODE',
        'JVSPATIAL_WALKER_MAX_EXECUTION_TIME',
        'JVSPATIAL_WALKER_MAX_QUEUE_SIZE'
    ]

    print("=== Environment Configuration ===")
    for var in vars_to_check:
        value = os.getenv(var)
        if value:
            print(f"{var}: {value}")
        else:
            print(f"{var}: Not set (using default)")

    # Test walker creation
    walker = Walker()
    print(f"\nActual walker config:")
    print(f"  max_steps: {walker.max_steps}")
    print(f"  max_visits_per_node: {walker.max_visits_per_node}")
    print(f"  max_execution_time: {walker.max_execution_time}")
    print(f"  protection_enabled: {walker.protection_enabled}")
    print("=================================")

# Usage
verify_environment_config()
```

This comprehensive infinite walk protection system ensures that jvspatial walkers operate safely and efficiently, preventing infinite loops while providing detailed monitoring and configuration options for different use cases.