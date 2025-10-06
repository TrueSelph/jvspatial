"""Abstract base class for file storage providers.

This module defines the FileStorageInterface that all storage providers
must implement, ensuring consistent behavior across different backends
(local filesystem, S3, Azure, GCP, etc.).
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


class FileStorageInterface(ABC):
    """Abstract base class for file storage backends.

    All storage providers must implement these methods with proper
    security, validation, and error handling. This interface ensures
    consistent behavior across different storage backends.

    Implementations must handle:
        - Path validation and sanitization
        - Proper error handling and logging
        - Thread-safe operations
        - Resource cleanup

    Note:
        All paths passed to these methods should already be sanitized
        by the security layer. Implementations should still validate
        paths relative to their storage root.

    Example:
        >>> class MyStorage(FileStorageInterface):
        ...     async def save_file(self, file_path, content, metadata=None):
        ...         # Implementation here
        ...         pass
    """

    @abstractmethod
    async def save_file(
        self, file_path: str, content: bytes, metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Save file to storage.

        This method must:
        - Validate the file path is within storage boundaries
        - Create any necessary parent directories
        - Write the file content atomically if possible
        - Store any provided metadata
        - Calculate and return checksums

        Args:
            file_path: Sanitized, validated relative file path
            content: File content as bytes
            metadata: Optional file metadata (tags, user info, etc.)

        Returns:
            Dict containing:
                - path: str - Stored file path
                - size: int - File size in bytes
                - checksum: str - File checksum (MD5, SHA256, etc.)
                - storage_url: Optional[str] - Storage-specific URL
                - metadata: Dict - Any stored metadata

        Raises:
            StorageProviderError: If save operation fails
            ValidationError: If file fails validation
            PathTraversalError: If path is unsafe

        Example:
            >>> result = await storage.save_file(
            ...     "uploads/doc.pdf",
            ...     file_bytes,
            ...     metadata={"user": "user123"}
            ... )
            >>> print(result['checksum'])
            'a1b2c3d4e5f6...'
        """
        pass

    @abstractmethod
    async def get_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file content.

        This method must:
        - Validate file path
        - Check if file exists
        - Read entire file content into memory
        - Return None if file doesn't exist

        Note:
            For large files, consider using stream_file() instead
            to avoid loading entire file into memory.

        Args:
            file_path: Sanitized relative file path

        Returns:
            File content as bytes, or None if file not found

        Raises:
            StorageProviderError: If read operation fails

        Example:
            >>> content = await storage.get_file("uploads/doc.pdf")
            >>> if content:
            ...     print(f"File size: {len(content)} bytes")
        """
        pass

    @abstractmethod
    def stream_file(
        self, file_path: str, chunk_size: int = 8192
    ) -> AsyncIterator[bytes]:
        """Stream file content in chunks.

        This method must:
        - Validate file path
        - Open file for reading
        - Yield content in chunks
        - Properly close file on completion or error

        Preferred over get_file() for large files to avoid
        loading entire file into memory.

        Args:
            file_path: Sanitized relative file path
            chunk_size: Size of chunks to yield (default: 8KB)

        Yields:
            File content in chunks of bytes

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageProviderError: If streaming fails

        Example:
            >>> async for chunk in storage.stream_file("large-video.mp4"):
            ...     await response.write(chunk)
        """
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from storage.

        This method must:
        - Validate file path
        - Delete the file if it exists
        - Clean up any associated metadata
        - Handle non-existent files gracefully

        Args:
            file_path: Sanitized relative file path

        Returns:
            True if file was deleted, False if file didn't exist

        Raises:
            StorageProviderError: If delete operation fails
            AccessDeniedError: If deletion not permitted

        Example:
            >>> deleted = await storage.delete_file("old-file.txt")
            >>> if deleted:
            ...     print("File deleted successfully")
        """
        pass

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists in storage.

        This method must:
        - Validate file path
        - Check existence without reading content
        - Return False for directories

        Args:
            file_path: Sanitized relative file path

        Returns:
            True if file exists, False otherwise

        Example:
            >>> exists = await storage.file_exists("uploads/doc.pdf")
            >>> if not exists:
            ...     print("File not found")
        """
        pass

    @abstractmethod
    async def get_metadata(self, file_path: str) -> Optional[Dict[str, Any]]:
        """Get file metadata without reading content.

        This method must:
        - Validate file path
        - Retrieve file metadata (size, timestamps, etc.)
        - Return None if file doesn't exist

        Args:
            file_path: Sanitized relative file path

        Returns:
            Dict containing file metadata:
                - size: int - File size in bytes
                - created_at: str - Creation timestamp (ISO format)
                - modified_at: str - Last modification timestamp
                - content_type: Optional[str] - MIME type if available
                - checksum: Optional[str] - File checksum
                - custom_metadata: Optional[Dict] - Provider-specific metadata
            Or None if file not found

        Example:
            >>> metadata = await storage.get_metadata("uploads/doc.pdf")
            >>> if metadata:
            ...     print(f"Size: {metadata['size']} bytes")
        """
        pass

    @abstractmethod
    async def get_file_url(
        self, file_path: str, expires_in: int = 3600
    ) -> Optional[str]:
        """Generate URL for file access.

        This method should:
        - Generate signed/presigned URLs for cloud storage
        - Generate local server URLs for filesystem storage
        - Include expiration for security
        - Return None if URL generation not supported

        Args:
            file_path: Sanitized relative file path
            expires_in: URL expiration time in seconds (default: 1 hour)

        Returns:
            Signed/presigned URL string, or None if not supported/file missing

        Example:
            >>> url = await storage.get_file_url("uploads/doc.pdf", expires_in=7200)
            >>> print(f"Download URL: {url}")
        """
        pass

    @abstractmethod
    def serve_file(self, file_path: str) -> AsyncIterator[bytes]:
        """Serve file for HTTP response.

        Similar to stream_file() but optimized for HTTP serving.
        May include content-type detection and headers.

        This method must:
        - Stream file content efficiently
        - Handle partial content requests if supported
        - Set appropriate content headers

        Args:
            file_path: Sanitized relative file path

        Yields:
            File content chunks for streaming response

        Raises:
            FileNotFoundError: If file doesn't exist
            StorageProviderError: If serving fails

        Example:
            >>> return StreamingResponse(
            ...     storage.serve_file("uploads/doc.pdf"),
            ...     media_type="application/pdf"
            ... )
        """
        pass

    async def list_files(
        self, prefix: str = "", max_results: int = 1000
    ) -> List[Dict[str, Any]]:
        """List files in storage (optional method).

        This is an optional method that providers may implement
        to support file listing functionality.

        Args:
            prefix: Path prefix to filter results
            max_results: Maximum number of results to return

        Returns:
            List of file info dicts

        Note:
            Default implementation returns empty list.
            Providers should override if listing is supported.
        """
        logger.warning(f"{self.__class__.__name__} does not implement list_files()")
        return []

    async def get_storage_info(self) -> Dict[str, Any]:
        """Get storage provider information (optional method).

        Returns information about the storage provider such as
        available space, configuration, capabilities, etc.

        Returns:
            Dict with storage information

        Note:
            Default implementation returns basic info.
            Providers should override with specific details.
        """
        return {
            "provider": self.__class__.__name__,
            "supports_streaming": True,
            "supports_signed_urls": False,
            "supports_metadata": True,
        }
