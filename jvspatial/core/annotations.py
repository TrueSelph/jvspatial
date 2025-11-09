"""Simplified decorator system for jvspatial entities.

This module provides a single @attribute decorator that replaces the complex
decorator system with a simplified approach.

Examples:
    class Entity(BaseModel):
        # Protected attribute - cannot be modified after initialization
        id: str = attribute(protected=True, description="Unique identifier")

        # Transient attribute - excluded from exports
        cache: dict = attribute(transient=True, default_factory=dict)

        # Both protected and transient
        internal: dict = attribute(protected=True, transient=True, default_factory=dict)

        # Private attribute (underscore field)
        _private_data: dict = attribute(private=True, default_factory=dict)

        # Regular attribute with validation
        name: str = attribute(min_length=1, max_length=100)
"""

from typing import Any, Dict, Optional, Set, Type

from pydantic import Field
from pydantic.fields import PrivateAttr


class AttributeProtectionError(AttributeError):
    """Exception raised when trying to modify a protected attribute."""

    def __init__(self, attr_name: str, cls_name: str):
        self.attr_name = attr_name
        self.cls_name = cls_name
        super().__init__(
            f"Cannot modify protected attribute '{attr_name}' of class '{cls_name}' after initialization"
        )


# Global registry for protected and transient attributes per class
_PROTECTED_ATTRS: Dict[Type, Set[str]] = {}
_TRANSIENT_ATTRS: Dict[Type, Set[str]] = {}


def attribute(
    default: Any = ...,
    *,
    # Protection flags
    protected: bool = False,
    transient: bool = False,
    private: bool = False,
    # Standard Pydantic Field parameters
    description: Optional[str] = None,
    title: Optional[str] = None,
    examples: Optional[list] = None,
    gt: Optional[float] = None,
    ge: Optional[float] = None,
    lt: Optional[float] = None,
    le: Optional[float] = None,
    min_length: Optional[int] = None,
    max_length: Optional[int] = None,
    pattern: Optional[str] = None,
    **kwargs: Any,
) -> Any:
    """Unified attribute decorator for jvspatial entities.

    This decorator replaces the old decorator system with a single
    unified interface that supports all attribute behaviors.

    Args:
        default: Default value for the attribute
        protected: If True, attribute cannot be modified after initialization
        transient: If True, attribute is excluded from export/serialization
        private: If True, creates a Pydantic private attribute (underscore field)
        description: Description for the attribute
        title: Title for the attribute
        examples: Example values for documentation
        gt, ge, lt, le: Numeric constraints
        min_length, max_length: String length constraints
        pattern: Regex pattern for string validation
        **kwargs: Additional Pydantic Field parameters

    Returns:
        Field or PrivateAttr configured with the specified behavior

    Examples:
        # Protected attribute
        id: str = attribute(protected=True, description="Unique identifier")

        # Transient attribute
        cache: dict = attribute(transient=True, default_factory=dict)

        # Both protected and transient
        internal: dict = attribute(protected=True, transient=True, default_factory=dict)

        # Private attribute
        _private_data: dict = attribute(private=True, default_factory=dict)

        # Regular attribute with validation
        name: str = attribute(min_length=1, max_length=100, description="Entity name")
    """
    # Handle private attributes (underscore fields)
    if private:
        if "default_factory" in kwargs:
            return PrivateAttr(default_factory=kwargs["default_factory"])
        else:
            return PrivateAttr(default=default)

    # Build Field parameters
    field_kwargs = {
        "description": description,
        "title": title,
        "examples": examples,
        "gt": gt,
        "ge": ge,
        "lt": lt,
        "le": le,
        "min_length": min_length,
        "max_length": max_length,
        "pattern": pattern,
        **kwargs,
    }

    # Remove None values
    field_kwargs = {k: v for k, v in field_kwargs.items() if v is not None}

    # Set default value
    if default is not ...:
        field_kwargs["default"] = default

    # Add protection/transient metadata to json_schema_extra
    if protected or transient:
        json_extra = field_kwargs.get("json_schema_extra", {})
        if protected:
            json_extra["protected"] = True
        if transient:
            json_extra["transient"] = True
        field_kwargs["json_schema_extra"] = json_extra

    return Field(**field_kwargs)


def register_protected_attrs(cls: Type, attr_names: Set[str]) -> None:
    """Register protected attribute names for a class."""
    if cls not in _PROTECTED_ATTRS:
        _PROTECTED_ATTRS[cls] = set()
    _PROTECTED_ATTRS[cls].update(attr_names)


def register_transient_attrs(cls: Type, attr_names: Set[str]) -> None:
    """Register transient attribute names for a class."""
    if cls not in _TRANSIENT_ATTRS:
        _TRANSIENT_ATTRS[cls] = set()
    _TRANSIENT_ATTRS[cls].update(attr_names)


def get_protected_attrs(cls: Type) -> Set[str]:
    """Get all protected attribute names for a class and its parents."""
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
    """Get all transient attribute names for a class and its parents."""
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
    """Check if an attribute is protected for a given class."""
    return attr_name in get_protected_attrs(cls)


def is_transient(cls: Type, attr_name: str) -> bool:
    """Check if an attribute is transient for a given class."""
    return attr_name in get_transient_attrs(cls)


class AttributeMixin:
    """Mixin class that provides attribute protection and transient functionality.

    This mixin automatically integrates with the @attribute decorator.
    It overrides __setattr__ to prevent modification of protected attributes after
    initialization, and enhances export methods to respect transient annotations.
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
        """Enhanced export that automatically respects transient annotations.

        Args:
            exclude_transient: Whether to exclude transient fields (default: True)
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


__all__ = [
    "AttributeMixin",
    "attribute",
]
