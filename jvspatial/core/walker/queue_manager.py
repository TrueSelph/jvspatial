"""Queue management for walker traversal operations.

This module provides queue management functionality for walker traversals,
including size limits and backing deque operations.
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Iterable, List, Optional


class WalkerQueue:
    """Manages walker traversal queue operations."""

    def __init__(
        self, backing_deque: Optional[Deque[object]] = None, max_size: int = 1000
    ) -> None:
        """Initialize the walker queue.

        Args:
            backing_deque: Optional backing deque to use
            max_size: Maximum queue size
        """
        # If a backing deque is provided, operate on it directly to avoid divergence
        self._backing: Deque[object] = (
            backing_deque if backing_deque is not None else deque()
        )
        self._max_size = max_size

    def visit(self, nodes: Iterable[object]) -> None:
        """Add nodes to queue, respecting max_size limit."""
        for n in nodes:
            # Only add if we haven't hit the limit
            if self._max_size <= 0 or len(self._backing) < self._max_size:
                self._backing.append(n)

    def dequeue(self, nodes: object) -> List[object]:
        """Remove specified node(s) from the queue.

        Args:
            nodes: Single node or list of nodes to remove

        Returns:
            List of nodes that were successfully removed
        """
        from typing import List as ListType

        # Handle single node or list
        nodes_list = nodes if isinstance(nodes, list) else [nodes]
        removed_nodes: ListType[object] = []

        # Convert deque to list for easier manipulation
        queue_list = list(self._backing)

        for node in nodes_list:
            # Remove all occurrences of the node from the queue
            while node in queue_list:
                queue_list.remove(node)
                removed_nodes.append(node)

        # Rebuild the queue with remaining nodes
        self._backing.clear()
        self._backing.extend(queue_list)
        return removed_nodes

    def prepend(self, nodes: Iterable[object]) -> None:
        """Add nodes to the front of the queue.

        Args:
            nodes: Nodes to prepend to the queue
        """
        for n in reversed(list(nodes)):
            self._backing.appendleft(n)

    def append(self, nodes: Iterable[object]) -> None:
        """Add nodes to the end of the queue.

        Args:
            nodes: Nodes to append to the queue
        """
        for n in nodes:
            self._backing.append(n)

    def clear(self) -> None:
        """Clear all nodes from the queue."""
        self._backing.clear()

    def __len__(self) -> int:  # pragma: no cover - trivial
        """Get the number of nodes in the queue.

        Returns:
            Number of nodes in the queue
        """
        return len(self._backing)
