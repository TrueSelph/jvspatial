"""Walker trail tracking for graph traversals.

This module provides functionality to track the path taken by walkers
during graph traversals, including metadata about each step.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class WalkerTrail:
    """Tracks traversal steps and metadata."""

    def __init__(self) -> None:
        """Initialize the trail tracker."""
        self._trail: List[Dict[str, Any]] = []

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
        return [step["node"] for step in self._trail[-count:]]

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
