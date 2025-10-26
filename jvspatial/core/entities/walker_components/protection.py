"""Walker protection system for preventing infinite loops and resource exhaustion.

This module provides protection mechanisms for walkers to prevent infinite
loops, excessive resource usage, and other potentially harmful behaviors.
"""

from __future__ import annotations

import time
from typing import Any, Dict, Optional


class ProtectionViolation(Exception):
    """Exception raised when a protection limit is exceeded."""

    def __init__(self, protection_type: str, details: Dict[str, Any]):
        """Initialize protection violation.

        Args:
            protection_type: Type of protection that was triggered
            details: Additional details about the violation
        """
        self.protection_type = protection_type
        self.details = details
        super().__init__(f"Protection triggered: {protection_type}")


class TraversalProtection:
    """Simple protection against runaway traversals."""

    def __init__(
        self,
        max_steps: int = 10000,
        max_visits_per_node: int = 100,
        max_execution_time: float = 300.0,
    ):
        """Initialize traversal protection.

        Args:
            max_steps: Maximum number of traversal steps
            max_visits_per_node: Maximum visits to any single node
            max_execution_time: Maximum execution time in seconds
        """
        self._max_steps = max_steps
        self._max_visits_per_node = max_visits_per_node
        self._max_execution_time = max_execution_time
        self._steps = 0
        self._visit_counts: dict[str, int] = {}
        self._start_time: Optional[float] = None

    async def increment_step(self) -> None:
        """Increment the step counter and check protection limits."""
        self._steps += 1

        # Check timeout first if enabled
        self._check_timeout()

        # Then check step limit
        if self._steps >= self._max_steps:
            raise ProtectionViolation(
                "max_steps",
                {
                    "steps_taken": self._steps,
                    "max_steps": self._max_steps,
                },
            )

    def record_visit(self, node_id: str) -> None:
        """Record a visit to a node and check visit limits.

        Args:
            node_id: ID of the node being visited

        Raises:
            ProtectionViolation: If visit limit is exceeded
        """
        count = self._visit_counts.get(node_id, 0) + 1
        self._visit_counts[node_id] = count
        if count >= self._max_visits_per_node:
            raise ProtectionViolation(
                "max_visits_per_node",
                {
                    "node_id": node_id,
                    "visit_count": count,
                    "max_visits_per_node": self._max_visits_per_node,
                },
            )

    def _check_timeout(self) -> None:
        """Check if execution time has exceeded the limit."""
        if self._start_time is None:
            return

        elapsed = time.time() - self._start_time
        if self._max_execution_time > 0 and elapsed >= self._max_execution_time:
            raise ProtectionViolation(
                "timeout",
                {
                    "execution_time": elapsed,
                    "max_execution_time": self._max_execution_time,
                },
            )

    async def reset(self) -> None:
        """Reset protection state and start timing."""
        self._steps = 0
        self._visit_counts.clear()
        self._start_time = time.time()

    @property
    def step_count(self) -> int:
        """Get current step count."""
        return self._steps

    @property
    def visit_counts(self) -> dict[str, int]:
        """Get visit counts per node."""
        return dict(self._visit_counts)

    @property
    def max_steps(self) -> int:
        """Get maximum steps limit."""
        return self._max_steps

    @max_steps.setter
    def max_steps(self, value: int) -> None:
        """Set maximum steps limit."""
        self._max_steps = max(0, value)

    @property
    def max_visits_per_node(self) -> int:
        """Get maximum visits per node limit."""
        return self._max_visits_per_node

    @max_visits_per_node.setter
    def max_visits_per_node(self, value: int) -> None:
        """Set maximum visits per node limit."""
        self._max_visits_per_node = max(0, value)

    @property
    def max_execution_time(self) -> float:
        """Get maximum execution time limit."""
        return self._max_execution_time

    @max_execution_time.setter
    def max_execution_time(self, value: float) -> None:
        """Set maximum execution time limit."""
        self._max_execution_time = max(0.0, value)

    @property
    def elapsed_time(self) -> Optional[float]:
        """Get elapsed execution time, or None if not started."""
        if self._start_time is None:
            return None
        return time.time() - self._start_time

    async def check_limits(self) -> bool:
        """Check if limits are exceeded without raising. Returns True if OK."""
        if self._steps >= self._max_steps:
            return False
        for count in self._visit_counts.values():
            if count >= self._max_visits_per_node:
                return False
        # Check timeout
        if self._start_time is not None and self._max_execution_time > 0:
            elapsed = time.time() - self._start_time
            if elapsed >= self._max_execution_time:
                return False
        return True
