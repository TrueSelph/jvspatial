"""Queue management for walker traversal operations.

This module provides queue management functionality for walker traversals,
including size limits and backing deque operations.
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Deque, Iterable, List, Optional

logger = logging.getLogger(__name__)


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
        # One-shot warning when ``max_size`` is hit — repeated drops are
        # rate-limited so a runaway producer cannot flood logs.
        self._drop_warned: bool = False

    def _has_capacity(self) -> bool:
        return self._max_size <= 0 or len(self._backing) < self._max_size

    def _warn_drop(self, op: str, count: int) -> None:
        """Warn once per queue when ``max_size`` causes drops (SPEC §6.3)."""
        if not self._drop_warned:
            logger.warning(
                "WalkerQueue.%s: queue at max_size=%d, dropped %d node(s); "
                "subsequent drops will be silent.",
                op,
                self._max_size,
                count,
            )
            self._drop_warned = True

    async def visit(self, nodes: Iterable[object]) -> None:
        """Add nodes to queue, respecting max_size limit."""
        dropped = 0
        for n in nodes:
            if self._has_capacity():
                self._backing.append(n)
            else:
                dropped += 1
        if dropped:
            self._warn_drop("visit", dropped)

    async def dequeue(self, nodes: object) -> List[object]:
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

    async def prepend(self, nodes: Iterable[object]) -> None:
        """Add nodes to the front of the queue.

        Respects ``max_size`` (audit §2.4 / SPEC §6.3) — earlier versions
        of this method bypassed the cap, providing a silent protection
        bypass via front-of-queue inserts.

        Args:
            nodes: Nodes to prepend to the queue
        """
        dropped = 0
        for n in reversed(list(nodes)):
            if self._has_capacity():
                self._backing.appendleft(n)
            else:
                dropped += 1
        if dropped:
            self._warn_drop("prepend", dropped)

    async def append(self, nodes: Iterable[object]) -> None:
        """Add nodes to the end of the queue.

        Args:
            nodes: Nodes to append to the queue
        """
        dropped = 0
        for n in nodes:
            if self._has_capacity():
                self._backing.append(n)
            else:
                dropped += 1
        if dropped:
            self._warn_drop("append", dropped)

    async def add_next(self, nodes: Iterable[object]) -> None:
        """Add nodes to the front of the queue in the order provided.

        Respects ``max_size`` (audit §2.4 / SPEC §6.3).

        Args:
            nodes: Nodes to add to the front of the queue
        """
        dropped = 0
        for n in reversed(list(nodes)):
            if self._has_capacity():
                self._backing.appendleft(n)
            else:
                dropped += 1
        if dropped:
            self._warn_drop("add_next", dropped)

    async def clear(self) -> None:
        """Clear all nodes from the queue."""
        self._backing.clear()

    def __len__(self) -> int:  # pragma: no cover - trivial
        """Get the number of nodes in the queue.

        Returns:
            Number of nodes in the queue
        """
        return len(self._backing)

    def __bool__(self) -> bool:
        """Check if queue is not empty."""
        return len(self._backing) > 0

    def __contains__(self, node: object) -> bool:
        """Check if node is in the queue."""
        return node in self._backing

    def popleft(self) -> object:
        """Remove and return the leftmost node from the queue.

        Returns:
            The leftmost node in the queue

        Raises:
            IndexError: If the queue is empty
        """
        return self._backing.popleft()

    def to_list(self) -> List[object]:
        """Convert queue to a list.

        Returns:
            List representation of the queue
        """
        return list(self._backing)

    async def insert_after(
        self, target_node: object, nodes: Iterable[object]
    ) -> List[object]:
        """Insert nodes after a target node in the queue.

        Respects ``max_size`` (audit §2.4 / SPEC §6.3). Excess nodes are
        dropped from the tail of the input rather than inserted.

        Args:
            target_node: The node to insert after
            nodes: Nodes to insert

        Returns:
            List of nodes that were actually inserted

        Raises:
            ValueError: If target node is not found in the queue
        """
        nodes_list = list(nodes)
        if not nodes_list:
            return []

        # Find the target node position
        try:
            target_index = list(self._backing).index(target_node)
        except ValueError:
            raise ValueError(f"Target node {target_node} not found in queue")

        inserted: List[object] = []
        dropped = 0
        for node in nodes_list:
            if self._has_capacity():
                self._backing.insert(target_index + 1 + len(inserted), node)
                inserted.append(node)
            else:
                dropped += 1
        if dropped:
            self._warn_drop("insert_after", dropped)

        return inserted

    async def insert_before(
        self, target_node: object, nodes: Iterable[object]
    ) -> List[object]:
        """Insert nodes before a target node in the queue.

        Respects ``max_size`` (audit §2.4 / SPEC §6.3).

        Args:
            target_node: The node to insert before
            nodes: Nodes to insert

        Returns:
            List of nodes that were actually inserted

        Raises:
            ValueError: If target node is not found in the queue
        """
        nodes_list = list(nodes)
        if not nodes_list:
            return []

        # Find the target node position
        try:
            target_index = list(self._backing).index(target_node)
        except ValueError:
            raise ValueError(f"Target node {target_node} not found in queue")

        inserted: List[object] = []
        dropped = 0
        for node in nodes_list:
            if self._has_capacity():
                self._backing.insert(target_index + len(inserted), node)
                inserted.append(node)
            else:
                dropped += 1
        if dropped:
            self._warn_drop("insert_before", dropped)

        return inserted
