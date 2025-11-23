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
        _initializing: Initialization flag (transient)
    """

    model_config = ConfigDict(extra="ignore")

    id: str = attribute(
        protected=True, transient=True, description="Unique identifier for the object"
    )
    entity: str = attribute(
        protected=True,
        transient=True,
        description="Entity class name (protected - cannot be modified after initialization)",
    )
    type_code: str = attribute(transient=True, default="o")
    _initializing: bool = attribute(private=True, default=True)
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
        """Initialize an Object with auto-generated ID and obj if not provided."""
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
                    type_code = "o"  # Default type code
            kwargs["id"] = generate_id(type_code, self.__class__.__name__)
        # Set entity to class name if not provided (protected attribute)
        if "entity" not in kwargs:
            kwargs["entity"] = self.__class__.__name__
        super().__init__(**kwargs)
        self._initializing = False

    def __setattr__(self: "Object", name: str, value: Any) -> None:
        """Set attribute, only allowing fields defined in the class hierarchy.

        This override allows setting fields that are defined in the class or its
        parent classes. It does NOT allow setting arbitrary properties that aren't
        part of the class definition. This ensures type safety and prevents injection
        of unexpected properties.

        Args:
            name: Attribute name
            value: Attribute value

        Raises:
            AttributeError: If trying to set a property that isn't in the class hierarchy
        """
        # Get all valid fields from this class and its parents (not children)
        valid_fields = self._get_class_hierarchy_fields()

        # Check if this is a valid field in the class hierarchy or private attribute
        if (name in valid_fields) or (name.startswith("_")):
            # Use normal Pydantic setattr for model fields or private attributes
            super().__setattr__(name, value)
        else:
            # Property is not in the class hierarchy - raise error
            raise AttributeError(
                f"Cannot set property '{name}' on {self.__class__.__name__}. "
                f"Property must be defined in the class or one of its parent classes. "
                f"Valid properties: {sorted(valid_fields)}"
            )

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

    async def update(
        self: "Object",
        properties: Dict[str, Any],
        skip_protected: bool = True,
        skip_private: bool = True,
    ) -> Dict[str, Any]:
        """Update properties from the class hierarchy.

        This method validates that each property is defined in the class or its
        parent classes (not child classes) before updating. This ensures type
        safety and prevents injection of unexpected properties.

        Args:
            properties: Dictionary of property names to values to update
            skip_protected: If True, skips protected attributes (default: True)
            skip_private: If True, skips private attributes (starting with _) (default: True)

        Returns:
            Dictionary with:
                - success: Boolean indicating if any properties were successfully updated
                - updated: Dict mapping property names to their new values
                - skipped: Dict mapping property names to skip reasons
                - message: Human-readable summary message

        Examples:
            # Update properties on an entity
            result = await entity.update({
                "name": "New Name",
                "description": "New Description",
                "invalid_field": "value"
            })
            # result = {
            #     "success": True,
            #     "updated": {
            #         "name": "New Name",
            #         "description": "New Description"
            #     },
            #     "skipped": {
            #         "invalid_field": "invalid_property"
            #     },
            #     "message": "Partially updated: 2 succeeded, 1 skipped"
            # }
        """
        from ..annotations import get_protected_attrs

        updated: Dict[str, Any] = {}  # property_name -> new_value
        skipped: Dict[str, str] = {}  # property_name -> reason

        # Get all valid fields from the class hierarchy
        valid_fields = self._get_class_hierarchy_fields()

        # Get protected attributes if we need to check them
        protected_attrs: Set[str] = set()
        if skip_protected:
            protected_attrs = get_protected_attrs(self.__class__)

        for prop_name, prop_value in properties.items():
            # Skip private attributes if requested
            if skip_private and prop_name.startswith("_"):
                skipped[prop_name] = "private_attribute"
                continue

            # Check if property is in the class hierarchy
            if prop_name not in valid_fields:
                skipped[prop_name] = "invalid_property"
                continue

            # Check if property is protected
            if skip_protected and prop_name in protected_attrs:
                skipped[prop_name] = "protected_attribute"
                continue

            # Attempt to update the property
            try:
                setattr(self, prop_name, prop_value)
                updated[prop_name] = prop_value
            except (AttributeError, ValueError, TypeError) as e:
                skipped[prop_name] = f"update_failed: {str(e)}"

        # Determine success status and message
        total_requested = len(properties)
        total_updated = len(updated)
        total_skipped = len(skipped)
        success = total_updated > 0

        if total_updated == total_requested:
            message = f"Successfully updated {total_updated} property(ies)"
        elif total_updated > 0:
            message = (
                f"Partially updated: {total_updated} succeeded, {total_skipped} skipped"
            )
        elif total_skipped > 0:
            message = f"Update failed: {total_skipped} property(ies) skipped"
        else:
            message = "No properties to update"

        return {
            "success": success,
            "updated": updated,
            "skipped": skipped,
            "message": message,
        }

    async def export(
        self: "Object",
        exclude_transient: bool = True,
        exclude: Optional[Union[set, Dict[str, Any]]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Export the object to a dictionary using model_dump() as the base.

        This is the standard, transparent method for dumping Object contents
        and all of its derivatives. It automatically handles transient properties,
        allows custom exclusions, and includes fields from the class hierarchy
        (the class itself and its parent classes, but not child classes).

        Args:
            exclude_transient: Whether to automatically exclude transient fields (default: True)
            exclude: Additional fields to exclude (can be a set of field names or a dict)
            **kwargs: Additional arguments passed to model_dump() (e.g., exclude_none, mode, etc.)

        Returns:
            Dictionary representation of the object, excluding transient and specified fields.
            Includes all fields from the class hierarchy (class and parent classes, not child classes).

        Examples:
            # Standard export (excludes transient fields)
            data = await obj.export()

            # Export including transient fields
            data = await obj.export(exclude_transient=False)

            # Export with custom exclusions
            data = await obj.export(exclude={"internal_field", "debug_field"})

            # Export with model_dump options
            data = await obj.export(exclude_none=True, mode="json")
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

            # Include fields from __dict__ that are defined in the class hierarchy
            # (class + parents, not children). This ensures all valid properties are exported.
            # But respect exclusions - don't add back fields that were explicitly excluded
            valid_fields = self._get_class_hierarchy_fields()

            # Include fields from __dict__ that are in the class hierarchy
            # but might not be in model_dump (e.g., if they were set via __setattr__)
            # Skip fields that were explicitly excluded
            for field_name in valid_fields:
                if (
                    field_name in self.__dict__
                    and field_name not in result
                    and field_name not in exclude_set
                ):
                    result[field_name] = self.__dict__[field_name]

            # Serialize datetime objects to ensure JSON compatibility
            from jvspatial.utils.serialization import serialize_datetime

            result = serialize_datetime(result)

            # Return nested persistence format (same as Node/Edge/Walker)
            return {
                "id": self.id,
                "entity": self.entity,
                "context": result,
            }
        else:
            # Handle non-Pydantic objects
            return self._export_with_transient_exclusion(exclude_transient)

    def _get_transient_attrs(self) -> set:
        """Get transient attributes for this object."""
        from ..annotations import get_transient_attrs

        return get_transient_attrs(self.__class__)

    @classmethod
    def _get_class_hierarchy_fields(cls: Type["Object"]) -> Set[str]:
        """Get all model fields from this class and its parent classes (not children).

        This method traverses up the inheritance chain (MRO) to collect all fields
        defined in the class and its ancestors. It does NOT include fields from
        child classes.

        Returns:
            Set of field names defined in this class and its parents
        """
        fields: Set[str] = set()

        # Traverse MRO (Method Resolution Order) to get all parent classes
        # MRO gives us the class itself first, then its parents in order
        for klass in cls.__mro__:
            # Only include classes that are Object or its subclasses
            if issubclass(klass, Object) and hasattr(klass, "model_fields"):
                fields.update(klass.model_fields.keys())

        return fields

    @classmethod
    def _get_top_level_fields(cls: Type["Object"]) -> set:
        """Get fields that are stored at top level in persistence format.

        Override this method in subclasses to declare which fields are stored
        at the top level (outside "context") in the export format.

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
        collection, final_query = await cls._build_database_query(
            context, query, kwargs
        )

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
        collection, final_query = await cls._build_database_query(
            context, query, kwargs
        )
        return await context.database.count(collection, final_query)

    @classmethod
    def _collect_class_names(cls: Type["Object"]) -> Set[str]:
        """Collect class names for this class and all imported subclasses.

        This method uses Python's __subclasses__() to find all imported
        subclasses. Dynamically loaded classes are found once they're imported.

        Returns:
            Set of class names including the class itself and all imported subclasses
        """
        names: Set[str] = {cls.__name__}

        # Add all imported subclasses recursively
        for subclass in cls.__subclasses__():
            names.update(subclass._collect_class_names())

        return names

    @classmethod
    async def _build_database_query(
        cls: Type["Object"],
        context: GraphContext,
        query: Optional[Dict[str, Any]],
        kwargs: Dict[str, Any],
    ) -> tuple[str, Dict[str, Any]]:
        """Build the database collection name and query dict.

        Uses __subclasses__() to find all imported subclasses, ensuring queries
        include the base class and all its imported subclasses.

        Args:
            context: Graph context
            query: Query filters
            kwargs: Additional query parameters

        Returns:
            Tuple of (collection_name, query_dict)
        """
        type_code = context._get_entity_type_code(cls)
        collection = context._get_collection_name(type_code)

        combined_filters: Dict[str, Any] = {}
        if query:
            combined_filters.update(query)
        if kwargs:
            combined_filters.update(kwargs)

        # Use standard class name collection (imported subclasses only)
        # This leverages __subclasses__() to find all imported subclasses
        # Dynamically loaded classes will be found once they're imported
        class_names = sorted(cls._collect_class_names())
        class_name_filter: Dict[str, Any] = {
            "$or": [{"entity": name} for name in class_names]
        }

        top_level_fields = cls._get_top_level_fields()
        db_query: Dict[str, Any] = {}

        for key, value in combined_filters.items():
            if key == "entity":
                continue
            if (key in top_level_fields) or (key.startswith("context.")):
                # For all entity types, top-level fields and context.* fields map directly
                db_query[key] = value
            else:
                # For all entity types, non-context fields map to context.* in database
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

    def __bool__(self: "Object") -> bool:
        """Check if object has meaningful data.

        Returns:
            True if object has meaningful fields (not just id and type_code)
        """
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
        return f"{self.__class__.__name__}(id={self.id})"
