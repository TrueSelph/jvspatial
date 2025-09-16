#!/usr/bin/env python3
"""
Comprehensive test script for Walker queue utility operations.

This script tests all the new queue methods added to the Walker class:
- dequeue()
- prepend()
- append()
- add_next()
- get_queue()
- clear_queue()
- insert_after()
- insert_before()
- is_queued()
"""

import asyncio
import os
import sys
from collections import deque
from typing import ClassVar, List

import pytest_asyncio

# Add the parent directory to the Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from jvspatial.core.entities import Node, Root, Walker

# Set up test environment
os.environ["JVSPATIAL_DB_TYPE"] = "json"
os.environ["JVSPATIAL_JSONDB_PATH"] = "jvdb/test_queue_operations"


class TestNode(Node):
    """Simple test node with a name for easy identification."""

    name: str


class TestWalker(Walker):
    """Test walker for queue operations."""

    pass


@pytest_asyncio.fixture
async def test_queue_operations():
    """Test all Walker queue operations."""

    print("🧪 Testing Walker Queue Operations")
    print("=" * 50)

    # Create test nodes
    node_a = TestNode(name="A")
    node_b = TestNode(name="B")
    node_c = TestNode(name="C")
    node_d = TestNode(name="D")
    node_e = TestNode(name="E")

    await node_a.save()
    await node_b.save()
    await node_c.save()
    await node_d.save()
    await node_e.save()

    print(
        f"Created test nodes: {[n.name for n in [node_a, node_b, node_c, node_d, node_e]]}"
    )

    # Create test walker
    walker = TestWalker()

    # Test 1: get_queue() - empty queue
    print("\n1️⃣ Testing get_queue() with empty queue:")
    queue = walker.get_queue()
    print(
        f"   Empty queue: {[n.name if hasattr(n, 'name') else str(n) for n in queue]}"
    )
    assert len(queue) == 0, "Empty queue should have length 0"
    print("   ✅ get_queue() works with empty queue")

    # Test 2: append() - add nodes to end
    print("\n2️⃣ Testing append():")
    walker.append([node_a, node_b])
    queue = walker.get_queue()
    print(f"   After append([A, B]): {[n.name for n in queue]}")
    assert len(queue) == 2, "Queue should have 2 nodes"
    assert queue[0].name == "A" and queue[1].name == "B", "Order should be A, B"
    print("   ✅ append() works correctly")

    # Test 3: prepend() - add nodes to beginning
    print("\n3️⃣ Testing prepend():")
    walker.prepend([node_c, node_d])
    queue = walker.get_queue()
    print(f"   After prepend([C, D]): {[n.name for n in queue]}")
    assert len(queue) == 4, "Queue should have 4 nodes"
    assert [n.name for n in queue] == ["C", "D", "A", "B"], "Order should be C, D, A, B"
    print("   ✅ prepend() works correctly")

    # Test 4: is_queued()
    print("\n4️⃣ Testing is_queued():")
    assert walker.is_queued(node_a) == True, "Node A should be in queue"
    assert walker.is_queued(node_e) == False, "Node E should not be in queue"
    print(f"   is_queued(A): {walker.is_queued(node_a)}")
    print(f"   is_queued(E): {walker.is_queued(node_e)}")
    print("   ✅ is_queued() works correctly")

    # Test 5: insert_after()
    print("\n5️⃣ Testing insert_after():")
    walker.insert_after(node_c, node_e)  # Insert E after C
    queue = walker.get_queue()
    print(f"   After insert_after(C, E): {[n.name for n in queue]}")
    assert [n.name for n in queue] == [
        "C",
        "E",
        "D",
        "A",
        "B",
    ], "Order should be C, E, D, A, B"
    print("   ✅ insert_after() works correctly")

    # Test 6: insert_before()
    print("\n6️⃣ Testing insert_before():")
    new_node = TestNode(name="X")
    await new_node.save()
    walker.insert_before(node_a, new_node)  # Insert X before A
    queue = walker.get_queue()
    print(f"   After insert_before(A, X): {[n.name for n in queue]}")
    assert [n.name for n in queue] == [
        "C",
        "E",
        "D",
        "X",
        "A",
        "B",
    ], "Order should be C, E, D, X, A, B"
    print("   ✅ insert_before() works correctly")

    # Test 7: dequeue() - remove specific nodes
    print("\n7️⃣ Testing dequeue():")
    removed = walker.dequeue([node_e, node_d])
    queue = walker.get_queue()
    print(f"   After dequeue([E, D]): {[n.name for n in queue]}")
    print(f"   Removed nodes: {[n.name for n in removed]}")
    assert len(queue) == 4, "Queue should have 4 nodes after removal"
    assert [n.name for n in queue] == ["C", "X", "A", "B"], "Order should be C, X, A, B"
    assert len(removed) == 2, "Should have removed 2 nodes"
    print("   ✅ dequeue() works correctly")

    # Test 8: add_next()
    print("\n8️⃣ Testing add_next():")
    walker.add_next(node_d)  # Add D next (to front)
    queue = walker.get_queue()
    print(f"   After add_next(D): {[n.name for n in queue]}")
    assert [n.name for n in queue] == [
        "D",
        "C",
        "X",
        "A",
        "B",
    ], "Order should be D, C, X, A, B"
    print("   ✅ add_next() works correctly")

    # Test 9: clear_queue()
    print("\n9️⃣ Testing clear_queue():")
    walker.clear_queue()
    queue = walker.get_queue()
    print(
        f"   After clear_queue(): {[n.name if hasattr(n, 'name') else str(n) for n in queue]}"
    )
    assert len(queue) == 0, "Queue should be empty after clear"
    print("   ✅ clear_queue() works correctly")

    # Test 10: Error handling
    print("\n🔟 Testing error handling:")
    try:
        walker.insert_after(node_a, node_b)  # node_a not in empty queue
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"   Expected error for insert_after(): {e}")
        print("   ✅ insert_after() raises ValueError for missing node")

    try:
        walker.insert_before(node_a, node_b)  # node_a not in empty queue
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"   Expected error for insert_before(): {e}")
        print("   ✅ insert_before() raises ValueError for missing node")

    # Test 11: Multiple operations and edge cases
    print("\n1️⃣1️⃣ Testing edge cases:")

    # Single node operations
    walker.append(node_a)
    walker.prepend(node_b)
    queue = walker.get_queue()
    print(f"   Single node operations [B, A]: {[n.name for n in queue]}")
    assert [n.name for n in queue] == ["B", "A"], "Should handle single nodes correctly"

    # Empty list operations (should be no-ops)
    walker.append([])
    walker.prepend([])
    queue_after_empty = walker.get_queue()
    assert len(queue_after_empty) == len(
        queue
    ), "Empty list operations should not change queue"
    print("   ✅ Empty list operations handled correctly")

    # Duplicate node handling
    walker.clear_queue()
    walker.append([node_a, node_a, node_b])  # Add A twice
    walker.dequeue(node_a)  # Should remove all instances of A
    queue = walker.get_queue()
    print(f"   After adding A twice and dequeuing A: {[n.name for n in queue]}")
    assert [n.name for n in queue] == [
        "B"
    ], "Should remove all instances of duplicate nodes"
    print("   ✅ Duplicate node handling works correctly")

    print("\n🎉 All queue operation tests passed!")
    print("=" * 50)


@pytest_asyncio.fixture
async def test_integration_with_spawn():
    """Test queue operations work correctly with spawn/traversal."""

    print("\n🔄 Testing integration with spawn/traversal")
    print("=" * 50)

    # Create a test walker that manipulates its queue during traversal
    class QueueManipulatingWalker(Walker):
        visited_nodes: ClassVar[List[str]] = []

        async def on_visit_any(self, node):
            self.visited_nodes.append(node.name if hasattr(node, "name") else str(node))
            print(f"   Visiting: {node.name if hasattr(node, 'name') else str(node)}")

            # Add some queue manipulation during traversal
            if hasattr(node, "name") and node.name == "A":
                # When visiting A, add C to be processed next
                test_node_c = (
                    await TestNode.get(test_node_c_id)
                    if "test_node_c_id" in globals()
                    else None
                )
                if test_node_c and not self.is_queued(test_node_c):
                    self.add_next(test_node_c)
                    print(f"     Added {test_node_c.name} next in queue")

    # Set up nodes
    node_a = TestNode(name="A")
    node_b = TestNode(name="B")
    node_c = TestNode(name="C")

    await node_a.save()
    await node_b.save()
    await node_c.save()

    global test_node_c_id
    test_node_c_id = node_c.id

    # Create walker and set up initial queue
    walker = QueueManipulatingWalker()
    walker.clear_queue()  # Start with empty queue
    walker.append([node_a, node_b])

    print(f"Initial queue: {[n.name for n in walker.get_queue()]}")

    # This would normally be done with spawn, but for testing we'll simulate traversal
    # Note: We can't easily test the full spawn integration without setting up hooks properly
    # So we'll test the queue state changes manually

    queue_before = walker.get_queue()
    print(f"Queue before manipulation: {[n.name for n in queue_before]}")

    # Simulate some queue operations during "traversal"
    if walker.is_queued(node_a):
        walker.add_next(node_c)  # Add C next

    queue_after = walker.get_queue()
    print(f"Queue after adding C next: {[n.name for n in queue_after]}")

    # Verify the queue was manipulated correctly
    assert walker.is_queued(node_c), "Node C should be in queue"
    assert queue_after[0].name == "C", "Node C should be first in queue"

    print("   ✅ Queue operations work correctly during traversal simulation")
    print("=" * 50)


if __name__ == "__main__":

    async def main():
        """Run all tests."""
        try:
            await test_queue_operations()
            await test_integration_with_spawn()
            print("\n🏆 All Walker queue operation tests completed successfully!")

        except Exception as e:
            print(f"\n❌ Test failed with error: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)

    # Run the tests
    asyncio.run(main())
