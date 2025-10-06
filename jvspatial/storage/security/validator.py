"""File validation for security and integrity checks.

This module provides comprehensive file validation including MIME type detection,
size limit enforcement, and dangerous file type blocking.
"""

import logging
import mimetypes
from pathlib import Path
from typing import Any, Dict, Optional, Set, TypedDict, cast

from ..exceptions import FileSizeLimitError, InvalidMimeTypeError


class ValidationResult(TypedDict):
    """Type definition for validation result."""

    valid: bool
    mime_type: str
    size_bytes: int
    extension: str
    filename: str


logger = logging.getLogger(__name__)


# Try to import python-magic for more accurate MIME detection
try:
    import magic

    HAS_MAGIC = True
except ImportError:
    HAS_MAGIC = False
    logger.info("python-magic not available, falling back to mimetypes module")


class FileValidator:
    """Comprehensive file validation for security and integrity.

    This class validates files based on:
        - MIME type detection and verification
        - File size limits
        - Dangerous file type blocking
        - Extension matching

    Security Features:
        - Detects actual file content (not just extension)
        - Blocks executable files and scripts
        - Enforces configurable size limits
        - Validates MIME type matches extension

    Example:
        >>> validator = FileValidator(max_size_mb=10)
        >>> validator.validate_file(
        ...     content=file_bytes,
        ...     filename="document.pdf"
        ... )
        >>> # Returns validation result dict
    """

    # Default maximum file size (100 MB)
    DEFAULT_MAX_SIZE_BYTES = 100 * 1024 * 1024

    # Allowed MIME types (configurable per deployment)
    DEFAULT_ALLOWED_MIME_TYPES: Set[str] = {
        # Images
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
        "image/svg+xml",
        "image/bmp",
        "image/tiff",
        # Documents
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.ms-excel",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.ms-powerpoint",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        # Text
        "text/plain",
        "text/csv",
        "text/html",
        "text/css",
        "text/javascript",
        "application/json",
        "application/xml",
        "text/xml",
        # Archives
        "application/zip",
        "application/x-tar",
        "application/gzip",
        "application/x-7z-compressed",
        # Media
        "audio/mpeg",
        "audio/wav",
        "audio/ogg",
        "video/mp4",
        "video/mpeg",
        "video/webm",
    }

    # Blocked MIME types (executables, scripts, dangerous files)
    BLOCKED_MIME_TYPES: Set[str] = {
        "application/x-executable",
        "application/x-msdos-program",
        "application/x-msdownload",
        "application/x-dosexec",
        "application/x-sharedlib",
        "application/x-sh",
        "application/x-shellscript",
        "text/x-shellscript",
        "application/x-perl",
        "application/x-python",
        "application/x-ruby",
        "application/x-php",
        "application/x-httpd-php",
        "text/x-php",
        "application/javascript",
        "application/x-javascript",
    }

    # Blocked file extensions
    BLOCKED_EXTENSIONS: Set[str] = {
        ".exe",
        ".dll",
        ".so",
        ".dylib",  # Executables
        ".sh",
        ".bash",
        ".zsh",
        ".fish",  # Shell scripts
        ".py",
        ".rb",
        ".pl",
        ".php",  # Scripts
        ".bat",
        ".cmd",
        ".ps1",  # Windows scripts
        ".app",
        ".deb",
        ".rpm",  # Installers
        ".bin",
        ".run",  # Binary files
    }

    def __init__(
        self,
        max_size_mb: Optional[float] = None,
        allowed_mime_types: Optional[Set[str]] = None,
        blocked_mime_types: Optional[Set[str]] = None,
        blocked_extensions: Optional[Set[str]] = None,
        strict_mime_check: bool = True,
    ):
        """Initialize file validator.

        Args:
            max_size_mb: Maximum file size in megabytes (None = use default)
            allowed_mime_types: Set of allowed MIME types (None = use defaults)
            blocked_mime_types: Set of blocked MIME types (None = use defaults)
            blocked_extensions: Set of blocked extensions (None = use defaults)
            strict_mime_check: Require MIME type to match extension
        """
        # Set size limit
        if max_size_mb is not None:
            self.max_size_bytes = int(max_size_mb * 1024 * 1024)
        else:
            self.max_size_bytes = self.DEFAULT_MAX_SIZE_BYTES

        # Set allowed/blocked types
        self.allowed_mime_types = allowed_mime_types or self.DEFAULT_ALLOWED_MIME_TYPES
        self.blocked_mime_types = blocked_mime_types or self.BLOCKED_MIME_TYPES
        self.blocked_extensions = blocked_extensions or self.BLOCKED_EXTENSIONS
        self.strict_mime_check = strict_mime_check

    def validate_file(
        self, content: bytes, filename: str, expected_mime_type: Optional[str] = None
    ) -> ValidationResult:
        """Validate file content and metadata.

        Performs comprehensive validation:
        1. File size check
        2. MIME type detection
        3. Extension validation
        4. Dangerous file type blocking

        Args:
            content: File content as bytes
            filename: Original filename
            expected_mime_type: Expected MIME type (optional)

        Returns:
            Dict with validation results:
                - valid: bool
                - mime_type: str
                - size_bytes: int
                - extension: str

        Raises:
            FileSizeLimitError: If file exceeds size limit
            InvalidMimeTypeError: If MIME type is invalid or blocked
            ValidationError: If validation fails

        Example:
            >>> result = validator.validate_file(
            ...     content=file_bytes,
            ...     filename="photo.jpg"
            ... )
            >>> print(result['mime_type'])
            'image/jpeg'
        """
        # Stage 1: Size validation
        file_size = len(content)
        if file_size > self.max_size_bytes:
            max_mb = self.max_size_bytes / (1024 * 1024)
            actual_mb = file_size / (1024 * 1024)
            logger.warning(
                f"File size limit exceeded: {actual_mb:.2f}MB > {max_mb:.2f}MB"
            )
            msg = f"File size ({actual_mb:.2f}MB) exceeds limit ({max_mb:.2f}MB)"
            raise FileSizeLimitError(
                msg, file_size=file_size, max_size=self.max_size_bytes
            )

        # Stage 2: MIME type detection
        detected_mime = self.detect_mime_type(content, filename)

        # Stage 3: Extension validation
        extension = Path(filename).suffix.lower()

        # Check for blocked extensions
        if extension in self.blocked_extensions:
            logger.warning(f"Blocked file extension: {extension}")
            raise InvalidMimeTypeError(
                f"File extension '{extension}' is not allowed",
                detected_type=detected_mime,
                expected_type="allowed extension",
            )

        # Stage 4: MIME type validation
        if detected_mime in self.blocked_mime_types:
            logger.warning(f"Blocked MIME type detected: {detected_mime}")
            raise InvalidMimeTypeError(
                f"File type '{detected_mime}' is not allowed",
                detected_type=detected_mime,
            )

        # Check if MIME type is in allowed list
        if self.allowed_mime_types and detected_mime not in self.allowed_mime_types:
            logger.warning(f"MIME type not in allowed list: {detected_mime}")
            raise InvalidMimeTypeError(
                f"File type '{detected_mime}' is not in allowed types",
                detected_type=detected_mime,
            )

        # Stage 5: Strict MIME/extension matching
        if (
            self.strict_mime_check
            and expected_mime_type
            and detected_mime != expected_mime_type
        ):
            logger.warning(
                f"MIME type mismatch: detected={detected_mime}, "
                f"expected={expected_mime_type}"
            )
            raise InvalidMimeTypeError(
                "File MIME type does not match expected type",
                detected_type=detected_mime,
                expected_type=expected_mime_type,
            )

        logger.info(
            f"File validation successful: {filename} "
            f"({detected_mime}, {file_size} bytes)"
        )

        return {
            "valid": True,
            "mime_type": detected_mime,
            "size_bytes": file_size,
            "extension": extension,
            "filename": filename,
        }

    def detect_mime_type(self, content: bytes, filename: Optional[str] = None) -> str:
        """Detect MIME type of file content.

        Uses python-magic if available for content-based detection,
        falls back to mimetypes module for extension-based detection.

        Args:
            content: File content as bytes
            filename: Filename for extension-based fallback

        Returns:
            Detected MIME type string

        Example:
            >>> mime = validator.detect_mime_type(b'%PDF-1.4...', 'doc.pdf')
            >>> print(mime)
            'application/pdf'
        """
        if HAS_MAGIC and content:
            try:
                # Use python-magic for content-based detection
                mime = cast(str, magic.from_buffer(content, mime=True))
                logger.debug(f"MIME type detected via magic: {mime}")
                return mime
            except Exception as e:
                logger.warning(f"Magic MIME detection failed: {e}, using fallback")

        # Fallback to extension-based detection
        if filename:
            mime_type, _ = mimetypes.guess_type(filename)
            if mime_type:
                logger.debug(f"MIME type guessed from extension: {mime_type}")
                return mime_type

        # Ultimate fallback
        logger.warning("Could not detect MIME type, defaulting to octet-stream")
        return "application/octet-stream"

    def check_mime_type(self, mime_type: str, allow_blocked: bool = False) -> bool:
        """Check if a MIME type is allowed.

        Args:
            mime_type: MIME type to check
            allow_blocked: Override blocked types check

        Returns:
            True if MIME type is allowed

        Example:
            >>> validator.check_mime_type('image/jpeg')
            True

            >>> validator.check_mime_type('application/x-executable')
            False
        """
        # Check blocked list first
        if not allow_blocked and mime_type in self.blocked_mime_types:
            return False

        # Check allowed list
        if self.allowed_mime_types:
            return mime_type in self.allowed_mime_types

        # If no allowed list, accept anything not blocked
        return True

    def check_size(self, content: bytes, max_size_bytes: Optional[int] = None) -> bool:
        """Check if file size is within limits.

        Args:
            content: File content as bytes
            max_size_bytes: Override default max size

        Returns:
            True if size is acceptable

        Example:
            >>> validator.check_size(file_bytes)
            True
        """
        size_limit = (
            max_size_bytes if max_size_bytes is not None else self.max_size_bytes
        )
        return len(content) <= size_limit

    def get_file_info(self, content: bytes, filename: str) -> Dict[str, Any]:
        """Get file information without raising errors.

        Args:
            content: File content as bytes
            filename: Filename

        Returns:
            Dict with file information

        Example:
            >>> info = validator.get_file_info(file_bytes, 'doc.pdf')
            >>> print(info['mime_type'])
            'application/pdf'
        """
        return {
            "filename": filename,
            "size_bytes": len(content),
            "extension": Path(filename).suffix.lower(),
            "mime_type": self.detect_mime_type(content, filename),
            "within_size_limit": self.check_size(content),
        }
