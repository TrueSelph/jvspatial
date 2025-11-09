"""Utility functions for jvspatial core module."""

import uuid
from typing import Dict, Optional, Tuple, Type

# Import serialize_datetime from common to avoid duplication
from jvspatial.utils.serialization import serialize_datetime  # noqa: F401


def generate_id(type_: str, class_name: str) -> str:
    """Generate an ID string for graph objects.

    Args:
        type_: Object type ('n' for node, 'e' for edge, 'w' for walker, 'o' for object)
        class_name: Name of the class (e.g., 'City', 'Highway')

    Returns:
        Unique ID string in the format "type:class_name:hex_id"
    """
    hex_id = uuid.uuid4().hex[:24]
    return f"{type_}:{class_name}:{hex_id}"


async def generate_id_async(type_: str, class_name: str) -> str:
    """Generate an ID string for graph objects (async version).

    Args:
        type_: Object type ('n' for node, 'e' for edge, 'w' for walker, 'o' for object)
        class_name: Name of the class (e.g., 'City', 'Highway')

    Returns:
        Unique ID string in the format "type:class_name:hex_id"
    """
    hex_id = uuid.uuid4().hex[:24]
    return f"{type_}:{class_name}:{hex_id}"


# Cache for subclass lookups to avoid repeated tree traversals
_subclass_cache: Dict[Tuple[Type, str], Optional[Type]] = {}


def find_subclass_by_name(base_class: Type, name: str) -> Optional[Type]:
    """Find a subclass by name recursively with caching.

    Returns the base class if it matches the name, otherwise returns
    the first matching subclass found. Uses caching for performance.
    """
    # Check base class first
    if base_class.__name__ == name:
        return base_class

    # Check cache
    cache_key = (base_class, name)
    if cache_key in _subclass_cache:
        return _subclass_cache[cache_key]

    def find_subclass(cls: Type) -> Optional[Type]:
        for subclass in cls.__subclasses__():
            if subclass.__name__ == name:
                return subclass
            found = find_subclass(subclass)
            if found:
                return found
        return None

    result = find_subclass(base_class)
    # Cache the result
    _subclass_cache[cache_key] = result
    return result
