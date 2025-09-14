import os
import json
import asyncio
from pathlib import Path
from typing import List, Optional
from jvspatial.db.database import Database


class JsonDB(Database):
    def __init__(self, base_path: str = "db/json"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()

    def _get_collection_path(self, collection: str) -> Path:
        """Get path for collection directory"""
        path = self.base_path / collection
        path.mkdir(exist_ok=True)
        return path

    def _get_file_path(self, collection: str, id: str) -> Path:
        """Get file path for document"""
        return self._get_collection_path(collection) / f"{id}.json"

    async def save(self, collection: str, data: dict) -> dict:
        """Save document to JSON file"""
        file_path = self._get_file_path(collection, data["id"])
        async with self._lock:
            with open(file_path, "w") as f:
                json.dump(data, f, indent=2)
        return data

    async def get(self, collection: str, id: str) -> Optional[dict]:
        """Get document by ID"""
        file_path = self._get_file_path(collection, id)
        if not file_path.exists():
            return None

        async with self._lock:
            with open(file_path, "r") as f:
                return json.load(f)

    async def delete(self, collection: str, id: str) -> bool:
        """Delete document by ID"""
        file_path = self._get_file_path(collection, id)
        if file_path.exists():
            async with self._lock:
                file_path.unlink()
            return True
        return False

    async def find(self, collection: str, query: dict) -> List[dict]:
        """Find documents matching query with nested field support"""
        collection_path = self._get_collection_path(collection)
        results = []
        seen_ids = set()

        for file_path in collection_path.glob("*.json"):
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

        return results

    def _matches_query(self, doc: dict, query: dict) -> bool:
        """Check if document matches query with nested field support"""
        for key, condition in query.items():
            # Handle nested fields using dot notation
            if "." in key:
                keys = key.split(".")
                current = doc
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
            if isinstance(condition, dict):
                for op, value in condition.items():
                    if op == "$eq" and doc_value != value:
                        return False
                    elif op == "$ne" and doc_value == value:
                        return False
                    elif op == "$gt" and (doc_value is None or doc_value <= value):
                        return False
                    elif op == "$gte" and (doc_value is None or doc_value < value):
                        return False
                    elif op == "$lt" and (doc_value is None or doc_value >= value):
                        return False
                    elif op == "$lte" and (doc_value is None or doc_value > value):
                        return False
                    elif op == "$in" and (doc_value is None or doc_value not in value):
                        return False
                    elif op == "$nin" and (
                        doc_value is not None and doc_value in value
                    ):
                        return False
            else:
                # Simple equality check
                if doc_value != condition:
                    return False
        return True
