"""File storage service for managing file uploads, downloads, and proxies.

This module provides a dedicated service class for handling file storage
operations, separating concerns from the main Server class.
"""

from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import Response

from jvspatial.api.constants import APIRoutes, ErrorMessages
from jvspatial.api.exceptions import (
    PathTraversalError,
    ValidationError,
)
from jvspatial.storage.exceptions import StorageError


class FileStorageService:
    """Service for managing file storage operations and endpoints.

    This service handles file uploads, downloads, deletions, and optional
    proxy URL management for temporary file access.

    Attributes:
        file_interface: File storage interface (local or S3)
        proxy_manager: Optional proxy manager for temporary URLs
        config: Server configuration with storage settings
    """

    def __init__(
        self,
        file_interface: Any,
        proxy_manager: Optional[Any] = None,
        config: Optional[Any] = None,
    ) -> None:
        """Initialize the file storage service.

        Args:
            file_interface: FileInterface implementation (local/S3)
            proxy_manager: Optional ProxyManager for temporary URLs
            config: Server configuration object
        """
        self.file_interface = file_interface
        self.proxy_manager = proxy_manager
        self.config = config

    async def handle_upload(
        self,
        file: UploadFile,
        path: str = "",
        create_proxy: bool = False,
        proxy_expires_in: int = 3600,
        proxy_one_time: bool = False,
    ) -> Dict[str, Any]:
        """Handle file upload with optional proxy creation.

        Args:
            file: Uploaded file
            path: Directory path for file (default: root)
            create_proxy: Whether to create a proxy URL
            proxy_expires_in: Proxy expiration time in seconds
            proxy_one_time: Whether proxy is single-use

        Returns:
            Upload result with file path, URL, and optional proxy

        Raises:
            HTTPException: On validation or storage errors
        """
        try:
            # Read file content
            content = file.read()

            # Determine file path
            file_path = f"{path}/{file.filename}" if path else file.filename

            # Save file
            await self.file_interface.save_file(file_path, content)

            result = {
                "success": True,
                "file_path": file_path,
                "file_size": len(content),
                "file_url": await self.file_interface.get_file_url(file_path),
            }

            # Create proxy if requested
            if create_proxy and self.proxy_manager:
                proxy_url = self.proxy_manager.create_proxy(
                    file_path=file_path,
                    expires_in=proxy_expires_in,
                    one_time=proxy_one_time,
                )
                result["proxy_url"] = proxy_url
                result["proxy_code"] = proxy_url.split("/")[-1]

            return result

        except (PathTraversalError, ValidationError) as e:
            raise HTTPException(status_code=400, detail=str(e))
        except StorageError as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def handle_serve(self, file_path: str) -> Response:
        """Handle file serving/download.

        Args:
            file_path: Path to file to serve

        Returns:
            FastAPI Response with file content

        Raises:
            HTTPException: If file not found or storage error
        """
        try:
            return await self.file_interface.serve_file(file_path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail=ErrorMessages.FILE_NOT_FOUND)
        except StorageError as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def handle_delete(self, file_path: str) -> Dict[str, Any]:
        """Handle file deletion.

        Args:
            file_path: Path to file to delete

        Returns:
            Deletion result with success status

        Raises:
            HTTPException: On storage error
        """
        try:
            success = self.file_interface.delete_file(file_path)
            return {"success": success, "file_path": file_path}
        except StorageError as e:
            raise HTTPException(status_code=500, detail=str(e))

    async def handle_create_proxy(
        self,
        file_path: str,
        expires_in: Optional[int] = None,
        one_time: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle proxy URL creation for existing file.

        Args:
            file_path: Path to file for proxy
            expires_in: Expiration time in seconds
            one_time: Whether proxy is single-use
            metadata: Optional metadata to store

        Returns:
            Proxy creation result with URL and code

        Raises:
            HTTPException: If file not found or storage error
        """
        try:
            # Verify file exists
            if not await self.file_interface.file_exists(file_path):
                raise HTTPException(404, ErrorMessages.FILE_NOT_FOUND)

            # Get default expiration from config
            default_expiration = (
                self.config.proxy_default_expiration if self.config else 3600
            )

            if self.proxy_manager is None:
                raise HTTPException(500, "Proxy manager not initialized")

            proxy_url = self.proxy_manager.create_proxy(
                file_path=file_path,
                expires_in=expires_in or default_expiration,
                one_time=one_time,
                metadata=metadata or {},
            )

            return {
                "proxy_url": proxy_url,
                "code": proxy_url.split("/")[-1],
                "file_path": file_path,
                "expires_in": expires_in or default_expiration,
            }
        except StorageError as e:
            raise HTTPException(500, str(e))

    async def handle_serve_proxied(self, code: str) -> Response:
        """Handle file serving via proxy URL.

        Args:
            code: Proxy code from URL

        Returns:
            FastAPI Response with file content

        Raises:
            HTTPException: If proxy not found or storage error
        """
        try:
            if self.proxy_manager is None:
                raise HTTPException(500, "Proxy manager not initialized")

            # Resolve proxy to file path
            file_path, _metadata = self.proxy_manager.resolve_proxy(code)

            # Serve the file
            return await self.file_interface.serve_file(file_path)

        except FileNotFoundError:
            raise HTTPException(404, "Proxy not found or expired")
        except StorageError as e:
            raise HTTPException(500, str(e))

    async def handle_revoke_proxy(self, code: str) -> Dict[str, Any]:
        """Handle proxy URL revocation.

        Args:
            code: Proxy code to revoke

        Returns:
            Revocation result with success status

        Raises:
            HTTPException: On storage error
        """
        try:
            if self.proxy_manager is None:
                raise HTTPException(500, "Proxy manager not initialized")

            success = self.proxy_manager.revoke_proxy(code)
            return {"success": success, "code": code}
        except StorageError as e:
            raise HTTPException(500, str(e))

    async def handle_proxy_stats(self, code: str) -> Dict[str, Any]:
        """Handle proxy statistics retrieval.

        Args:
            code: Proxy code to get stats for

        Returns:
            Proxy statistics dictionary

        Raises:
            HTTPException: If proxy not found or storage error
        """
        try:
            if self.proxy_manager is None:
                raise HTTPException(500, "Proxy manager not initialized")

            stats = self.proxy_manager.get_stats(code)
            if not stats:
                raise HTTPException(404, "Proxy not found")
            return dict(stats) if stats else {}
        except StorageError as e:
            raise HTTPException(500, str(e))

    @classmethod
    async def register_endpoints(
        cls,
        app: FastAPI,
        service: "FileStorageService",
    ) -> None:
        """Register all file storage endpoints with the FastAPI app.

        This class method registers the file storage routes and binds them
        to the service instance's handler methods.

        Args:
            app: FastAPI application instance
            service: FileStorageService instance with handlers
        """

        # File upload endpoint
        @app.post(APIRoutes.STORAGE_UPLOAD)
        async def upload_file(
            file: UploadFile,
            path: str = "",
            create_proxy: bool = False,
            proxy_expires_in: int = 3600,
            proxy_one_time: bool = False,
        ):
            """Upload a file with optional proxy URL creation."""
            return await service.handle_upload(
                file=file,
                path=path,
                create_proxy=create_proxy,
                proxy_expires_in=proxy_expires_in,
                proxy_one_time=proxy_one_time,
            )

        # File download/serve endpoint
        @app.get(f"{APIRoutes.STORAGE_FILES}/{{file_path:path}}")
        async def serve_file(file_path: str):
            """Serve a file directly."""
            return await service.handle_serve(file_path)

        # File delete endpoint
        @app.delete(f"{APIRoutes.STORAGE_FILES}/{{file_path:path}}")
        async def delete_file(file_path: str):
            """Delete a file."""
            return await service.handle_delete(file_path)

        # Proxy endpoints (if proxy manager is available)
        if service.proxy_manager:
            # Create proxy for existing file
            @app.post(APIRoutes.STORAGE_PROXY)
            async def create_proxy(
                file_path: str,
                expires_in: Optional[int] = None,
                one_time: bool = False,
                metadata: Optional[Dict[str, Any]] = None,
            ):
                """Create a proxy URL for a file."""
                return await service.handle_create_proxy(
                    file_path=file_path,
                    expires_in=expires_in,
                    one_time=one_time,
                    metadata=metadata,
                )

            # Access file via proxy
            @app.get(f"{APIRoutes.PROXY_PREFIX}/{{code}}")
            async def serve_proxied_file(code: str):
                """Serve file via proxy URL."""
                return await service.handle_serve_proxied(code)

            # Revoke proxy
            @app.delete(f"{APIRoutes.STORAGE_PROXY}/{{code}}")
            async def revoke_proxy(code: str):
                """Revoke a proxy URL."""
                return await service.handle_revoke_proxy(code)

            # Get proxy stats
            @app.get(f"{APIRoutes.STORAGE_PROXY}/{{code}}/stats")
            async def get_proxy_stats(code: str):
                """Get statistics for a proxy URL."""
                return await service.handle_proxy_stats(code)


__all__ = ["FileStorageService"]
