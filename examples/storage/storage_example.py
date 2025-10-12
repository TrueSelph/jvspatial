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
from typing import Optional

from jvspatial.api import Server
from jvspatial.api.auth.decorators import auth_endpoint
from jvspatial.api.endpoint.decorators import EndpointField
from jvspatial.core.entities import Node, Walker
from jvspatial.core.storage import StorageManager
from jvspatial.core.storage.backends import LocalStorage, S3Storage


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
        self, file_path: str, storage_type: str = "local"
    ) -> StoredFile:
        """Store a file and create its node.

        Args:
            file_path: Path to local file to store
            storage_type: Storage backend to use
        """
        # Get file info
        local_path = Path(file_path)
        if not local_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        # Determine mime type
        import mimetypes

        mime_type, _ = mimetypes.guess_type(file_path)

        # Store file
        storage = self.server.get_storage(storage_type)
        if storage is None:
            raise ValueError(f"Storage type not configured: {storage_type}")

        storage_path = await storage.store_file(file_path, mime_type=mime_type)

        # Create node
        stored_file = await StoredFile.create(
            filename=local_path.name,
            file_path=storage_path,
            mime_type=mime_type or "application/octet-stream",
            size=local_path.stat().st_size,
            uploaded_at=datetime.now(),
            storage_type=storage_type,
        )

        # Set public URL if available
        if hasattr(storage, "get_public_url"):
            stored_file.public_url = await storage.get_public_url(storage_path)
            await stored_file.save()

        return stored_file


@auth_endpoint("/api/files/upload", methods=["POST"])
class FileUploader(FileWalker):
    """Upload files to storage."""

    storage_type: str = EndpointField(
        default="local", description="Storage backend to use (local or s3)"
    )

    make_public: bool = EndpointField(
        default=False, description="Make the file publicly accessible"
    )

    async def on_start(self):
        """Handle file upload."""
        # Get the uploaded file from request
        upload = await self.endpoint.request.form()
        if "file" not in upload:
            return self.endpoint.bad_request(
                message="No file provided", details={"field": "file"}
            )

        uploaded_file = upload["file"]

        # Save uploaded file temporarily
        temp_path = f"/tmp/{uploaded_file.filename}"
        with open(temp_path, "wb") as f:
            data = await uploaded_file.read()
            f.write(data)

        try:
            # Store file using appropriate backend
            stored_file = await self.store_file(
                temp_path, storage_type=self.storage_type
            )

            # Make public if requested
            if self.make_public:
                storage = self.server.get_storage(self.storage_type)
                if hasattr(storage, "make_public"):
                    await storage.make_public(stored_file.file_path)
                    stored_file.public_url = await storage.get_public_url(
                        stored_file.file_path
                    )
                    await stored_file.save()

            # Report success
            return self.endpoint.success(
                data={
                    "file_id": stored_file.id,
                    "filename": stored_file.filename,
                    "size": stored_file.size,
                    "public_url": stored_file.public_url,
                },
                message="File uploaded successfully",
            )

        finally:
            # Clean up temp file
            os.unlink(temp_path)


@auth_endpoint("/api/files/list", methods=["GET"])
class FileList(FileWalker):
    """List stored files."""

    storage_type: Optional[str] = EndpointField(
        default=None, description="Filter by storage type"
    )

    public_only: bool = EndpointField(
        default=False, description="Only show public files"
    )

    async def on_start(self):
        """List files matching criteria."""
        query = {}
        if self.storage_type:
            query["storage_type"] = self.storage_type
        if self.public_only:
            query["public_url"] = {"$ne": None}

        files = await StoredFile.all(**query)

        return self.endpoint.success(
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


@auth_endpoint("/api/files/{file_id}/download")
class FileDownloader(FileWalker):
    """Download stored files."""

    async def on_start(self, file_id: str):
        """Download a specific file."""
        # Get file info
        stored_file = await StoredFile.get(file_id)
        if not stored_file:
            return self.endpoint.not_found(
                message="File not found", details={"file_id": file_id}
            )

        # Get storage backend
        storage = self.server.get_storage(stored_file.storage_type)
        if storage is None:
            return self.endpoint.server_error(
                message=f"Storage type not configured: {stored_file.storage_type}"
            )

        # Stream file
        stream = await storage.get_file(stored_file.file_path)
        if not stream:
            return self.endpoint.not_found(
                message="File content not found",
                details={"path": stored_file.file_path},
            )

        # Return file download response
        return self.endpoint.stream_file(
            stream, filename=stored_file.filename, mime_type=stored_file.mime_type
        )


def create_server():
    """Create and configure the server with storage backends."""
    server = Server(
        title="Storage Example API",
        description="API demonstrating storage backends",
        version="1.0.0",
    )

    # Configure storage
    storage = StorageManager()

    # Local storage in .files directory
    storage.register(
        "local", LocalStorage(root_dir=".files", base_url="http://localhost:8000/files")
    )

    # S3 storage (if configured)
    if os.getenv("AWS_ACCESS_KEY_ID"):
        storage.register(
            "s3",
            S3Storage(
                bucket=os.getenv("AWS_BUCKET_NAME", "jvspatial-files"),
                region=os.getenv("AWS_REGION", "us-east-1"),
                access_key=os.getenv("AWS_ACCESS_KEY_ID"),
                secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                endpoint_url=os.getenv("AWS_ENDPOINT_URL"),
            ),
        )

    server.storage = storage
    return server


async def main():
    """Run the storage example."""
    print("Setting up server...")
    server = create_server()

    print("\nStorage backends configured:")
    for name in server.storage.backends:
        print(f"- {name}")

    print("\nAvailable endpoints:")
    print("POST /api/files/upload - Upload files")
    print("GET  /api/files/list - List stored files")
    print("GET  /api/files/{id}/download - Download files")

    print("\nStarting server...")
    server.run()


if __name__ == "__main__":
    asyncio.run(main())
