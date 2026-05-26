"""Walker trail tracking for graph traversals.

This module provides functionality to track the path taken by walkers
during graph traversals, including metadata about each step.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List, Optional


class WalkerTrail:
    """Tracks traversal steps and metadata.

    ``max_length`` bounds the trail so long traversals cannot blow memory
    (SPEC §6.4 — ``0`` means unlimited, the documented Walker contract).
    Older steps are dropped from the front when the bound is hit.
    """

    def __init__(self, max_length: int = 0) -> None:
        """Initialize the trail tracker.

        Args:
            max_length: Maximum number of steps retained. ``0`` (default)
                means unlimited. Use a positive integer to cap memory on
                long-running traversals.
        """
        self._max_length = max(0, int(max_length))
        # ``maxlen=None`` makes the deque unbounded. Annotating in one place
        # so mypy knows the element type regardless of which branch ran.
        bound: Optional[int] = self._max_length if self._max_length > 0 else None
        self._trail: Deque[Dict[str, Any]] = deque(maxlen=bound)

    def record_step(
        self, node_id: Any, edge_id: Optional[Any] = None, **metadata: Any
    ) -> None:
        """Record a step in the traversal trail.

        Args:
            node_id: ID of the node being visited
            edge_id: ID of the edge used to reach the node
            **metadata: Additional metadata about the step
        """
        step = {"node": node_id, "edge": edge_id, **metadata}
        self._trail.append(step)

    def get_trail(self) -> List[Dict[str, Any]]:
        """Get the complete trail.

        Returns:
            List of all recorded steps
        """
        return list(self._trail)

    async def get_recent(self, count: int = 5) -> List[str]:
        """Get most recent node IDs from trail."""
        if count <= 0:
            return []
        # ``deque`` does not support slice access; materialize once.
        trail_list = list(self._trail)
        return [step["node"] for step in trail_list[-count:]]

    def get_length(self) -> int:
        """Get trail length."""
        return len(self._trail)

    def clear_trail(self) -> None:
        """Clear all steps from the trail."""
        self._trail.clear()

    async def detect_cycles(self) -> List[tuple]:
        """Detect cycles in the trail.

        Returns:
            List of (start_position, end_position) tuples for detected cycles
        """
        cycles = []
        node_positions: Dict[str, int] = {}

        for i, step in enumerate(self._trail):
            node_id = step.get("node")
            if node_id is not None:
                if node_id in node_positions:
                    # Found a cycle: from first occurrence to current position
                    cycles.append((node_positions[node_id], i))
                else:
                    node_positions[node_id] = i

        return cycles
