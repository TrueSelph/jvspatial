"""Path sanitization to prevent path traversal and security attacks.

This module provides robust path validation and sanitization to protect
against path traversal attacks, directory escapes, and other file system
security vulnerabilities.
"""

import logging
import os
import re
from pathlib import Path
from typing import Optional

from ..exceptions import InvalidPathError, PathTraversalError

logger = logging.getLogger(__name__)


class PathSanitizer:
    r"""Secure path sanitization to prevent path traversal attacks.

    This class implements multi-stage validation to ensure all file paths
    are safe and confined within the designated base directory.

    Security Features:
        - Path traversal prevention (../, ..\\)
        - Absolute path blocking
        - Hidden file detection
        - Special character filtering
        - Symlink attack prevention
        - Path depth limits
        - Filename length limits

    Example:
        >>> sanitizer = PathSanitizer()
        >>> safe_path = sanitizer.sanitize_path("docs/report.pdf")
        >>> # Returns: "docs/report.pdf"

        >>> sanitizer.sanitize_path("../../etc/passwd")
        >>> # Raises: PathTraversalError
    """

    # Allowed filename characters (alphanumeric, dash, underscore, dot)
    SAFE_FILENAME_PATTERN = re.compile(r"^[a-zA-Z0-9_\-\.]+$")

    # Dangerous patterns that should never appear in paths
    DANGEROUS_PATTERNS = [
        r"\.\.",  # Parent directory
        r"~",  # Home directory
        r"\$",  # Shell variables
        r"`",  # Command substitution
        r"\|",  # Pipe
        r";",  # Command separator
        r"&",  # Background execution
        r">",  # Redirection
        r"<",  # Redirection
        r"\0",  # Null byte
    ]

    # Maximum path depth (number of directory levels)
    MAX_PATH_DEPTH = 10

    # Maximum filename length (filesystem limit)
    MAX_FILENAME_LENGTH = 255

    # Maximum total path length
    MAX_PATH_LENGTH = 4096

    @classmethod
    def sanitize_path(
        cls, file_path: str, base_dir: Optional[str] = None, allow_hidden: bool = False
    ) -> str:
        """Sanitize and validate file path.

        Performs multi-stage validation:
        1. Input validation and normalization
        2. Dangerous pattern detection
        3. Path component validation
        4. Base directory confinement

        Args:
            file_path: Raw file path from user input
            base_dir: Base directory to confine paths within (optional)
            allow_hidden: Allow hidden files (starting with .) (default: False)

        Returns:
            Sanitized safe path (relative to base_dir if provided)

        Raises:
            PathTraversalError: If path traversal attempt detected
            InvalidPathError: If path is invalid or malformed

        Example:
            >>> PathSanitizer.sanitize_path("uploads/doc.pdf", "/var/files")
            'uploads/doc.pdf'

            >>> PathSanitizer.sanitize_path("../../../etc/passwd", "/var/files")
            PathTraversalError: Path traversal attempt detected
        """
        if not file_path:
            raise InvalidPathError("File path cannot be empty")

        # Stage 1: Input validation
        if len(file_path) > cls.MAX_PATH_LENGTH:
            raise InvalidPathError(
                f"Path length exceeds maximum ({cls.MAX_PATH_LENGTH})"
            )

        # Remove null bytes and other control characters
        file_path = file_path.replace("\0", "")
        file_path = "".join(
            char for char in file_path if ord(char) >= 32 or char == "\n"
        )

        # Check for absolute paths (Unix and Windows)
        if os.path.isabs(file_path):
            logger.warning(f"Absolute path rejected: {file_path}")
            raise PathTraversalError("Absolute paths are not allowed", path=file_path)

        # Stage 2: Dangerous pattern detection
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, file_path):
                logger.warning(f"Dangerous pattern detected in path: {file_path}")
                raise PathTraversalError(
                    "Dangerous pattern detected in path", path=file_path
                )

        # Stage 3: Path normalization
        # Normalize path separators and remove redundant separators
        normalized = os.path.normpath(file_path)

        # Convert Windows path separators to Unix for consistency
        normalized = normalized.replace("\\", "/")

        # Re-check for parent directory references after normalization
        if normalized.startswith("..") or "/.." in normalized or normalized == ".":
            logger.warning(f"Path traversal detected after normalization: {file_path}")
            raise PathTraversalError("Path traversal attempt detected", path=file_path)

        # Stage 4: Path component validation
        path_obj = Path(normalized)
        parts = path_obj.parts

        # Check path depth
        if len(parts) > cls.MAX_PATH_DEPTH:
            raise InvalidPathError(
                f"Path depth exceeds maximum ({cls.MAX_PATH_DEPTH})", path=file_path
            )

        # Validate each path component
        for part in parts:
            # Check for hidden files
            if not allow_hidden and part.startswith(".") and part != ".":
                raise InvalidPathError(
                    f"Hidden files not allowed: {part}", path=file_path
                )

            # Validate filename pattern
            if not cls.SAFE_FILENAME_PATTERN.match(part):
                raise InvalidPathError(
                    f"Invalid path component (contains unsafe characters): {part}",
                    path=file_path,
                )

            # Check filename length
            if len(part) > cls.MAX_FILENAME_LENGTH:
                raise InvalidPathError(
                    f"Path component too long (max {cls.MAX_FILENAME_LENGTH}): {part}",
                    path=file_path,
                )

        # Stage 5: Base directory confinement (if base_dir provided)
        if base_dir:
            # Resolve base directory to absolute path
            base = Path(base_dir).resolve()

            # Construct full path and resolve it
            full_path = (base / normalized).resolve()

            # Verify the resolved path is within base directory
            try:
                relative = full_path.relative_to(base)
            except ValueError:
                logger.error(f"Path escape attempt: {file_path} escapes {base_dir}")
                raise PathTraversalError("Path escapes base directory", path=file_path)

            # Return the relative path from base
            return str(relative).replace("\\", "/")

        # Return normalized path
        return normalized.replace("\\", "/")

    @classmethod
    def sanitize_filename(cls, filename: str, allow_hidden: bool = False) -> str:
        """Sanitize a single filename (no path separators).

        Args:
            filename: Raw filename
            allow_hidden: Allow hidden files (starting with .)

        Returns:
            Sanitized filename

        Raises:
            InvalidPathError: If filename is invalid

        Example:
            >>> PathSanitizer.sanitize_filename("my-document.pdf")
            'my-document.pdf'

            >>> PathSanitizer.sanitize_filename("../etc/passwd")
            'etc_passwd'  # Path separators removed
        """
        if not filename:
            raise InvalidPathError("Filename cannot be empty")

        # Remove path separators (convert to underscores)
        filename = filename.replace("/", "_").replace("\\", "_")

        # Remove null bytes
        filename = filename.replace("\0", "")

        # Check for hidden files
        if not allow_hidden and filename.startswith(".") and filename != ".":
            raise InvalidPathError(f"Hidden files not allowed: {filename}")

        # Check pattern and sanitize if needed
        if not cls.SAFE_FILENAME_PATTERN.match(filename):
            # Remove invalid characters
            filename = re.sub(r"[^a-zA-Z0-9_\-\.]", "_", filename)
            logger.info("Filename sanitized by removing invalid characters")

        # Enforce length limit
        if len(filename) > cls.MAX_FILENAME_LENGTH:
            # Preserve extension
            name, ext = os.path.splitext(filename)
            max_name_len = cls.MAX_FILENAME_LENGTH - len(ext)
            filename = name[:max_name_len] + ext
            logger.info("Filename truncated to %d characters", cls.MAX_FILENAME_LENGTH)

        return filename

    @classmethod
    def validate_path(cls, file_path: str, base_dir: Optional[str] = None) -> bool:
        """Validate a file path without modifying it.

        Args:
            file_path: Path to validate
            base_dir: Base directory to confine within (optional)

        Returns:
            True if path is valid and safe

        Example:
            >>> PathSanitizer.validate_path("docs/report.pdf")
            True

            >>> PathSanitizer.validate_path("../../etc/passwd")
            False
        """
        try:
            cls.sanitize_path(file_path, base_dir=base_dir)
            return True
        except (PathTraversalError, InvalidPathError):
            return False

    @classmethod
    def is_safe_path(cls, file_path: str, base_dir: Optional[str] = None) -> bool:
        """Check if a path is safe (alias for validate_path).

        Args:
            file_path: Path to check
            base_dir: Base directory to confine within (optional)

        Returns:
            True if path is safe
        """
        return cls.validate_path(file_path, base_dir=base_dir)
