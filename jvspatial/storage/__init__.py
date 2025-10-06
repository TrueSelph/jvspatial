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
    >>> from jvspatial.storage import get_file_interface, get_proxy_manager
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
    >>> storage = get_file_interface("local", root_dir=".files")
    >>>
    >>> # Create URL proxy for secure file access
    >>> manager = get_proxy_manager()
    >>> proxy = await manager.create_proxy(
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
from typing import Any, Dict, Optional

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


# Environment variable constants (for backward compatibility with old file_interface)
FILE_INTERFACE_TYPE = os.environ.get("JVSPATIAL_FILE_INTERFACE", "local")
DEFAULT_FILES_ROOT = os.environ.get("JVSPATIAL_FILES_ROOT_PATH", ".files")


__version__ = "1.0.0-phase3"
__all__ = [
    # Main factory function
    "get_file_interface",
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


def get_file_interface(
    provider: Optional[str] = None,
    root_dir: Optional[str] = None,
    config: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> FileStorageInterface:
    """Factory function to get file storage interface.

    Creates and returns a storage provider instance based on the
    specified provider type and configuration.

    Provider can be specified via:
        1. provider parameter
        2. JVSPATIAL_FILE_INTERFACE environment variable
        3. Default: "local"

    Args:
        provider: Storage provider type. Options:
            - "local": Local filesystem storage
            - "s3": AWS S3 storage
        root_dir: Root directory for local storage (convenience parameter)
        config: Provider-specific configuration dict. May include:
            Local:
                - root_dir: Root directory for files (default: ".files")
                - base_url: Base URL for file URLs
                - create_root: Auto-create root directory (default: True)
            S3:
                - bucket_name: S3 bucket name (required)
                - region_name: AWS region (default: us-east-1)
                - access_key_id: AWS access key ID
                - secret_access_key: AWS secret access key
                - endpoint_url: Custom endpoint URL (for S3-compatible services)
                - url_expiration: Default URL expiration in seconds
        **kwargs: Additional provider-specific parameters

    Returns:
        FileStorageInterface implementation for the specified provider

    Raises:
        ValueError: If provider type is invalid or required config missing
        StorageError: If provider initialization fails

    Example:
        >>> # Local filesystem storage (simplest)
        >>> storage = get_file_interface()
        >>>
        >>> # Local with custom root directory
        >>> storage = get_file_interface(provider="local", root_dir="/var/files")
        >>>
        >>> # AWS S3 storage
        >>> storage = get_file_interface(
        ...     provider="s3",
        ...     config={
        ...         "bucket_name": "my-bucket",
        ...         "region_name": "us-west-2"
        ...     }
        ... )
        >>>
        >>> # Use environment variable (JVSPATIAL_FILE_INTERFACE=s3)
        >>> storage = get_file_interface()  # Will use S3 if env var set

    Environment Variables:
        - JVSPATIAL_FILE_INTERFACE: Provider type (local, s3)

        For S3:
            - JVSPATIAL_S3_BUCKET_NAME: S3 bucket name
            - JVSPATIAL_S3_REGION_NAME: AWS region
            - JVSPATIAL_S3_ACCESS_KEY_ID: AWS access key ID
            - JVSPATIAL_S3_SECRET_ACCESS_KEY: AWS secret access key
            - JVSPATIAL_S3_ENDPOINT_URL: Custom endpoint URL
    """
    # Determine provider (parameter > env var > default)
    provider = provider or os.getenv("JVSPATIAL_FILE_INTERFACE", "local")
    provider = provider.lower() if provider else "local"

    # Merge config with kwargs
    config = config or {}
    config.update(kwargs)

    logger.info(f"Initializing file storage interface: provider={provider}")

    try:
        if provider == "local":
            # Local filesystem storage
            local_root_dir = root_dir or config.get("root_dir", ".files")
            base_url = config.get("base_url")
            create_root = config.get("create_root", True)

            # Create validator if custom settings provided
            validator = None
            if "max_size_mb" in config or "allowed_mime_types" in config:
                validator = FileValidator(
                    max_size_mb=config.get("max_size_mb"),
                    allowed_mime_types=config.get("allowed_mime_types"),
                )

            logger.info(f"Creating LocalFileInterface: root_dir={local_root_dir}")
            return LocalFileInterface(
                root_dir=local_root_dir,
                base_url=base_url,
                validator=validator,
                create_root=create_root,
            )

        elif provider == "s3":
            # AWS S3 storage
            s3_config = {
                "bucket_name": config.get("bucket_name"),
                "region_name": config.get("region_name"),
                "access_key_id": config.get("access_key_id"),
                "secret_access_key": config.get("secret_access_key"),
                "endpoint_url": config.get("endpoint_url"),
                "url_expiration": config.get("url_expiration", 3600),
            }

            # Create validator if custom settings provided
            if "max_size_mb" in config or "allowed_mime_types" in config:
                s3_config["validator"] = FileValidator(
                    max_size_mb=config.get("max_size_mb"),
                    allowed_mime_types=config.get("allowed_mime_types"),
                )

            logger.info(
                f"Creating S3FileInterface: bucket={s3_config.get('bucket_name')}"
            )
            return S3FileInterface(**s3_config)

        else:
            # Unknown provider
            available = ["local", "s3"]
            raise ValueError(
                f"Unknown storage provider: '{provider}'. "
                f"Available providers: {', '.join(available)}"
            )

    except Exception as e:
        if isinstance(e, ValueError):
            raise

        logger.error(f"Failed to initialize storage provider '{provider}': {e}")
        raise StorageProviderError(
            f"Failed to initialize {provider} storage: {e}",
            provider=provider,
            operation="init",
        )


# Module-level configuration
_default_config = {
    "max_file_size_mb": 100,
    "max_path_depth": 10,
    "max_filename_length": 255,
    "strict_mime_check": True,
    "allow_hidden_files": False,
}


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
