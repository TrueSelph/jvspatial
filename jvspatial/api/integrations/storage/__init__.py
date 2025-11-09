"""File storage integration for jvspatial API.

Provides file storage service integration with the API.
"""

try:
    from .service import FileStorageService  # noqa: F401

    __all__ = ["FileStorageService"]
except ImportError:
    # Service may not be available in all configurations
    __all__ = []
