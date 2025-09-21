"""GraphContext for managing database dependencies."""

import time
from contextlib import asynccontextmanager, contextmanager
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Type, TypeVar

if TYPE_CHECKING:
    from .entities import Object

from jvspatial.db.database import Database
from jvspatial.db.factory import get_database

T = TypeVar("T", bound="Object")


# Simple performance monitor for tracking operations
class PerformanceMonitor:
    """Simple performance monitoring for database operations."""

    def __init__(self):
        self.db_operations: List[Dict[str, Any]] = []
        self.hook_executions: List[Dict[str, Any]] = []
        self.db_errors: List[Dict[str, Any]] = []

    def record_db_operation(
        self,
        collection: str,
        operation: str,
        duration: float,
        doc_size: int,
        version_conflict: bool = False,
    ):
        """Record a database operation."""
        self.db_operations.append(
            {
                "collection": collection,
                "operation": operation,
                "duration": duration,
                "doc_size": doc_size,
                "version_conflict": version_conflict,
                "timestamp": time.time(),
            }
        )

    def record_hook_execution(
        self,
        hook_name: str,
        duration: float,
        walker_type: str,
        target_type: Optional[str],
    ):
        """Record a hook execution."""
        self.hook_executions.append(
            {
                "hook_name": hook_name,
                "duration": duration,
                "walker_type": walker_type,
                "target_type": target_type,
                "timestamp": time.time(),
            }
        )

    def record_db_error(self, collection: str, operation: str, error: str):
        """Record a database error."""
        self.db_errors.append(
            {
                "collection": collection,
                "operation": operation,
                "error": error,
                "timestamp": time.time(),
            }
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        total_ops = len(self.db_operations)
        if total_ops == 0:
            return {"total_operations": 0}

        avg_duration = sum(op["duration"] for op in self.db_operations) / total_ops
        return {
            "total_operations": total_ops,
            "average_duration": avg_duration,
            "total_errors": len(self.db_errors),
            "hook_executions": len(self.hook_executions),
        }


# Global performance monitor instance
perf_monitor: Optional[PerformanceMonitor] = None


def enable_performance_monitoring():
    """Enable performance monitoring."""
    global perf_monitor
    perf_monitor = PerformanceMonitor()


def disable_performance_monitoring():
    """Disable performance monitoring."""
    global perf_monitor
    perf_monitor = None


def get_performance_stats() -> Optional[Dict[str, Any]]:
    """Get current performance statistics."""
    return perf_monitor.get_stats() if perf_monitor else None


class GraphContext:
    """Context manager for graph operations with dependency injection.

    Provides centralized database management and eliminates the need for
    scattered database selection across classes.

    Usage:
        # Create context with default database
        ctx = GraphContext()

        # Create context with specific database
        ctx = GraphContext(database=my_db)

        # Use context for operations
        node = await ctx.create_node(name="Test")
        retrieved = await ctx.get_node(node.id)
    """

    def __init__(self, database: Optional[Database] = None):
        """Initialize GraphContext.

        Args:
            database: Database instance to use. If None, uses factory default.
        """
        self._database = database

    @property
    def database(self) -> Database:
        """Get the database instance, initializing if needed."""
        if self._database is None:
            self._database = get_database()
        return self._database

    def set_database(self, database: Database) -> None:
        """Set a new database instance."""
        self._database = database

    # Entity creation methods
    async def create(self, entity_class: Type[T], **kwargs) -> T:
        """Create and save an entity instance.

        Args:
            entity_class: The entity class to instantiate
            **kwargs: Entity attributes

        Returns:
            Created and saved entity instance
        """
        entity = entity_class(**kwargs)
        entity._graph_context = self
        await self.save(entity)
        return entity

    async def get(self, entity_class: Type[T], entity_id: str) -> Optional[T]:
        """Retrieve an entity from the database by ID.

        Args:
            entity_class: The entity class type
            entity_id: ID of the entity to retrieve

        Returns:
            Entity instance if found, else None
        """
        # Import here to avoid circular imports
        from .entities import find_subclass_by_name

        collection = self._get_collection_name(entity_class.type_code)
        data = await self.database.get(collection, entity_id)

        if not data:
            return None

        stored_name = data.get("name", entity_class.__name__)
        target_class = find_subclass_by_name(entity_class, stored_name) or entity_class

        # Create object with proper subclass
        context_data = data["context"].copy()

        if entity_class.type_code == "n":
            # Handle Node-specific logic
            if "edges" in data:
                context_data["edge_ids"] = data["edges"]
            elif "edge_ids" in data["context"]:  # Handle legacy format
                context_data["edge_ids"] = data["context"]["edge_ids"]

            # Extract _data if present
            stored_data = context_data.pop("_data", {})
            entity = target_class(id=data["id"], **context_data)

        elif entity_class.type_code == "e":
            # Handle Edge-specific logic with source/target/bidirectional
            if "source" in data and "target" in data:
                # New format: source/target/bidirectional at top level
                source = data["source"]
                target = data["target"]
                bidirectional = data.get("bidirectional", True)
            else:
                # Context format: source/target/bidirectional in context
                source = context_data.get("source", "")
                target = context_data.get("target", "")
                bidirectional = context_data.get("bidirectional", True)

            # Remove these from context_data to avoid duplication
            context_data = {
                k: v
                for k, v in context_data.items()
                if k not in ["source", "target", "bidirectional"]
            }

            # Extract _data if present
            stored_data = context_data.pop("_data", {})

            entity = target_class(
                id=data["id"],
                source=source,
                target=target,
                bidirectional=bidirectional,
                **context_data,
            )

        else:
            # Handle other entity types
            stored_data = context_data.pop("_data", {})
            entity = target_class(id=data["id"], **context_data)

        entity._graph_context = self

        # Restore _data after object creation
        if stored_data:
            entity._data.update(stored_data)

        return entity

    async def save(self, entity):
        """Save an entity to the database.

        Args:
            entity: Entity instance to save

        Returns:
            The saved entity instance
        """
        record = entity.export()
        collection = self._get_collection_name(entity.type_code)
        await self.database.save(collection, record)
        return entity

    async def delete(self, entity, cascade: bool = True) -> None:
        """Delete an entity from the database.

        Args:
            entity: Entity instance to delete
            cascade: Whether to delete related entities
        """
        if cascade and entity.type_code == "n":
            await self._cascade_delete(entity)

        collection = self._get_collection_name(entity.type_code)
        await self.database.delete(collection, entity.id)

    async def _cascade_delete(self, node_entity) -> None:
        """Delete related objects when cascading."""
        if hasattr(node_entity, "edge_ids"):
            edge_ids = getattr(node_entity, "edge_ids", [])

            # Import Edge here to avoid circular imports
            from .entities import Edge

            for edge_id in edge_ids:
                try:
                    edge = await self.get(Edge, edge_id)
                    if edge:
                        await self.delete(edge, cascade=False)
                except Exception:
                    pass  # Continue with other edges

    def _get_collection_name(self, type_code: str) -> str:
        """Get the database collection name for a type code."""
        collection_map = {"n": "node", "e": "edge", "o": "object", "w": "walker"}
        return collection_map.get(type_code, "object")

    # Convenience methods for common entity types
    async def create_node(self, node_class=None, **kwargs):
        """Create a node with this context."""
        from .entities import Node

        cls = node_class or Node
        return await self.create(cls, **kwargs)

    async def create_edge(self, edge_class=None, **kwargs):
        """Create an edge with this context."""
        from .entities import Edge

        cls = edge_class or Edge
        return await self.create(cls, **kwargs)

    async def get_node(self, node_class, node_id: str):
        """Get a node by class and ID with this context.

        Args:
            node_class: The node class type to retrieve
            node_id: ID of the node to retrieve

        Returns:
            Node instance if found, else None
        """
        return await self.get(node_class, node_id)

    async def get_edge(self, edge_class, edge_id: str):
        """Get an edge by class and ID with this context.

        Args:
            edge_class: The edge class type to retrieve
            edge_id: ID of the edge to retrieve

        Returns:
            Edge instance if found, else None
        """
        return await self.get(edge_class, edge_id)

    async def save_node(self, node):
        """Save a node with this context.

        Args:
            node: Node instance to save

        Returns:
            The saved node instance
        """
        await self.save(node)
        return node

    async def save_edge(self, edge):
        """Save an edge with this context.

        Args:
            edge: Edge instance to save

        Returns:
            The saved edge instance
        """
        await self.save(edge)
        return edge

    async def delete_node(self, node, cascade: bool = True):
        """Delete a node with this context.

        Args:
            node: Node instance to delete
            cascade: Whether to cascade delete related edges

        Returns:
            True if deletion was successful
        """
        try:
            await self.delete(node, cascade=cascade)
            return True
        except Exception:
            return False

    async def delete_edge(self, edge):
        """Delete an edge with this context.

        Args:
            edge: Edge instance to delete

        Returns:
            True if deletion was successful
        """
        try:
            await self.delete(edge, cascade=False)
            return True
        except Exception:
            return False

    # Advanced query operations for performance optimization
    async def find_nodes(
        self, node_class, query: Dict[str, Any], limit: Optional[int] = None
    ) -> List:
        """Find nodes using database-level queries for better performance.

        Args:
            node_class: Node class to search for
            query: Database query parameters
            limit: Maximum number of results

        Returns:
            List of matching node instances
        """
        collection = self._get_collection_name(node_class.type_code)

        # Add class name filter to query for type safety
        db_query = {"name": node_class.__name__, **query}

        results = await self.database.find(collection, db_query)

        if limit:
            results = results[:limit]

        nodes = []
        for data in results:
            try:
                node = await self._deserialize_entity(node_class, data)
                if node:
                    nodes.append(node)
            except Exception:
                continue  # Skip invalid nodes

        return nodes

    async def find_edges_between(
        self, source_id: str, target_id: Optional[str] = None, edge_class=None, **kwargs
    ) -> List:
        """Find edges between nodes using database queries.

        Args:
            source_id: Source node ID
            target_id: Target node ID (optional)
            edge_class: Edge class to filter by
            **kwargs: Additional edge properties to match

        Returns:
            List of matching edge instances
        """
        from .entities import Edge

        edge_cls = edge_class or Edge

        source_query = {"$or": [{"source": source_id}, {"context.source": source_id}]}

        if target_id:
            target_query = {
                "$or": [{"target": target_id}, {"context.target": target_id}]
            }
            query: Dict[str, Any] = {"$and": [source_query, target_query]}
        else:
            query = source_query

        if edge_class:
            query["name"] = edge_class.__name__

        # Add additional property filters
        for key, value in kwargs.items():
            query[f"context.{key}"] = value

        collection = self._get_collection_name(edge_cls.type_code)
        results = await self.database.find(collection, query)

        edges = []
        for data in results:
            try:
                edge = await self._deserialize_entity(edge_cls, data)
                if edge:
                    edges.append(edge)
            except Exception:
                continue

        return edges

    async def _deserialize_entity(
        self, entity_class: Type[T], data: Dict[str, Any]
    ) -> Optional[T]:
        """Helper method to deserialize entity data into objects.

        Args:
            entity_class: Entity class to instantiate
            data: Raw entity data from database

        Returns:
            Entity instance or None if deserialization fails
        """
        try:
            # Import here to avoid circular imports
            from .entities import find_subclass_by_name

            stored_name = data.get("name", entity_class.__name__)
            target_class = (
                find_subclass_by_name(entity_class, stored_name) or entity_class
            )

            # Create object with proper subclass
            context_data = data["context"].copy()

            if entity_class.type_code == "n":
                # Handle Node-specific logic
                if "edges" in data:
                    context_data["edge_ids"] = data["edges"]
                elif "edge_ids" in data["context"]:  # Handle legacy format
                    context_data["edge_ids"] = data["context"]["edge_ids"]

                # Extract _data if present
                stored_data = context_data.pop("_data", {})
                entity = target_class(id=data["id"], **context_data)

            elif entity_class.type_code == "e":
                # Handle Edge-specific logic with source/target
                # Handle both new and legacy data formats
                if "source" in data and "target" in data:
                    # New format: source/target at top level
                    source = data["source"]
                    target = data["target"]
                    direction = data.get("direction", "both")
                else:
                    # Legacy format: source/target in context
                    source = context_data.get("source", "")
                    target = context_data.get("target", "")
                    direction = context_data.get("direction", "both")

                # Remove these from context_data to avoid duplication
                context_data = {
                    k: v
                    for k, v in context_data.items()
                    if k not in ["source", "target", "direction"]
                }

                # Extract _data if present
                stored_data = context_data.pop("_data", {})

                entity = target_class(
                    id=data["id"],
                    source=source,
                    target=target,
                    direction=direction,
                    **context_data,
                )

            else:
                # Handle other entity types
                stored_data = context_data.pop("_data", {})
                entity = target_class(id=data["id"], **context_data)

            entity._graph_context = self

            # Restore _data after object creation
            if stored_data:
                entity._data.update(stored_data)

            return entity
        except Exception:
            return None


# Global context instance for backwards compatibility
_default_context: Optional[GraphContext] = None


def get_default_context() -> GraphContext:
    """Get the default global context."""
    global _default_context
    if _default_context is None:
        _default_context = GraphContext()
    return _default_context


def set_default_context(context: GraphContext) -> None:
    """Set the default global context."""
    global _default_context
    _default_context = context


@contextmanager
def graph_context(database: Optional[Database] = None):
    """Context manager for temporary graph context.

    Usage:
        with graph_context(my_db) as ctx:
            node = await ctx.create_node(name="Test")
    """
    ctx = GraphContext(database)
    yield ctx


@asynccontextmanager
async def async_graph_context(database: Optional[Database] = None):
    """Async context manager for temporary graph context.

    Usage:
        async with async_graph_context(my_db) as ctx:
            node = await ctx.create_node(name="Test")
    """
    ctx = GraphContext(database)
    yield ctx
