"""Per-path lock manager with bounded LRU eviction.

JsonDB previously held a single process-wide ``threading.Lock`` for all
write operations. That lock is correct (it serializes cross-thread writes
from places like ``DBLogHandler`` that call ``asyncio.run`` in side
threads), but it's coarse: a write to ``node/A.json`` blocks an unrelated
write to ``edge/B.json``.

This module provides a lock manager keyed by string path (or any hashable
key) with the following properties:

* **Cross-thread safe.** Locks are ``threading.Lock`` so they work from
  worker threads, side threads, and signal handlers.
* **Per-key isolation.** Concurrent writes to different paths run in
  parallel.
* **Bounded memory.** A simple LRU policy evicts unused locks once the
  cache fills, so a long-running process churning through millions of
  unique node ids can't grow the lock table unbounded.
* **Eviction-safe.** A lock is never evicted while held; eviction
  candidates are scanned in LRU order and skipped if currently locked.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from contextlib import contextmanager
from typing import Iterator

# Default cap. ~1024 locks * (~100 bytes each) = ~100 KB worst case --
# trivial. Tuned higher than typical concurrent-writer count for any
# realistic workload, low enough to bound the table.
DEFAULT_MAX_LOCKS = 1024


class PathLockManager:
    """Bounded-LRU manager for per-path ``threading.Lock`` instances.

    Usage:
        manager = PathLockManager()
        with manager.lock("node/A.json"):
            ... do the write ...

    Thread-safe.
    """

    def __init__(self, max_locks: int = DEFAULT_MAX_LOCKS) -> None:
        if max_locks < 1:
            raise ValueError("max_locks must be >= 1")
        self._max_locks = max_locks
        # OrderedDict gives us O(1) move-to-end for LRU.
        self._locks: "OrderedDict[str, threading.Lock]" = OrderedDict()
        # Guards mutations of self._locks. Held only briefly.
        self._registry_lock = threading.Lock()

    def _get_or_create_lock(self, key: str) -> threading.Lock:
        """Return the lock for ``key``, creating it if needed.

        Updates LRU order. May evict an idle lock if at capacity.
        """
        with self._registry_lock:
            if key in self._locks:
                self._locks.move_to_end(key)
                return self._locks[key]

            # At capacity? Try to evict the oldest *unheld* lock. If every
            # lock is held (rare, would mean ``max_locks`` distinct paths
            # are simultaneously being written to), we let the table grow
            # by one rather than block -- correctness over strict bound.
            if len(self._locks) >= self._max_locks:
                self._evict_idle_lock()

            new_lock = threading.Lock()
            self._locks[key] = new_lock
            return new_lock

    def _evict_idle_lock(self) -> None:
        """Drop one unheld lock from the LRU end of the table.

        Caller must already hold ``self._registry_lock``.
        """
        for evict_key in list(self._locks.keys()):
            candidate = self._locks[evict_key]
            # ``Lock.acquire(blocking=False)`` returns True only if the
            # lock was free. If we get it, we immediately release and
            # delete the entry (no waiter could grab it because callers
            # always go through ``_get_or_create_lock`` which holds
            # ``_registry_lock`` for the lookup).
            if candidate.acquire(blocking=False):
                try:
                    del self._locks[evict_key]
                finally:
                    candidate.release()
                return
        # All locks held: caller will let the table grow by one.

    @contextmanager
    def lock(self, key: str) -> Iterator[None]:
        """Acquire the lock for ``key`` for the duration of the ``with`` block."""
        threading_lock = self._get_or_create_lock(key)
        threading_lock.acquire()
        try:
            yield
        finally:
            threading_lock.release()

    def __len__(self) -> int:
        """Return the current number of cached locks (for tests + ops)."""
        with self._registry_lock:
            return len(self._locks)


__all__ = ["PathLockManager", "DEFAULT_MAX_LOCKS"]
