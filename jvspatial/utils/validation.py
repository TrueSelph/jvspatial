"""Validation utilities for common data types.

This module provides validation helpers for IDs, collection names, and other
common data types used throughout the JVspatial system.
"""

from __future__ import annotations

import re
from typing import Pattern


class PathValidator:
    """Common validation helpers for IDs and collection names."""

    _id_re: Pattern[str] = re.compile(r"^[A-Za-z0-9_\-:]{1,256}$")
    _collection_re: Pattern[str] = re.compile(r"^[A-Za-z][A-Za-z0-9_\-]{0,127}$")

    @staticmethod
    def is_valid_id(value: str) -> bool:
        """Check if a string is a valid ID.

        Args:
            value: String to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(PathValidator._id_re.fullmatch(value))

    @staticmethod
    def is_valid_collection_name(value: str) -> bool:
        """Check if a string is a valid collection name.

        Args:
            value: String to validate

        Returns:
            True if valid, False otherwise
        """
        return bool(PathValidator._collection_re.fullmatch(value))
