"""Example demonstrating jvspatial storage backends.

This example shows:
1. Local file storage setup and usage
2. S3 storage integration
3. File upload and download
4. Storage-aware Node attributes
5. Storage configuration options
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from jvspatial.api import Server, endpoint
from jvspatial.api.decorators import EndpointField
from jvspatial.core.decorators import on_visit
from jvspatial.core.entities import Node, Root, Walker
from jvspatial.storage import create_storage, get_proxy_manager


# Define storage-aware entities
class StoredFile(Node):
    """Node representing a file in storage."""

    filename: str = ""
    file_path: str = ""  # Storage path
    mime_type: str = ""
    size: int = 0
    uploaded_at: datetime = datetime.now()
    storage_type: str = "local"  # 'local' or 's3'
    public_url: Optional[str] = None


class FileWalker(Walker):
    """Walker for managing stored files."""

    async def store_file(
        self, file_path: str, file_content: bytes, storage_type: str = "local"
    ) -> StoredFile:
        """Store a file and create its node.

        Args:
            file_path: Path where file should be stored
            file_content: File content as bytes
            storage_type: Storage backend to use ('local' or 's3')
        """
        # Determine mime type
        import mimetypes

        mime_type, _ = mimetypes.guess_type(file_path)

        # Get storage interface
        if storage_type == "local":
            storage = create_storage(provider="local", root_dir=".files")
        elif storage_type == "s3":
            storage = create_storage(
                provider="s3",
                bucket_name=os.getenv("AWS_BUCKET_NAME", "jvspatial-files"),
                region_name=os.getenv("AWS_REGION", "us-east-1"),
                access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
            )
        else:
            raise ValueError(f"Unsupported storage type: {storage_type}")

        # Save file
        await storage.save_file(file_path, file_content)

        # Create node
        stored_file = await StoredFile.create(
            filename=Path(file_path).name,
            file_path=file_path,
            mime_type=mime_type or "application/octet-stream",
            size=len(file_content),
            uploaded_at=datetime.now(),
            storage_type=storage_type,
        )

        # Set public URL if available
        public_url = await storage.get_file_url(file_path)
        if public_url:
            stored_file.public_url = public_url
            await stored_file.save()

        return stored_file


@endpoint("/api/files/upload", methods=["POST"], auth=True)
class FileUploader(FileWalker):
    """Upload files to storage."""

    file_path: str = EndpointField(description="Path where file should be stored")
    file_content: bytes = EndpointField(
        description="File content as bytes (base64 encoded)"
    )
    storage_type: str = EndpointField(
        default="local", description="Storage backend to use (local or s3)"
    )

    @on_visit(Root)
    async def upload_file(self, here: Root):
        """Handle file upload."""
        try:
            # Store file using appropriate backend
            stored_file = await self.store_file(
                self.file_path, self.file_content, storage_type=self.storage_type
            )

            # Return success
            return await self.endpoint.success(
                data={
                    "file_id": stored_file.id,
                    "filename": stored_file.filename,
                    "size": stored_file.size,
                    "public_url": stored_file.public_url,
                },
                message="File uploaded successfully",
            )
        except Exception as e:
            return await self.endpoint.error(
                message=f"Failed to upload file: {str(e)}", status_code=500
            )


@endpoint("/api/files/list", methods=["GET"], auth=True)
class FileList(FileWalker):
    """List stored files."""

    storage_type: Optional[str] = EndpointField(
        default=None, description="Filter by storage type"
    )

    public_only: bool = EndpointField(
        default=False, description="Only show public files"
    )

    @on_visit(Root)
    async def list_files(self, here: Root):
        """List files matching criteria."""
        query: Dict[str, Any] = {}
        if self.storage_type:
            query["storage_type"] = self.storage_type
        if self.public_only:
            query["public_url"] = {"$ne": None}  # type: ignore[dict-item]

        files = await StoredFile.find(query)

        return await self.endpoint.success(
            data={
                "files": [
                    {
                        "id": f.id,
                        "filename": f.filename,
                        "size": f.size,
                        "uploaded_at": f.uploaded_at.isoformat(),
                        "public_url": f.public_url,
                    }
                    for f in files
                ]
            }
        )


@endpoint("/api/files/{file_id}/download", methods=["GET"], auth=True)
class FileDownloader(FileWalker):
    """Download stored files."""

    file_id: str = EndpointField(description="File ID to download")

    @on_visit(Root)
    async def download_file(self, here: Root):
        """Download a specific file."""
        # Get file info
        stored_file = await StoredFile.get(self.file_id)
        if not stored_file:
            return await self.endpoint.not_found(
                message="File not found", details={"file_id": self.file_id}
            )

        # Get storage backend
        try:
            if stored_file.storage_type == "local":
                storage = create_storage(provider="local", root_dir=".files")
            elif stored_file.storage_type == "s3":
                storage = create_storage(
                    provider="s3",
                    bucket_name=os.getenv("AWS_BUCKET_NAME", "jvspatial-files"),
                    region_name=os.getenv("AWS_REGION", "us-east-1"),
                    access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                    secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                    endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
                )
            else:
                return await self.endpoint.error(
                    message=f"Unsupported storage type: {stored_file.storage_type}",
                    status_code=500,
                )

            # Get file content
            content = await storage.get_file(stored_file.file_path)
            if content is None:
                return await self.endpoint.not_found(
                    message="File content not found",
                    details={"path": stored_file.file_path},
                )

            # Return file content (in a real implementation, you'd stream this)
            return await self.endpoint.success(
                data={
                    "file_id": stored_file.id,
                    "filename": stored_file.filename,
                    "content": content.hex(),  # Return as hex for JSON response
                    "mime_type": stored_file.mime_type,
                },
                message="File retrieved successfully",
            )
        except Exception as e:
            return await self.endpoint.error(
                message=f"Failed to retrieve file: {str(e)}", status_code=500
            )


def create_server():
    """Create and configure the server with storage backends."""
    server = Server(
        title="Storage Example API",
        description="API demonstrating storage backends",
        version="1.0.0",
        file_storage_enabled=True,
        file_storage_provider="local",
        file_storage_root=".files",
        proxy_enabled=True,
    )
    return server


def main():
    """Run the storage example."""
    print("Setting up server...")
    server = create_server()

    print("\nStorage backends configured:")
    print("- local (default)")
    if os.getenv("AWS_ACCESS_KEY_ID"):
        print("- s3 (AWS credentials found)")

    print("\nAvailable endpoints:")
    print("POST /api/files/upload - Upload files")
    print("GET  /api/files/list - List stored files")
    print("GET  /api/files/{id}/download - Download files")

    print("\nStarting server...")
    # server.run() uses uvicorn which manages its own event loop
    server.run()


if __name__ == "__main__":
    # server.run() manages its own event loop via uvicorn
    # No need for asyncio.run() here
    main()
