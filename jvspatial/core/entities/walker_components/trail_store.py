"""Pluggable persistence for ``WalkerTrail`` steps.

By default a walker's trail lives in an in-memory ``deque`` (the
:class:`InMemoryTrailStore`). That's fine for synchronous local
workloads, but it doesn't survive a Lambda cold start or a process
restart — a long-running agentive walker that resumes after a deferred
invoke would lose its history.

This module adds a ``TrailStore`` protocol with two adapters:

* :class:`InMemoryTrailStore` — the default. Wraps a ``deque``; behaves
  identically to the legacy in-memory trail.
* :class:`DBTrailStore` — persists steps to any registered
  :class:`jvspatial.db.database.Database`. Use this when walker state
  must outlive the current process.

``Walker.resume(walker_id, store=...)`` rehydrates a walker from a
persisted trail so a fresh process can pick up where the prior one
left off.

Closes ROADMAP §2.5.
"""

from __future__ import annotations

from collections import deque
from typing import Any, Deque, Dict, List, Optional, Protocol


class TrailStore(Protocol):
    """Persistence contract for walker trail steps.

    A trail store records steps for a given ``walker_id`` and can replay
    them later. Implementations should be idempotent against duplicate
    ``append`` calls for the same step (the position-based id makes
    deduplication easy: see :class:`DBTrailStore` for the pattern).
    """

    async def append(self, walker_id: str, step: Dict[str, Any]) -> None:
        """Record a single step for ``walker_id``."""
        ...

    async def load(self, walker_id: str, *, since: int = 0) -> List[Dict[str, Any]]:
        """Return all steps for ``walker_id`` (optionally from index ``since``)."""
        ...

    async def clear(self, walker_id: str) -> None:
        """Drop the entire trail for ``walker_id``."""
        ...


class InMemoryTrailStore:
    """In-process trail store backed by a ``deque`` per walker.

    Default implementation; preserves the legacy behavior of
    :class:`~jvspatial.core.entities.walker_components.walker_trail.WalkerTrail`.
    Use this when walker state does not need to outlive the process.

    Args:
        max_length: Maximum steps retained per walker. ``0`` (default)
            means unlimited. Mirrors ``WalkerTrail(max_length=...)``.
    """

    def __init__(self, max_length: int = 0) -> None:
        self._max_length = max(0, int(max_length))
        self._trails: Dict[str, Deque[Dict[str, Any]]] = {}

    def _get_trail(self, walker_id: str) -> Deque[Dict[str, Any]]:
        trail = self._trails.get(walker_id)
        if trail is None:
            bound: Optional[int] = self._max_length if self._max_length > 0 else None
            trail = deque(maxlen=bound)
            self._trails[walker_id] = trail
        return trail

    async def append(self, walker_id: str, step: Dict[str, Any]) -> None:
        """Record ``step`` for ``walker_id``."""
        self._get_trail(walker_id).append(step)

    async def load(self, walker_id: str, *, since: int = 0) -> List[Dict[str, Any]]:
        """Return recorded steps for ``walker_id`` (optionally from ``since``)."""
        trail = self._trails.get(walker_id)
        if not trail:
            return []
        steps = list(trail)
        return steps[since:] if since > 0 else steps

    async def clear(self, walker_id: str) -> None:
        """Drop all recorded steps for ``walker_id``."""
        self._trails.pop(walker_id, None)


class DBTrailStore:
    """Trail store that persists steps to a jvspatial :class:`Database`.

    Each step lands as one record in ``collection`` (default
    ``"walker_trail"``). Records are keyed
    ``trail.<walker_id>.<seq>`` so they sort lexically by step order
    and can be range-loaded efficiently on every supported backend
    (Mongo, SQLite, Postgres, DynamoDB, JsonDB).

    Use this when:

    * The walker must resume across cold starts (Lambda + deferred invoke).
    * Multiple processes share the walker (rare; needs coordination).
    * Audit / debugging requires post-hoc inspection of the path.

    The append path issues one ``save`` per step. For chatty walkers
    consider:

    * Batching: collect steps locally then ``flush()`` to the store.
      (Future enhancement — for v1 we always write through.)
    * A faster backend (Postgres or DynamoDB beats JsonDB by orders of
      magnitude for high-frequency append).

    Args:
        db: Any registered :class:`Database` instance (Mongo / Postgres /
            SQLite / DynamoDB / JsonDB).
        collection: Collection / table name. Default ``"walker_trail"``.
    """

    def __init__(self, db: Any, *, collection: str = "walker_trail") -> None:
        self._db = db
        self._collection = collection
        # Per-walker monotonic counters. Reset whenever ``clear()`` runs.
        # Note: ``DBTrailStore`` is intentionally not safe for two
        # processes appending to the same walker — that case requires a
        # backend-side sequence which is out of scope for v1.
        self._seq: Dict[str, int] = {}

    @staticmethod
    def _record_id(walker_id: str, seq: int) -> str:
        return f"trail.{walker_id}.{seq:09d}"

    async def append(self, walker_id: str, step: Dict[str, Any]) -> None:
        """Persist ``step`` for ``walker_id`` as one row in the backing store."""
        seq = self._seq.get(walker_id, 0)
        rec_id = self._record_id(walker_id, seq)
        record = {
            "id": rec_id,
            "entity": "WalkerTrailStep",
            "walker_id": str(walker_id),
            "seq": seq,
            # Persist the step payload verbatim under ``data`` so the
            # JSONB / nested-doc backends can keep it together.
            "data": step,
        }
        await self._db.save(self._collection, record)
        self._seq[walker_id] = seq + 1

    async def load(self, walker_id: str, *, since: int = 0) -> List[Dict[str, Any]]:
        """Return persisted steps for ``walker_id`` (optionally from ``since``)."""
        # Single round trip via the standard ``find`` API. The query is
        # backend-portable; PG / Mongo can push the sort + filter down,
        # JsonDB / DynamoDB filter in-memory.
        rows = await self._db.find(
            self._collection,
            {"walker_id": str(walker_id), "seq": {"$gte": int(since)}},
            sort=[("seq", 1)],
        )
        # Recover the original step dicts. Refresh the in-process
        # counter so a follow-up ``append`` continues from the right
        # sequence number.
        steps: List[Dict[str, Any]] = []
        last_seq = -1
        for row in rows:
            steps.append(row.get("data") or {})
            seq = row.get("seq")
            if isinstance(seq, int) and seq > last_seq:
                last_seq = seq
        if last_seq >= 0:
            self._seq[walker_id] = last_seq + 1
        return steps

    async def clear(self, walker_id: str) -> None:
        """Delete every persisted step for ``walker_id``."""
        # No bulk-delete in the base Database ABC — fetch and delete one
        # by one. Fine for the cleanup case; if this gets called in a hot
        # loop the backend's native bulk delete should be wired in later.
        rows = await self._db.find(self._collection, {"walker_id": str(walker_id)})
        for row in rows:
            rid = row.get("id")
            if rid:
                await self._db.delete(self._collection, str(rid))
        self._seq.pop(walker_id, None)


__all__ = ["TrailStore", "InMemoryTrailStore", "DBTrailStore"]
