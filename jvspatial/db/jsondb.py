"""JSON-based database implementation for spatial graph persistence."""

import asyncio
import contextlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from jvspatial.db.database import Database
from jvspatial.db.query import matches_query


class JsonDB(Database):
    """JSON file-based database implementation."""

    def __init__(self, base_path: str = "jvdb") -> None:
        """Initialize JSON database.

        Args:
            base_path: Base directory for JSON files
        """
        self.base_path = Path(base_path).resolve()
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(
                f"Cannot create database directory {base_path}: {e}"
            ) from e
        self._lock = asyncio.Lock()

    @property
    def data_dir(self) -> Path:
        """Get the data directory path.

        Returns:
            Path to the data directory
        """
        return self.base_path

    async def initialize(self) -> None:
        """Initialize the database (ensure directory exists).

        This method is provided for compatibility with tests.
        The JsonDB is initialized automatically in __init__.
        """
        try:
            self.base_path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(
                f"Cannot initialize database directory {self.base_path}: {e}"
            ) from e

    def _get_collection_path(self, collection: str) -> Path:
        """Get path for collection directory.

        Args:
            collection: Collection name

        Returns:
            Path to collection directory

        Raises:
            ValueError: If collection name is invalid
            RuntimeError: If directory cannot be created
        """
        if not collection or "/" in collection or "\\" in collection:
            raise ValueError(f"Invalid collection name: {collection}")

        path = self.base_path / collection
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise RuntimeError(f"Cannot create collection directory {path}: {e}") from e
        return path

    def _get_file_path(self, collection: str, id: str) -> Path:
        """Get file path for a document.

        Args:
            collection: Collection name
            id: Document ID

        Returns:
            Path to document file

        Raises:
            ValueError: If id contains invalid characters
        """
        if not id or "/" in id or "\\" in id or id.startswith("."):
            raise ValueError(f"Invalid document ID: {id}")

        return self._get_collection_path(collection) / f"{id}.json"

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save document to JSON file.

        Args:
            collection: Collection name
            data: Document data

        Returns:
            Saved document

        Raises:
            KeyError: If document data lacks required 'id' field
            ValueError: If collection name or document ID is invalid
            RuntimeError: If file cannot be written
        """
        if "id" not in data:
            raise KeyError("Document data must contain 'id' field")

        file_path = self._get_file_path(collection, data["id"])
        async with self._lock:
            try:
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
            except OSError as e:
                raise RuntimeError(f"Cannot write to file {file_path}: {e}") from e
            except (TypeError, ValueError) as e:
                raise RuntimeError(f"Cannot serialize data to JSON: {e}") from e
        return data

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Get document by ID.

        Args:
            collection: Collection name
            id: Document ID

        Returns:
            Document data or None if not found
        """
        try:
            file_path = self._get_file_path(collection, id)
        except ValueError:
            return None  # Invalid ID returns None instead of error

        if not file_path.exists():
            return None

        async with self._lock:
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    result = json.load(f)
                    return dict(result) if isinstance(result, dict) else None
            except (OSError, json.JSONDecodeError):
                # Corrupted or inaccessible file - return None
                return None

    async def delete(self, collection: str, id: str) -> None:
        """Delete document by ID.

        Args:
            collection: Collection name
            id: Document ID
        """
        try:
            file_path = self._get_file_path(collection, id)
        except ValueError:
            return  # Invalid ID is silently ignored

        if file_path.exists():
            async with self._lock:
                with contextlib.suppress(OSError):
                    file_path.unlink()

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find documents matching query.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)

        Returns:
            List of matching documents
        """
        try:
            collection_path = self._get_collection_path(collection)
        except (ValueError, RuntimeError):
            return []  # Invalid collection returns empty list

        results = []
        seen_ids = set()

        for file_path in collection_path.glob("*.json"):
            try:
                async with self._lock:
                    with open(file_path, "r", encoding="utf-8") as f:
                        doc = json.load(f)

                # Validate document structure
                if not isinstance(doc, dict) or "id" not in doc:
                    continue

                # Skip duplicate documents
                if doc["id"] in seen_ids:
                    continue
                seen_ids.add(doc["id"])

                # Check if document matches query using standardized MongoDB-style matcher
                if matches_query(doc, query):
                    results.append(doc)
            except (json.JSONDecodeError, KeyError, IOError, TypeError):
                # Skip invalid JSON files or files without proper structure
                continue

        return results

    async def count(
        self, collection: str, query: Optional[Dict[str, Any]] = None
    ) -> int:
        """Count documents matching query.

        Args:
            collection: Collection name
            query: Query parameters (empty dict for all records)

        Returns:
            Number of matching documents
        """
        if query is None:
            query = {}
        results = await self.find(collection, query)
        return len(results)

    async def find_one(
        self, collection: str, query: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Find first document matching query.

        Args:
            collection: Collection name
            query: Query parameters

        Returns:
            First matching document or None if not found
        """
        results = await self.find(collection, query)
        return results[0] if results else None

    async def clean(self) -> None:
        """Clean up orphaned edges with invalid node references.

        This implementation finds all edges and checks if their source/target
        nodes exist, removing edges that reference non-existent nodes.
        """
        try:
            # Get all valid node IDs
            node_collection = self._get_collection_path("node")
            valid_node_ids = set()

            if node_collection.exists():
                for file_path in node_collection.glob("*.json"):
                    try:
                        async with self._lock:
                            with open(file_path, "r", encoding="utf-8") as f:
                                node_doc = json.load(f)
                                if isinstance(node_doc, dict) and "id" in node_doc:
                                    valid_node_ids.add(node_doc["id"])
                    except (json.JSONDecodeError, IOError):
                        continue

            # Check edges and remove orphaned ones
            edge_collection = self._get_collection_path("edge")
            if not edge_collection.exists():
                return

            orphaned_files = []
            for file_path in edge_collection.glob("*.json"):
                try:
                    async with self._lock:
                        with open(file_path, "r", encoding="utf-8") as f:
                            edge_doc = json.load(f)

                    if not isinstance(edge_doc, dict):
                        orphaned_files.append(file_path)
                        continue

                    # Check both old and new format
                    source = edge_doc.get("source") or edge_doc.get("context", {}).get(
                        "source"
                    )
                    target = edge_doc.get("target") or edge_doc.get("context", {}).get(
                        "target"
                    )

                    if (source and source not in valid_node_ids) or (
                        target and target not in valid_node_ids
                    ):
                        orphaned_files.append(file_path)

                except (json.JSONDecodeError, IOError):
                    orphaned_files.append(file_path)
                    continue

            # Remove orphaned files
            for file_path in orphaned_files:
                try:
                    async with self._lock:
                        file_path.unlink()
                except OSError:
                    continue  # Skip files that can't be deleted

        except (ValueError, RuntimeError):
            # If we can't access collections, skip cleanup
            pass
