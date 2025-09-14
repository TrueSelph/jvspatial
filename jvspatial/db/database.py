from abc import ABC, abstractmethod
from typing import List, Optional


class Database(ABC):
    @abstractmethod
    async def save(self, collection: str, data: dict) -> dict: ...

    @abstractmethod
    async def get(self, collection: str, id: str) -> Optional[dict]: ...

    @abstractmethod
    async def delete(self, collection: str, id: str): ...

    @abstractmethod
    async def find(self, collection: str, query: dict) -> List[dict]: ...
