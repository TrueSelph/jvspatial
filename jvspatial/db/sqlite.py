"""SQLite database implementation for jvspatial.

This module provides a lightweight SQLite-based database implementation that
conforms to the simplified Database interface used throughout jvspatial. Data
is stored in a single table with JSON payloads to maintain compatibility with
the JSON database structure and query behaviour.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Set, Tuple, Union

from ._sqlite_translate import (
    translate_partial_filter_expression,
    translate_query,
    translate_sort,
)
from .database import Database, finalize_find_results
from .query import QueryEngine

logger = logging.getLogger(__name__)

try:
    import aiosqlite
except ImportError:  # pragma: no cover - handled by raising in __init__
    aiosqlite = None  # type: ignore[assignment]

if TYPE_CHECKING:  # pragma: no cover - typing only
    from aiosqlite import Connection


class SQLiteDB(Database):
    """SQLite-based database implementation.

    Stores records in a single table and keeps payloads as JSON to mirror the
    structure used by other database backends.

    Index Creation Behavior:
        SQLite index creation is synchronous and blocks until the index is built.
        For typical use cases with small to medium datasets, index creation is very fast
        (milliseconds to seconds). For very large databases, index creation may take longer
        but is generally much faster than DynamoDB GSI creation.

    Connection model:
        One persistent ``aiosqlite`` connection per :class:`SQLiteDB`
        instance, created lazily on first use and held until :meth:`close`.
        We do not pool connections: SQLite is in-process and the cost of
        opening a new connection is negligible, while WAL mode already
        gives us reader/writer parallelism (concurrent readers, one
        writer) on the single connection.

        Writes are serialized through ``self._lock`` (an
        :class:`asyncio.Lock`). Reads run unlocked to take advantage of
        WAL.

        The single-connection model assumes a single event loop per
        :class:`SQLiteDB` instance. Sharing a single instance across
        loops is not supported -- if you need that, instantiate one
        :class:`SQLiteDB` per loop. (Mongo and DynamoDB adapters have
        explicit cross-loop handling because they speak to a network
        service; SQLite does not.)
    """

    def __init__(
        self,
        db_path: Optional[Union[str, Path]] = None,
        timeout: float = 5.0,
        journal_mode: str = "WAL",
        synchronous: str = "NORMAL",
    ) -> None:
        if aiosqlite is None:  # pragma: no cover - exercised when dependency missing
            raise ImportError(
                "aiosqlite is required for SQLite support. "
                "Install it with: pip install aiosqlite"
            )

        if db_path is None:
            db_path = "jvdb/sqlite/jvspatial.db"

        # Handle :memory: special case
        if str(db_path) == ":memory:":
            self.db_path_str = ":memory:"
            self.db_path = Path(":memory:")  # Keep for compatibility
        else:
            # Convert to Path and resolve to absolute path
            path_obj = Path(db_path)
            # Always resolve to get absolute path for consistency
            # This handles both absolute and relative paths correctly
            self.db_path = path_obj.resolve()

            # Create parent directory if it doesn't exist (only for file paths)
            parent = self.db_path.parent
            if parent != self.db_path and str(parent) != ".":
                try:
                    parent.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    raise OSError(
                        f"Failed to create directory for SQLite database at {parent}: {e}"
                    ) from e

            # Store as string for aiosqlite
            self.db_path_str = str(self.db_path)

        self.timeout = timeout
        self.journal_mode = journal_mode
        self.synchronous = synchronous

        self._connection: Optional["Connection"] = None
        self._lock = asyncio.Lock()
        self._initialized = False
        self._created_indexes: Dict[str, Set[str]] = (
            {}
        )  # collection -> set of index names
        # The event loop that owns ``self._connection``. ``aiosqlite``
        # binds its connection to a single loop; using the connection
        # from a different loop produces opaque "Future attached to a
        # different loop" errors. We track the binding here and raise
        # a clear ``DatabaseError`` on cross-loop reuse (audit §5.10).
        self._owning_loop: Optional[asyncio.AbstractEventLoop] = None

    async def _get_connection(self) -> "Connection":
        """Get or create the SQLite connection.

        Cross-loop reuse handling (audit §5.10 / SPEC §4.3):

        * For **file-backed databases**, the connection is silently
          rebound to the current loop — the old loop is presumed gone,
          and on-disk state persists across the rebind so callers do
          not observe data loss.
        * For ``:memory:`` databases, data lives in the connection
          itself; rebinding would silently truncate the dataset. We
          keep the existing connection and trust aiosqlite's internal
          thread to dispatch queries from any loop (this matches
          historical behavior — the audit's concern was an opaque
          failure mode, not data loss).
        """
        current_loop = asyncio.get_running_loop()
        if (
            self._connection is not None
            and self._owning_loop is not None
            and self._owning_loop is not current_loop
            and self.db_path_str != ":memory:"
        ):
            logger.debug(
                "SQLiteDB rebinding to a new event loop; abandoning "
                "connection owned by %r and reconnecting on %r",
                self._owning_loop,
                current_loop,
            )
            self._connection = None
            self._owning_loop = None
            self._initialized = False
            # Reset per-loop state; index re-creation is idempotent.
            self._created_indexes.clear()
        if self._connection is None:
            # Ensure parent directory exists before connecting (for file paths)
            if self.db_path_str != ":memory:":
                # For :memory:, db_path is Path(":memory:") which has no parent
                # For file paths, ensure parent directory exists
                try:
                    parent = self.db_path.parent
                    if parent != self.db_path and str(parent) != ".":
                        parent.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    raise OSError(
                        f"Failed to create directory for SQLite database at {self.db_path.parent}: {e}"
                    ) from e

            # Use the string path (handles :memory: and file paths)
            self._connection = await aiosqlite.connect(
                self.db_path_str, timeout=self.timeout
            )
            self._owning_loop = current_loop
            self._connection.row_factory = aiosqlite.Row
            await self._connection.execute(f"PRAGMA journal_mode={self.journal_mode};")
            await self._connection.execute(f"PRAGMA synchronous={self.synchronous};")
            await self._connection.execute("PRAGMA foreign_keys=ON;")

        if not self._initialized:
            await self._connection.execute(
                """
                CREATE TABLE IF NOT EXISTS records (
                    collection TEXT NOT NULL,
                    id TEXT NOT NULL,
                    data TEXT NOT NULL,
                    PRIMARY KEY (collection, id)
                )
                """
            )
            await self._connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_records_collection
                ON records (collection)
                """
            )
            await self._connection.commit()
            # Drop legacy global unique indexes on session_id before any
            # writes — CREATE INDEX IF NOT EXISTS would leave them in place
            # and Interaction rows sharing a Conversation session_id get wiped.
            await self._repair_non_partial_unique_indexes(self._connection)
            self._initialized = True

        return self._connection

    def _json_path(self, field_path: str) -> str:
        """Convert a field path (e.g., 'context.user_id') to SQLite JSON path expression.

        Args:
            field_path: Field path using dot notation

        Returns:
            SQLite JSON path expression
        """
        # Convert "context.user_id" to "$.context.user_id" for JSON extraction
        return f"$.{field_path}"

    @staticmethod
    def _is_non_partial_session_id_unique_index(sql: Optional[str]) -> bool:
        """True for UNIQUE indexes on context.session_id with no WHERE clause."""
        if not sql:
            return False
        lower = sql.lower()
        if "unique" not in lower:
            return False
        if "where" in lower:
            return False
        return "json_extract(data, '$.context.session_id')" in lower

    async def _repair_non_partial_unique_indexes(
        self, connection: "Connection"
    ) -> None:
        """Drop global unique indexes on ``context.session_id`` that lack WHERE.

        Pre-partial-filter SQLite builds created a blanket UNIQUE on
        ``session_id`` for the whole ``node`` collection. Conversation and
        Interaction share that field; ``INSERT OR REPLACE`` then deleted
        Interaction rows whenever Conversation was saved. Dropping here
        lets the next ``ensure_indexes(Conversation)`` recreate a partial
        unique index.
        """
        cursor = await connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"
        )
        rows = await cursor.fetchall()
        dropped = 0
        for row in rows:
            name = row[0]
            sql = row[1]
            if not self._is_non_partial_session_id_unique_index(sql):
                continue
            # Only drop indexes we (or prior jvspatial) named — avoid
            # touching unrelated user indexes with similar SQL text.
            if not str(name).startswith("idx_"):
                continue
            logger.warning(
                "Dropping non-partial unique index '%s' on connect "
                "(session_id uniqueness must be partial so Interaction "
                "rows are not wiped). It will be recreated with WHERE on "
                "the next Conversation ensure_indexes.",
                name,
            )
            await connection.execute(f'DROP INDEX IF EXISTS "{name}"')
            dropped += 1
            for names in self._created_indexes.values():
                names.discard(name)
        if dropped:
            await connection.commit()

    @staticmethod
    def _resolve_index_where(**kwargs: Any) -> Optional[str]:
        """Resolve a CREATE INDEX WHERE clause from kwargs.

        Honors an explicit ``where=`` string, otherwise translates a
        Mongo-style partial filter under any of the names
        ``get_indexes()`` / annotations may emit. Returns ``None`` when
        no partial filter was requested. Raises ``ValueError`` when a
        partial filter is present but cannot be translated — never
        silently demote a partial unique index to a global unique.
        """
        explicit = kwargs.get("where")
        if isinstance(explicit, str) and explicit.strip():
            return explicit.strip()

        pfe = (
            kwargs.get("index_partial_filter_expression")
            or kwargs.get("partial_filter_expression")
            or kwargs.get("partialFilterExpression")
        )
        if not pfe:
            return None
        translated = translate_partial_filter_expression(pfe)
        if translated is None:
            raise ValueError(
                "SQLiteDB.create_index: cannot translate "
                f"index_partial_filter_expression {pfe!r} to a "
                "SQLite WHERE clause. Pass an explicit ``where=`` "
                "argument or use a supported filter shape "
                "(equality / $gt / $exists on safe field paths "
                "with scalar values)."
            )
        return translated

    @staticmethod
    def _index_needs_partial_repair(
        existing_sql: Optional[str], where_sql: Optional[str]
    ) -> bool:
        """Return True when an on-disk index must be dropped and rebuilt.

        A global unique index created before partial-filter support will
        lack a WHERE clause; ``CREATE INDEX IF NOT EXISTS`` would leave
        it in place and keep wiping colliding rows (Conversation vs
        Interaction ``session_id``).
        """
        if not where_sql:
            return False
        if not existing_sql:
            return False
        lower = existing_sql.lower()
        if "where" not in lower:
            return True
        # Require each AND-ed predicate from the desired WHERE to appear
        # (SQLite stores CREATE INDEX SQL as we wrote it).
        return any(
            part.strip() not in existing_sql for part in where_sql.split(" AND ")
        )

    async def create_index(
        self,
        collection: str,
        field_or_fields: Union[str, List[Tuple[str, int]]],
        unique: bool = False,
        **kwargs: Any,
    ) -> None:
        """Create an index on the specified field(s) using JSON path extraction.

        Args:
            collection: Collection name
            field_or_fields: Single field name (str) or list of (field_name, direction) tuples for compound indexes
            unique: Whether the index should enforce uniqueness
            **kwargs: Partial-filter options (``partialFilterExpression``,
                ``partial_filter_expression``,
                ``index_partial_filter_expression``, or explicit ``where=``).
                Same Mongo dialect as PostgresDB.create_index.

        Note:
            SQLite indexes on nested JSON fields use json_extract() function.
            Direction parameter is ignored for SQLite (always ascending).
            When a partial filter is required and an older non-partial
            index of the same name exists, it is dropped and recreated.
        """
        connection = await self._get_connection()

        # Initialize index tracking for this collection if needed
        if collection not in self._created_indexes:
            self._created_indexes[collection] = set()

        # Build index specification
        if isinstance(field_or_fields, str):
            # Single field index
            fields = [(field_or_fields, 1)]
            index_name = f"idx_{collection}_{field_or_fields.replace('.', '_')}"
        else:
            # Compound index
            fields = field_or_fields
            field_names = "_".join(field.replace(".", "_") for field, _ in fields)
            index_name = f"idx_{collection}_{field_names}"

        where_sql = self._resolve_index_where(**kwargs)

        # Inspect on-disk definition so a prior global unique index can
        # be repaired after upgrading to partial-filter support.
        cursor = await connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
            (index_name,),
        )
        row = await cursor.fetchone()
        existing_sql = row[0] if row else None

        if self._index_needs_partial_repair(existing_sql, where_sql):
            logger.info(
                "Dropping non-partial index '%s' so it can be recreated "
                "with WHERE %s",
                index_name,
                where_sql,
            )
            await connection.execute(f"DROP INDEX IF EXISTS {index_name}")
            await connection.commit()
            self._created_indexes[collection].discard(index_name)
            existing_sql = None

        # Check if index already exists (in-process or on disk, correct form)
        if index_name in self._created_indexes[collection]:
            return
        if existing_sql is not None and not self._index_needs_partial_repair(
            existing_sql, where_sql
        ):
            self._created_indexes[collection].add(index_name)
            return

        # Build SQLite index creation statement
        # For nested fields, use json_extract() to extract values from JSON
        index_expressions = []
        for field_path, _direction in fields:
            json_path = self._json_path(field_path)
            index_expressions.append(f"json_extract(data, '{json_path}')")

        index_columns = ", ".join(index_expressions)
        unique_clause = "UNIQUE" if unique else ""
        where_clause = f" WHERE {where_sql}" if where_sql else ""

        try:
            # Include collection in the index to support efficient filtering.
            # Partial filters become a SQLite partial index WHERE clause so
            # uniqueness is scoped the same way as Mongo/Postgres.
            sql = f"""
            CREATE {unique_clause} INDEX IF NOT EXISTS {index_name}
            ON records (collection, {index_columns}){where_clause}
            """

            await connection.execute(sql)
            await connection.commit()

            # Track that we created this index
            self._created_indexes[collection].add(index_name)

            logger.debug(
                f"Created index '{index_name}' on collection '{collection}' "
                f"(unique={unique}, fields={[f[0] for f in fields]}"
                f"{', partial' if where_sql else ''})"
            )

        except Exception as e:
            # Partial unique indexes protect Conversation/Interaction
            # coexistence — never swallow create failures for those.
            if unique and where_sql:
                raise RuntimeError(
                    f"Failed to create partial unique index '{index_name}' "
                    f"on collection '{collection}': {e}"
                ) from e
            logger.warning(
                f"Failed to create index '{index_name}' on collection '{collection}': {e}"
            )

    async def close(self) -> None:
        """Close the underlying SQLite connection.

        Clears the owning-loop binding so the instance can be reused on
        a fresh event loop (audit §5.10).
        """
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._initialized = False
            self._created_indexes.clear()
            self._owning_loop = None

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database.

        Args:
            collection: Collection name
            data: Record data dictionary

        Returns:
            Saved record with generated ID if not provided
        """
        async with self._lock:
            connection = await self._get_connection()

            record = data.copy()
            # Coerce id to ``str`` so non-string ids (int, uuid.UUID)
            # round-trip cleanly through SQLite's TEXT column. The
            # legacy code only stringified the default uuid and bound
            # the raw value; ``get(collection, id)`` then missed when
            # callers passed an int-typed id (audit §5.20).
            record_id = str(record.setdefault("id", str(uuid.uuid4())))
            record["id"] = record_id
            payload = json.dumps(record)

            await connection.execute(
                """
                INSERT OR REPLACE INTO records (collection, id, data)
                VALUES (?, ?, ?)
                """,
                (collection, record_id, payload),
            )
            await connection.commit()
            return record

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record from the database.

        Args:
            collection: Collection name
            id: Record ID

        Returns:
            Record data if found, None otherwise

        Note:
            Read operations don't require the write lock since SQLite WAL mode
            allows concurrent reads. Only write operations are serialized.
        """
        connection = await self._get_connection()
        cursor = await connection.execute(
            "SELECT data FROM records WHERE collection = ? AND id = ?",
            (collection, id),
        )
        row = await cursor.fetchone()
        await cursor.close()
        if row is None:
            return None
        return json.loads(row["data"])

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record from the database.

        Args:
            collection: Collection name
            id: Record ID
        """
        async with self._lock:
            connection = await self._get_connection()
            await connection.execute(
                "DELETE FROM records WHERE collection = ? AND id = ?",
                (collection, id),
            )
            await connection.commit()

    async def find_many(
        self, collection: str, ids: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Bulk fetch via a single ``WHERE collection=? AND id IN (...)``.

        Chunks ids into groups of 500 to stay safely within SQLite's
        default ``SQLITE_MAX_VARIABLE_NUMBER`` (typically 999 or 32766
        depending on the build, but 500 is conservative for both).
        """
        if not ids:
            return {}
        unique_ids = list(dict.fromkeys(ids))
        connection = await self._get_connection()
        out: Dict[str, Dict[str, Any]] = {}
        chunk_size = 500
        for i in range(0, len(unique_ids), chunk_size):
            chunk = unique_ids[i : i + chunk_size]
            placeholders = ",".join("?" * len(chunk))
            sql = (
                f"SELECT id, data FROM records "
                f"WHERE collection = ? AND id IN ({placeholders})"
            )
            cursor = await connection.execute(sql, (collection, *chunk))
            rows = await cursor.fetchall()
            await cursor.close()
            for row in rows:
                out[row["id"]] = json.loads(row["data"])
        return out

    async def bulk_save(self, collection: str, records: List[Dict[str, Any]]) -> int:
        """Atomic batch write under a single transaction.

        Either every record in ``records`` is persisted or none are.
        A constraint violation rolls back the whole batch and re-raises
        the underlying ``sqlite3`` error.
        """
        if not records:
            return 0
        for r in records:
            if "id" not in r:
                raise ValueError(
                    "bulk_save requires every record to have an 'id' field"
                )
        params = [(collection, str(r["id"]), json.dumps(dict(r))) for r in records]
        async with self._lock:
            connection = await self._get_connection()
            try:
                await connection.execute("BEGIN")
                await connection.executemany(
                    "INSERT OR REPLACE INTO records "
                    "(collection, id, data) VALUES (?, ?, ?)",
                    params,
                )
                await connection.commit()
            except Exception:
                # ``aiosqlite`` rollback is best-effort; if the
                # connection itself is wedged we'd rather surface the
                # original exception.
                with contextlib.suppress(Exception):
                    await connection.rollback()
                raise
        return len(records)

    async def find(
        self,
        collection: str,
        query: Dict[str, Any],
        *,
        limit: Optional[int] = None,
        sort: Optional[List[Tuple[str, int]]] = None,
    ) -> List[Dict[str, Any]]:
        """Find records matching the query.

        Args:
            collection: Collection name
            query: Query dictionary

        Returns:
            List of matching records

        Pushdown
        --------
        For queries built from operators we recognize
        (see :mod:`jvspatial.db._sqlite_translate`), the WHERE clause and
        LIMIT/ORDER BY are pushed into SQL via ``json_extract``. This is
        dramatically cheaper than the previous "load every row, filter in
        Python" path. Queries we don't translate (``$regex``,
        ``$elemMatch``, etc.) fall back to the legacy in-Python filter
        with the same semantics as before.

        Note:
            Read operations don't require the write lock since SQLite WAL
            mode allows concurrent reads. Only write operations are
            serialized.
        """
        connection = await self._get_connection()
        # An empty sort spec is "no ordering requested", same as None. Without
        # this the ``sort is None`` guard below fails and an empty list takes
        # the untranslatable-sort branch: full-collection load, LIMIT applied
        # only in memory.
        if not sort:
            sort = None
        translated = translate_query(query) if query else ("", [])

        if translated is not None:
            where_extra, params = translated
            sql = "SELECT data FROM records WHERE collection = ?"
            sql_params: List[Any] = [collection]
            if where_extra:
                sql += f" AND ({where_extra})"
                sql_params.extend(params)

            order_by = translate_sort(sort)
            if order_by is not None:
                sql += f" ORDER BY {order_by}"
                # Pushed-down sort means LIMIT can also be pushed.
                if limit is not None:
                    sql += " LIMIT ?"
                    sql_params.append(int(limit))
                cursor = await connection.execute(sql, tuple(sql_params))
                rows = await cursor.fetchall()
                await cursor.close()
                return [json.loads(row["data"]) for row in rows]

            # No sort, or sort not translatable.
            if sort is None and limit is not None:
                sql += " LIMIT ?"
                sql_params.append(int(limit))
                cursor = await connection.execute(sql, tuple(sql_params))
                rows = await cursor.fetchall()
                await cursor.close()
                return [json.loads(row["data"]) for row in rows]

            # Sort spec we can't translate: pull all matching rows, sort
            # in memory via finalize_find_results.
            cursor = await connection.execute(sql, tuple(sql_params))
            rows = await cursor.fetchall()
            await cursor.close()
            return finalize_find_results(
                [json.loads(row["data"]) for row in rows], sort=sort, limit=limit
            )

        # Fallback: untranslatable query (e.g. $regex). Original behavior.
        cursor = await connection.execute(
            "SELECT data FROM records WHERE collection = ?", (collection,)
        )
        rows = await cursor.fetchall()
        await cursor.close()

        results: List[Dict[str, Any]] = []
        for row in rows:
            record = json.loads(row["data"])
            if not query or QueryEngine.match(record, query):
                results.append(record)
        return finalize_find_results(results, sort=sort, limit=limit)

    async def count(
        self,
        collection: str,
        query: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count records using SQL ``COUNT(*)`` whenever possible.

        * Empty query: ``SELECT COUNT(*) … WHERE collection = ?``.
        * Translatable filtered query: ``SELECT COUNT(*) … WHERE
          collection = ? AND <translated WHERE>``.
        * Untranslatable filtered query (e.g. ``$regex``): falls back to
          ``find()`` and ``len()``.
        """
        q = query or {}
        connection = await self._get_connection()
        if not q:
            cursor = await connection.execute(
                "SELECT COUNT(*) FROM records WHERE collection = ?", (collection,)
            )
            row = await cursor.fetchone()
            await cursor.close()
            return row[0] if row else 0

        translated = translate_query(q)
        if translated is not None:
            where_extra, params = translated
            sql = "SELECT COUNT(*) FROM records WHERE collection = ?"
            sql_params: List[Any] = [collection]
            if where_extra:
                sql += f" AND ({where_extra})"
                sql_params.extend(params)
            cursor = await connection.execute(sql, tuple(sql_params))
            row = await cursor.fetchone()
            await cursor.close()
            return row[0] if row else 0

        # Untranslatable: legacy fallback.
        rows = await self.find(collection, q)
        return len(rows)

    # Context manager helpers for convenience
    async def __aenter__(self) -> "SQLiteDB":
        """Async context manager entry."""
        await self._get_connection()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Async context manager exit."""
        await self.close()
