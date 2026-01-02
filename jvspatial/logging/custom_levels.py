"""Custom log level utilities for jvspatial logging.

This module provides utilities for adding and using custom log levels in the
jvspatial logging system. Custom log levels can be used to categorize logs
beyond the standard DEBUG, INFO, WARNING, ERROR, and CRITICAL levels.
"""

import logging
from typing import Any, Optional, Set

# Registry of custom log levels
_custom_levels: Set[str] = set()


def add_custom_log_level(
    level_name: str, level_number: int, method_name: Optional[str] = None
) -> int:
    """Add a custom log level to Python's logging system.

    This function registers a new log level with the logging module and
    adds a corresponding method to the Logger class.

    Args:
        level_name: Name of the log level (e.g., "CUSTOM", "TRACE", "AUDIT")
        level_number: Numeric value for the level. Standard levels:
            - CRITICAL: 50
            - ERROR: 40
            - WARNING: 30
            - INFO: 20
            - DEBUG: 10
            - NOTSET: 0
            Choose a number between these values for custom levels.
        method_name: Optional method name to add to Logger class.
            If not provided, uses level_name.lower()

    Returns:
        The level number that was registered

    Example:
        ```python
        # Add a CUSTOM level between INFO and WARNING
        add_custom_log_level("CUSTOM", 25)

        # Now you can use it with standard logging
        import logging
        logger = logging.getLogger(__name__)
        logger.custom("This is a custom log message")

        # Or with the database logging handler
        from jvspatial.logging import install_db_log_handler
        install_db_log_handler(log_levels={logging.CUSTOM})
        ```

    Note:
        - Level names must be unique and not conflict with existing levels
        - Level numbers should not conflict with existing level numbers
        - This function is idempotent - calling it multiple times with the
          same level_name is safe
    """
    if method_name is None:
        method_name = level_name.lower()

    # Check if level already exists
    existing_level = logging.getLevelName(level_name)
    if existing_level != f"Level {level_name}":
        # Level already exists, check if number matches
        if existing_level == level_number:
            # Same name and number, this is idempotent
            _custom_levels.add(level_name)
            return level_number
        else:
            raise ValueError(
                f"Log level '{level_name}' already exists with number {existing_level}"
            )

    # Add the level to the logging module
    logging.addLevelName(level_number, level_name)

    # Add the level as an attribute to the logging module
    setattr(logging, level_name, level_number)

    # Add logging method to Logger class
    def log_for_level(self, message: str, *args: Any, **kwargs: Any) -> None:
        """Log a message at the custom level."""
        if self.isEnabledFor(level_number):
            self._log(level_number, message, args, **kwargs)

    def log_to_root(message: str, *args: Any, **kwargs: Any) -> None:
        """Log a message at the custom level to root logger."""
        logging.log(level_number, message, *args, **kwargs)

    # Add method to Logger class
    setattr(logging.getLoggerClass(), method_name, log_for_level)

    # Add convenience function to logging module
    setattr(logging, method_name, log_to_root)

    # Track this custom level
    _custom_levels.add(level_name)

    return level_number


def get_custom_levels() -> Set[str]:
    """Get all registered custom log levels.

    Returns:
        Set of custom level names
    """
    return _custom_levels.copy()


def is_custom_level(level_name: str) -> bool:
    """Check if a log level is a custom level.

    Args:
        level_name: Name of the level to check

    Returns:
        True if the level is a custom level, False otherwise
    """
    return level_name in _custom_levels


# Pre-register a CUSTOM level at 25 (between INFO=20 and WARNING=30)
CUSTOM_LEVEL_NUMBER = 25
add_custom_log_level("CUSTOM", CUSTOM_LEVEL_NUMBER)


__all__ = [
    "add_custom_log_level",
    "get_custom_levels",
    "is_custom_level",
    "CUSTOM_LEVEL_NUMBER",
]
