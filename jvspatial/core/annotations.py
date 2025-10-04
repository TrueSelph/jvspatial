"""Attribute protection and annotation system for jvspatial entities.

This module provides a comprehensive system for annotating and protecting object attributes:

1. @protected decorator: Prevents modification after initial assignment
2. @transient decorator: Excludes from serialization/export operations
3. @private decorator: Pydantic private attributes (underscore fields)
4. Compound usage: @protected @transient for both behaviors

The system integrates with Pydantic models and provides clear error messages
when protection violations occur.

Examples:
    class Entity(ProtectedAttributeMixin, BaseModel):
        # Protected attribute - cannot be modified after initialization
        id: str = protected("", description="Unique identifier")

        # Transient attribute - excluded from exports
        temp_data: dict = transient(Field(default_factory=dict))

        # Private attribute - Pydantic private (underscore fields)
        _internal_cache: dict = private(default_factory=dict)

        # Both protected and transient using compound decorators
        internal_state: dict = protected(transient(Field(default_factory=dict)))
"""

from typing import Any, Dict, Set, Type

from pydantic import Field
from pydantic.fields import PrivateAttr

# Global registry for protected and transient attributes per class
_PROTECTED_ATTRS: Dict[Type, Set[str]] = {}
_TRANSIENT_ATTRS: Dict[Type, Set[str]] = {}


class AnnotatedField:
    """Field wrapper that tracks protection and transient annotations."""

    def __init__(self, field_def: Any):
        self.field_def = field_def
        self.is_protected = False
        self.is_transient = False
        self.additional_kwargs: Dict[str, Any] = {}

    def mark_protected(self) -> "AnnotatedField":
        """Mark this field as protected."""
        self.is_protected = True
        return self

    def mark_transient(self) -> "AnnotatedField":
        """Mark this field as transient."""
        self.is_transient = True
        return self

    def to_field(self) -> Any:
        """Convert to Pydantic Field with appropriate annotations."""
        # If it's already a Field, copy its complete configuration
        if hasattr(self.field_def, "default"):
            # Start with the original field's complete config
            kwargs = {}

            # Copy all the important field attributes
            field_attrs = [
                "default",
                "default_factory",
                "alias",
                "description",
                "title",
                "examples",
                "exclude",
                "include",
                "discriminator",
                "json_schema_extra",
                "frozen",
                "validate_default",
                "repr",
                "init",
                "init_var",
                "kw_only",
            ]

            for attr in field_attrs:
                if hasattr(self.field_def, attr):
                    value = getattr(self.field_def, attr)
                    if value is not None or attr in ["default"]:  # Allow None defaults
                        kwargs[attr] = value

            # Merge additional kwargs without overwriting existing Field properties
            # Only apply additional_kwargs if the key doesn't already have a value
            for key, value in self.additional_kwargs.items():
                if key not in kwargs or kwargs[key] is None:
                    kwargs[key] = value
        else:
            # It's a raw value, treat as default
            kwargs = {"default": self.field_def}
            # Add all additional kwargs for raw values
            kwargs.update(self.additional_kwargs)

        # Add/update annotations in json_schema_extra
        json_extra = kwargs.get("json_schema_extra", {})
        if self.is_protected:
            json_extra["protected"] = True
        if self.is_transient:
            json_extra["transient"] = True

        if json_extra:
            kwargs["json_schema_extra"] = json_extra

        return Field(**kwargs)


def protected(field_def: Any = None, **kwargs: Any) -> Any:
    """Decorator to mark a field as protected - cannot be modified after initial assignment.

    Args:
        field_def: Field definition (default value, Field object, or AnnotatedField)
        **kwargs: Additional Field arguments (description, alias, etc.)

    Returns:
        AnnotatedField or Field with protection metadata

    Examples:
        # Simple usage
        id: str = protected("", description="Unique identifier")

        # Compound usage
        data: dict = protected(transient(Field(default_factory=dict)))

        # With Field and arguments
        name: str = protected(Field(default=""), description="Entity name", min_length=1)
    """
    if field_def is None:
        # Called as @protected() - return decorator function
        def decorator(actual_field_def: Any) -> Any:
            return protected(actual_field_def, **kwargs)

        return decorator

    # Handle compound decorator usage
    if isinstance(field_def, AnnotatedField):
        # Add any additional kwargs to the AnnotatedField before converting
        if kwargs:
            field_def.additional_kwargs.update(kwargs)
        return field_def.mark_protected().to_field()

    # Handle Field objects with additional kwargs
    if kwargs and hasattr(field_def, "default"):
        # Merge kwargs into existing Field without losing properties
        annotated = AnnotatedField(field_def)
        annotated.additional_kwargs = kwargs
        return annotated.mark_protected().to_field()

    # Create AnnotatedField and mark as protected
    annotated = AnnotatedField(field_def)
    if kwargs:
        annotated.additional_kwargs = kwargs
    return annotated.mark_protected().to_field()


def transient(field_def: Any = None, **kwargs: Any) -> Any:
    """Decorator to mark a field as transient - excluded from export/serialization operations.

    Args:
        field_def: Field definition (default value, Field object, or AnnotatedField)
        **kwargs: Additional Field arguments (description, etc.)

    Returns:
        AnnotatedField or Field with transient metadata

    Examples:
        # Simple usage
        temp_data: dict = transient(Field(default_factory=dict))

        # Compound usage
        cache: dict = transient(protected(Field(default_factory=dict)))

        # With Field and description
        debug_info: str = transient(Field(default=""), description="Debug information")
    """
    if field_def is None:
        # Called as @transient() - return decorator function
        def decorator(actual_field_def: Any) -> Any:
            return transient(actual_field_def, **kwargs)

        return decorator

    # Handle compound decorator usage
    if isinstance(field_def, AnnotatedField):
        # Add any additional kwargs to the AnnotatedField before converting
        if kwargs:
            field_def.additional_kwargs.update(kwargs)
        return field_def.mark_transient().to_field()

    # Handle Field objects with additional kwargs
    if kwargs and hasattr(field_def, "default"):
        # Merge kwargs into existing Field without losing properties
        annotated = AnnotatedField(field_def)
        annotated.additional_kwargs = kwargs
        return annotated.mark_transient().to_field()

    # Create AnnotatedField and mark as transient
    annotated = AnnotatedField(field_def)
    if kwargs:
        annotated.additional_kwargs = kwargs
    return annotated.mark_transient().to_field()


def register_protected_attrs(cls: Type, attr_names: Set[str]) -> None:
    """Register protected attribute names for a class.

    Args:
        cls: Class to register attributes for
        attr_names: Set of attribute names to protect
    """
    if cls not in _PROTECTED_ATTRS:
        _PROTECTED_ATTRS[cls] = set()
    _PROTECTED_ATTRS[cls].update(attr_names)


def register_transient_attrs(cls: Type, attr_names: Set[str]) -> None:
    """Register transient attribute names for a class.

    Args:
        cls: Class to register attributes for
        attr_names: Set of attribute names to mark as transient
    """
    if cls not in _TRANSIENT_ATTRS:
        _TRANSIENT_ATTRS[cls] = set()
    _TRANSIENT_ATTRS[cls].update(attr_names)


def get_protected_attrs(cls: Type) -> Set[str]:
    """Get all protected attribute names for a class and its parents.

    Args:
        cls: Class to check

    Returns:
        Set of protected attribute names
    """
    protected = set()

    # Collect from class hierarchy
    for klass in cls.__mro__:
        if klass in _PROTECTED_ATTRS:
            protected.update(_PROTECTED_ATTRS[klass])

        # Also check field annotations for protected markers
        if hasattr(klass, "model_fields"):
            for field_name, field_info in klass.model_fields.items():
                json_extra = getattr(field_info, "json_schema_extra", None)
                if callable(json_extra):
                    schema: Dict[str, Any] = {}
                    json_extra(schema, klass)
                    json_extra = schema
                if json_extra and json_extra.get("protected", False):
                    protected.add(field_name)

    return protected


def get_transient_attrs(cls: Type) -> Set[str]:
    """Get all transient attribute names for a class and its parents.

    Args:
        cls: Class to check

    Returns:
        Set of transient attribute names
    """
    transient_set = set()

    # Collect from class hierarchy
    for klass in cls.__mro__:
        if klass in _TRANSIENT_ATTRS:
            transient_set.update(_TRANSIENT_ATTRS[klass])

        # Also check field annotations for transient markers
        if hasattr(klass, "model_fields"):
            for field_name, field_info in klass.model_fields.items():
                json_extra = getattr(field_info, "json_schema_extra", None)
                if callable(json_extra):
                    schema: Dict[str, Any] = {}
                    json_extra(schema, klass)
                    json_extra = schema
                if json_extra and json_extra.get("transient", False):
                    transient_set.add(field_name)

    return transient_set


def is_protected(cls: Type, attr_name: str) -> bool:
    """Check if an attribute is protected for a class.

    Args:
        cls: Class to check
        attr_name: Name of attribute to check

    Returns:
        True if attribute is protected
    """
    return attr_name in get_protected_attrs(cls)


def is_transient(cls: Type, attr_name: str) -> bool:
    """Check if an attribute is transient for a class.

    Args:
        cls: Class to check
        attr_name: Name of attribute to check

    Returns:
        True if attribute is transient
    """
    return attr_name in get_transient_attrs(cls)


class AttributeProtectionError(Exception):
    """Raised when trying to modify a protected attribute."""

    def __init__(self, attr_name: str, cls_name: str):
        self.attr_name = attr_name
        self.cls_name = cls_name
        super().__init__(
            f"Cannot modify protected attribute '{attr_name}' on {cls_name} after initialization"
        )


class ProtectedAttributeMixin:
    """Mixin class that provides attribute protection functionality.

    This mixin automatically integrates with @protected and @transient decorators.
    It overrides __setattr__ to prevent modification of protected attributes after
    initialization, and enhances export methods to respect transient annotations.

    The mixin automatically manages the _initializing flag to enable protection
    after object construction is complete.
    """

    def __init__(self, *args: Any, **kwargs: Any):
        """Initialize with protection management."""
        # Set initializing flag before calling parent __init__
        object.__setattr__(self, "_initializing", True)

        # Call parent __init__
        super().__init__(*args, **kwargs)

        # Clear initializing flag after initialization complete
        object.__setattr__(self, "_initializing", False)

    def __init_subclass__(cls, **kwargs):
        """Automatically register protected/transient fields when class is created."""
        super().__init_subclass__(**kwargs)

        # Auto-register fields from this class (not parent classes)
        protected_attrs = set()
        transient_attrs = set()

        # Check model_fields if it exists (Pydantic)
        if hasattr(cls, "model_fields"):
            for field_name, field_info in cls.model_fields.items():
                json_extra = getattr(field_info, "json_schema_extra", None)
                if callable(json_extra):
                    json_extra = json_extra({})
                if json_extra:
                    if json_extra.get("protected", False):
                        protected_attrs.add(field_name)
                    if json_extra.get("transient", False):
                        transient_attrs.add(field_name)

        # Register any found attributes
        if protected_attrs:
            register_protected_attrs(cls, protected_attrs)
        if transient_attrs:
            register_transient_attrs(cls, transient_attrs)

    def __setattr__(self, name: str, value: Any) -> None:
        """Override to protect attributes from modification after initialization."""
        # Allow setting during initialization
        initializing = getattr(self, "_initializing", True)
        if initializing:
            super().__setattr__(name, value)
            return

        # Check if attribute is protected
        protected_attrs = get_protected_attrs(self.__class__)
        if name in protected_attrs and hasattr(self, name):
            # Attribute is protected and already exists - prevent modification
            raise AttributeProtectionError(name, self.__class__.__name__)

        super().__setattr__(name, value)

    def export(self, exclude_transient: bool = True, **kwargs) -> Dict[str, Any]:
        """Enhanced export that automatically respects @transient annotations.

        Args:
            exclude_transient: Whether to exclude @transient fields (default: True)
            **kwargs: Additional arguments passed to model_dump()

        Returns:
            Dictionary representation excluding transient fields if requested
        """
        if hasattr(self, "model_dump"):
            # Build exclude set for transient fields
            exclude_set = set(kwargs.get("exclude", set()))
            if exclude_transient:
                exclude_set.update(get_transient_attrs(self.__class__))

            if exclude_set:
                kwargs["exclude"] = exclude_set

            result: Dict[str, Any] = self.model_dump(**kwargs)
            return result
        else:
            # Fallback for non-Pydantic objects
            return export_with_transient_exclusion(self, exclude_transient)


def export_with_transient_exclusion(
    obj: Any, exclude_transient: bool = True
) -> Dict[str, Any]:
    """Export object data while respecting transient attribute annotations.

    Args:
        obj: Object to export
        exclude_transient: Whether to exclude transient attributes

    Returns:
        Dictionary of object data with transient attributes excluded if requested
    """
    if hasattr(obj, "model_dump"):
        # For Pydantic models, get base export
        exclude_set = set()
        if exclude_transient:
            exclude_set.update(get_transient_attrs(obj.__class__))

        # Use Pydantic's exclude parameter for efficiency
        result: Dict[str, Any] = obj.model_dump(
            exclude=exclude_set if exclude_set else None
        )
        return result

    # For regular objects, use __dict__
    result_data: Dict[str, Any] = obj.__dict__.copy()

    if exclude_transient:
        # Remove transient attributes
        transient_attrs = get_transient_attrs(obj.__class__)
        for attr in transient_attrs:
            result_data.pop(attr, None)

    return result_data


# Note: with_protection decorator is no longer needed!
# The ProtectedAttributeMixin now automatically handles registration
# via __init_subclass__, making decoration unnecessary.


def private(default: Any = None, **kwargs: Any) -> Any:
    """Decorator for Pydantic private attributes (fields with leading underscore).

    This is a wrapper around Pydantic's PrivateAttr, designed for fields that start
    with underscore (_). Private attributes are automatically excluded from serialization
    and are not part of the model's public API.

    For regular fields that need both protected and transient behaviors, use the
    compound syntax: protected(transient(Field(...)))

    Args:
        default: Default value for the private attribute
        **kwargs: Additional arguments, primarily 'default_factory' for callable defaults

    Returns:
        PrivateAttr configured with the provided default or factory

    Examples:
        # Private attribute with default value
        _counter: int = private(default=0)

        # Private attribute with factory
        _cache: dict = private(default_factory=dict)
        _data: dict = private(default_factory=dict)

        # For non-underscore fields, use compound decorators:
        internal: dict = protected(transient(Field(default_factory=dict)))
    """
    if "default_factory" in kwargs:
        return PrivateAttr(default_factory=kwargs["default_factory"])
    else:
        return PrivateAttr(default=default)
