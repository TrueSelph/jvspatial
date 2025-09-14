import os
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from pymongo import ReturnDocument
from typing import Any, List, Optional
import asyncio

from jvspatial.db.database import Database


class MongoDB(Database):
    _client: AsyncIOMotorClient = None
    _db = None
    _lock = asyncio.Lock()

    async def get_db(self):
        """Get database instance with thread-safe initialization."""
        if self._client is None:
            async with self._lock:
                if self._client is None:  # Double-check locking
                    uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
                    self._client = AsyncIOMotorClient(
                        uri,
                        maxPoolSize=10,
                        minPoolSize=5,
                        connectTimeoutMS=30000,
                        socketTimeoutMS=30000,
                    )
                    db_name = os.getenv("MONGODB_DATABASE_NAME", "jvspatial_db")
                    self._db = self._client.get_database(db_name)
        return self._db

    async def _get_collection(self, collection: str) -> AsyncIOMotorCollection:
        """Helper to get collection with connection pooling."""
        db = await self.get_db()
        return db[collection]

    async def save(self, collection: str, data: dict) -> dict:
        coll = await self._get_collection(collection)
        if "id" in data:
            result = await coll.find_one_and_update(
                {"id": data["id"]},
                {"$set": data},
                return_document=ReturnDocument.AFTER,
                upsert=True,
            )
            return result
        else:
            result = await coll.insert_one(data)
            data["id"] = str(result.inserted_id)
            return data

    async def get(self, collection: str, id: str) -> Optional[dict]:
        coll = await self._get_collection(collection)
        return await coll.find_one({"id": id})

    async def delete(self, collection: str, id: str) -> bool:
        coll = await self._get_collection(collection)
        result = await coll.delete_one({"id": id})
        return result.deleted_count > 0

    async def find(self, collection: str, query: dict) -> List[dict]:
        coll = await self._get_collection(collection)
        return [doc async for doc in coll.find(query)]
