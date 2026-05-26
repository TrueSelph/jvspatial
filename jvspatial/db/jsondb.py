r"""Simplified JSON-based database implementation.

Durability semantics
--------------------
``JsonDB`` writes one record per file. Every write goes through
:func:`jvspatial.db._atomic.atomic_write_bytes` which performs
``write tmp -> fsync -> rename -> fsync(dir)``. As a result, a process
crash, kernel panic, or power loss will never leave a partially written
record on disk -- readers always see either the previous fully-formed
record or the new fully-formed record.

Concurrency model
-----------------
Writes are serialized **per record path** by a
:class:`~jvspatial.db._path_locks.PathLockManager`. Concurrent writes to
different files run in parallel; concurrent writes to the *same* file
serialize. The locks are ``threading.Lock`` instances so that side-thread
callers (e.g. ``DBLogHandler``'s serverless path that uses
``asyncio.run`` in a worker thread) work the same as event-loop-thread
callers.

Reads are unlocked: a reader either observes the completed previous
write (atomic rename guarantees this) or the completed new write.
"""

import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from jvspatial.db._atomic import atomic_write_bytes, cleanup_orphan_tmp_files
from jvspatial.db._path_locks import PathLockManager
from jvspatial.db.database import Database, finalize_find_results
from jvspatial.db.query import QueryEngine
from jvspatial.runtime.serverless import is_serverless_mode

logger = logging.getLogger(__name__)

# Optional orjson fast path for serialization. Falls back to stdlib ``json``
# when not installed. orjson is ~10x faster than stdlib json on dump and
# ~37x faster than ``json.dumps(indent=2)`` -- a meaningful dev-loop win for
# the JsonDB backend, which is the only consumer.
try:
    import orjson  # type: ignore[import-untyped]

    _HAS_ORJSON = True

    def _dumps(data: Dict[str, Any]) -> bytes:
        return orjson.dumps(data)

    def _loads(content: bytes) -> Dict[str, Any]:
        return orjson.loads(content)  # type: ignore[no-any-return]

except ImportError:
    _HAS_ORJSON = False

    def _dumps(data: Dict[str, Any]) -> bytes:
        return json.dumps(data).encode("utf-8")

    def _loads(content: bytes) -> Dict[str, Any]:
        return json.loads(content)  # type: ignore[no-any-return]


class JsonDB(Database):
    """Simplified JSON file-based database implementation."""

    # Public capability flags -- callers can branch on these without sniffing
    # for adapter classes.
    supports_transactions: bool = False

    def __init__(self, base_path: str = "jvdb") -> None:
        """Initialize JSON database.

        Args:
            base_path: Base directory for JSON files
        """
        self.base_path = Path(base_path).resolve()
        self._warned_non_tmp_serverless = False
        # Per-path locks: writes to different files run concurrently, writes
        # to the same file serialize. Locks are threading.Lock so they're
        # safe across event loops / side-thread callers (DBLogHandler in
        # serverless mode uses asyncio.run from a worker thread).
        self._path_locks = PathLockManager()
        # Initialization gate -- the orphan-tmp sweep must complete
        # before any write begins. Concurrent writers entering
        # ``_get_collection_dir`` for the first time race on this lock,
        # but only the first one does the sweep; the others see
        # ``_tmp_sweep_done = True`` and proceed immediately.
        self._init_lock = threading.Lock()
        self._tmp_sweep_done = False

    def _maybe_sweep_orphan_tmp_files(self) -> None:
        """Reap leftover ``*.jvtmp`` files from a prior crashed process.

        Idempotent and lazy: runs the first time the base directory is
        actually used. No-op under serverless mode -- cold starts on
        managed runtimes don't share filesystem state with prior
        invocations.

        Concurrency
        -----------
        Guarded by ``self._init_lock`` so concurrent writers can't
        race the sweep against their own in-flight ``.jvtmp`` files.
        Only the first thread through actually does the sweep; the
        rest see ``_tmp_sweep_done = True`` after the lock and exit.
        """
        # Fast path -- no lock required after first init.
        if self._tmp_sweep_done:
            return
        if is_serverless_mode():
            self._tmp_sweep_done = True
            return
        with self._init_lock:
            # Re-check under the lock.
            if self._tmp_sweep_done:
                return
            if not self.base_path.exists():
                self._tmp_sweep_done = True
                return
            try:
                n = cleanup_orphan_tmp_files([self.base_path])
                if n:
                    logger.info(
                        "JsonDB at %s: reaped %d orphan temp file(s) from prior run",
                        self.base_path,
                        n,
                    )
            except Exception as exc:
                # Sweep is best-effort -- never fail startup on it.
                logger.warning("JsonDB tmp sweep failed at %s: %s", self.base_path, exc)
            finally:
                self._tmp_sweep_done = True

    def _get_collection_dir(self, collection: str) -> Path:
        """Get the directory path for a collection."""
        if (
            is_serverless_mode()
            and not self._warned_non_tmp_serverless
            and not str(self.base_path).startswith("/tmp")
        ):
            self._warned_non_tmp_serverless = True
            logger.warning(
                "JsonDB is using '%s' in serverless mode. "
                "Use a /tmp path or a durable external database backend.",
                self.base_path,
            )
        # Create base directory lazily (only when actually used)
        # This prevents 'jvdb' from being created when DatabaseManager is auto-created
        # before Server initializes with the correct database path
        self.base_path.mkdir(parents=True, exist_ok=True)
        # First-touch orphan sweep (cheap, idempotent, serverless-skipped).
        self._maybe_sweep_orphan_tmp_files()
        collection_dir = self.base_path / collection
        collection_dir.mkdir(parents=True, exist_ok=True)
        return collection_dir

    def _get_record_path(self, collection: str, record_id: str) -> Path:
        """Get the file path for a specific record.

        IDs use dot separators (format: "type.ClassName.id") which are
        filesystem-compatible on all platforms including Windows.
        """
        collection_dir = self._get_collection_dir(collection)
        return collection_dir / f"{record_id}.json"

    @staticmethod
    def _list_collection_json_files(collection_dir: Path) -> List[Path]:
        """Enumerate persisted ``*.json`` records.

        Called from inside ``asyncio.to_thread`` by ``count`` and ``find``
        so the directory scan does not block the event loop.

        Note: in-flight ``*.jvtmp`` files are named
        ``<id>.json.<pid>.<hex>.jvtmp`` (see ``_atomic._make_temp_path``)
        so the ``*.json`` glob already excludes them — the historical
        ``not endswith('.jvtmp')`` filter was dead (audit §5.16).
        """
        return list(collection_dir.glob("*.json"))

    async def _async_write_json(self, path: Path, data: Dict[str, Any]) -> None:
        """Write JSON data to file asynchronously.

        Uses :func:`atomic_write_bytes` so writes are crash-safe.
        Caller is responsible for serializing concurrent writes to the
        same path (use ``self._path_locks``).
        """
        await asyncio.to_thread(atomic_write_bytes, path, _dumps(data))

    async def _async_read_json(self, path: Path) -> Optional[Dict[str, Any]]:
        """Read JSON data from file asynchronously.

        Returns None if file doesn't exist or is invalid.
        """
        # ``Path.exists`` performs a stat() syscall — blocking I/O inside
        # an async function (audit §3.6 / SPEC §3.3). Offload to the
        # default executor instead.
        if not await asyncio.to_thread(path.exists):
            return None

        def _sync_read(path: Path) -> Optional[Dict[str, Any]]:
            try:
                with open(path, "rb") as f:
                    return _loads(f.read())
            except (ValueError, OSError):
                # ``ValueError`` covers both json.JSONDecodeError and
                # orjson.JSONDecodeError (orjson subclasses ValueError).
                return None

        try:
            return await asyncio.to_thread(_sync_read, path)
        except (ValueError, OSError):
            return None

    async def _async_load_record(self, json_file: Path) -> Optional[Dict[str, Any]]:
        """Load a single record from a JSON file asynchronously.

        Returns None if the file is invalid or cannot be read.
        """
        try:
            return await self._async_read_json(json_file)
        except Exception:
            return None

    def _sync_write_record(self, collection: str, data: Dict[str, Any]) -> None:
        """Write one record atomically with per-path locking.

        Cross-thread safe: callable from any OS thread (including
        side-thread ``asyncio.run`` callers in the serverless logging
        path).
        """
        record_path = self._get_record_path(collection, data["id"])
        payload = _dumps(data)
        with self._path_locks.lock(str(record_path)):
            atomic_write_bytes(record_path, payload)

    def _sync_delete_record(self, collection: str, record_id: str) -> None:
        """Delete one record under per-path lock (cross-thread safe)."""
        record_path = self._get_record_path(collection, record_id)
        with self._path_locks.lock(str(record_path)):
            if record_path.exists():
                record_path.unlink()

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database.

        Note: Entities should always have IDs set by their __init__ methods.
        This method expects the ID to already be present in the data.
        """
        await asyncio.to_thread(self._sync_write_record, collection, dict(data))
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""
        record_path = self._get_record_path(collection, id)
        return await self._async_read_json(record_path)

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""
        await asyncio.to_thread(self._sync_delete_record, collection, id)

    async def count(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count records matching ``query``.

        * Empty query: counts files in the collection directory without
          opening any of them. ``O(N)`` directory entries, no JSON parse.
        * Filtered query: streams the records through ``QueryEngine`` and
          returns the count without materializing a result list.
        """
        q = query or {}
        collection_dir = self._get_collection_dir(collection)
        # Sync ``exists``/``glob`` block the event loop — offload both
        # (audit §3.6 / SPEC §3.3).
        if not await asyncio.to_thread(collection_dir.exists):
            return 0

        json_files = await asyncio.to_thread(
            self._list_collection_json_files, collection_dir
        )

        if not q:
            return len(json_files)

        # Filtered count: parse + match, but don't accumulate records.
        tasks = [self._async_load_record(p) for p in json_files]
        records = await asyncio.gather(*tasks, return_exceptions=True)
        n = 0
        for record in records:
            if isinstance(record, Exception) or record is None:
                continue
            if isinstance(record, dict) and QueryEngine.match(record, q):
                n += 1
        return n

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Bulk-fetch via parallel per-file reads.

        N round trips at the OS level (one open() per id), but they
        run in parallel via ``asyncio.gather``, so wall-clock time is
        bounded by ``max(io_latency)`` rather than ``sum(io_latency)``.
        """
        if not ids:
            return {}
        unique_ids = list(dict.fromkeys(ids))
        # Build (id, path) pairs first so we can short-circuit when
        # the collection dir doesn't exist.
        collection_dir = self._get_collection_dir(collection)
        # Sync stat blocks the event loop (audit §3.6 / SPEC §3.3).
        if not await asyncio.to_thread(collection_dir.exists):
            return {}
        paths = [
            (rec_id, self._get_record_path(collection, rec_id)) for rec_id in unique_ids
        ]
        records = await asyncio.gather(
            *[self._async_load_record(p) for _, p in paths],
            return_exceptions=True,
        )
        out: Dict[str, Dict[str, Any]] = {}
        for (rec_id, _path), record in zip(paths, records):
            if isinstance(record, Exception) or record is None:
                continue
            if isinstance(record, dict):
                out[rec_id] = record
        return out

    async def bulk_save(self, collection: str, records: List[Dict[str, Any]]) -> int:
        """Atomic per-file writes in parallel.

        Each file write is independently atomic (temp + fsync + rename).
        The set as a whole is **not** atomic -- a process crash mid-bulk
        can leave a partial set on disk, but each individual record is
        either fully written or not present at all.
        """
        if not records:
            return 0
        for r in records:
            if "id" not in r:
                raise ValueError(
                    "bulk_save requires every record to have an 'id' field"
                )
        # Run writes via the existing single-record sync helper (which
        # already takes the per-path lock and uses atomic_write_bytes).
        # ``asyncio.to_thread`` parallelizes them across the loop's
        # default executor.
        results = await asyncio.gather(
            *[
                asyncio.to_thread(self._sync_write_record, collection, dict(r))
                for r in records
            ],
            return_exceptions=True,
        )
        saved = 0
        for r, result in zip(records, results):
            if isinstance(result, Exception):
                logger.warning(
                    "JsonDB bulk_save failed for id=%s: %s",
                    r.get("id"),
                    result,
                )
                continue
            saved += 1
        return saved

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Find records matching a query.

        Uses parallel file reads for improved performance under concurrent load.
        """
        collection_dir = self._get_collection_dir(collection)

        # Sync ``exists``/``glob`` block the event loop — offload both
        # (audit §3.6 / SPEC §3.3).
        if not await asyncio.to_thread(collection_dir.exists):
            return []

        # Get all JSON files in the collection directory.
        # Skip ``*.jvtmp`` files left behind by an in-flight write -- they
        # are not yet part of the published dataset.
        json_files = await asyncio.to_thread(
            self._list_collection_json_files, collection_dir
        )

        if not json_files:
            return []

        # Parallel file reads using asyncio.gather
        tasks = [self._async_load_record(json_file) for json_file in json_files]
        records = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter results and handle exceptions
        results: List[Dict[str, Any]] = []
        for record in records:
            if isinstance(record, Exception):
                # Log but continue processing other files
                logger.debug(f"Error loading record: {record}")
                continue
            if record is None:
                continue
            # Type check: record should be Dict[str, Any] at this point
            # Check if record matches query using QueryEngine for proper operator support
            if isinstance(record, dict) and (
                not query or QueryEngine.match(record, query)
            ):
                results.append(record)

        return finalize_find_results(results, sort=sort, limit=limit)

    def _get_nested_value(self, data: Dict[str, Any], key: str) -> Any:
        """Get a nested value using dot notation."""
        keys = key.split(".")
        current = data

        for k in keys:
            if isinstance(current, dict) and k in current:
                current = current[k]
            else:
                return None

        return current

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        **kwargs: Any,
    ) -> None:
        """Create an index on the specified field(s).

        Note:
            JSON file-based storage does not support native indexing.
            This is a no-op implementation that maintains API consistency.
            All queries will perform full scans regardless of index declarations.

        Args:
            collection: Collection name
            field_or_fields: Single field name (str) or list of (field_name, direction) tuples
            unique: Whether the index should enforce uniqueness (ignored)
            **kwargs: Additional options (ignored)
        """
        logger.debug(
            f"Index creation requested for JSON database (collection='{collection}', "
            f"field(s)='{field_or_fields}', unique={unique}). "
            f"JSON file storage does not support native indexing - this is a no-op."
        )
