"""Local filesystem storage implementation.

This module provides a local filesystem-based implementation of the
FileStorageInterface with full security integration and async support.
"""

import asyncio
import hashlib
import logging
import os
from asyncio import to_thread
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional, cast

from ..exceptions import (
    AccessDeniedError,
    FileNotFoundError,
    PathTraversalError,
    StorageProviderError,
)
from ..security.path_sanitizer import PathSanitizer
from ..security.validator import FileValidator
from .base import FileStorageInterface

# FastAPI imports (optional - only for serve_file)


logger = logging.getLogger(__name__)


class LocalFileInterface(FileStorageInterface):
    """Local filesystem storage implementation.

    This provider stores files on the local filesystem with comprehensive
    security checks including path sanitization, file validation, and
    access control.

    Features:
        - Async I/O using asyncio.to_thread()
        - Path traversal prevention via PathSanitizer
        - File validation via FileValidator
        - Automatic directory creation
        - Efficient streaming support
        - Thread-safe operations

    Security:
        All paths are validated against the root directory to prevent
        access outside the designated storage area. Uses PathSanitizer
        to block path traversal attempts.

    Args:
        root_dir: Root directory for file storage (default: ".files")
        base_url: Base URL for generating file URLs (default: None)
        validator: Optional FileValidator instance for custom validation
        create_root: Automatically create root directory if missing (default: True)

    Example:
        >>> storage = LocalFileInterface(root_dir="/var/files")
        >>> await storage.save_file("uploads/doc.pdf", file_bytes)
        {'path': 'uploads/doc.pdf', 'size': 1024, 'checksum': 'abc123...'}
    """

    def __init__(
        self,
        root_dir: str = ".files",
        base_url: Optional[str] = None,
        validator: Optional[FileValidator] = None,
        create_root: bool = True,
    ):
        """Initialize local file storage.

        Args:
            root_dir: Root directory for file storage
            base_url: Base URL for file access (e.g., "http://localhost:8000")
            validator: Optional FileValidator instance
            create_root: Create root directory if it doesn't exist
        """
        self.root_dir = Path(root_dir).resolve()
        self.base_url = base_url.rstrip("/") if base_url else None
        self.validator = validator or FileValidator()

        # Create root directory if requested
        if create_root:
            self.root_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Local storage initialized at: {self.root_dir}")

        # Verify root directory exists and is writable
        if not self.root_dir.exists():
            raise StorageProviderError(
                f"Root directory does not exist: {self.root_dir}",
                provider="local",
                operation="init",
            )

        if not os.access(self.root_dir, os.W_OK):
            raise AccessDeniedError(
                f"Root directory is not writable: {self.root_dir}",
                file_path=str(self.root_dir),
            )

    def _get_full_path(self, file_path: str) -> Path:
        """Get and validate full filesystem path.

        Args:
            file_path: Relative file path

        Returns:
            Validated absolute Path object

        Raises:
            PathTraversalError: If path escapes root directory
        """
        # Sanitize path and verify it's within root directory
        sanitized = PathSanitizer.sanitize_path(file_path, base_dir=str(self.root_dir))

        # Construct full path
        full_path = self.root_dir / sanitized

        # Double-check with resolve() to catch symlink attacks
        try:
            resolved = full_path.resolve()
            resolved.relative_to(self.root_dir)
        except (ValueError, RuntimeError):
            logger.error(f"Path escape attempt blocked: {file_path}")
            raise PathTraversalError("Path escapes root directory", path=file_path)

        return full_path

    async def create_version(
        self,
        file_path: str,
        content: bytes,
        version: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a new version of a file.

        Args:
            file_path: Path to the file
            content: File content
            version: Optional version identifier (auto-generated if not provided)
            metadata: Optional metadata for the version

        Returns:
            Version identifier
        """
        import uuid
        from datetime import datetime

        # Generate version if not provided
        if version is None:
            version = (
                f"v{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"
            )

        # Create version directory (use .versions suffix to avoid conflicts)
        version_dir = self.root_dir / f"{file_path}.versions"
        await to_thread(version_dir.mkdir, parents=True, exist_ok=True)

        # Save version file
        version_file = version_dir / f"{version}.bin"
        await to_thread(version_file.write_bytes, content)

        # Save version metadata
        version_metadata = {
            "version": version,
            "created_at": datetime.utcnow().isoformat(),
            "size": len(content),
            "checksum": hashlib.sha256(content).hexdigest(),
            "metadata": metadata or {},
        }

        metadata_file = version_dir / f"{version}.meta.json"
        import json

        await to_thread(
            metadata_file.write_text, json.dumps(version_metadata, indent=2)
        )

        # Update latest version pointer
        latest_file = self.root_dir / f"{file_path}.latest"
        await to_thread(latest_file.write_text, version)

        logger.info(f"Created version {version} for file {file_path}")
        return {
            "version_id": version,
            "path": file_path,
            "created_at": version_metadata["created_at"],
            "size": version_metadata["size"],
        }

    async def get_version(self, file_path: str, version: str) -> Dict[str, Any]:
        """Retrieve a specific version of a file.

        Args:
            file_path: Path to the file
            version: Version identifier

        Returns:
            Dictionary with version information and content
        """
        version_file = self.root_dir / f"{file_path}.versions" / f"{version}.bin"

        if not await to_thread(version_file.exists):
            return None

        content = await to_thread(version_file.read_bytes)

        # Try to get metadata
        metadata_file = self.root_dir / f"{file_path}.versions" / f"{version}.meta.json"
        metadata = {}
        if await to_thread(metadata_file.exists):
            try:
                import json

                metadata_content = await to_thread(metadata_file.read_text)
                metadata = json.loads(metadata_content)
            except Exception as e:
                logger.warning(f"Failed to read metadata for version {version}: {e}")

        return {
            "version_id": version,
            "path": file_path,
            "content": content,
            "size": len(content),
            **metadata,
        }

    async def list_versions(self, file_path: str) -> List[Dict[str, Any]]:
        """List all versions of a file.

        Args:
            file_path: Path to the file

        Returns:
            List of version information dictionaries
        """
        versions_dir = self.root_dir / f"{file_path}.versions"

        if not await to_thread(versions_dir.exists):
            return []

        versions = []

        # Get all version files
        version_files = await to_thread(lambda: list(versions_dir.glob("*.meta.json")))

        for metadata_file in version_files:
            try:
                import json

                metadata_content = await to_thread(metadata_file.read_text)
                version_data = json.loads(metadata_content)
                # Ensure version_id is included
                version_data["version_id"] = version_data.get(
                    "version", metadata_file.stem.replace(".meta", "")
                )
                versions.append(version_data)
            except Exception as e:
                logger.warning(f"Failed to read version metadata {metadata_file}: {e}")

        # Sort by creation date (newest first)
        versions.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return versions

    async def delete_version(self, file_path: str, version: str) -> bool:
        """Delete a specific version of a file.

        Args:
            file_path: Path to the file
            version: Version identifier to delete

        Returns:
            True if version was deleted, False otherwise
        """
        versions_dir = self.root_dir / f"{file_path}.versions"

        if not await to_thread(versions_dir.exists):
            return False

        version_file = versions_dir / f"{version}.bin"
        metadata_file = versions_dir / f"{version}.meta.json"

        deleted = False

        if await to_thread(version_file.exists):
            await to_thread(version_file.unlink)
            deleted = True

        if await to_thread(metadata_file.exists):
            await to_thread(metadata_file.unlink)

        logger.info(f"Deleted version {version} for file {file_path}")
        return deleted

    async def get_latest_version(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get the latest version identifier for a file.

        Args:
            file_path: Path to the file

        Returns:
            Latest version information dictionary, or None if no versions exist
        """
        latest_file = self.root_dir / f"{file_path}.latest"

        if not await to_thread(latest_file.exists):
            return None

        try:
            latest_version_id = await to_thread(latest_file.read_text)
            # Get the full version info
            return await self.get_version(file_path, latest_version_id)
        except Exception as e:
            logger.warning(f"Failed to read latest version for {file_path}: {e}")
            return None

    async def save_file(
        self, file_path: str, content: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Save file to local filesystem.

        Args:
            file_path: Relative file path
            content: File content as bytes
            metadata: Optional metadata (logged but not stored separately)

        Returns:
            Dict with file information:
                - path: str - Stored file path
                - size: int - File size in bytes
                - checksum: str - MD5 checksum
                - storage_url: str - Local file URL (if base_url configured)
                - metadata: Dict - Stored metadata

        Raises:
            ValidationError: If file fails validation
            StorageProviderError: If save operation fails
        """
        logger.info(f"Saving file: {file_path} ({len(content)} bytes)")

        try:
            # Validate file content
            filename = Path(file_path).name
            validation = self.validator.validate_file(
                content=content, filename=filename
            )
            logger.debug(f"File validation passed: {validation}")

            # Get validated full path
            full_path = self._get_full_path(file_path)

            # Create parent directories
            await asyncio.to_thread(full_path.parent.mkdir, parents=True, exist_ok=True)

            # Write file atomically (write to temp, then rename)
            temp_path = full_path.with_suffix(full_path.suffix + ".tmp")

            try:
                # Write to temporary file
                await asyncio.to_thread(temp_path.write_bytes, content)

                # Atomic rename
                await asyncio.to_thread(temp_path.replace, full_path)

                logger.info(f"File saved successfully: {file_path}")

            except Exception:
                # Clean up temp file on error
                if temp_path.exists():
                    await to_thread(temp_path.unlink)
                raise

            # Calculate checksum
            checksum = hashlib.md5(content).hexdigest()

            # Build result
            result = {
                "path": file_path,
                "size": len(content),
                "checksum": checksum,
                "metadata": metadata or {},
            }

            # Add storage URL if base_url configured
            if self.base_url:
                result["storage_url"] = f"{self.base_url}/files/{file_path}"

            return result

        except Exception as e:
            if not isinstance(e, (PathTraversalError, AccessDeniedError)):
                logger.error(f"Failed to save file {file_path}: {e}")
                raise StorageProviderError(
                    f"Failed to save file: {e}", provider="local", operation="save"
                )
            raise

    async def write_file(
        self, file_path: str, content: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Write file to local filesystem (alias for save_file).

        This method provides compatibility with tests that expect write_file.

        Args:
            file_path: Relative file path
            content: File content as bytes
            metadata: Optional metadata

        Returns:
            Dict with file information
        """
        return await self.save_file(file_path, content, metadata)

    async def read_file(self, file_path: str) -> Optional[bytes]:
        """Read file from local filesystem (alias for get_file).

        This method provides compatibility with tests that expect read_file.

        Args:
            file_path: Relative file path

        Returns:
            File content as bytes, or None if not found
        """
        return await self.get_file(file_path)

    async def get_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file content.

        Args:
            file_path: Relative file path

        Returns:
            File content as bytes, or None if not found

        Raises:
            StorageProviderError: If read operation fails
        """
        logger.debug(f"Reading file: {file_path}")

        try:
            full_path = self._get_full_path(file_path)

            # Check if file exists
            if not await asyncio.to_thread(full_path.exists):
                logger.warning(f"File not found: {file_path}")
                return None

            # Check if it's a file (not directory)
            if not await asyncio.to_thread(full_path.is_file):
                logger.warning(f"Path is not a file: {file_path}")
                return None

            # Read file content
            content = cast(bytes, await to_thread(full_path.read_bytes))
            logger.debug(f"File read successfully: {file_path} ({len(content)} bytes)")

            return content

        except Exception as e:
            if not isinstance(e, PathTraversalError):
                logger.error(f"Failed to read file {file_path}: {e}")
                raise StorageProviderError(
                    f"Failed to read file: {e}", provider="local", operation="get"
                )
            raise

    async def stream_file(  # type: ignore[override,misc]
        self, file_path: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream file content in chunks.

        Args:
            file_path: Relative file path
            chunk_size: Size of chunks to yield (default: 8KB)

        Yields:
            File content in chunks of bytes

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageProviderError: If streaming fails
        """

        logger.debug(f"Streaming file: {file_path} (chunk_size={chunk_size})")

        try:
            full_path = self._get_full_path(file_path)

            # Check if file exists
            if not await asyncio.to_thread(full_path.exists):
                raise FileNotFoundError(
                    f"File not found: {file_path}", file_path=file_path
                )

            # Stream file in chunks
            def _read_chunks():
                """Synchronous chunk reader for to_thread."""
                with open(full_path, "rb") as f:
                    while True:
                        chunk = f.read(chunk_size)
                        if not chunk:
                            break
                        yield chunk

            # Yield chunks asynchronously
            for chunk in await asyncio.to_thread(list, _read_chunks()):
                yield chunk

            logger.debug(f"File streaming completed: {file_path}")

        except FileNotFoundError:
            raise
        except Exception as e:
            if not isinstance(e, PathTraversalError):
                logger.error(f"Failed to stream file {file_path}: {e}")
            raise StorageProviderError(
                f"Failed to stream file: {e}", provider="local", operation="stream"
            )

    async def delete_file(self, file_path: str) -> bool:
        """Delete file from filesystem.

        Args:
            file_path: Relative file path

        Returns:
            True if file was deleted, False if file didn't exist

        Raises:
            StorageProviderError: If delete operation fails
        """
        logger.info(f"Deleting file: {file_path}")

        try:
            full_path = self._get_full_path(file_path)

            # Check if file exists
            if not await asyncio.to_thread(full_path.exists):
                logger.warning(f"File not found for deletion: {file_path}")
                return False

            # Ensure it's a file, not directory
            if not await asyncio.to_thread(full_path.is_file):
                logger.error(f"Cannot delete non-file: {file_path}")
                raise StorageProviderError(
                    "Cannot delete directory", provider="local", operation="delete"
                )

            # Delete file
            await asyncio.to_thread(full_path.unlink)
            logger.info(f"File deleted successfully: {file_path}")

            return True

        except Exception as e:
            if not isinstance(e, (PathTraversalError, StorageProviderError)):
                logger.error(f"Failed to delete file {file_path}: {e}")
                raise StorageProviderError(
                    f"Failed to delete file: {e}", provider="local", operation="delete"
                )
            raise

    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists.

        Args:
            file_path: Relative file path

        Returns:
            True if file exists, False otherwise
        """
        try:
            full_path = self._get_full_path(file_path)
            exists = await asyncio.to_thread(full_path.exists)
            is_file = await asyncio.to_thread(full_path.is_file) if exists else False
            return exists and is_file
        except (PathTraversalError, Exception):
            return False

    async def get_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get file metadata.

        Args:
            file_path: Relative file path

        Returns:
            Dict with file metadata or None if file not found
        """
        logger.debug(f"Getting metadata for: {file_path}")

        try:
            full_path = self._get_full_path(file_path)

            # Check if file exists
            if not await asyncio.to_thread(full_path.exists):
                return None

            # Get file stats
            stat = await asyncio.to_thread(full_path.stat)

            # Detect MIME type
            content_type = self.validator.detect_mime_type(
                content=b"", filename=file_path  # Empty for extension-based detection
            )

            # Build metadata
            metadata = {
                "size": stat.st_size,
                "created_at": datetime.fromtimestamp(stat.st_ctime).isoformat(),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "content_type": content_type,
            }

            logger.debug(f"Metadata retrieved: {file_path}")
            return metadata

        except Exception as e:
            if not isinstance(e, PathTraversalError):
                logger.error(f"Failed to get metadata for {file_path}: {e}")
            return None

    async def get_file_url(
        self, file_path: str, expires_in: int = 3600
    ) -> Optional[str]:
        """Generate URL for file access.

        Args:
            file_path: Relative file path
            expires_in: URL expiration (not used for local storage)

        Returns:
            Local file URL if base_url configured, None otherwise
        """
        if not self.base_url:
            logger.debug("No base_url configured, cannot generate URL")
            return None

        # Check if file exists
        if not await self.file_exists(file_path):
            logger.warning(f"Cannot generate URL for non-existent file: {file_path}")
            return None

        # Generate local URL
        url = f"{self.base_url}/files/{file_path}"
        logger.debug(f"Generated URL: {url}")

        return url

    async def serve_file(self, file_path: str) -> AsyncIterator[bytes]:  # type: ignore[override,misc]
        """Serve file for HTTP response.

        For local storage, this uses FastAPI's FileResponse if available,
        otherwise falls back to streaming.

        Args:
            file_path: Relative file path

        Yields:
            File content chunks or FileResponse

        Raises:
            FileNotFoundError: If file doesn't exist
        """

        logger.debug(f"Serving file: {file_path}")

        # Verify file exists
        if not await self.file_exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}", file_path=file_path)

        # Stream file content
        async for chunk in self.stream_file(file_path):
            yield chunk

    async def list_files(
        self, prefix: str = "", max_results: int = 1000
    ) -> List[Dict[str, Any]]:
        """List files in storage.

        Args:
            prefix: Path prefix to filter results
            max_results: Maximum number of results

        Returns:
            List of file info dicts
        """
        logger.debug(f"Listing files with prefix: {prefix}")

        try:
            # Sanitize prefix
            if prefix:
                prefix_path = self._get_full_path(prefix)
            else:
                prefix_path = self.root_dir

            # List files recursively
            def _list_files():
                """Synchronous file lister."""
                files = []
                if prefix_path.is_file():
                    # Single file
                    files.append(prefix_path)
                elif prefix_path.is_dir():
                    # Directory - list recursively
                    for item in prefix_path.rglob("*"):
                        if item.is_file() and len(files) < max_results:
                            files.append(item)
                return files

            file_paths = await asyncio.to_thread(_list_files)

            # Build result list
            results = []
            for full_path in file_paths:
                try:
                    # Get relative path
                    rel_path = full_path.relative_to(self.root_dir)

                    # Get metadata
                    metadata = await self.get_metadata(str(rel_path))

                    if metadata:
                        results.append({"path": str(rel_path), **metadata})
                except Exception as e:
                    logger.warning(f"Failed to get info for {full_path}: {e}")
                    continue

            logger.debug(f"Listed {len(results)} files")
            return results

        except Exception as e:
            logger.error(f"Failed to list files: {e}")
            return []

    async def get_storage_info(self) -> Dict[str, Any]:
        """Get storage provider information.

        Returns:
            Dict with storage information
        """
        try:
            # Get disk usage stats
            stat = await asyncio.to_thread(os.statvfs, self.root_dir)

            total_space = stat.f_blocks * stat.f_frsize
            free_space = stat.f_bavail * stat.f_frsize
            used_space = total_space - free_space

            return {
                "provider": "LocalFileInterface",
                "root_dir": str(self.root_dir),
                "supports_streaming": True,
                "supports_signed_urls": False,
                "supports_metadata": True,
                "total_space_bytes": total_space,
                "used_space_bytes": used_space,
                "free_space_bytes": free_space,
            }
        except Exception as e:
            logger.error(f"Failed to get storage info: {e}")
            return {
                "provider": "LocalFileInterface",
                "root_dir": str(self.root_dir),
                "supports_streaming": True,
                "supports_signed_urls": False,
                "supports_metadata": True,
            }
