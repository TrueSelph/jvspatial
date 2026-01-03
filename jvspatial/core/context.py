"""GraphContext for managing database dependencies."""

import logging
import time
from contextlib import asynccontextmanager, contextmanager
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncIterator,
    Dict,
    List,
    Optional,
    Set,
    Type,
    TypeVar,
    cast,
)

from jvspatial.db.database import Database
from jvspatial.db.factory import create_database, get_current_database
from jvspatial.db.manager import get_database_manager

if TYPE_CHECKING:
    from .entities import Object

T = TypeVar("T", bound="Object")

logger = logging.getLogger(__name__)

# Global registry to track which collections have had indexes ensured
_ensured_indexes: Set[str] = set()


# Simple performance monitor for tracking operations
class PerformanceMonitor:
    """Enhanced performance monitoring for database operations and general operations."""

    def __init__(self) -> None:
        self.db_operations: List[Dict[str, Any]] = []
        self.hook_executions: List[Dict[str, Any]] = []
        self.db_errors: List[Dict[str, Any]] = []
        self.general_operations: List[Dict[str, Any]] = []
        self.general_errors: List[Dict[str, Any]] = []

    async def record_db_operation(
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

    async def record_hook_execution(
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

    async def record_db_error(self, collection: str, operation: str, error: str):
        """Record a database error."""
        self.db_errors.append(
            {
                "collection": collection,
                "operation": operation,
                "error": error,
                "timestamp": time.time(),
            }
        )

    async def record_operation(
        self, operation_name: str, duration: float, **kwargs: Any
    ):
        """Record a general operation.

        Args:
            operation_name: Name of the operation
            duration: Duration in seconds
            **kwargs: Additional operation metadata
        """
        self.general_operations.append(
            {
                "operation_name": operation_name,
                "duration": duration,
                "timestamp": time.time(),
                **kwargs,
            }
        )

    async def record_error(self, operation_name: str, error: str):
        """Record a general error.

        Args:
            operation_name: Name of the operation that failed
            error: Error message
        """
        self.general_errors.append(
            {
                "operation_name": operation_name,
                "error": error,
                "timestamp": time.time(),
            }
        )

    async def get_stats(self) -> Dict[str, Any]:
        """Get comprehensive performance statistics."""
        total_db_ops = len(self.db_operations)
        total_general_ops = len(self.general_operations)
        total_ops = total_db_ops + total_general_ops

        if total_ops == 0:
            return {"total_operations": 0}

        # Calculate database operation statistics
        db_stats = {}
        if total_db_ops > 0:
            avg_db_duration = (
                sum(op["duration"] for op in self.db_operations) / total_db_ops
            )
            db_stats = {
                "db_operations": total_db_ops,
                "avg_db_duration": avg_db_duration,
                "db_errors": len(self.db_errors),
            }

        # Calculate general operation statistics
        general_stats = {}
        if total_general_ops > 0:
            avg_general_duration = (
                sum(op["duration"] for op in self.general_operations)
                / total_general_ops
            )
            general_stats = {
                "general_operations": total_general_ops,
                "avg_general_duration": avg_general_duration,
                "general_errors": len(self.general_errors),
            }

        return {
            "total_operations": total_ops,
            "hook_executions": len(self.hook_executions),
            **db_stats,
            **general_stats,
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


async def get_performance_stats() -> Optional[Dict[str, Any]]:
    """Get current performance statistics."""
    return await perf_monitor.get_stats() if perf_monitor else None


class GraphContext:
    """Context manager for graph operations with dependency injection and built-in performance monitoring.

    Provides centralized database management and eliminates the need for
    scattered database selection across classes. Includes integrated performance
    monitoring for tracking operations and optimizing performance.

    Usage:
        # Create context with default database and performance monitoring
        ctx = GraphContext()

        # Create context with specific database and performance monitoring
        ctx = GraphContext(database=my_db, enable_performance_monitoring=True)

        # Use context for operations
        node = ctx.create_node(name="Test")
        retrieved = ctx.get_node(node.id)
    """

    def __init__(
        self,
        database: Optional[Database] = None,
        cache_backend=None,
        enable_performance_monitoring: bool = True,
    ):
        """Initialize GraphContext with integrated performance monitoring.

        Args:
            database: Database instance to use. If None, uses factory default.
            cache_backend: Cache backend instance (CacheBackend). If None, creates
                          one based on environment configuration. Can be:
                          - CacheBackend instance
                          - None (auto-detect from environment)
            enable_performance_monitoring: Whether to enable built-in performance monitoring
        """
        self._database = database
        self._perf_monitoring_enabled = enable_performance_monitoring
        self._perf_monitor = (
            PerformanceMonitor() if enable_performance_monitoring else None
        )

        # Initialize cache backend
        if cache_backend is None:
            from jvspatial.cache import create_cache

            self._cache = create_cache()
        else:
            self._cache = cache_backend

    @property
    def database(self) -> Database:
        """Get the database instance, initializing if needed."""
        if self._database is None:
            # Use current database from manager if available
            try:
                from jvspatial.db.manager import DatabaseManager

                # Check if DatabaseManager exists and was auto-created (not initialized by Server)
                # If it was auto-created, it uses default 'jvdb' path which we want to avoid
                if (
                    DatabaseManager._instance is not None
                    and DatabaseManager._instance._auto_created
                ):
                    # DatabaseManager was auto-created with default 'jvdb' path
                    # Don't use it - require explicit database configuration
                    raise RuntimeError(
                        "Database not configured. GraphContext requires a database to be set "
                        "explicitly or DatabaseManager to be initialized by Server first."
                    )

                self._database = get_current_database()
            except RuntimeError as e:
                # Re-raise our explicit error
                if "Database not configured" in str(e):
                    raise
                # For other RuntimeErrors (e.g., prime database not initialized),
                # fall back to creating default database only if DatabaseManager exists and wasn't auto-created
                from jvspatial.db.manager import DatabaseManager

                if (
                    DatabaseManager._instance is not None
                    and not DatabaseManager._instance._auto_created
                ):
                    # DatabaseManager exists and was explicitly initialized, create default
                    self._database = create_database()
                else:
                    # DatabaseManager doesn't exist or was auto-created - don't create default database
                    raise RuntimeError(
                        "Database not configured. GraphContext requires a database to be set "
                        "explicitly or DatabaseManager to be initialized by Server first."
                    )
            except Exception:
                # For other exceptions, only create default if DatabaseManager exists and wasn't auto-created
                from jvspatial.db.manager import DatabaseManager

                if (
                    DatabaseManager._instance is not None
                    and not DatabaseManager._instance._auto_created
                ):
                    # DatabaseManager exists and was explicitly initialized, create default database
                    self._database = create_database()
                else:
                    # DatabaseManager doesn't exist or was auto-created - don't create default database
                    raise RuntimeError(
                        "Database not configured. GraphContext requires a database to be set "
                        "explicitly or DatabaseManager to be initialized by Server first."
                    )
        return self._database

    async def set_database(self, database: Database) -> None:
        """Set a new database instance."""
        self._database = database
        # Clear cache when database changes
        await self.clear_cache()

    def switch_database(self, name: str) -> None:
        """Switch to a different database by name using DatabaseManager.

        Args:
            name: Database name to switch to

        Raises:
            ValueError: If database is not registered
        """
        manager = get_database_manager()
        manager.set_current_database(name)
        # Update internal database reference
        self._database = manager.get_current_database()

    def use_prime_database(self) -> None:
        """Switch to the prime database for core persistence operations.

        The prime database is always used for authentication, session management,
        and system-level data.
        """
        manager = get_database_manager()
        manager.set_current_database("prime")
        self._database = manager.get_prime_database()

    def _get_entity_type_code(self, entity_class: Type[T]) -> str:
        """Get the type_code for an entity class.

        Args:
            entity_class: The entity class to get type_code for

        Returns:
            The type_code string, defaulting to 'o' if not found
        """
        type_code_field = entity_class.model_fields.get("type_code")
        if type_code_field and hasattr(type_code_field, "default"):
            default_value = type_code_field.default
            if isinstance(default_value, str):
                return default_value
        return "o"

    async def _get_from_cache(self, entity_id: str) -> Optional[Any]:
        """Get entity from cache if available."""
        return await self._cache.get(entity_id)

    async def _add_to_cache(self, entity_id: str, entity: Any) -> None:
        """Add entity to cache."""
        await self._cache.set(entity_id, entity)

    async def clear_cache(self) -> None:
        """Clear the entity cache."""
        await self._cache.clear()

    async def get_performance_stats(self) -> Optional[Dict[str, Any]]:
        """Get performance statistics for this GraphContext instance.

        Returns:
            Performance statistics dictionary if monitoring is enabled, None otherwise
        """
        if not self._perf_monitoring_enabled or not self._perf_monitor:
            return None

        return await self._perf_monitor.get_stats()

    def enable_performance_monitoring(self) -> None:
        """Enable performance monitoring for this GraphContext instance."""
        if not self._perf_monitoring_enabled:
            self._perf_monitoring_enabled = True
            self._perf_monitor = PerformanceMonitor()

    def disable_performance_monitoring(self) -> None:
        """Disable performance monitoring for this GraphContext instance."""
        self._perf_monitoring_enabled = False
        self._perf_monitor = None

    async def _record_operation(
        self, operation_name: str, duration: float, **kwargs: Any
    ) -> None:
        """Record an operation for performance monitoring.

        Args:
            operation_name: Name of the operation
            duration: Duration in seconds
            **kwargs: Additional operation metadata
        """
        if not self._perf_monitoring_enabled or not self._perf_monitor:
            return

        # Record generic operation
        if hasattr(self._perf_monitor, "record_operation"):
            await self._perf_monitor.record_operation(
                operation_name, duration, **kwargs
            )

    async def _record_error(self, operation_name: str, error: str) -> None:
        """Record an error for performance monitoring.

        Args:
            operation_name: Name of the operation that failed
            error: Error message
        """
        if not self._perf_monitoring_enabled or not self._perf_monitor:
            return

        # Record error
        if hasattr(self._perf_monitor, "record_error"):
            await self._perf_monitor.record_error(operation_name, error)

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return self._cache.get_stats()

    # Entity creation methods
    async def create(self, entity_class: Type[T], **kwargs) -> T:
        """Create and save an entity instance.

        Args:
            entity_class: The entity class to instantiate
            **kwargs: Entity attributes

        Returns:
            Created and saved entity instance
        """
        # Check if the entity class has overridden create() method
        # If so, delegate to it (e.g., Root.create() enforces singleton)
        if hasattr(entity_class, "create"):
            # Check if create() is actually overridden (not inherited from Object)
            from .entities.object import Object

            if entity_class.create is not Object.create:
                # Use the overridden create() method
                entity = await entity_class.create(**kwargs)
                entity._graph_context = self
                return entity

        # Default behavior: instantiate and save
        entity = entity_class(**kwargs)
        entity._graph_context = self
        await self.save(entity)
        return entity

    async def get(self, entity_class: Type[T], entity_id: str) -> Optional[T]:
        """Retrieve an entity from the database by ID with caching.

        Args:
            entity_class: The entity class type
            entity_id: ID of the entity to retrieve

        Returns:
            Entity instance if found, else None
        """
        # Check cache first
        cached = await self._get_from_cache(entity_id)
        if cached and isinstance(cached, entity_class):
            return cast(T, cached)

        # Import here to avoid circular imports
        from .utils import find_subclass_by_name

        # Get type_code from model fields
        type_code = self._get_entity_type_code(entity_class)
        collection = self._get_collection_name(type_code)
        db = self.database
        data = await db.get(collection, entity_id)

        if not data:
            return None

        # Check entity class before deserialization - ensure stored entity matches requested class
        # This ensures class-aware get() - e.g., Agent.get() won't return an Action
        stored_entity = data.get("entity")
        if stored_entity:

            # Only proceed if stored entity is the requested class or a subclass of it
            target_class = find_subclass_by_name(entity_class, stored_entity)
            if target_class is None:
                # Stored entity is not the requested class or its subclass - return None
                return None

        # Deserialize the entity
        entity = await self._deserialize_entity(entity_class, data)

        # Additional safety check: verify the deserialized entity is an instance of the requested class
        if entity is not None and not isinstance(entity, entity_class):
            return None

        # Add to cache
        if entity is not None:
            await self._add_to_cache(entity_id, entity)

        return entity

    async def _remove_from_cache(self, entity_id: str) -> None:
        """Remove entity from cache."""
        if self._cache:
            await self._cache.delete(entity_id)

    async def save(self, entity):
        """Save an entity to the database.

        Args:
            entity: Entity instance to save

        Returns:
            The saved entity instance
        """
        # Export entity - Node, Edge, and Walker return nested format
        if hasattr(entity, "type_code"):
            type_code = getattr(entity, "type_code", "")
            if type_code == "n":  # Node - include edges for database persistence
                record = await entity.export(include_edges=True)
                # Ensure entity field is set
                if "entity" not in record:
                    record["entity"] = entity.entity
            elif type_code in ("e", "w"):  # Edge or Walker
                record = await entity.export()
                # Ensure entity field is set
                if "entity" not in record:
                    record["entity"] = entity.entity
            else:
                # For Objects, export returns nested format (id, entity, context)
                record = await entity.export()
                # Ensure ID follows proper format: type_code.ClassName.hex_id
                # Check entity's ID directly (it's transient so not in export)
                entity_id = getattr(entity, "id", None)
                if entity_id:
                    id_parts = entity_id.split(".")
                    # Check if ID matches expected format: type_code.ClassName.hex_id
                    if (
                        len(id_parts) != 3
                        or id_parts[0] != entity.type_code
                        or id_parts[1] != entity.__class__.__name__
                    ):
                        # ID doesn't match expected format, regenerate it
                        from jvspatial.core.utils import generate_id

                        new_id = generate_id(
                            entity.type_code, entity.__class__.__name__
                        )
                        object.__setattr__(entity, "id", new_id)
                        record["id"] = new_id
                    # ID is in record from export()
        else:
            record = await entity.export()
            from jvspatial.utils.serialization import serialize_datetime

            record = serialize_datetime(record)
            # Ensure entity field is set
            if "entity" not in record and hasattr(entity, "entity"):
                record["entity"] = entity.entity

        # Apply text normalization if enabled
        # Note: For nodes/edges/walkers, datetimes are already serialized in export()
        # normalize_data only processes strings, so it's safe to apply to all records
        from jvspatial.utils.normalization import (
            is_text_normalization_enabled,
            normalize_data,
        )

        if is_text_normalization_enabled():
            record = normalize_data(record)

        # Use entity's get_collection_name method if available, otherwise use type_code
        if hasattr(entity, "get_collection_name"):
            collection = entity.get_collection_name()
        else:
            # Use type_code-based collection name
            type_code = entity.type_code
            if type_code == "n":
                collection = "node"
            elif type_code == "e":
                collection = "edge"
            else:
                collection = type_code.lower()

        db = self.database
        await db.save(collection, record)
        # Update cache with latest version
        await self._add_to_cache(entity.id, entity)
        return entity

    async def delete(self, entity, cascade: bool = False) -> None:
        """Delete an entity from the database.

        For Node entities, this method delegates to Node.delete() which handles
        cascading deletion of edges and dependent nodes. For Object entities (including
        Edge), this method performs simple entity deletion.

        Args:
            entity: Entity instance to delete
            cascade: Whether to cascade deletion (only applies to Node entities)
        """
        # For Node entities, delegate to Node.delete() to ensure proper edge cleanup
        # and cascade handling. However, if cascade=False and we're being called
        # from within Node.delete() (which has already cleaned up edges), we should
        # do simple deletion to avoid infinite recursion.
        from .entities.node import Node

        if isinstance(entity, Node):
            # Check if this is a recursive call from Node.delete() by checking
            # if cascade=False and the node has no edges (cleaned up by Node.delete())
            if not cascade and len(entity.edge_ids) == 0:
                # Node.delete() has cleaned up edges, just delete the entity
                collection = self._get_collection_name(entity.type_code)
                db = self.database
                await db.delete(collection, entity.id)
                await self._cache.delete(entity.id)
            else:
                # Delegate to Node.delete() for proper edge cleanup and cascading
                await entity.delete(cascade=cascade)
            return

        # For Object entities (including Edge), perform simple deletion
        collection = self._get_collection_name(entity.type_code)
        db = self.database
        await db.delete(collection, entity.id)
        # Remove from cache
        await self._cache.delete(entity.id)

    async def export_graph(
        self,
        format: str = "dot",
        output_file: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """Export the graph in a renderable format.

        Args:
            format: Output format - "dot" (Graphviz) or "mermaid"
            output_file: Optional file path to save the output. If provided, the graph
                        will be written to this file in addition to being returned.
            **kwargs: Additional format-specific options

        Returns:
            Graph representation string in the specified format

        Example:
            ```python
            context = GraphContext()

            # Generate DOT format
            dot_graph = await context.export_graph(format="dot", rankdir="LR")

            # Generate Mermaid format
            mermaid_graph = await context.export_graph(
                format="mermaid",
                direction="LR",
                include_attributes=True
            )

            # Save to file optionally
            dot_graph = await context.export_graph(
                format="dot",
                output_file="graph.dot",
                rankdir="LR"
            )
            ```

        See `jvspatial.core.graph` for detailed options.
        """
        from .graph import export_graph

        return await export_graph(
            self, format=format, output_file=output_file, **kwargs
        )

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

        Note: This method calls Node.delete() which handles cascading deletion
        of edges and dependent nodes. The cascade parameter is passed to Node.delete().

        Args:
            node: Node instance to delete
            cascade: Whether to cascade delete related edges and dependent nodes

        Returns:
            True if deletion was successful
        """
        try:
            # Use Node.delete() which handles cascading
            await node.delete(cascade=cascade)
            return True
        except Exception:
            return False

    async def delete_edge(self, edge):
        """Delete an edge with this context.

        Edge entities are not connected by edges and are simply removed from the database.

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
        collection = self._get_collection_name(self._get_entity_type_code(node_class))

        # Add class name filter to query for type safety
        db_query = {"entity": node_class.__name__, **query}

        db = self.database
        results = await db.find(collection, db_query)

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

    async def ensure_indexes(self, entity_class: Type[T]) -> None:
        """Ensure indexes are created for the given entity class.

        This method retrieves index definitions from the entity class and creates
        them in the database if they don't already exist. Index creation is idempotent.

        Args:
            entity_class: Entity class to ensure indexes for
        """
        if not hasattr(entity_class, "get_indexes"):
            return  # Class doesn't support indexes

        # Get collection name
        type_code = self._get_entity_type_code(entity_class)
        collection = self._get_collection_name(type_code)

        # Check if we've already ensured indexes for this collection
        collection_key = f"{collection}:{entity_class.__name__}"
        if collection_key in _ensured_indexes:
            return  # Already ensured

        # Get index definitions from the class
        indexes = entity_class.get_indexes()
        if not indexes:
            _ensured_indexes.add(collection_key)
            return  # No indexes defined

        # Check if database supports indexing
        if not hasattr(self.database, "create_index"):
            _ensured_indexes.add(collection_key)
            return  # Database doesn't support indexing

        # Create each index
        for index_def in indexes:
            try:
                if "field" in index_def:
                    # Single-field index
                    await self.database.create_index(
                        collection,
                        index_def["field"],
                        unique=index_def.get("unique", False),
                    )
                elif "fields" in index_def:
                    # Compound index
                    await self.database.create_index(
                        collection,
                        index_def["fields"],
                        unique=index_def.get("unique", False),
                    )
            except Exception as e:
                # Log error but continue with other indexes
                logger.warning(
                    f"Failed to create index for {entity_class.__name__} "
                    f"on collection '{collection}': {e}"
                )

        # Mark as ensured
        _ensured_indexes.add(collection_key)

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

        query: Dict[str, Any] = {}

        if source_id is not None:
            query["source"] = source_id
        if target_id is not None:
            query["target"] = target_id

        # Filter by edge class if specified
        if edge_class:
            query["entity"] = edge_class.__name__

        # Add additional property filters
        for key, value in kwargs.items():
            query[f"context.{key}"] = value

        collection = self._get_collection_name(self._get_entity_type_code(edge_cls))
        db = self.database
        results = await db.find(collection, query)

        edges = []
        for data in results:
            try:
                edge = await self._deserialize_entity(edge_cls, data)
                if edge is not None:
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
            from .utils import find_subclass_by_name

            # Use entity field for class identification
            stored_entity = data.get("entity", entity_class.__name__)
            target_class = (
                find_subclass_by_name(entity_class, stored_entity) or entity_class
            )

            # Create object with proper subclass
            # All entities use nested format with context field
            if "context" not in data:
                raise ValueError(
                    f"Entity data missing 'context' field: {data.get('id', 'unknown')}"
                )
            context_data = data["context"].copy()

            entity_type_code = self._get_entity_type_code(entity_class)

            if entity_type_code == "n":
                # Handle Node-specific logic
                # Extract edge_ids from data (stored as "edges" at top level)
                # Edges are included in database exports but excluded from default exports
                edge_ids = data.get("edges", [])

                # Remove edge_ids, id, and type_code from context_data as they're handled separately
                context_data.pop("edge_ids", None)
                context_data.pop("id", None)
                context_data.pop("type_code", None)

                entity = target_class(id=data["id"], edge_ids=edge_ids, **context_data)

            elif entity_type_code == "e":
                # Handle Edge-specific logic with source/target at top level
                source = data["source"]
                target = data["target"]
                bidirectional = data.get("bidirectional", True)

                # Remove these from context_data to avoid duplication
                context_data.pop("source", None)
                context_data.pop("target", None)
                context_data.pop("bidirectional", None)
                context_data.pop("id", None)
                context_data.pop("type_code", None)

                entity = target_class(
                    id=data["id"],
                    source=source,
                    target=target,
                    bidirectional=bidirectional,
                    **context_data,
                )

            else:
                # Handle Object types
                # Remove system fields from context_data
                context_data.pop("id", None)
                context_data.pop("type_code", None)
                context_data.pop(
                    "entity", None
                )  # entity is at top level, not in context
                entity = target_class(id=data["id"], **context_data)

            entity._graph_context = self

            return entity
        except Exception:
            return None

    # Batch operations for improved performance
    async def save_batch(self, entities: List[Any]) -> List[Any]:
        """Save multiple entities in a single transaction.

        Args:
            entities: List of entity instances to save

        Returns:
            List of saved entity instances
        """
        if not entities:
            return []

        # Group entities by type for efficient batch operations
        entities_by_type: Dict[str, List[Any]] = {}
        for entity in entities:
            collection = self._get_collection_name(entity.type_code)
            if collection not in entities_by_type:
                entities_by_type[collection] = []
            entities_by_type[collection].append(entity)

        saved_entities = []

        # Process each type group
        for collection, type_entities in entities_by_type.items():
            # Export all entities of this type
            records = []
            for entity in type_entities:
                record = await entity.export()
                records.append(record)

            # Save all records of this type
            db = self.database
            for i, record in enumerate(records):
                try:
                    await db.save(collection, record)
                    # Update cache with latest version
                    await self._add_to_cache(record["id"], type_entities[i])
                    saved_entities.append(type_entities[i])
                except Exception as e:
                    # Log error but continue with other entities
                    print(
                        f"Failed to save entity {type_entities[i].get('id', 'unknown')}: {e}"
                    )
                    continue

        return saved_entities

    async def get_batch(self, entity_class: Type[T], ids: List[str]) -> List[T]:
        """Retrieve multiple entities by ID.

        Args:
            entity_class: Entity class type to retrieve
            ids: List of entity IDs to retrieve

        Returns:
            List of entity instances (may be shorter than input if some not found)
        """
        if not ids:
            return []

        # Check cache first
        cached_entities = []
        uncached_ids = []

        for entity_id in ids:
            cached_entity = await self._get_from_cache(entity_id)
            if cached_entity:
                cached_entities.append(cached_entity)
            else:
                uncached_ids.append(entity_id)

        # Fetch uncached entities from database
        if uncached_ids:
            collection = self._get_collection_name(entity_class.type_code)
            db = self.database

            # Use database batch query if available
            query = {"id": {"$in": uncached_ids}}
            results = await db.find(collection, query)

            # Deserialize results
            for data in results:
                try:
                    entity = await self._deserialize_entity(entity_class, data)
                    if entity:
                        await self._add_to_cache(entity.id, entity)
                        cached_entities.append(entity)
                except Exception:
                    continue

        return cached_entities

    async def delete_batch(self, entities: List[Any]) -> None:
        """Delete multiple entities in a single transaction.

        Args:
            entities: List of entity instances to delete
        """
        if not entities:
            return

        # Group entities by type for efficient batch operations
        entities_by_type: Dict[str, List[Any]] = {}
        for entity in entities:
            collection = self._get_collection_name(entity.type_code)
            if collection not in entities_by_type:
                entities_by_type[collection] = []
            entities_by_type[collection].append(entity)

        # Process each type group
        for collection, type_entities in entities_by_type.items():
            db = self.database
            for entity in type_entities:
                try:
                    await db.delete(collection, entity["id"])
                    # Remove from cache
                    await self._cache.delete(entity["id"])
                except Exception as e:
                    # Log error but continue with other entities
                    print(f"Failed to delete entity {entity.get('id', 'unknown')}: {e}")
                    continue

    # Async iterators for large datasets
    async def async_node_iterator(
        self, node_class, query: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[T]:
        """Async iterator for large node collections.

        Args:
            node_class: Node class to iterate over
            query: Database query parameters

        Yields:
            Node instances one at a time
        """
        if query is None:
            query = {}

        collection = self._get_collection_name(node_class.type_code)
        db = self.database

        # Use database cursor if available, otherwise use find
        if hasattr(db, "async_find"):
            async for data in db.async_find(collection, query):
                entity = await self._deserialize_entity(node_class, data)
                if entity:
                    yield entity
        else:
            # Use regular find
            results = await db.find(collection, query)
            for data in results:
                entity = await self._deserialize_entity(node_class, data)
                if entity:
                    yield entity

    async def async_edge_iterator(
        self, edge_class, query: Optional[Dict[str, Any]] = None
    ) -> AsyncIterator[T]:
        """Async iterator for large edge collections.

        Args:
            edge_class: Edge class to iterate over
            query: Database query parameters

        Yields:
            Edge instances one at a time
        """
        if query is None:
            query = {}

        collection = self._get_collection_name(edge_class.type_code)
        db = self.database

        # Use database cursor if available, otherwise use find
        if hasattr(db, "async_find"):
            async for data in db.async_find(collection, query):
                entity = await self._deserialize_entity(edge_class, data)
                if entity:
                    yield entity
        else:
            # Use regular find
            results = await db.find(collection, query)
            for data in results:
                entity = await self._deserialize_entity(edge_class, data)
                if entity:
                    yield entity


# Global context instance
_default_context: Optional[GraphContext] = None


def get_default_context() -> GraphContext:
    """Get the default global context."""
    global _default_context
    if _default_context is None:
        # Check if DatabaseManager was auto-created (not initialized by Server)
        # If so, don't create a default GraphContext yet - wait for Server to initialize
        from jvspatial.db.manager import DatabaseManager

        if (
            DatabaseManager._instance is not None
            and DatabaseManager._instance._auto_created
        ):
            # DatabaseManager was auto-created with default 'jvdb' path
            # Don't create default context - Server should initialize it
            raise RuntimeError(
                "Default GraphContext not initialized. Server must initialize the database "
                "before accessing the default context. Ensure Server is initialized before "
                "calling Root.get() or other operations that require a database."
            )
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
        with await graph_context(my_db) as ctx:
            node = ctx.create_node(name="Test")
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


@asynccontextmanager
async def async_transaction_context(database: Optional[Database] = None):
    """Async context manager for database transactions.

    Usage:
        async with async_transaction_context(my_db) as ctx:
            node = await ctx.create_node(name="Test")
            # All operations are automatically committed
    """
    ctx = GraphContext(database)
    try:
        # Start transaction if database supports it
        if hasattr(ctx.database, "begin_transaction"):
            await ctx.database.begin_transaction()
        yield ctx
        # Commit transaction
        if hasattr(ctx.database, "commit_transaction"):
            await ctx.database.commit_transaction()
    except Exception:
        # Rollback transaction on error
        if hasattr(ctx.database, "rollback_transaction"):
            await ctx.database.rollback_transaction()
        raise
