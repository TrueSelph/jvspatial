"""
Test suite for Walker queue management operations.

This module implements comprehensive tests for:
- Queue methods: append(), prepend(), add_next(), dequeue(), insert_after(), insert_before()
- Queue inspection methods: get_queue(), is_queued(), clear_queue()
- Conditional queue operations and state management
- Queue overflow handling and boundary conditions
- Integration with traversal patterns
"""

from collections import deque
from typing import Any, Dict, List
from unittest.mock import MagicMock

import pytest
from pydantic import Field

from jvspatial.core.entities import Edge, Node, Walker


class QueueTestNode(Node):
    """Test node for queue testing."""

    name: str = ""
    priority: int = 0
    category: str = ""


class QueueTestEdge(Edge):
    """Test edge for queue testing."""

    name: str = ""
    weight: int = 1


class QueueTestWalker(Walker):
    """Test walker for queue operations."""

    operations_log: List[Dict[str, Any]] = Field(default_factory=list)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def log_operation(self, operation: str, result: List[Node]):
        """Log queue operations for testing."""
        self.operations_log.append(
            {
                "operation": operation,
                "result_count": len(result),
                "queue_size": len(self.queue),
                "queue_items": [
                    getattr(item, "name", str(item)) for item in list(self.queue)
                ],
            }
        )


@pytest.fixture
def walker():
    """Create a test walker."""
    return QueueTestWalker()


@pytest.fixture
def test_nodes():
    """Create test nodes for queue operations."""
    return [
        QueueTestNode(name="node_a", priority=1, category="type1"),
        QueueTestNode(name="node_b", priority=2, category="type2"),
        QueueTestNode(name="node_c", priority=3, category="type1"),
        QueueTestNode(name="node_d", priority=4, category="type2"),
        QueueTestNode(name="node_e", priority=5, category="type1"),
    ]


class TestQueueBasicOperations:
    """Test basic queue operations."""

    def test_empty_queue_initialization(self, walker):
        """Test empty queue state after initialization."""
        assert len(walker.queue) == 0
        assert isinstance(walker.queue, deque)
        assert walker.get_queue() == []

    def test_append_single_node(self, walker, test_nodes):
        """Test appending a single node."""
        node = test_nodes[0]
        result = walker.append(node)

        walker.log_operation("append_single", result)

        assert result == [node]
        assert len(walker.queue) == 1
        assert walker.queue[0] == node
        assert walker.is_queued(node)

        log_entry = walker.operations_log[0]
        assert log_entry["result_count"] == 1
        assert log_entry["queue_size"] == 1

    def test_append_multiple_nodes(self, walker, test_nodes):
        """Test appending multiple nodes."""
        nodes_to_add = test_nodes[:3]
        result = walker.append(nodes_to_add)

        walker.log_operation("append_multiple", result)

        assert result == nodes_to_add
        assert len(walker.queue) == 3
        assert list(walker.queue) == nodes_to_add
        assert all(walker.is_queued(node) for node in nodes_to_add)

    def test_append_preserves_order(self, walker, test_nodes):
        """Test that append preserves the order of nodes."""
        # Add nodes one by one
        for node in test_nodes:
            walker.append(node)

        queue_list = walker.get_queue()
        assert queue_list == test_nodes

        # Verify FIFO behavior
        assert walker.queue[0] == test_nodes[0]  # First added
        assert walker.queue[-1] == test_nodes[-1]  # Last added

    def test_prepend_single_node(self, walker, test_nodes):
        """Test prepending a single node."""
        # Add base nodes first
        walker.append(test_nodes[:2])

        # Prepend new node
        new_node = test_nodes[2]
        result = walker.prepend(new_node)

        walker.log_operation("prepend_single", result)

        assert result == [new_node]
        assert len(walker.queue) == 3
        assert walker.queue[0] == new_node  # Should be first
        assert list(walker.queue) == [new_node] + test_nodes[:2]

    def test_prepend_multiple_nodes(self, walker, test_nodes):
        """Test prepending multiple nodes."""
        # Add base node
        walker.append(test_nodes[0])

        # Prepend multiple nodes
        nodes_to_prepend = test_nodes[1:3]
        result = walker.prepend(nodes_to_prepend)

        walker.log_operation("prepend_multiple", result)

        assert result == nodes_to_prepend
        assert len(walker.queue) == 3
        # Should maintain relative order: node_b, node_c, node_a
        expected_order = [test_nodes[1], test_nodes[2], test_nodes[0]]
        assert list(walker.queue) == expected_order

    def test_add_next_empty_queue(self, walker, test_nodes):
        """Test add_next() with empty queue."""
        nodes_to_add = test_nodes[:2]
        result = walker.add_next(nodes_to_add)

        walker.log_operation("add_next_empty", result)

        assert result == nodes_to_add
        assert len(walker.queue) == 2
        assert list(walker.queue) == nodes_to_add

    def test_add_next_with_existing_queue(self, walker, test_nodes):
        """Test add_next() with existing queue items."""
        # Add base nodes
        walker.append(test_nodes[:2])

        # Add next
        nodes_to_add = test_nodes[2:4]
        result = walker.add_next(nodes_to_add)

        walker.log_operation("add_next_existing", result)

        assert result == nodes_to_add
        assert len(walker.queue) == 4
        # Should be: node_c, node_d, node_a, node_b
        expected_order = [test_nodes[2], test_nodes[3]] + test_nodes[:2]
        assert list(walker.queue) == expected_order


class TestQueueRemovalOperations:
    """Test queue removal operations."""

    def test_dequeue_single_node(self, walker, test_nodes):
        """Test removing a single node from queue."""
        # Add nodes
        walker.append(test_nodes[:3])

        # Remove middle node
        node_to_remove = test_nodes[1]
        result = walker.dequeue(node_to_remove)

        walker.log_operation("dequeue_single", result)

        assert result == [node_to_remove]
        assert len(walker.queue) == 2
        assert not walker.is_queued(node_to_remove)
        assert list(walker.queue) == [test_nodes[0], test_nodes[2]]

    def test_dequeue_multiple_nodes(self, walker, test_nodes):
        """Test removing multiple nodes from queue."""
        # Add all nodes
        walker.append(test_nodes)

        # Remove multiple nodes
        nodes_to_remove = [test_nodes[1], test_nodes[3]]
        result = walker.dequeue(nodes_to_remove)

        walker.log_operation("dequeue_multiple", result)

        assert len(result) == 2
        assert test_nodes[1] in result
        assert test_nodes[3] in result
        assert len(walker.queue) == 3
        expected_remaining = [test_nodes[0], test_nodes[2], test_nodes[4]]
        assert list(walker.queue) == expected_remaining

    def test_dequeue_nonexistent_node(self, walker, test_nodes):
        """Test dequeuing a node that's not in the queue."""
        walker.append(test_nodes[:2])

        # Try to remove node not in queue
        result = walker.dequeue(test_nodes[2])

        walker.log_operation("dequeue_nonexistent", result)

        assert result == []
        assert len(walker.queue) == 2  # No change

    def test_dequeue_duplicate_nodes(self, walker, test_nodes):
        """Test dequeuing when same node appears multiple times."""
        node = test_nodes[0]
        walker.append([node, test_nodes[1], node, test_nodes[2]])

        result = walker.dequeue(node)

        walker.log_operation("dequeue_duplicates", result)

        # Should remove all occurrences
        assert len(result) == 2  # Two instances removed
        assert all(r == node for r in result)
        assert len(walker.queue) == 2
        assert not walker.is_queued(node)

    def test_clear_queue(self, walker, test_nodes):
        """Test clearing the entire queue."""
        walker.append(test_nodes)
        assert len(walker.queue) == len(test_nodes)

        walker.clear_queue()
        walker.log_operation("clear_queue", [])

        assert len(walker.queue) == 0
        assert walker.get_queue() == []
        assert all(not walker.is_queued(node) for node in test_nodes)


class TestQueueInsertionOperations:
    """Test queue insertion operations."""

    def test_insert_after_existing_node(self, walker, test_nodes):
        """Test inserting nodes after a specific node."""
        # Set up initial queue: [A, B, C]
        walker.append(test_nodes[:3])

        # Insert after B
        target_node = test_nodes[1]  # node_b
        nodes_to_insert = test_nodes[3:5]  # [node_d, node_e]

        result = walker.insert_after(target_node, nodes_to_insert)

        walker.log_operation("insert_after", result)

        assert result == nodes_to_insert
        assert len(walker.queue) == 5
        # Expected: [A, B, D, E, C]
        expected_order = [
            test_nodes[0],
            test_nodes[1],
            test_nodes[3],
            test_nodes[4],
            test_nodes[2],
        ]
        assert list(walker.queue) == expected_order

    def test_insert_after_last_node(self, walker, test_nodes):
        """Test inserting after the last node in queue."""
        walker.append(test_nodes[:2])

        # Insert after last node
        target_node = test_nodes[1]
        nodes_to_insert = test_nodes[2:4]

        result = walker.insert_after(target_node, nodes_to_insert)

        assert result == nodes_to_insert
        assert len(walker.queue) == 4
        # Should be appended at end
        expected_order = test_nodes[:2] + test_nodes[2:4]
        assert list(walker.queue) == expected_order

    def test_insert_after_nonexistent_node(self, walker, test_nodes):
        """Test inserting after a node not in queue."""
        walker.append(test_nodes[:2])

        with pytest.raises(ValueError, match="Target node .* not found in queue"):
            walker.insert_after(test_nodes[2], [test_nodes[3]])

    def test_insert_before_existing_node(self, walker, test_nodes):
        """Test inserting nodes before a specific node."""
        # Set up initial queue: [A, B, C]
        walker.append(test_nodes[:3])

        # Insert before B
        target_node = test_nodes[1]  # node_b
        nodes_to_insert = test_nodes[3:5]  # [node_d, node_e]

        result = walker.insert_before(target_node, nodes_to_insert)

        walker.log_operation("insert_before", result)

        assert result == nodes_to_insert
        assert len(walker.queue) == 5
        # Expected: [A, D, E, B, C]
        expected_order = [
            test_nodes[0],
            test_nodes[3],
            test_nodes[4],
            test_nodes[1],
            test_nodes[2],
        ]
        assert list(walker.queue) == expected_order

    def test_insert_before_first_node(self, walker, test_nodes):
        """Test inserting before the first node in queue."""
        walker.append(test_nodes[:2])

        # Insert before first node
        target_node = test_nodes[0]
        nodes_to_insert = test_nodes[2:4]

        result = walker.insert_before(target_node, nodes_to_insert)

        assert result == nodes_to_insert
        assert len(walker.queue) == 4
        # Should be prepended at beginning
        expected_order = test_nodes[2:4] + test_nodes[:2]
        assert list(walker.queue) == expected_order

    def test_insert_before_nonexistent_node(self, walker, test_nodes):
        """Test inserting before a node not in queue."""
        walker.append(test_nodes[:2])

        with pytest.raises(ValueError, match="Target node .* not found in queue"):
            walker.insert_before(test_nodes[2], [test_nodes[3]])


class TestQueueInspectionMethods:
    """Test queue inspection and utility methods."""

    def test_is_queued_true(self, walker, test_nodes):
        """Test is_queued() returns True for queued nodes."""
        walker.append(test_nodes[:3])

        assert walker.is_queued(test_nodes[0])
        assert walker.is_queued(test_nodes[1])
        assert walker.is_queued(test_nodes[2])

    def test_is_queued_false(self, walker, test_nodes):
        """Test is_queued() returns False for non-queued nodes."""
        walker.append(test_nodes[:2])

        assert not walker.is_queued(test_nodes[2])
        assert not walker.is_queued(test_nodes[3])

    def test_get_queue_returns_copy(self, walker, test_nodes):
        """Test get_queue() returns a copy, not the original deque."""
        walker.append(test_nodes[:3])

        queue_copy = walker.get_queue()

        assert isinstance(queue_copy, list)
        assert queue_copy == test_nodes[:3]

        # Modifying the copy should not affect the original
        queue_copy.append(test_nodes[3])
        assert len(walker.queue) == 3  # Original unchanged

    def test_get_queue_empty(self, walker):
        """Test get_queue() with empty queue."""
        queue_list = walker.get_queue()
        assert queue_list == []
        assert isinstance(queue_list, list)

    def test_queue_state_after_operations(self, walker, test_nodes):
        """Test queue state consistency after multiple operations."""
        # Complex sequence of operations
        walker.append(test_nodes[:2])  # [A, B]
        walker.prepend([test_nodes[2]])  # [C, A, B]
        walker.insert_after(test_nodes[0], [test_nodes[3]])  # [C, A, D, B]
        walker.dequeue(test_nodes[2])  # [A, D, B]
        walker.add_next([test_nodes[4]])  # [E, A, D, B]

        expected_final = [test_nodes[4], test_nodes[0], test_nodes[3], test_nodes[1]]
        assert list(walker.queue) == expected_final
        assert len(walker.queue) == 4
        assert all(walker.is_queued(node) for node in expected_final)


class TestQueueConditionalOperations:
    """Test conditional and advanced queue operations."""

    def test_queue_filtering_by_category(self, walker, test_nodes):
        """Test filtering queue by node properties."""
        walker.append(test_nodes)

        # Filter type1 nodes
        type1_nodes = [node for node in walker.get_queue() if node.category == "type1"]
        type2_nodes = [node for node in walker.get_queue() if node.category == "type2"]

        assert len(type1_nodes) == 3  # node_a, node_c, node_e
        assert len(type2_nodes) == 2  # node_b, node_d
        assert all(node.category == "type1" for node in type1_nodes)
        assert all(node.category == "type2" for node in type2_nodes)

    def test_queue_sorting_by_priority(self, walker, test_nodes):
        """Test sorting queue by node priorities."""
        # Add nodes in random order
        random_order = [
            test_nodes[3],
            test_nodes[1],
            test_nodes[4],
            test_nodes[0],
            test_nodes[2],
        ]
        walker.append(random_order)

        # Get sorted by priority
        queue_list = walker.get_queue()
        sorted_by_priority = sorted(queue_list, key=lambda x: x.priority)

        assert [node.priority for node in sorted_by_priority] == [1, 2, 3, 4, 5]
        assert sorted_by_priority == test_nodes  # Should match original order

    def test_conditional_dequeue(self, walker, test_nodes):
        """Test conditionally removing nodes from queue."""
        walker.append(test_nodes)

        # Remove all type2 nodes
        type2_nodes = [node for node in walker.get_queue() if node.category == "type2"]
        removed = walker.dequeue(type2_nodes)

        walker.log_operation("conditional_dequeue", removed)

        assert len(removed) == 2
        assert all(node.category == "type2" for node in removed)

        # Verify only type1 nodes remain
        remaining = walker.get_queue()
        assert len(remaining) == 3
        assert all(node.category == "type1" for node in remaining)

    def test_queue_batch_operations(self, walker, test_nodes):
        """Test performing multiple queue operations in batch."""
        # Batch operation: add, insert, remove
        operations = [
            ("append", test_nodes[:2]),
            ("prepend", [test_nodes[2]]),
            ("insert_after", test_nodes[0], [test_nodes[3]]),
            ("dequeue", [test_nodes[2]]),
            ("add_next", [test_nodes[4]]),
        ]

        for operation in operations:
            if operation[0] == "append":
                walker.append(operation[1])
            elif operation[0] == "prepend":
                walker.prepend(operation[1])
            elif operation[0] == "insert_after":
                walker.insert_after(operation[1], operation[2])
            elif operation[0] == "dequeue":
                walker.dequeue(operation[1])
            elif operation[0] == "add_next":
                walker.add_next(operation[1])

        # Final state should be: [E, A, D, B]
        expected_final = [test_nodes[4], test_nodes[0], test_nodes[3], test_nodes[1]]
        assert list(walker.queue) == expected_final


class TestQueueBoundaryConditions:
    """Test queue operations at boundary conditions."""

    def test_operations_on_single_node_queue(self, walker, test_nodes):
        """Test operations when queue has only one node."""
        single_node = test_nodes[0]
        walker.append([single_node])

        # Test insert operations
        walker.insert_after(single_node, [test_nodes[1]])
        assert len(walker.queue) == 2
        assert list(walker.queue) == [single_node, test_nodes[1]]

        # Reset
        walker.clear_queue()
        walker.append([single_node])

        walker.insert_before(single_node, [test_nodes[2]])
        assert len(walker.queue) == 2
        assert list(walker.queue) == [test_nodes[2], single_node]

    def test_operations_with_empty_lists(self, walker, test_nodes):
        """Test operations with empty node lists."""
        walker.append(test_nodes[:2])

        # Operations with empty lists should not change queue
        result1 = walker.append([])
        result2 = walker.prepend([])
        result3 = walker.dequeue([])

        assert result1 == []
        assert result2 == []
        assert result3 == []
        assert len(walker.queue) == 2
        assert list(walker.queue) == test_nodes[:2]

    def test_large_queue_operations(self, walker):
        """Test operations with large number of nodes."""
        # Create large number of test nodes
        large_node_set = [
            QueueTestNode(name=f"node_{i}", priority=i) for i in range(1000)
        ]

        # Test large append
        walker.append(large_node_set[:500])
        assert len(walker.queue) == 500

        # Test large prepend
        walker.prepend(large_node_set[500:750])
        assert len(walker.queue) == 750

        # Test large removal
        to_remove = large_node_set[100:200]
        removed = walker.dequeue(to_remove)
        assert len(removed) <= 100  # Some might not be in queue

        # Verify queue integrity
        queue_list = walker.get_queue()
        assert len(queue_list) == len(walker.queue)
        assert all(walker.is_queued(node) for node in queue_list)


class TestQueueWithEdges:
    """Test queue operations with Edge objects."""

    def test_mixed_node_edge_queue(self, walker, test_nodes):
        """Test queue operations with both nodes and edges."""
        edges = [
            QueueTestEdge(name="edge_1", weight=10),
            QueueTestEdge(name="edge_2", weight=20),
        ]

        # Mix nodes and edges in queue
        mixed_items = [test_nodes[0], edges[0], test_nodes[1], edges[1]]
        walker.append(mixed_items)

        assert len(walker.queue) == 4
        assert list(walker.queue) == mixed_items

        # Test operations work with mixed types
        walker.insert_after(edges[0], [test_nodes[2]])
        expected_order = [
            test_nodes[0],
            edges[0],
            test_nodes[2],
            test_nodes[1],
            edges[1],
        ]
        assert list(walker.queue) == expected_order

    def test_edge_specific_operations(self, walker):
        """Test queue operations specific to edges."""
        edges = [QueueTestEdge(name=f"edge_{i}", weight=i * 10) for i in range(5)]

        walker.append(edges)

        # Filter by weight
        heavy_edges = [e for e in walker.get_queue() if e.weight >= 30]
        light_edges = [e for e in walker.get_queue() if e.weight < 30]

        assert len(heavy_edges) == 2  # weight 30, 40
        assert len(light_edges) == 3  # weight 0, 10, 20

        # Remove heavy edges
        walker.dequeue(heavy_edges)
        assert len(walker.queue) == 3
        assert all(e.weight < 30 for e in walker.get_queue())


class TestQueueErrorRecovery:
    """Test queue error handling and recovery."""

    def test_queue_consistency_after_errors(self, walker, test_nodes):
        """Test queue remains consistent after operation errors."""
        walker.append(test_nodes[:3])
        original_state = walker.get_queue().copy()

        # Try invalid operations
        try:
            walker.insert_after(test_nodes[4], [test_nodes[3]])  # Node not in queue
        except ValueError:
            pass

        # Queue should remain unchanged
        assert walker.get_queue() == original_state

        try:
            walker.insert_before(QueueTestNode(name="nonexistent"), [test_nodes[4]])
        except ValueError:
            pass

        # Queue should still be unchanged
        assert walker.get_queue() == original_state

    def test_queue_recovery_after_partial_failures(self, walker, test_nodes):
        """Test queue recovery when some operations succeed and others fail."""
        walker.append(test_nodes[:2])

        # Mix of valid and invalid nodes for dequeue
        mixed_nodes = [test_nodes[0], QueueTestNode(name="invalid"), test_nodes[1]]
        result = walker.dequeue(mixed_nodes)

        # Should remove valid nodes only
        assert len(result) == 2
        assert test_nodes[0] in result
        assert test_nodes[1] in result
        assert len(walker.queue) == 0  # All valid nodes removed
