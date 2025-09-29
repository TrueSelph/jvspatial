"""
Collection module for jvspatial agent framework.

This module provides collection management functionality with proper
exception handling and jvspatial integration patterns.
"""

from typing import Any, Dict, List, Optional, Type, TypeVar, Generic, Iterator, AsyncIterator
from abc import ABC, abstractmethod
import asyncio

from jvspatial.core.entities import Object
from jvspatial.exceptions import (
    JVSpatialError,
    ValidationError,
    EntityNotFoundError,
    ConfigurationError
)

T = TypeVar('T', bound=Object)


class Collection(Generic[T], Object):
    """
    Base collection class for managing groups of objects.
    
    Provides async-first collection operations with proper exception handling
    and integration with the jvspatial persistence layer.
    """
    
    type_code: str = "c"
    
    def __init__(self, item_type: Type[T], **kwargs):
        super().__init__(**kwargs)
        self.item_type = item_type
        self.items: List[T] = []
        self._index: Dict[str, int] = {}  # ID to index mapping for O(1) lookups
    
    # ============== CORE COLLECTION OPERATIONS ==============
    
    async def add(self, item: T) -> None:
        """Add an item to the collection."""
        if not isinstance(item, self.item_type):
            raise ValidationError(
                f"Item must be of type {self.item_type.__name__}",
                details={"expected_type": self.item_type.__name__, "actual_type": type(item).__name__}
            )
        
        if item.id in self._index:
            raise ValidationError(
                f"Item with ID {item.id} already exists in collection",
                details={"item_id": item.id}
            )
        
        self.items.append(item)
        self._index[item.id] = len(self.items) - 1
        await self.save()
    
    async def remove(self, item_id: str) -> bool:
        """Remove an item by ID."""
        if item_id not in self._index:
            return False
        
        index = self._index[item_id]
        del self.items[index]
        del self._index[item_id]
        
        # Rebuild index for items after the removed one
        self._rebuild_index()
        await self.save()
        return True
    
    async def get(self, item_id: str) -> Optional[T]:
        """Get an item by ID."""
        if item_id not in self._index:
            return None
        
        index = self._index[item_id]
        return self.items[index]
    
    async def find(self, **criteria) -> List[T]:
        """Find items matching the given criteria."""
        results = []
        
        for item in self.items:
            match = True
            for key, value in criteria.items():
                if not hasattr(item, key) or getattr(item, key) != value:
                    match = False
                    break
            
            if match:
                results.append(item)
        
        return results
    
    async def count(self) -> int:
        """Get the number of items in the collection."""
        return len(self.items)
    
    async def clear(self) -> None:
        """Remove all items from the collection."""
        self.items.clear()
        self._index.clear()
        await self.save()
    
    def _rebuild_index(self) -> None:
        """Rebuild the ID to index mapping."""
        self._index.clear()
        for i, item in enumerate(self.items):
            self._index[item.id] = i
    
    # ============== ITERATION SUPPORT ==============
    
    def __iter__(self) -> Iterator[T]:
        """Iterate over items in the collection."""
        return iter(self.items)
    
    def __len__(self) -> int:
        """Get the number of items in the collection."""
        return len(self.items)
    
    def __contains__(self, item_id: str) -> bool:
        """Check if an item ID exists in the collection."""
        return item_id in self._index
    
    # ============== ASYNC ITERATION ==============
    
    async def __aiter__(self) -> AsyncIterator[T]:
        """Async iterate over items in the collection."""
        for item in self.items:
            yield item
    
    # ============== VALIDATION AND HEALTH ==============
    
    async def validate(self) -> bool:
        """Validate the collection and all its items."""
        try:
            # Check if all items are valid
            for item in self.items:
                if hasattr(item, 'validate') and not await item.validate():
                    return False
            
            # Check index consistency
            if len(self._index) != len(self.items):
                return False
            
            # Check all items have unique IDs
            ids = [item.id for item in self.items]
            if len(set(ids)) != len(ids):
                return False
            
            return True
        except Exception:
            return False
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check on the collection."""
        health = {
            "status": "healthy",
            "issues": [],
            "warnings": [],
            "stats": {
                "total_items": len(self.items),
                "index_size": len(self._index)
            }
        }
        
        try:
            # Check for index inconsistencies
            if len(self._index) != len(self.items):
                health["issues"].append({
                    "type": "index_inconsistency",
                    "details": f"Index size ({len(self._index)}) != items size ({len(self.items)})"
                })
                health["status"] = "degraded"
            
            # Check for invalid items
            invalid_count = 0
            for item in self.items:
                if hasattr(item, 'validate'):
                    try:
                        if not await item.validate():
                            invalid_count += 1
                    except Exception:
                        invalid_count += 1
            
            if invalid_count > 0:
                health["warnings"].append({
                    "type": "invalid_items",
                    "count": invalid_count
                })
            
        except Exception as e:
            health["status"] = "unhealthy"
            health["issues"].append({
                "type": "health_check_error",
                "details": str(e)
            })
        
        return health


class AsyncCollection(Collection[T]):
    """
    Async-enhanced collection with additional async operations.
    """
    
    async def add_bulk(self, items: List[T]) -> int:
        """Add multiple items to the collection."""
        added_count = 0
        
        for item in items:
            try:
                await self.add(item)
                added_count += 1
            except ValidationError:
                # Skip invalid items but continue processing
                continue
        
        return added_count
    
    async def remove_bulk(self, item_ids: List[str]) -> int:
        """Remove multiple items by ID."""
        removed_count = 0
        
        for item_id in item_ids:
            if await self.remove(item_id):
                removed_count += 1
        
        return removed_count
    
    async def filter_async(self, predicate_func) -> List[T]:
        """Filter items using an async predicate function."""
        results = []
        
        for item in self.items:
            try:
                if await predicate_func(item):
                    results.append(item)
            except Exception:
                # Skip items that cause errors in the predicate
                continue
        
        return results
    
    async def map_async(self, transform_func):
        """Transform items using an async function."""
        results = []
        
        for item in self.items:
            try:
                result = await transform_func(item)
                results.append(result)
            except Exception as e:
                raise ValidationError(f"Transform failed for item {item.id}: {e}")
        
        return results


# ============== UTILITY FUNCTIONS ==============

async def create_collection(item_type: Type[T], **kwargs) -> Collection[T]:
    """Create a new collection for the given item type."""
    try:
        collection = Collection(item_type, **kwargs)
        await collection.save()
        return collection
    except Exception as e:
        raise ConfigurationError(f"Failed to create collection: {e}")


async def load_collection(collection_id: str, item_type: Type[T]) -> Optional[Collection[T]]:
    """Load an existing collection by ID."""
    try:
        # This would integrate with the actual persistence layer
        # For now, just return None as this is a basic implementation
        return None
    except Exception as e:
        raise EntityNotFoundError("Collection", collection_id)


# ============== SPECIALIZED COLLECTIONS ==============

class NodeCollection(Collection):
    """Specialized collection for Node objects."""
    
    def __init__(self, **kwargs):
        from .core.entities import Node
        super().__init__(Node, **kwargs)
    
    async def find_by_type(self, node_type: str) -> List:
        """Find nodes by their type."""
        return [node for node in self.items if node.__class__.__name__ == node_type]


class EdgeCollection(Collection):
    """Specialized collection for Edge objects."""
    
    def __init__(self, **kwargs):
        from .core.entities import Edge
        super().__init__(Edge, **kwargs)
    
    async def find_connecting(self, source_id: str, target_id: str) -> List:
        """Find edges connecting specific nodes."""
        return [
            edge for edge in self.items 
            if (edge.source == source_id and edge.target == target_id) or
               (edge.bidirectional and edge.source == target_id and edge.target == source_id)
        ]