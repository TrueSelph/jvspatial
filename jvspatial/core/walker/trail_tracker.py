"""Trail tracking for walker traversals.

This module provides functionality to track the path taken by walkers
during graph traversals, including metadata about each step.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class TrailTracker:
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
        self._trail.append({"node": node_id, "edge": edge_id, **metadata})

    def get_trail(self) -> List[Dict[str, Any]]:
        """Get the complete trail.

        Returns:
            List of all recorded steps
        """
        return list(self._trail)

    def get_recent(self, count: int = 5) -> List[str]:
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
