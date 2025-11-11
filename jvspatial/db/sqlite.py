"""SQLite database implementation for jvspatial.

This module provides a lightweight SQLite-based database implementation that
conforms to the simplified Database interface used throughout jvspatial. Data
is stored in a single table with JSON payloads to maintain compatibility with
the JSON database structure and query behaviour.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

from .database import Database
from .query import QueryEngine

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

    async def _get_connection(self) -> "Connection":
        """Get or create the SQLite connection."""
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
            self._initialized = True

        return self._connection

    async def close(self) -> None:
        """Close the underlying SQLite connection."""
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._initialized = False

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
            record_id = record.setdefault("id", str(uuid.uuid4()))
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

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching the query.

        Args:
            collection: Collection name
            query: Query dictionary

        Returns:
            List of matching records
        """
        connection = await self._get_connection()
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
        return results

    # Context manager helpers for convenience
    async def __aenter__(self) -> "SQLiteDB":
        """Async context manager entry."""
        await self._get_connection()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        """Async context manager exit."""
        await self.close()
