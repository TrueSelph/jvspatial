"""Base Object class for jvspatial entities."""

from typing import Any, Dict, List, Optional, Set, Type, Union

from pydantic import BaseModel, ConfigDict

from jvspatial.core.context import GraphContext

from ..annotations import AttributeMixin, attribute
from ..utils import generate_id


class Object(AttributeMixin, BaseModel):
    """Base object with persistence capabilities.

    Attributes:
        id: Unique identifier for the object (protected - cannot be modified after initialization)
        type_code: Type identifier for database partitioning
        _graph_context: GraphContext instance for database operations (transient)
        _data: Internal data storage (transient)
        _initializing: Initialization flag (transient)
    """

    model_config = ConfigDict(extra="ignore")

    id: str = attribute(protected=True, description="Unique identifier for the object")
    type_code: str = attribute(transient=True, default="o")
    _initializing: bool = attribute(private=True, default=True)
    _data: dict = attribute(private=True, default_factory=dict)
    _graph_context: Optional["GraphContext"] = attribute(private=True, default=None)

    async def set_context(self: "Object", context: "GraphContext") -> None:
        """Set the GraphContext for this object.

        Args:
            context: GraphContext instance to use for database operations
        """
        self._graph_context = context

    async def get_context(self: "Object") -> "GraphContext":
        """Get the GraphContext, using default if not set.

        Returns:
            GraphContext instance
        """
        if self._graph_context is None:
            from ..context import get_default_context

            self._graph_context = get_default_context()
        return self._graph_context

    def get_collection_name(self: "Object") -> str:
        """Get the collection name for this object type.

        Returns:
            Collection name for database operations
        """
        collection_map = {"n": "node", "e": "edge", "o": "object", "w": "walker"}
        return collection_map.get(self.type_code, "object")

    def __init__(self: "Object", **kwargs: Any) -> None:
        """Initialize an Object with auto-generated ID if not provided."""
        self._initializing = True
        if "id" not in kwargs:
            # Use class-level type_code or default from Field
            type_code = kwargs.get("type_code")
            if type_code is None:
                # Get the default value from the Field definition
                type_code_field = self.__class__.model_fields.get("type_code")
                if type_code_field and hasattr(type_code_field, "default"):
                    type_code = type_code_field.default
                else:
                    type_code = "o"  # fallback default
            kwargs["id"] = generate_id(type_code, self.__class__.__name__)
        super().__init__(**kwargs)
        self._initializing = False

    def __setattr__(self: "Object", name: str, value: Any) -> None:
        """Set attribute without automatic save operations."""
        super().__setattr__(name, value)

    @classmethod
    async def create(cls: Type["Object"], **kwargs: Any) -> "Object":
        """Create and save a new object instance.

        Args:
            **kwargs: Object attributes

        Returns:
            Created and saved object instance
        """
        obj = cls(**kwargs)
        await obj.save()
        return obj

    def export(
        self: "Object",
        exclude_transient: bool = True,
        exclude: Optional[Union[set, Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Export the object to a dictionary using model_dump() as the base.

        This is the standard, transparent method for dumping Object contents
        and all of its derivatives. It automatically handles transient properties
        and allows custom exclusions.

        Args:
            exclude_transient: Whether to automatically exclude transient fields (default: True)
            exclude: Additional fields to exclude (can be a set of field names or a dict)
            **kwargs: Additional arguments passed to model_dump() (e.g., exclude_none, mode, etc.)

        Returns:
            Dictionary representation of the object, excluding transient and specified fields

        Examples:
            # Standard export (excludes transient fields)
            data = obj.export()

            # Export including transient fields
            data = obj.export(exclude_transient=False)

            # Export with custom exclusions
            data = obj.export(exclude={"internal_field", "debug_field"})

            # Export with model_dump options
            data = obj.export(exclude_none=True, mode="json")
        """
        if hasattr(self, "model_dump"):
            # Build exclude set starting with any provided exclusions
            exclude_set = set(exclude) if exclude else set()

            # Merge with any exclude from kwargs (model_dump format)
            if "exclude" in kwargs:
                kwargs_exclude = kwargs.pop("exclude")
                if isinstance(kwargs_exclude, (set, dict)):
                    exclude_set.update(
                        kwargs_exclude
                        if isinstance(kwargs_exclude, set)
                        else kwargs_exclude.keys()
                    )

            # Add transient fields if requested
            if exclude_transient:
                exclude_set.update(self._get_transient_attrs())

            # Pass exclude to model_dump if we have anything to exclude
            if exclude_set:
                kwargs["exclude"] = exclude_set

            # Use model_dump with all options
            result: Dict[str, Any] = self.model_dump(**kwargs)
            return result
        else:
            # Fallback for non-Pydantic objects
            return self._export_with_transient_exclusion(exclude_transient)

    def _get_transient_attrs(self) -> set:
        """Get transient attributes for this object."""
        from ..annotations import get_transient_attrs

        return get_transient_attrs(self.__class__)

    @classmethod
    def _get_top_level_fields(cls: Type["Object"]) -> set:
        """Get fields that are stored at top level in persistence format.

        Override this method in subclasses to declare which fields are stored
        at the top level (outside "context") when for_persistence=True.

        Returns:
            Set of field names stored at top level (default: empty set)

        Examples:
            # In Edge subclass:
            @classmethod
            def _get_top_level_fields(cls):
                return {"source", "target", "bidirectional"}
        """
        return set()

    def _export_with_transient_exclusion(
        self, exclude_transient: bool = True
    ) -> Dict[str, Any]:
        """Export object data while respecting transient attribute annotations.

        Args:
            exclude_transient: Whether to exclude transient attributes

        Returns:
            Dictionary of object data with transient attributes excluded if requested
        """
        if hasattr(self, "model_dump"):
            # For Pydantic models, get base export
            exclude_set = set()
            if exclude_transient:
                exclude_set.update(self._get_transient_attrs())

            # Use Pydantic's exclude parameter for efficiency
            result: Dict[str, Any] = self.model_dump(
                exclude=exclude_set if exclude_set else None
            )
            return result

        # For regular objects, use __dict__
        result_data: Dict[str, Any] = self.__dict__.copy()

        if exclude_transient:
            # Remove transient attributes
            transient_attrs = self._get_transient_attrs()
            for attr in transient_attrs:
                result_data.pop(attr, None)

        return result_data

    async def save(self: "Object") -> "Object":
        """Save the object to the database.

        Returns:
            The saved object instance
        """
        context = await self.get_context()
        await context.save(self)
        return self

    async def delete(self: "Object", cascade: bool = False) -> None:
        """Delete the object from the database.

        Object is a fundamental entity type that is NOT connected by edges on the graph.
        This method simply removes the entity from the database. The cascade parameter
        is ignored for Object entities as they have no graph connections.

        For Node entities, use Node.delete() which handles cascading deletion of edges
        and dependent nodes.

        Args:
            cascade: Ignored for Object entities
        """
        context = await self.get_context()
        await context.delete(self, cascade=False)

    @classmethod
    async def get(cls: Type["Object"], obj_id: str) -> Optional["Object"]:
        """Retrieve an object by ID.

        Args:
            obj_id: Object ID to retrieve

        Returns:
            Object instance if found, else None
        """
        from ..context import get_default_context

        context = get_default_context()
        return await context.get(cls, obj_id)

    @classmethod
    async def find(
        cls: Type["Object"], query: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> List["Object"]:
        """Find objects matching the given filters.

        Args:
            query: Optional query dictionary (e.g., {"context.active": True})
            **kwargs: Additional filters as keyword arguments (e.g., active=True)

        Returns:
            List of matching Object instances

        Examples:
            # Fetch all matching objects
            users = await User.find({"context.active": True})

            # Count matching objects
            count = await User.count({"context.active": True})
        """
        from ..context import get_default_context

        context = get_default_context()
        collection, final_query = cls._build_database_query(context, query, kwargs)

        results = await context.database.find(collection, final_query)
        objects: List["Object"] = []
        for data in results:
            try:
                obj = await context._deserialize_entity(cls, data)
                if obj:
                    objects.append(obj)
            except Exception:
                continue
        return objects

    @classmethod
    async def count(
        cls: Type["Object"], query: Optional[Dict[str, Any]] = None, **kwargs: Any
    ) -> int:
        """Count objects matching the provided filters.

        Args:
            query: Optional query dictionary (e.g., {"context.active": True})
            **kwargs: Additional filters as keyword arguments (e.g., active=True)

        Returns:
            Number of matching records

        Examples:
            # Count all objects
            total = await User.count()

            # Count filtered objects using query dict
            active = await User.count({"context.active": True})

            # Count filtered objects using keyword arguments
            active = await User.count(active=True)
        """
        from ..context import get_default_context

        context = get_default_context()
        collection, final_query = cls._build_database_query(context, query, kwargs)
        return await context.database.count(collection, final_query)

    @classmethod
    def _collect_class_names(cls: Type["Object"]) -> Set[str]:
        """Collect class names for this class and all subclasses."""
        names: Set[str] = {cls.__name__}
        for subclass in cls.__subclasses__():
            names.update(subclass._collect_class_names())
        return names

    @classmethod
    def _build_database_query(
        cls: Type["Object"],
        context: GraphContext,
        query: Optional[Dict[str, Any]],
        kwargs: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        """Build the database collection name and query dict."""
        type_code = context._get_entity_type_code(cls)
        collection = context._get_collection_name(type_code)

        combined_filters: Dict[str, Any] = {}
        if query:
            combined_filters.update(query)
        if kwargs:
            combined_filters.update(kwargs)

        class_names = sorted(cls._collect_class_names())
        class_name_filter: Dict[str, Any] = {
            "$or": (
                [{"_class": name} for name in class_names]
                + [{"name": name} for name in class_names]
            )
        }

        top_level_fields = cls._get_top_level_fields()
        is_object = type_code == "o"
        db_query: Dict[str, Any] = {}

        for key, value in combined_filters.items():
            if key == "name":
                continue
            if key in top_level_fields:
                db_query[key] = value
            elif key.startswith("context."):
                if is_object:
                    db_query[key[8:]] = value
                else:
                    db_query[key] = value
            else:
                if is_object:
                    db_query[key] = value
                else:
                    db_query[f"context.{key}"] = value

        final_query = (
            {"$and": [class_name_filter, db_query]} if db_query else class_name_filter
        )
        return collection, final_query

    @classmethod
    async def all(cls: Type["Object"]) -> List["Object"]:
        """Retrieve all objects of this type.

        Returns:
            List of all objects of this type
        """
        return await cls.find()

    def __getitem__(self: "Object", key: str) -> Any:
        """Get item from internal data storage.

        Args:
            key: Key to retrieve

        Returns:
            Value from internal data storage
        """
        return self._data.get(key)

    def __setitem__(self: "Object", key: str, value: Any) -> None:
        """Set item in internal data storage.

        Args:
            key: Key to set
            value: Value to set
        """
        self._data[key] = value

    def __contains__(self: "Object", key: str) -> bool:
        """Check if key exists in internal data storage.

        Args:
            key: Key to check

        Returns:
            True if key exists
        """
        return key in self._data

    def get_data(self: "Object", key: str, default: Any = None) -> Any:
        """Get value from internal data storage with default.

        Args:
            key: Key to retrieve
            default: Default value if key not found

        Returns:
            Value from internal data storage or default
        """
        return self._data.get(key, default)

    def set(self: "Object", key: str, value: Any) -> None:
        """Set value in internal data storage.

        Args:
            key: Key to set
            value: Value to set
        """
        self._data[key] = value

    def pop(self: "Object", key: str, default: Any = None) -> Any:
        """Pop value from internal data storage.

        Args:
            key: Key to pop
            default: Default value if key not found

        Returns:
            Value from internal data storage or default
        """
        return self._data.pop(key, default)

    def keys(self: "Object") -> List[str]:
        """Get keys from internal data storage.

        Returns:
            List of keys
        """
        return list(self._data.keys())

    def values(self: "Object") -> List[Any]:
        """Get values from internal data storage.

        Returns:
            List of values
        """
        return list(self._data.values())

    def items(self: "Object") -> List[tuple]:
        """Get items from internal data storage.

        Returns:
            List of (key, value) tuples
        """
        return list(self._data.items())

    def clear(self: "Object") -> None:
        """Clear internal data storage."""
        self._data.clear()

    def update(self: "Object", data: Dict[str, Any]) -> None:
        """Update internal data storage with new data.

        Args:
            data: Dictionary of data to update
        """
        self._data.update(data)

    def copy_data(self: "Object") -> Dict[str, Any]:
        """Copy internal data storage.

        Returns:
            Copy of internal data storage
        """
        return self._data.copy()

    def __len__(self: "Object") -> int:
        """Get length of internal data storage.

        Returns:
            Length of internal data storage
        """
        return len(self._data)

    def __bool__(self: "Object") -> bool:
        """Check if object has data.

        Returns:
            True if object has data
        """
        # Check if _data has content
        if self._data:
            return True

        # Check if object has meaningful fields (not just id and type_code)
        meaningful_fields = set(self.__class__.model_fields.keys()) - {
            "id",
            "type_code",
        }
        return any(
            hasattr(self, field) and getattr(self, field) not in (None, "", 0, [], {})
            for field in meaningful_fields
        )

    def __str__(self: "Object") -> str:
        """String representation of the object.

        Returns:
            String representation
        """
        return f"{self.__class__.__name__}(id={self.id})"

    def __repr__(self: "Object") -> str:
        """Representation of the object.

        Returns:
            Representation string
        """
        return f"{self.__class__.__name__}(id={self.id}, data={self._data})"
