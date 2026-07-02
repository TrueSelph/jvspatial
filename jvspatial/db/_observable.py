"""Observability wrapper for :class:`Database` instances.

Wraps any backend (raw or already wrapped in :class:`CachingDatabase`)
and emits, for each operation:

1. A structured log line with the standard fields
   ``backend`` / ``op`` / ``collection`` / ``duration_ms`` / ``result_count``
   / ``success``. INFO level under the threshold; WARNING when the
   call exceeds ``slow_query_ms``.
2. One metrics emission to the configured :class:`MetricsRecorder`:
   a duration histogram and a counter, both labeled with the standard
   dimensions.

The wrapper is itself a :class:`Database`, so the outer call path
doesn't need to know whether observation is enabled.

Why this lives next to ``_cache.py``
------------------------------------
``_observable.py`` and ``_cache.py`` are sibling decorators of the
:class:`Database` interface. They compose naturally: the factory
applies caching first (closer to the backend) and observation
second (closer to the caller). That ordering means the structured
log line measures the *user-visible* latency, including cache hits
and misses, which is what SLO calculations care about.

Failures
--------
Metrics emission errors are swallowed (best-effort observability
must never break the request path). Logging errors propagate -- if
the application's logging subsystem is broken, a request crashing on
the log call is more honest than silently dropping the work.
"""

from __future__ import annotations

import logging
import time
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

from jvspatial.db.database import Database
from jvspatial.observability import db_op_counter
from jvspatial.observability.metrics import (
    MetricsRecorder,
    NullMetricsRecorder,
)

logger = logging.getLogger("jvspatial.db.observable")


# Default slow-query threshold. Anything above 100 ms gets surfaced as
# a WARNING so it shows up in normal log feeds without operator
# configuration. Tunable per-instance via ``slow_query_ms``.
DEFAULT_SLOW_QUERY_MS = 100.0


def _backend_label(inner: Database) -> str:
    """Return a stable, human-readable backend identifier."""
    # We unwrap one layer (e.g. CachingDatabase wrapping JsonDB) so
    # the metric label reflects the backing store, not the wrapper
    # chain.
    candidate: Any = inner
    seen: int = 0
    while seen < 4 and hasattr(candidate, "inner"):
        candidate = candidate.inner
        seen += 1
    return type(candidate).__name__


class ObservableDatabase(Database):
    """Wraps a :class:`Database` with structured logging + metrics.

    Args:
        inner: The wrapped database. May itself be wrapped (e.g. by
            :class:`~jvspatial.db._cache.CachingDatabase`).
        metrics: A :class:`MetricsRecorder`. Defaults to
            :class:`NullMetricsRecorder` (zero overhead).
        slow_query_ms: Threshold above which the per-op log line is
            elevated from INFO to WARNING. Defaults to 100ms.
    """

    def __init__(
        self,
        inner: Database,
        *,
        metrics: Optional[MetricsRecorder] = None,
        slow_query_ms: float = DEFAULT_SLOW_QUERY_MS,
    ) -> None:
        if slow_query_ms < 0:
            raise ValueError("slow_query_ms must be >= 0")
        self.inner = inner
        self.metrics: MetricsRecorder = metrics or NullMetricsRecorder()
        self.slow_query_ms = float(slow_query_ms)
        self._backend = _backend_label(inner)
        # Mirror capability flag.
        self.supports_transactions = getattr(inner, "supports_transactions", False)

    # -------------------------- core helpers ---------------------------

    async def _instrument(
        self,
        op: str,
        collection: str,
        coro_factory: Callable[[], Awaitable[Any]],
        *,
        result_count_extractor: Optional[Callable[[Any], int]] = None,
    ) -> Any:
        """Run ``coro_factory()`` while emitting a log line and metric.

        ``coro_factory`` is a thunk so we measure the underlying call
        only, not the time spent constructing the coroutine.
        """
        start = time.monotonic()
        success = True
        result: Any = None
        try:
            result = await coro_factory()
            return result
        except BaseException:
            success = False
            raise
        finally:
            # Increment per-flow DB operation count even on failures.
            db_op_counter.set(db_op_counter.get() + 1)
            duration_s = time.monotonic() - start
            duration_ms = duration_s * 1000.0
            result_count: Optional[int] = None
            if success and result_count_extractor is not None:
                try:
                    result_count = result_count_extractor(result)
                except Exception:
                    result_count = None
            self._emit(
                op=op,
                collection=collection,
                duration_ms=duration_ms,
                duration_s=duration_s,
                success=success,
                result_count=result_count,
            )

    def _emit(
        self,
        *,
        op: str,
        collection: str,
        duration_ms: float,
        duration_s: float,
        success: bool,
        result_count: Optional[int],
    ) -> None:
        # Build the structured payload once; reuse for log + metrics.
        labels: Dict[str, Any] = {
            "backend": self._backend,
            "op": op,
            "collection": collection,
            "success": success,
        }
        log_extra = {**labels, "duration_ms": round(duration_ms, 3)}
        if result_count is not None:
            log_extra["result_count"] = result_count

        # Structured log. WARNING when slow, INFO otherwise. extra=
        # supplies the structured fields to any handler that
        # understands them (json formatters, structlog, etc.).
        slow = duration_ms >= self.slow_query_ms
        msg = "db.%s on '%s' took %.2fms" % (op, collection, duration_ms)
        if slow:
            logger.warning("SLOW %s", msg, extra=log_extra)
        else:
            logger.info(msg, extra=log_extra)

        # Metrics. Best-effort -- do not surface backend errors here.
        try:
            self.metrics.record_duration(
                "jvspatial.db.op.duration_seconds",
                duration_s,
                **labels,
            )
            self.metrics.increment_counter(
                "jvspatial.db.op.count",
                **labels,
            )
            if result_count is not None:
                self.metrics.record_value(
                    "jvspatial.db.op.result_count",
                    float(result_count),
                    **labels,
                )
            if slow:
                self.metrics.increment_counter(
                    "jvspatial.db.op.slow_count",
                    **labels,
                )
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Metrics emission failed (suppressed): %s", exc)

    # ------------------------- Database protocol -----------------------

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Instrumented ``save`` (emits structured log + metric)."""
        return await self._instrument(
            "save", collection, lambda: self.inner.save(collection, data)
        )

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Instrumented ``get`` (emits structured log + metric)."""
        return await self._instrument(
            "get",
            collection,
            lambda: self.inner.get(collection, id),
            result_count_extractor=lambda r: 0 if r is None else 1,
        )

    async def delete(self, collection: str, id: str) -> None:
        """Instrumented ``delete`` (emits structured log + metric)."""
        await self._instrument(
            "delete",
            collection,
            lambda: self.inner.delete(collection, id),
        )

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Instrumented ``find`` (emits structured log + metric)."""
        return await self._instrument(
            "find",
            collection,
            lambda: self.inner.find(collection, query, limit=limit, sort=sort),
            result_count_extractor=lambda r: len(r) if isinstance(r, list) else 0,
        )

    async def count(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Instrumented ``count`` (emits structured log + metric)."""
        return await self._instrument(
            "count",
            collection,
            lambda: self.inner.count(collection, query),
            result_count_extractor=lambda r: int(r) if r is not None else 0,
        )

    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Instrumented ``find_one`` (emits structured log + metric)."""
        return await self._instrument(
            "find_one",
            collection,
            lambda: self.inner.find_one(collection, query),
            result_count_extractor=lambda r: 0 if r is None else 1,
        )

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Instrumented ``find_many`` (emits structured log + metric)."""
        return await self._instrument(
            "find_many",
            collection,
            lambda: self.inner.find_many(collection, ids),
            result_count_extractor=lambda r: len(r) if isinstance(r, dict) else 0,
        )

    async def bulk_save(self, collection: str, records: List[Dict[str, Any]]) -> int:
        """Instrumented ``bulk_save`` (emits structured log + metric)."""
        return await self._instrument(
            "bulk_save",
            collection,
            lambda: self.inner.bulk_save(collection, records),
            result_count_extractor=lambda r: int(r) if r is not None else 0,
        )

    async def find_one_and_delete(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Instrumented ``find_one_and_delete`` (emits structured log + metric)."""
        return await self._instrument(
            "find_one_and_delete",
            collection,
            lambda: self.inner.find_one_and_delete(collection, query),
            result_count_extractor=lambda r: 0 if r is None else 1,
        )

    async def find_one_and_update(
        self,
        collection: str,
        query: Dict[str, Any],
        update: Dict[str, Any],
        upsert: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Instrumented ``find_one_and_update`` (emits structured log + metric)."""
        return await self._instrument(
            "find_one_and_update",
            collection,
            lambda: self.inner.find_one_and_update(
                collection, query, update, upsert=upsert
            ),
            result_count_extractor=lambda r: 0 if r is None else 1,
        )

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        **kwargs: Any,
    ) -> None:
        """Pass through index creation (intentionally not instrumented)."""
        # Index creation is rare enough that we don't bother
        # instrumenting it -- it would just add noise.
        await self.inner.create_index(
            collection, field_or_fields, unique=unique, **kwargs
        )

    async def drop_deprecated_indexes(self, deprecated: Dict[str, List[str]]) -> None:
        """Pass through deprecated-index cleanup to the wrapped backend."""
        await self.inner.drop_deprecated_indexes(deprecated)

    async def find_connected_nodes(
        self,
        node_collection: str,
        edge_collection: str,
        node_id: str,
        *,
        direction: str = "out",
        edge_entity: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Instrumented single-hop neighbor join when the backend supports it."""
        inner = getattr(self.inner, "find_connected_nodes", None)
        if not callable(inner):
            raise AttributeError("find_connected_nodes")
        return await self._instrument(
            "find_connected_nodes",
            node_collection,
            lambda: inner(
                node_collection,
                edge_collection,
                node_id,
                direction=direction,
                edge_entity=edge_entity,
                limit=limit,
            ),
            result_count_extractor=lambda r: len(r) if isinstance(r, list) else 0,
        )

    async def traverse(
        self,
        edge_collection: str,
        start_id: str,
        *,
        direction: str = "out",
        max_depth: int = 1,
        edge_filter: Optional[Dict[str, Any]] = None,
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Instrumented multi-hop graph walk when the backend supports it."""
        inner = getattr(self.inner, "traverse", None)
        if not callable(inner):
            raise AttributeError("traverse")
        return await self._instrument(
            "traverse",
            edge_collection,
            lambda: inner(
                edge_collection,
                start_id,
                direction=direction,
                max_depth=max_depth,
                edge_filter=edge_filter,
                limit=limit,
            ),
            result_count_extractor=lambda r: len(r) if isinstance(r, list) else 0,
        )

    async def find_iter(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        sort: Optional[List[Tuple[str, int]]] = None,
        batch_size: int = 100,
        cursor: Optional[bytes] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Instrumented streaming find when the backend supports it."""
        inner = getattr(self.inner, "find_iter", None)
        if not callable(inner):
            raise AttributeError("find_iter")

        start = time.monotonic()
        success = True
        result_count = 0
        try:
            async for row in inner(
                collection,
                query,
                sort=sort,
                batch_size=batch_size,
                cursor=cursor,
            ):
                result_count += 1
                yield row
        except BaseException:
            success = False
            raise
        finally:
            db_op_counter.set(db_op_counter.get() + 1)
            duration_s = time.monotonic() - start
            self._emit(
                op="find_iter",
                collection=collection,
                duration_ms=duration_s * 1000.0,
                duration_s=duration_s,
                success=success,
                result_count=result_count,
            )

    def __getattr__(self, name: str) -> Any:
        """Forward unknown attribute access to the wrapped database."""
        return getattr(self.inner, name)


__all__ = ["ObservableDatabase", "DEFAULT_SLOW_QUERY_MS"]
