"""Annotations for private attributes."""

from typing import Any

from pydantic import PrivateAttr


def private(default: Any = None, **kwargs) -> Any:
    """Annotation for private attributes with default value and metadata.

    Usage:
        _internal: dict = private(default_factory=dict, description="Internal cache")
    """
    return PrivateAttr(default=default, **kwargs)
