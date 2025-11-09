"""Custom exceptions for the file storage system.

This module defines all custom exceptions used throughout the storage layer,
providing clear error handling and security event tracking.
"""

from typing import Any, Dict, Optional


class StorageError(Exception):
    """Base exception for storage-related errors."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        """Initialize storage error.

        Args:
            message: Error message
            details: Optional additional details
        """
        super().__init__(message)
        self.message = message
        self.details = details or {}


class PathTraversalError(StorageError):
    """Raised when path traversal attempt is detected.

    This is a critical security error that should be logged
    and potentially trigger security alerts.
    """

    def __init__(self, message: str, path: Optional[str] = None):
        """Initialize path traversal error.

        Args:
            message: Error message
            path: The offending path that triggered the error
        """
        details = {"path": path} if path else {}
        super().__init__(message, details)


class InvalidPathError(StorageError):
    """Raised when a path is invalid or malformed."""

    def __init__(self, message: str, path: Optional[str] = None):
        """Initialize invalid path error.

        Args:
            message: Error message
            path: The invalid path
        """
        details = {"path": path} if path else {}
        super().__init__(message, details)


class ValidationError(StorageError):
    """Raised when file validation fails."""

    def __init__(self, message: str, validation_type: Optional[str] = None, **kwargs):
        """Initialize validation error.

        Args:
            message: Error message
            validation_type: Type of validation that failed (mime, size, etc.)
            **kwargs: Additional validation details
        """
        details = kwargs
        if validation_type:
            details["validation_type"] = validation_type
        super().__init__(message, details)


class FileNotFoundError(StorageError):
    """Raised when a requested file is not found."""

    def __init__(self, message: str, file_path: Optional[str] = None):
        """Initialize file not found error.

        Args:
            message: Error message
            file_path: Path of the missing file
        """
        details = {"file_path": file_path} if file_path else {}
        super().__init__(message, details)


class FileSizeLimitError(ValidationError):
    """Raised when file exceeds size limits."""

    def __init__(
        self,
        message: str,
        file_size: Optional[int] = None,
        max_size: Optional[int] = None,
    ):
        """Initialize file size limit error.

        Args:
            message: Error message
            file_size: Actual file size
            max_size: Maximum allowed size
        """
        super().__init__(
            message, validation_type="size", file_size=file_size, max_size=max_size
        )


class InvalidMimeTypeError(ValidationError):
    """Raised when file MIME type is invalid or not allowed."""

    def __init__(
        self,
        message: str,
        detected_type: Optional[str] = None,
        expected_type: Optional[str] = None,
    ):
        """Initialize invalid MIME type error.

        Args:
            message: Error message
            detected_type: The detected MIME type
            expected_type: The expected/allowed MIME type
        """
        super().__init__(
            message,
            validation_type="mime_type",
            detected_type=detected_type,
            expected_type=expected_type,
        )


class StorageProviderError(StorageError):
    """Raised when storage provider operation fails."""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        operation: Optional[str] = None,
    ):
        """Initialize storage provider error.

        Args:
            message: Error message
            provider: Storage provider name (local, s3, azure, etc.)
            operation: Operation that failed (save, get, delete, etc.)
        """
        super().__init__(
            message, details={"provider": provider, "operation": operation}
        )


class AccessDeniedError(StorageError):
    """Raised when access to a file is denied."""

    def __init__(self, message: str, file_path: Optional[str] = None):
        """Initialize access denied error.

        Args:
            message: Error message
            file_path: Path to the file
        """
        details = {"file_path": file_path} if file_path else {}
        super().__init__(message, details)
