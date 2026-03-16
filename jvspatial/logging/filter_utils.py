"""Filter validation utilities for logging queries.

Validates MongoDB-style filter dictionaries to ensure they only target
allowed DBLog fields (context.* prefix).
"""

from typing import Any, Dict

from fastapi import HTTPException


def validate_log_filter(filter_dict: Dict[str, Any]) -> Dict[str, Any]:
    """Validate that filter keys use the context. prefix only.

    Rejects top-level keys that could override required constraints
    (e.g. entity, id). Recursively validates $and, $or, $not conditions.

    Args:
        filter_dict: Raw filter from request (parsed JSON)

    Returns:
        Validated filter dict (unchanged if valid)

    Raises:
        HTTPException: 400 if any key is disallowed
    """
    if not filter_dict:
        return filter_dict

    _validate_filter_keys(filter_dict)
    return filter_dict


def _validate_filter_keys(d: Dict[str, Any]) -> None:
    """Recursively validate filter keys."""
    for key, value in d.items():
        if (key == "$and") or (key == "$or"):
            if isinstance(value, list):
                for sub in value:
                    if isinstance(sub, dict):
                        _validate_filter_keys(sub)
        elif key == "$not":
            if isinstance(value, dict):
                _validate_filter_keys(value)
        elif not key.startswith("context."):
            raise HTTPException(
                status_code=400,
                detail=f"Filter key '{key}' is not allowed. All keys must use 'context.' prefix (e.g. context.log_level, context.log_data.user_id)",
            )
