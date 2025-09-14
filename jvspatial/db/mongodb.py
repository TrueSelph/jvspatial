"""MongoDB database implementation for spatial graph persistence."""

import asyncio
import os
from typing import Any, List, Optional

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import ReturnDocument

from jvspatial.db.database import Database


class MongoDB(Database):
    """MongoDB-based database implementation."""

    _client: Optional[AsyncIOMotorClient] = None
    _db = None
    _lock = asyncio.Lock()

    async def get_db(self: "MongoDB") -> Any:
        """Get database instance with thread-safe initialization.

        Returns:
            MongoDB database instance
        """
        if self._client is None:
            async with self._lock:
                if self._client is None:  # Double-check locking
                    uri = os.getenv(
                        "JVSPATIAL_MONGODB_URI", "mongodb://localhost:27017"
                    )
                    db_name = os.getenv("JVSPATIAL_MONGODB_DB_NAME", "jvspatial_db")

                    self._client = AsyncIOMotorClient(
                        uri,
                        maxPoolSize=10,
                        minPoolSize=5,
                        connectTimeoutMS=30000,
                        socketTimeoutMS=30000,
                    )
                    self._db = self._client.get_database(db_name)
        return self._db

    async def _get_collection(
        self: "MongoDB", collection: str
    ) -> AsyncIOMotorCollection:
        """Get collection with connection pooling.

        Args:
            collection: Collection name

        Returns:
            MongoDB collection instance
        """
        db = await self.get_db()
        return db[collection]

    async def save(self: "MongoDB", collection: str, data: dict) -> dict:
        """Save document to MongoDB.

        Args:
            collection: Collection name
            data: Document data

        Returns:
            Saved document
        """
        coll = await self._get_collection(collection)
        if "id" in data:
            return await coll.find_one_and_update(
                {"id": data["id"]},
                {"$set": data},
                return_document=ReturnDocument.AFTER,
                upsert=True,
            )
        else:
            result = await coll.insert_one(data)
            data["id"] = str(result.inserted_id)
            return data

    async def get(self: "MongoDB", collection: str, id: str) -> Optional[dict]:
        """Get document by ID.

        Args:
            collection: Collection name
            id: Document ID

        Returns:
            Document data or None if not found
        """
        coll = await self._get_collection(collection)
        return await coll.find_one({"id": id})

    async def delete(self: "MongoDB", collection: str, id: str) -> None:
        """Delete document by ID.

        Args:
            collection: Collection name
            id: Document ID
        """
        coll = await self._get_collection(collection)
        await coll.delete_one({"id": id})

    async def find(self: "MongoDB", collection: str, query: dict) -> List[dict]:
        """Find documents matching query.

        Args:
            collection: Collection name
            query: Query parameters

        Returns:
            List of matching documents
        """
        coll = await self._get_collection(collection)
        return [doc async for doc in coll.find(query)]
