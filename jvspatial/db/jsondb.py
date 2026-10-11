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
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple, Union

from jvspatial.db._atomic import atomic_write_bytes, cleanup_orphan_tmp_files
from jvspatial.db._path_locks import PathLockManager
from jvspatial.db.database import (
    BulkSaveResult,
    Database,
    InsertIfAbsentResult,
    _keyset_condition,
    _keyset_sort_fields,
    decode_cursor,
    finalize_find_results,
)
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
        return orjson.dumps(data, option=orjson.OPT_INDENT_2)

    def _loads(content: bytes) -> Dict[str, Any]:
        return orjson.loads(content)  # type: ignore[no-any-return]

except ImportError:
    _HAS_ORJSON = False

    def _dumps(data: Dict[str, Any]) -> bytes:
        return json.dumps(data, indent=2).encode("utf-8")

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
        self._validate_path_component(collection, "collection")
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
        if not collection_dir.resolve().is_relative_to(self.base_path):
            raise ValueError("Collection path escapes database root")
        collection_dir.mkdir(parents=True, exist_ok=True)
        return collection_dir

    @staticmethod
    def _validate_path_component(value: str, label: str) -> None:
        if (
            not isinstance(value, str)
            or value in ("", ".", "..")
            or "/" in value
            or "\\" in value
            or "\x00" in value
            or Path(value).is_absolute()
        ):
            raise ValueError(f"Invalid {label}")

    def _get_record_path(self, collection: str, record_id: str) -> Path:
        """Get the file path for a specific record.

        IDs use dot separators (format: "type.ClassName.id") which are
        filesystem-compatible on all platforms including Windows.
        """
        self._validate_path_component(record_id, "record id")
        collection_dir = self._get_collection_dir(collection)
        record_path = collection_dir / f"{record_id}.json"
        if not record_path.resolve().is_relative_to(self.base_path):
            raise ValueError("Record path escapes database root")
        return record_path

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

    async def insert_if_absent(
        self,
        collection: str,
        data: Dict[str, Any],
        *,
        conflict_target: str = "id",
    ) -> InsertIfAbsentResult:
        """Insert under path lock only when the record file is absent."""
        record_id = self._validate_insert_if_absent(data, conflict_target)
        payload = dict(data)
        payload["id"] = record_id

        def _sync_insert_if_absent() -> InsertIfAbsentResult:
            record_path = self._get_record_path(collection, record_id)
            with self._path_locks.lock(str(record_path)):
                if record_path.exists():
                    try:
                        with open(record_path, "rb") as f:
                            existing = _loads(f.read())
                    except (ValueError, OSError):
                        existing = None
                    if existing is None:
                        from jvspatial.db.database import DatabaseError

                        raise DatabaseError(
                            "insert_if_absent found an unreadable existing "
                            f"file for id={record_id!r}"
                        )
                    return InsertIfAbsentResult(record=existing, created=False)
                atomic_write_bytes(record_path, _dumps(payload))
                return InsertIfAbsentResult(record=payload, created=True)

        return await asyncio.to_thread(_sync_insert_if_absent)

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""
        record_path = await asyncio.to_thread(self._get_record_path, collection, id)
        return await self._async_read_json(record_path)

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""
        await asyncio.to_thread(self._sync_delete_record, collection, id)

    async def _scan_records(
        self, collection: str, *, reverse: bool = False, batch_size: int = 32
    ) -> AsyncIterator[Dict[str, Any]]:
        """List paths once and decode at most 32 records concurrently.

        Path metadata is O(N); decoded record memory is bounded. The file
        list is a read-at-start enumeration, not a transactional snapshot.
        """
        directory = await asyncio.to_thread(self._get_collection_dir, collection)
        paths = await asyncio.to_thread(self._list_collection_json_files, directory)
        paths.sort(key=lambda p: p.stem, reverse=reverse)
        width = min(32, batch_size)
        for offset in range(0, len(paths), width):
            records = await asyncio.gather(
                *(self._async_load_record(p) for p in paths[offset : offset + width]),
                return_exceptions=True,
            )
            for record in records:
                if isinstance(record, dict):
                    yield record

    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count dirents for an empty query; stream matches otherwise."""
        if not query:
            directory = await asyncio.to_thread(self._get_collection_dir, collection)
            paths = await asyncio.to_thread(self._list_collection_json_files, directory)
            return len(paths)
        count = 0
        async for record in self._scan_records(collection):
            if QueryEngine.match(record, query):
                count += 1
        return count

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Fetch only requested IDs with bounded parallel I/O."""
        unique_ids = list(dict.fromkeys(ids))
        out: Dict[str, Dict[str, Any]] = {}
        for offset in range(0, len(unique_ids), 32):
            chunk = unique_ids[offset : offset + 32]
            records = await asyncio.gather(
                *(self.get(collection, rid) for rid in chunk)
            )
            out.update({rid: r for rid, r in zip(chunk, records) if r is not None})
        return out

    async def bulk_save(self, collection: str, records: List[Dict[str, Any]]) -> int:
        """Return the number of durable per-file saves, preserving partial results."""
        return (await self.bulk_save_detailed(collection, records)).saved

    async def bulk_save_detailed(
        self, collection: str, records: List[Dict[str, Any]]
    ) -> BulkSaveResult:
        """Bounded per-file atomic writes with ordered duplicate-ID handling."""
        groups: Dict[str, List[Dict[str, Any]]] = {}
        for index, record in enumerate(records):
            if "id" not in record:
                raise ValueError(
                    f"bulk_save: record at index {index} has no 'id' field"
                )
            groups.setdefault(str(record["id"]), []).append(record)

        async def save_group(group: List[Dict[str, Any]]) -> Tuple[int, List[str]]:
            saved = 0
            failed = []
            for record in group:
                try:
                    await asyncio.to_thread(
                        self._sync_write_record, collection, dict(record)
                    )
                    saved += 1
                except Exception as exc:
                    failed.append(str(record["id"]))
                    logger.warning(
                        "JsonDB bulk_save failed for id=%s: %s", record["id"], exc
                    )
            return saved, failed

        saved = 0
        failed_ids: List[str] = []
        batches = list(groups.values())
        for offset in range(0, len(batches), 32):
            outcomes = await asyncio.gather(
                *(save_group(g) for g in batches[offset : offset + 32])
            )
            for count, failed in outcomes:
                saved += count
                failed_ids.extend(failed)
        return BulkSaveResult(len(records), saved, failed_ids)

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Stream matches and stop early when no global ordering is required."""
        if limit == 0:
            return []
        if limit == 0:
            return []
        results = []
        async for record in self._scan_records(collection):
            if not query or QueryEngine.match(record, query):
                results.append(record)
                if (
                    not sort
                    and limit is not None
                    and limit > 0
                    and len(results) >= limit
                ):
                    break
        return finalize_find_results(results, sort=sort, limit=limit)

    async def find_iter(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        sort: Optional[List[Tuple[str, int]]] = None,
        batch_size: int = 100,
        cursor: Optional[bytes] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Scan once; ID ordering buffers paths, custom ordering buffers matches."""
        if (
            isinstance(batch_size, bool)
            or not isinstance(batch_size, int)
            or batch_size < 1
        ):
            raise ValueError("batch_size must be a positive integer")
        fields = _keyset_sort_fields(sort)
        after = _keyset_condition(fields, decode_cursor(cursor))
        final_query = ({"$and": [query, after]} if query else after) if after else query
        if len(fields) == 1 and fields[0][0] == "id":
            async for record in self._scan_records(
                collection, reverse=fields[0][1] < 0, batch_size=batch_size
            ):
                if QueryEngine.match(record, final_query):
                    yield record
        else:
            for record in await self.find(collection, final_query, sort=fields):
                yield record

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

    async def strip_node_edges(
        self,
        collection: str = "node",
        *,
        batch_size: int = 5000,
        dry_run: bool = False,
    ) -> int:
        """Remove legacy ``edges`` arrays from node JSON files.

        Idempotent. Returns the number of records that carried (or still carry,
        under ``dry_run``) an ``edges`` key.
        """
        if batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {batch_size}")
        collection_path = self.base_path / collection
        if not collection_path.exists():
            return 0
        stripped = 0
        for json_file in sorted(collection_path.glob("*.json")):
            try:
                record = await self._async_load_record(json_file)
            except Exception:
                continue
            if not isinstance(record, dict) or "edges" not in record:
                continue
            stripped += 1
            if dry_run:
                continue
            record.pop("edges", None)
            await self.save(collection, record)
        return stripped

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
