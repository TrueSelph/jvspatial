"""Simplified MongoDB database implementation."""

from typing import Any, Dict, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pymongo.errors import PyMongoError

from jvspatial.db.database import Database
from jvspatial.exceptions import DatabaseError


class MongoDB(Database):
    """Simplified MongoDB-based database implementation."""

    def __init__(
        self, uri: str = "mongodb://localhost:27017", db_name: str = "jvdb"
    ) -> None:
        """Initialize MongoDB database.

        Args:
            uri: MongoDB connection URI
            db_name: Database name
        """
        self.uri = uri
        self.db_name = db_name
        self._client: Optional[AsyncIOMotorClient] = None
        self._db: Optional[AsyncIOMotorDatabase] = None

    async def _ensure_connected(self) -> None:
        """Ensure database connection is established."""
        if self._client is None:
            self._client = AsyncIOMotorClient(self.uri)
            self._db = self._client[self.db_name]

    async def save(self, collection: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Save a record to the database."""
        await self._ensure_connected()

        # Ensure record has an ID
        if "_id" not in data and "id" not in data:
            import uuid

            data["_id"] = str(uuid.uuid4())
        elif "id" in data and "_id" not in data:
            data["_id"] = data["id"]

        try:
            collection_obj = self._db[collection]
            await collection_obj.replace_one({"_id": data["_id"]}, data, upsert=True)
            return data
        except PyMongoError as e:
            raise DatabaseError(f"MongoDB save error: {e}") from e

    async def get(self, collection: str, id: str) -> Optional[Dict[str, Any]]:
        """Retrieve a record by ID."""
        await self._ensure_connected()

        try:
            collection_obj = self._db[collection]
            result = await collection_obj.find_one({"_id": id})
            return result
        except PyMongoError as e:
            raise DatabaseError(f"MongoDB get error: {e}") from e

    async def delete(self, collection: str, id: str) -> None:
        """Delete a record by ID."""
        await self._ensure_connected()

        try:
            collection_obj = self._db[collection]
            await collection_obj.delete_one({"_id": id})
        except PyMongoError as e:
            raise DatabaseError(f"MongoDB delete error: {e}") from e

    async def find(
        self, collection: str, query: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Find records matching a query."""
        await self._ensure_connected()

        try:
            collection_obj = self._db[collection]
            cursor = collection_obj.find(query)
            results = await cursor.to_list(length=None)
            return results
        except PyMongoError as e:
            raise DatabaseError(f"MongoDB find error: {e}") from e

    async def close(self) -> None:
        """Close the database connection."""
        if self._client:
            self._client.close()
            self._client = None
            self._db = None
