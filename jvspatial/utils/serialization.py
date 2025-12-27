"""Serialization utilities for datetime objects and text normalization.

This module provides functions for serializing and deserializing datetime
objects to/from ISO format strings, and normalizing Unicode text to ASCII,
with support for nested data structures.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any


def serialize_datetime(obj: Any) -> Any:
    """Recursively serialize datetimes to ISO strings.

    Keeps structure (dicts/lists) intact while converting datetime instances.
    """

    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, list):
        return [serialize_datetime(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize_datetime(v) for k, v in obj.items()}
    return obj


def serialize_for_persistence(obj: Any, normalize_text: bool = True) -> Any:
    """Serialize data for database persistence.

    Combines datetime serialization and optional text normalization.
    This function should be used when preparing data for database storage.

    Args:
        obj: Data structure to serialize
        normalize_text: Whether to normalize Unicode text to ASCII (default: True)

    Returns:
        Serialized data structure with datetimes converted to ISO strings
        and optionally Unicode text normalized to ASCII
    """
    # First serialize datetimes
    result = serialize_datetime(obj)

    # Then normalize text if requested
    if normalize_text:
        from jvspatial.utils.normalization import normalize_data

        result = normalize_data(result)

    return result


def deserialize_datetime(obj: Any) -> Any:
    """Recursively parse ISO strings into datetimes when possible.

    Best-effort; leaves values as-is if parsing fails.
    """

    async def try_parse(value: Any) -> Any:
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                return value
        return value

    if isinstance(obj, list):
        return [deserialize_datetime(item) for item in obj]
    if isinstance(obj, dict):
        return {k: deserialize_datetime(v) for k, v in obj.items()}
    return try_parse(obj)
