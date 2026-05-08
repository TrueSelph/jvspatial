"""Read-through cache wrapper for :class:`Database` instances.

Wraps any backend with an LRU + TTL cache for ``get()`` calls. Writes
(``save``, ``delete``, ``find_one_and_update``, ``find_one_and_delete``)
invalidate the cached entry. ``find()`` is **not** cached: results
depend on the full collection state and a stale list is much harder to
recover from than a stale single-record read.

Why opt-in
----------
This is off by default. A cache that's wrong is worse than no cache,
and the safe-default policy is "read the source of truth every time"
unless an adopter opts in. Opt-in surfaces:

* ``create_database(..., cache_get_size=N, cache_get_ttl=S)``
* ``CachingDatabase(inner, max_entries=N, ttl_seconds=S)``

Serverless behavior
-------------------
Caches are skipped under :func:`is_serverless_mode` -- cold starts make
a process-local cache useless, and the operational footgun (stale
data after a deploy) outweighs the marginal latency win. Adopters
running on Lambda who really want caching should reach for an
external cache like Redis (see :mod:`jvspatial.cache`).

Concurrency
-----------
The cache is guarded by a :class:`threading.Lock`. The lock is held
only for the dict mutation -- never across an ``await`` -- so it does
not serialize the underlying database calls.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import OrderedDict
from typing import Any, Dict, List, Optional, Tuple, Union

from jvspatial.db.database import Database
from jvspatial.runtime.serverless import is_serverless_mode

logger = logging.getLogger(__name__)


# (collection, id) -> (deadline_epoch_seconds, payload_or_None)
# Storing ``None`` as payload represents a negative cache (a confirmed
# absence). Negative caching is bounded by the same TTL so a record
# created right after a miss becomes visible at most ``ttl`` later.
_CacheEntry = Tuple[float, Optional[Dict[str, Any]]]


class CachingDatabase(Database):
    """Wraps a :class:`Database` with a read-through LRU+TTL cache.

    The wrapper is itself a :class:`Database` so call sites that hold a
    ``Database`` reference don't need to know whether caching is
    enabled.

    Args:
        inner: The underlying database to wrap.
        max_entries: LRU cap. Default 1024. Set to 0 to disable.
        ttl_seconds: Maximum age of a cached entry before it's
            re-fetched. Default 60. Set to 0 for no TTL (LRU only).

    Attributes:
        inner: The wrapped database. Adopters can reach through to the
            backend if they need adapter-specific methods.
        supports_transactions: Mirrors the wrapped database's flag.
    """

    def __init__(
        self,
        inner: Database,
        *,
        max_entries: int = 1024,
        ttl_seconds: float = 60.0,
    ) -> None:
        if max_entries < 0:
            raise ValueError("max_entries must be >= 0")
        if ttl_seconds < 0:
            raise ValueError("ttl_seconds must be >= 0")
        self.inner = inner
        self._max_entries = max_entries
        self._ttl = ttl_seconds
        self._cache: "OrderedDict[Tuple[str, str], _CacheEntry]" = OrderedDict()
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "evictions": 0, "invalidations": 0}
        # Inherit the wrapped backend's transaction capability flag so
        # callers see the right answer.
        self.supports_transactions = getattr(inner, "supports_transactions", False)

    # ----- helpers ----------------------------------------------------

    def _enabled(self) -> bool:
        if self._max_entries == 0:
            return False
        if is_serverless_mode():
            return False
        return True

    def _cache_get(self, collection: str, rec_id: str) -> Optional[_CacheEntry]:
        key = (collection, rec_id)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None
            deadline, _payload = entry
            if self._ttl > 0 and time.monotonic() > deadline:
                # Expired -- drop and report miss.
                self._cache.pop(key, None)
                return None
            # LRU promotion.
            self._cache.move_to_end(key)
            return entry

    def _cache_put(
        self, collection: str, rec_id: str, payload: Optional[Dict[str, Any]]
    ) -> None:
        key = (collection, rec_id)
        deadline = time.monotonic() + self._ttl if self._ttl > 0 else float("inf")
        with self._lock:
            self._cache[key] = (deadline, payload)
            self._cache.move_to_end(key)
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)
                self._stats["evictions"] += 1

    def _invalidate(self, collection: str, rec_id: str) -> None:
        key = (collection, rec_id)
        with self._lock:
            if self._cache.pop(key, None) is not None:
                self._stats["invalidations"] += 1

    # ----- introspection ---------------------------------------------

    def cache_stats(self) -> Dict[str, int]:
        """Snapshot of the cache counters. Useful for tests + ops."""
        with self._lock:
            return dict(self._stats, size=len(self._cache))

    def clear_cache(self) -> None:
        """Drop all cached entries. Doesn't touch the underlying database."""
        with self._lock:
            self._cache.clear()

    # ----- Database protocol -----------------------------------------

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist via the wrapped backend and refresh the cached copy."""
        result = await self.inner.save(collection, data)
        rec_id = result.get("id", result.get("_id"))
        if rec_id is not None and self._enabled():
            # Refresh the cached copy with the just-saved value rather
            # than just invalidating -- a save is the strongest possible
            # confirmation of the current state.
            self._cache_put(collection, str(rec_id), dict(result))
        return result

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Read with cache: hit on the in-memory map, else fetch + cache."""
        if not self._enabled():
            return await self.inner.get(collection, id)
        entry = self._cache_get(collection, id)
        if entry is not None:
            with self._lock:
                self._stats["hits"] += 1
            _deadline, payload = entry
            return None if payload is None else dict(payload)
        with self._lock:
            self._stats["misses"] += 1
        result = await self.inner.get(collection, id)
        # Cache both hits and misses (negative caching) so a tight
        # loop calling get() for a missing id doesn't slam the
        # backend.
        self._cache_put(collection, id, dict(result) if result is not None else None)
        return result

    async def delete(self, collection: str, id: str) -> None:
        """Delete via the wrapped backend and invalidate any cached copy."""
        await self.inner.delete(collection, id)
        if self._enabled():
            self._invalidate(collection, id)

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Pass through; ``find`` results are intentionally never cached."""
        # find() is intentionally NOT cached. See module docstring.
        return await self.inner.find(collection, query, limit=limit, sort=sort)

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Cache-aware bulk fetch.

        Splits the request into a cached portion (served from the
        in-memory map) and an uncached portion (forwarded to the
        backend's native ``find_many``). Backend responses are
        promoted into the cache so the next call sees them as hits.
        Negative-cached entries (``None``) are honored.
        """
        if not self._enabled():
            return await self.inner.find_many(collection, ids)
        if not ids:
            return {}
        unique_ids = list(dict.fromkeys(ids))

        cached_hits: Dict[str, Dict[str, Any]] = {}
        misses: List[str] = []
        for rid in unique_ids:
            entry = self._cache_get(collection, rid)
            if entry is None:
                misses.append(rid)
                continue
            with self._lock:
                self._stats["hits"] += 1
            _deadline, payload = entry
            if payload is not None:
                cached_hits[rid] = dict(payload)

        with self._lock:
            self._stats["misses"] += len(misses)

        fetched: Dict[str, Dict[str, Any]] = {}
        if misses:
            fetched = await self.inner.find_many(collection, misses)
            # Promote both hits and misses (negative cache) for the
            # set of ids we just looked up.
            for rid in misses:
                self._cache_put(
                    collection,
                    rid,
                    dict(fetched[rid]) if rid in fetched else None,
                )
        out = dict(cached_hits)
        out.update(fetched)
        return out

    async def bulk_save(self, collection: str, records: List[Dict[str, Any]]) -> int:
        """Pass through to the backend, then refresh cached entries."""
        result = await self.inner.bulk_save(collection, records)
        if self._enabled():
            for r in records:
                rid = r.get("id", r.get("_id"))
                if rid is not None:
                    self._cache_put(collection, str(rid), dict(r))
        return result

    async def count(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Pass through to the backend; counts are not cached."""
        return await self.inner.count(collection, query)

    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Pass through to the backend; find_one results are not cached."""
        return await self.inner.find_one(collection, query)

    async def find_one_and_delete(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Atomically find-and-delete on the backend, invalidate the cache."""
        result = await self.inner.find_one_and_delete(collection, query)
        if result is not None and self._enabled():
            rec_id = result.get("id", result.get("_id"))
            if rec_id is not None:
                self._invalidate(collection, str(rec_id))
        return result

    async def find_one_and_update(
        self,
        collection: str,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Atomically find-and-update on the backend, refresh the cache."""
        result = await self.inner.find_one_and_update(
            collection, query, update, upsert=upsert
        )
        if result is not None and self._enabled():
            rec_id = result.get("id", result.get("_id"))
            if rec_id is not None:
                # Refresh the cached copy with the post-update payload.
                self._cache_put(collection, str(rec_id), dict(result))
        return result

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        **kwargs: Any,
    ) -> None:
        """Pass through index creation to the wrapped backend."""
        await self.inner.create_index(
            collection, field_or_fields, unique=unique, **kwargs
        )

    async def drop_deprecated_indexes(self, deprecated: Dict[str, List[str]]) -> None:
        """Pass through deprecated-index cleanup to the wrapped backend."""
        await self.inner.drop_deprecated_indexes(deprecated)

    # Pass through optional adapter methods (transactions, close, etc.)
    # via __getattr__ so callers reaching for adapter-specific surface
    # still work.

    def __getattr__(self, name: str) -> Any:
        """Forward unknown attribute access to the wrapped database."""
        # Only consulted for attributes we didn't define ourselves.
        return getattr(self.inner, name)


__all__ = ["CachingDatabase"]
