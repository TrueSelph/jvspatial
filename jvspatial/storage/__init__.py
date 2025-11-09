"""File storage system for jvspatial.

This package provides a secure, scalable file storage system with support for
multiple storage backends (local, S3, Azure, GCP). It includes comprehensive
security features, validation, and MongoDB-backed URL proxy management.

Architecture:
    - Security Layer: Path sanitization, file validation
    - Interface Layer: Abstract storage providers
    - Management Layer: File management, URL proxy, metadata
    - API Layer: RESTful endpoints (Phase 4)

Phase 3 (Current):
    URL Proxy Manager with MongoDB integration for secure file access.

Example:
    >>> from jvspatial.storage import create_storage, get_proxy_manager
    >>> from jvspatial.storage.security import PathSanitizer, FileValidator
    >>>
    >>> # Sanitize paths
    >>> safe_path = PathSanitizer.sanitize_path("uploads/doc.pdf")
    >>>
    >>> # Validate files
    >>> validator = FileValidator(max_size_mb=10)
    >>> result = validator.validate_file(file_bytes, "doc.pdf")
    >>>
    >>> # Get storage interface
    >>> storage = create_storage("local", root_dir=".files")
    >>>
    >>> # Create URL proxy for secure file access
    >>> manager = get_proxy_manager()
    >>> proxy = manager.create_proxy(
    ...     file_path="uploads/document.pdf",
    ...     expires_in=3600,  # 1 hour
    ...     one_time=True
    ... )
    >>> print(f"Access via: /p/{proxy.code}")

Security Features:
    - Multi-stage path traversal prevention
    - MIME type detection and validation
    - File size limit enforcement
    - Dangerous file type blocking
    - Path depth and length limits
    - Cryptographically secure URL proxy codes
    - Automatic proxy expiration
    - One-time use URLs
    - Access tracking and statistics

For detailed documentation, see:
    jvspatial/docs/md/file-storage-architecture.md
"""

import logging
import os
from typing import Any, Dict

# Import core components
from .interfaces import FileStorageInterface, LocalFileInterface, S3FileInterface
from .security import FileValidator, PathSanitizer

# Phase 3 imports (conditionally import if available)
try:
    from .managers import URLProxyManager, get_proxy_manager
    from .models import URLProxy

    _HAS_PROXY_MANAGER = True
except ImportError:
    URLProxy = Any  # type: ignore
    URLProxyManager = Any  # type: ignore
    get_proxy_manager = None  # type: ignore
    _HAS_PROXY_MANAGER = False

from .exceptions import (
    AccessDeniedError,
    FileNotFoundError,
    FileSizeLimitError,
    InvalidMimeTypeError,
    InvalidPathError,
    PathTraversalError,
    StorageError,
    StorageProviderError,
    ValidationError,
)

logger = logging.getLogger(__name__)

# Default storage configuration
_default_config: Dict[str, Any] = {
    "max_file_size_mb": 100,
    "allowed_extensions": [],
    "blocked_extensions": [".exe", ".bat", ".sh", ".cmd"],
    "max_path_depth": 10,
    "max_path_length": 255,
}

# Environment variable constants (for backward compatibility with old file_interface)
FILE_INTERFACE_TYPE = os.environ.get("JVSPATIAL_FILE_INTERFACE", "local")
DEFAULT_FILES_ROOT = os.environ.get("JVSPATIAL_FILES_ROOT_PATH", ".files")


__version__ = "1.0.0-phase3"
__all__ = [
    # Main factory function
    "create_storage",
    "create_default_storage",
    # Core interfaces
    "FileStorageInterface",
    "LocalFileInterface",
    "S3FileInterface",
    # Security components
    "PathSanitizer",
    "FileValidator",
    # Models (Phase 3)
    "URLProxy",
    # Managers (Phase 3)
    "URLProxyManager",
    "get_proxy_manager",
    # Exceptions
    "StorageError",
    "PathTraversalError",
    "InvalidPathError",
    "ValidationError",
    "FileNotFoundError",
    "FileSizeLimitError",
    "InvalidMimeTypeError",
    "StorageProviderError",
    "AccessDeniedError",
    # Backward compatibility constants
    "FILE_INTERFACE_TYPE",
    "DEFAULT_FILES_ROOT",
]


def create_storage(provider: str = "local", **kwargs: Any) -> FileStorageInterface:
    """Create a storage interface with direct instantiation.

    Args:
        provider: Storage provider type ('local', 's3')
        **kwargs: Provider-specific configuration

    Returns:
        FileStorageInterface implementation

    Examples:
        # Local storage
        storage = create_storage("local", root_dir="./files")

        # S3 storage
        storage = create_storage("s3", bucket_name="my-bucket")
    """
    if provider == "local":
        root_dir = kwargs.get("root_dir", ".files")
        base_url = kwargs.get("base_url")
        create_root = kwargs.get("create_root", True)

        # Create validator if custom settings provided
        validator = None
        if "max_size_mb" in kwargs or "allowed_mime_types" in kwargs:
            validator = FileValidator(
                max_size_mb=kwargs.get("max_size_mb"),
                allowed_mime_types=kwargs.get("allowed_mime_types"),
            )

        return LocalFileInterface(
            root_dir=root_dir,
            base_url=base_url,
            create_root=create_root,
            validator=validator,
        )

    elif provider == "s3":
        bucket_name = kwargs.get("bucket_name") or os.getenv("JVSPATIAL_S3_BUCKET_NAME")
        if not bucket_name:
            raise ValueError("S3 bucket_name is required")

        return S3FileInterface(
            bucket_name=bucket_name,
            region_name=kwargs.get("region_name")
            or os.getenv("JVSPATIAL_S3_REGION_NAME", "us-east-1"),
            access_key_id=kwargs.get("access_key_id")
            or os.getenv("JVSPATIAL_S3_ACCESS_KEY_ID"),
            secret_access_key=kwargs.get("secret_access_key")
            or os.getenv("JVSPATIAL_S3_SECRET_ACCESS_KEY"),
            endpoint_url=kwargs.get("endpoint_url")
            or os.getenv("JVSPATIAL_S3_ENDPOINT_URL"),
            url_expiration=kwargs.get("url_expiration", 3600),
        )

    else:
        raise ValueError(f"Unsupported storage provider: '{provider}'")


def create_default_storage() -> FileStorageInterface:
    """Create the default storage based on environment.

    Returns:
        Configured storage interface
    """
    provider = os.getenv("JVSPATIAL_FILE_INTERFACE", "local")
    return create_storage(provider)


def get_default_config() -> Dict[str, Any]:
    """Get default storage configuration.

    Returns:
        Dict with default configuration values

    Example:
        >>> config = get_default_config()
        >>> print(config['max_file_size_mb'])
        100
    """
    return _default_config.copy()


def set_default_config(**kwargs) -> None:
    """Update default storage configuration.

    Args:
        **kwargs: Configuration values to update

    Example:
        >>> set_default_config(max_file_size_mb=50)
    """
    _default_config.update(kwargs)
    logger.info(f"Updated default storage config: {kwargs}")
