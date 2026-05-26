"""Utility functions for jvspatial core module."""

import contextlib
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
        Unique ID string in the format "type.class_name.hex_id"
    """
    hex_id = uuid.uuid4().hex[:24]
    return f"{type_}.{class_name}.{hex_id}"


async def generate_id_async(type_: str, class_name: str) -> str:
    """Deprecated async alias for :func:`generate_id`.

    ID generation is pure computation (no I/O); the async signature was
    a vestige of an earlier design. SPEC §3.2 documents ``generate_id``
    as the canonical sync API (audit §3.11). Will be removed in a
    future minor release.

    Args:
        type_: Object type ('n' for node, 'e' for edge, 'w' for walker, 'o' for object)
        class_name: Name of the class (e.g., 'City', 'Highway')

    Returns:
        Unique ID string in the format "type.class_name.hex_id"
    """
    # Lazy import — deprecation helper lives outside the core hot path.
    from jvspatial.utils.deprecation import deprecated

    @deprecated(
        replacement="jvspatial.core.utils.generate_id",
        remove_in="0.1.0",
        name="jvspatial.core.utils.generate_id_async",
    )
    def _emit() -> None:
        return None

    _emit()
    return generate_id(type_, class_name)


# Cache for subclass lookups to avoid repeated tree traversals
_subclass_cache: Dict[Tuple[Type, str], Optional[Type]] = {}


def _class_entity_name(cls: Type) -> str:
    """Return the persisted entity discriminator for ``cls``.

    Mirrors ``Object._entity_name()`` but is safe to call on arbitrary types —
    falls back to ``cls.__name__`` when ``_entity_name`` is absent. Lets
    ``find_subclass_by_name`` honor ``__entity_name__`` overrides without
    forcing every caller to pass an ``Object`` descendant.
    """
    fn = getattr(cls, "_entity_name", None)
    if callable(fn):
        with contextlib.suppress(Exception):
            return fn()
    return cls.__name__


def find_subclass_by_name(base_class: Type, name: str) -> Optional[Type]:
    """Find a subclass by name recursively with caching.

    Matches against each class's ``_entity_name()`` (which honors the
    ``__entity_name__`` override) and falls back to ``cls.__name__``.
    Returns the base class if it matches, otherwise the first matching
    subclass found. Uses caching for performance.
    """
    # Check base class first
    if _class_entity_name(base_class) == name:
        return base_class

    # Check cache
    cache_key = (base_class, name)
    if cache_key in _subclass_cache:
        return _subclass_cache[cache_key]

    def find_subclass(cls: Type) -> Optional[Type]:
        for subclass in cls.__subclasses__():
            if _class_entity_name(subclass) == name:
                return subclass
            found = find_subclass(subclass)
            if found:
                return found
        return None

    result = find_subclass(base_class)
    # Only cache positive hits. Caching None permanently breaks lookups after the class
    # is imported later (subclass cache poisoning during bootstrap).
    if result is not None:
        _subclass_cache[cache_key] = result
    return result
