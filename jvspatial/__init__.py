"""
jvspatial package initialization.

This package provides an asynchronous, object-spatial Python library for building
persistence and business logic application layers.
"""

__version__ = "0.0.1"

# Make storage module available (new in this version)
# Make exceptions available at package level
from . import exceptions, storage

__all__ = [
    "exceptions",
    "storage",
]
