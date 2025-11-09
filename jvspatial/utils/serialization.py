"""Serialization utilities for datetime objects.

This module provides functions for serializing and deserializing datetime
objects to/from ISO format strings, with support for nested data structures.
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
