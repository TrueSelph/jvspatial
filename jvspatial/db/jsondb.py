"""Simplified JSON-based database implementation."""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from jvspatial.db.database import Database


class JsonDB(Database):
    """Simplified JSON file-based database implementation."""

    def __init__(self, base_path: str = "jvdb") -> None:
        """Initialize JSON database.

        Args:
            base_path: Base directory for JSON files
        """
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
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
        collection_dir = self.base_path / collection
        collection_dir.mkdir(parents=True, exist_ok=True)
        return collection_dir

    def _get_record_path(self, collection: str, record_id: str) -> Path:
        """Get the file path for a specific record."""
        collection_dir = self._get_collection_dir(collection)
        return collection_dir / f"{record_id.replace(':', '.')}.json"

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database."""
        async with self._ensure_lock():
            # Ensure record has an ID
            if "id" not in data:
                import uuid

                data["id"] = str(uuid.uuid4())

            # Save the record to its own file
            record_path = self._get_record_path(collection, data["id"])
            with open(record_path, "w") as f:
                json.dump(data, f, indent=2)

            return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""
        record_path = self._get_record_path(collection, id)

        if not record_path.exists():
            return None

        try:
            with open(record_path, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""
        async with self._ensure_lock():
            record_path = self._get_record_path(collection, id)

            if record_path.exists():
                record_path.unlink()

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query."""
        collection_dir = self._get_collection_dir(collection)

        if not collection_dir.exists():
            return []

        results = []

        # Iterate through all JSON files in the collection directory
        for json_file in collection_dir.glob("*.json"):
            try:
                with open(json_file, "r") as f:
                    record = json.load(f)

                # Check if record matches query
                if not query or self._matches_query(record, query):
                    results.append(record)

            except (json.JSONDecodeError, IOError):
                continue  # Skip invalid files

        return results

    def _matches_query(self, record: Dict[str, Any], query: Dict[str, Any]) -> bool:
        """Check if a record matches a query."""
        for key, expected_value in query.items():
            if key.startswith("$"):
                continue  # Skip MongoDB operators for now

            actual_value = self._get_nested_value(record, key)

            if actual_value != expected_value:
                return False

        return True

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
