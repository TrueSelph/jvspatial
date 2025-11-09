"""File storage interfaces package.

This package defines the abstract interfaces and contracts that all
storage providers must implement.

Main Components:
    - FileStorageInterface: Abstract base class for storage providers
    - LocalFileInterface: Local filesystem storage implementation
    - S3FileInterface: AWS S3 storage implementation

Example:
    >>> from jvspatial.storage.interfaces import FileStorageInterface
    >>>
    >>> class MyStorage(FileStorageInterface):
    ...     async def save_file(self, file_path, content, metadata=None):
    ...         # Implementation
    ...         pass

    >>> # Using built-in implementations
    >>> from jvspatial.storage.interfaces import LocalFileInterface, S3FileInterface
    >>>
    >>> local_storage = LocalFileInterface(root_dir=".files")
    >>> s3_storage = S3FileInterface(bucket_name="my-bucket")
"""

from .base import FileStorageInterface
from .local import LocalFileInterface
from .s3 import S3FileInterface

__all__ = [
    "FileStorageInterface",
    "LocalFileInterface",
    "S3FileInterface",
]
