"""Walker trail tracking for graph traversals.

This module provides functionality to track the path taken by walkers
during graph traversals, including metadata about each step. Steps are
held in an in-memory ``deque`` for fast read-back, and may optionally
mirror to a pluggable :class:`TrailStore` so the history survives
process boundaries (Lambda cold starts, deferred-invoke resumes).
"""

from __future__ import annotations

import asyncio
from collections import deque
from typing import TYPE_CHECKING, Any, Deque, Dict, List, Optional

if TYPE_CHECKING:  # pragma: no cover - typing only
    from .trail_store import TrailStore


class WalkerTrail:
    """Tracks traversal steps and metadata.

    ``max_length`` bounds the in-memory ``deque`` so long traversals cannot
    blow memory (SPEC §6.4 — ``0`` means unlimited, the documented Walker
    contract). Older steps are dropped from the front when the bound is hit.

    When a ``store`` + ``walker_id`` are supplied the trail also mirrors
    every recorded step to the store, enabling resume across processes.
    The in-memory deque stays the read path (cheap), while the store
    provides durability.
    """

    def __init__(
        self,
        max_length: int = 0,
        *,
        store: Optional["TrailStore"] = None,
        walker_id: Optional[str] = None,
    ) -> None:
        """Initialize the trail tracker.

        Args:
            max_length: Maximum number of steps retained in memory. ``0``
                (default) means unlimited. Use a positive integer to cap
                memory on long-running traversals. Does NOT bound the
                persisted trail in ``store``; control that via the
                store's own retention policy.
            store: Optional :class:`TrailStore` to mirror steps to. When
                ``None``, the trail is in-memory only (the legacy
                behavior). Pass an
                :class:`~jvspatial.core.entities.walker_components.trail_store.InMemoryTrailStore`
                if you want store semantics without persistence.
            walker_id: Stable identifier used as the persistence key.
                Required when ``store`` is provided. Walker subclasses
                wire this automatically in ``__init__``.
        """
        self._max_length = max(0, int(max_length))
        # ``maxlen=None`` makes the deque unbounded. Annotating in one place
        # so mypy knows the element type regardless of which branch ran.
        bound: Optional[int] = self._max_length if self._max_length > 0 else None
        self._trail: Deque[Dict[str, Any]] = deque(maxlen=bound)

        if store is not None and not walker_id:
            raise ValueError(
                "WalkerTrail: walker_id is required when a store is provided"
            )
        self._store: Optional["TrailStore"] = store
        self._walker_id: Optional[str] = walker_id

    def record_step(
        self, node_id: Any, edge_id: Optional[Any] = None, **metadata: Any
    ) -> None:
        """Record a step in the traversal trail.

        When a ``store`` is configured the step is also written to the
        store. The write is fire-and-forget via ``asyncio.create_task``
        when called from inside a running loop, so this method stays
        sync-friendly for callers. To wait on the persistence write
        explicitly, use :meth:`arecord_step`.

        Args:
            node_id: ID of the node being visited
            edge_id: ID of the edge used to reach the node
            **metadata: Additional metadata about the step
        """
        step = {"node": node_id, "edge": edge_id, **metadata}
        self._trail.append(step)
        if self._store is not None and self._walker_id is not None:
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                # Not in an event loop — caller is using ``record_step``
                # from sync code. Skip the durable write; durability is a
                # best-effort guarantee for sync callers.
                return
            # Fire and forget; the store handles its own errors.
            loop.create_task(self._store.append(self._walker_id, step))

    async def arecord_step(
        self, node_id: Any, edge_id: Optional[Any] = None, **metadata: Any
    ) -> None:
        """Async sibling of :meth:`record_step` that awaits the store write.

        Use this when the caller wants durability guarantees on each
        step (no fire-and-forget). When no store is configured this
        behaves identically to :meth:`record_step`.
        """
        step = {"node": node_id, "edge": edge_id, **metadata}
        self._trail.append(step)
        if self._store is not None and self._walker_id is not None:
            await self._store.append(self._walker_id, step)

    async def hydrate_from_store(self) -> int:
        """Replay persisted steps into the in-memory deque.

        Called by ``Walker.resume()`` after constructing a fresh walker
        bound to the same ``walker_id`` so the in-memory trail reflects
        the history. Returns the number of steps loaded.
        """
        if self._store is None or self._walker_id is None:
            return 0
        steps = await self._store.load(self._walker_id)
        # Don't go through ``record_step`` — that would re-write each
        # step to the store and double-count.
        self._trail.clear()
        for step in steps:
            self._trail.append(step)
        return len(steps)

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
