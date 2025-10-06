"""Security utilities for file storage.

This package provides security-focused utilities for path sanitization,
file validation, and protection against common file storage attacks.

Main Components:
    - PathSanitizer: Multi-stage path validation and sanitization
    - FileValidator: Comprehensive file validation (MIME, size, type)

Example:
    >>> from jvspatial.storage.security import PathSanitizer, FileValidator
    >>>
    >>> # Sanitize a file path
    >>> safe_path = PathSanitizer.sanitize_path("uploads/document.pdf")
    >>>
    >>> # Validate file content
    >>> validator = FileValidator(max_size_mb=10)
    >>> result = validator.validate_file(file_bytes, "document.pdf")
"""

from .path_sanitizer import PathSanitizer
from .validator import FileValidator

__all__ = [
    "PathSanitizer",
    "FileValidator",
]
