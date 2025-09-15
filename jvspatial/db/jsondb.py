"""JSON-based database implementation for spatial graph persistence."""

import asyncio
import json
from pathlib import Path
from typing import Any, List, Optional

from jvspatial.db.database import Database


class JsonDB(Database):
    """JSON file-based database implementation."""

    def __init__(self: "JsonDB", base_path: str = "jvdb") -> None:
        """Initialize JSON database.

        Args:
            base_path: Base directory for JSON files
        """
        self.base_path = Path(base_path).resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_collection_path(self: "JsonDB", collection: str) -> Path:
        """Get path for collection directory.

        Args:
            collection: Collection name

        Returns:
            Path to collection directory
        """
        path = self.base_path / collection
        path.mkdir(parents=True, exist_ok=True)
        return path

    def _get_file_path(self: "JsonDB", collection: str, id: str) -> Path:
        """Get file path for a document.

        Args:
            collection: Collection name
            id: Document ID

        Returns:
            Path to document file
        """
        return self._get_collection_path(collection) / f"{id}.json"

    async def save(self: "JsonDB", collection: str, data: dict) -> dict:
        """Save document to JSON file.

        Args:
            collection: Collection name
            data: Document data

        Returns:
            Saved document
        """
        file_path = self._get_file_path(collection, data["id"])
        async with self._lock:
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
        return data

    async def get(self: "JsonDB", collection: str, id: str) -> Optional[dict]:
        """Get document by ID.

        Args:
            collection: Collection name
            id: Document ID

        Returns:
            Document data or None if not found
        """
        file_path = self._get_file_path(collection, id)
        if not file_path.exists():
            return None

        async with self._lock:
            with open(file_path, "r") as f:
                return json.load(f)

    async def delete(self: "JsonDB", collection: str, id: str) -> None:
        """Delete document by ID.

        Args:
            collection: Collection name
            id: Document ID
        """
        file_path = self._get_file_path(collection, id)
        if file_path.exists():
            async with self._lock:
                file_path.unlink()

    async def find(self: "JsonDB", collection: str, query: dict) -> List[dict]:
        """Find documents matching query.

        Args:
            collection: Collection name
            query: Query parameters

        Returns:
            List of matching documents
        """
        collection_path = self._get_collection_path(collection)
        results = []
        seen_ids = set()

        for file_path in collection_path.glob("*.json"):
            try:
                async with self._lock:
                    with open(file_path, "r") as f:
                        doc = json.load(f)

                # Skip duplicate documents
                if doc["id"] in seen_ids:
                    continue
                seen_ids.add(doc["id"])

                # Check if document matches query
                if self._matches_query(doc, query):
                    results.append(doc)
            except (json.JSONDecodeError, KeyError, IOError):
                # Skip invalid JSON files or files without proper structure
                continue

        return results

    def _matches_query(self: "JsonDB", doc: dict, query: dict) -> bool:
        """Check if document matches query.

        Args:
            doc: Document to check
            query: Query parameters

        Returns:
            True if document matches query, else False
        """
        for key, condition in query.items():
            # Handle nested fields using dot notation
            doc_value: Any = None
            if "." in key:
                keys = key.split(".")
                current: Any = doc
                for k in keys:
                    if isinstance(current, dict) and k in current:
                        current = current[k]
                    else:
                        current = None
                        break
                doc_value = current
            else:
                doc_value = doc.get(key)

            # If condition is a dict, it contains operators
            if not isinstance(condition, dict):
                # Simple equality check
                if doc_value != condition:
                    return False
            else:
                # Handle operator conditions
                for op, value in condition.items():
                    if (
                        (op == "$eq" and doc_value != value)
                        or (op == "$ne" and doc_value == value)
                        or (op == "$gt" and (doc_value is None or doc_value <= value))
                        or (op == "$gte" and (doc_value is None or doc_value < value))
                        or (op == "$lt" and (doc_value is None or doc_value >= value))
                        or (op == "$lte" and (doc_value is None or doc_value > value))
                        or (
                            op == "$in"
                            and (doc_value is None or doc_value not in value)
                        )
                        or (
                            op == "$nin"
                            and (doc_value is not None and doc_value in value)
                        )
                    ):
                        return False
        return True
