"""Simplified JSON-based database implementation."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from jvspatial.db.database import Database
from jvspatial.db.query import QueryEngine

logger = logging.getLogger(__name__)

# Try to import aiofiles for async file operations, fallback to asyncio.to_thread
try:
    import aiofiles  # type: ignore[import-untyped]

    HAS_AIOFILES = True
except ImportError:
    HAS_AIOFILES = False


class JsonDB(Database):
    """Simplified JSON file-based database implementation."""

    def __init__(self, base_path: str = "jvdb") -> None:
        """Initialize JSON database.

        Args:
            base_path: Base directory for JSON files
        """
        self.base_path = Path(base_path).resolve()
        # Don't create directory immediately - create it lazily on first use
        # This prevents 'jvdb' from being created when DatabaseManager is auto-created
        # before Server initializes with the correct database path
        self._lock: Optional[asyncio.Lock] = None

    def _ensure_lock(self) -> asyncio.Lock:
        """Ensure lock is initialized (lazy initialization for async context)."""
        if self._lock is None:
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            self._lock = asyncio.Lock()
        return self._lock

    def _get_collection_dir(self, collection: str) -> Path:
        """Get the directory path for a collection."""
        # Create base directory lazily (only when actually used)
        # This prevents 'jvdb' from being created when DatabaseManager is auto-created
        # before Server initializes with the correct database path
        self.base_path.mkdir(parents=True, exist_ok=True)
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

    async def _async_write_json(self, path: Path, data: Dict[str, Any]) -> None:
        """Write JSON data to file asynchronously.

        Uses aiofiles if available, otherwise falls back to asyncio.to_thread.
        """
        json_str = json.dumps(data, indent=2)
        if HAS_AIOFILES:
            async with aiofiles.open(path, "w") as f:
                await f.write(json_str)
        else:
            # Fallback to thread pool for async execution
            def _sync_write(path: Path, content: str) -> None:
                path.write_text(content)

            await asyncio.to_thread(_sync_write, path, json_str)

    async def _async_read_json(self, path: Path) -> Optional[Dict[str, Any]]:
        """Read JSON data from file asynchronously.

        Uses aiofiles if available, otherwise falls back to asyncio.to_thread.
        Returns None if file doesn't exist or is invalid.
        """
        if not path.exists():
            return None

        try:
            if HAS_AIOFILES:
                async with aiofiles.open(path, "r") as f:
                    content = await f.read()
                    return json.loads(content)
            else:
                # Fallback to thread pool for async execution
                def _sync_read(path: Path) -> Optional[Dict[str, Any]]:
                    try:
                        with open(path, "r") as f:
                            return json.load(f)
                    except (json.JSONDecodeError, OSError):
                        return None

                return await asyncio.to_thread(_sync_read, path)
        except (json.JSONDecodeError, OSError):
            return None

    async def _async_load_record(self, json_file: Path) -> Optional[Dict[str, Any]]:
        """Load a single record from a JSON file asynchronously.

        Returns None if the file is invalid or cannot be read.
        """
        try:
            return await self._async_read_json(json_file)
        except Exception:
            return None

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database.

        Note: Entities should always have IDs set by their __init__ methods.
        This method expects the ID to already be present in the data.
        """
        async with self._ensure_lock():
            # Save the record to its own file
            record_path = self._get_record_path(collection, data["id"])
            await self._async_write_json(record_path, data)
            return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""
        record_path = self._get_record_path(collection, id)
        return await self._async_read_json(record_path)

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""
        async with self._ensure_lock():
            record_path = self._get_record_path(collection, id)

            if record_path.exists():
                # Use asyncio.to_thread for file deletion to avoid blocking
                await asyncio.to_thread(record_path.unlink)

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query.

        Uses parallel file reads for improved performance under concurrent load.
        """
        collection_dir = self._get_collection_dir(collection)

        if not collection_dir.exists():
            return []

        # Get all JSON files in the collection directory
        json_files = list(collection_dir.glob("*.json"))

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

        return results

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
