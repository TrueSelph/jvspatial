"""
File Storage Demo - jvspatial Examples

This example demonstrates the integrated file storage system in jvspatial,
including local/S3 storage, URL proxy management, and Walker integration.

Features demonstrated:
- File upload with automatic proxy URL generation
- Direct file serving
- Short URL proxy system with expiration
- One-time access URLs
- File management via Walkers
- Security features (path validation, file type checking)

Run this example:
    python examples/file_storage_demo.py

Then test the endpoints:
    # Upload a file
    curl -X POST -F "file=@test.pdf" http://localhost:8000/api/storage/upload

    # Upload with proxy
    curl -X POST -F "file=@test.pdf" \
         http://localhost:8000/api/storage/upload?create_proxy=true

    # Access via proxy
    curl http://localhost:8000/p/{code}
"""

import asyncio
import os
from typing import Any, Dict, Optional

from jvspatial.api import Server, endpoint
from jvspatial.core.decorators import on_visit
from jvspatial.core.entities import Node, Root, Walker


# Example 1: Basic Server Setup with File Storage
def create_file_storage_server():
    """Create a server with file storage enabled."""

    # Option 1: Local file storage (default)
    server = Server(
        title="File Storage Demo API",
        description="Demo of jvspatial file storage capabilities",
        file_storage_enabled=True,
        file_storage_provider="local",  # or "s3"
        file_storage_root=".files",
        file_storage_base_url="http://localhost:8000",
        file_storage_max_size=50 * 1024 * 1024,  # 50MB
        proxy_enabled=True,
        proxy_default_expiration=3600,  # 1 hour
        db_type="json",
        db_path="./jvdb",
    )

    # Option 2: S3 file storage (commented)
    # server = Server(
    #     title="File Storage Demo API",
    #     file_storage_enabled=True,
    #     file_storage_provider="s3",
    #     s3_bucket_name="my-bucket",
    #     s3_region="us-east-1",
    #     s3_access_key=os.getenv("AWS_ACCESS_KEY_ID"),
    #     s3_secret_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    #     proxy_enabled=True,
    #     db_type="json",
    #     db_path="./jvdb"
    # )

    return server


# Create server instance
server = create_file_storage_server()


# Example 2: Walker that Uploads Files
@endpoint("/upload-document")
class UploadDocument(Walker):
    """Walker that handles document uploads with metadata."""

    file_path: str
    file_data: bytes
    create_proxy: bool = False
    proxy_expires_in: int = 3600

    @on_visit(Root)
    async def process_upload(self, here: Root):
        """Upload file and optionally create proxy URL."""
        from jvspatial.storage import create_storage, get_proxy_manager

        # Get file interface
        file_interface = create_storage(provider="local", root_dir=".files")

        # Save file
        await file_interface.save_file(self.file_path, self.file_data)

        result: Dict[str, Any] = {
            "file_path": self.file_path,
            "file_url": await file_interface.get_file_url(self.file_path),
        }

        # Create proxy if requested
        if self.create_proxy:
            proxy_manager = get_proxy_manager()
            proxy = await proxy_manager.create_proxy(
                file_path=self.file_path,
                expires_in=self.proxy_expires_in,
                metadata={"uploaded_by": "UploadDocument walker"},
            )
            result["proxy_url"] = f"/p/{proxy.code}"

        return await self.endpoint.success(
            data=result, message="File uploaded successfully"
        )


# Example 3: Walker that Creates Shareable Links
@endpoint("/create-share-link")
class CreateShareLink(Walker):
    """Create shareable links for existing files."""

    file_path: str
    expires_in: int = 3600
    one_time: bool = False

    @on_visit(Root)
    async def create_link(self, here: Root):
        """Create a proxy URL for sharing."""
        from jvspatial.storage import create_storage, get_proxy_manager

        # Verify file exists
        file_interface = create_storage(provider="local", root_dir=".files")

        if not await file_interface.file_exists(self.file_path):
            return await self.endpoint.not_found(message="File not found")

        # Create proxy
        proxy_manager = get_proxy_manager()
        proxy = await proxy_manager.create_proxy(
            file_path=self.file_path,
            expires_in=self.expires_in,
            one_time=self.one_time,
            metadata={
                "share_type": "one_time" if self.one_time else "temporary",
                "created_by": "CreateShareLink walker",
            },
        )

        return await self.endpoint.success(
            data={
                "share_url": f"/p/{proxy.code}",
                "expires_in": self.expires_in,
                "one_time": self.one_time,
            },
            message="Share link created successfully",
        )


# Example 4: Walker that Processes Files
@endpoint("/process-file")
class ProcessFile(Walker):
    """Walker that retrieves and processes a file."""

    file_path: str

    @on_visit(Root)
    async def process(self, here: Root):
        """Read and process file content."""
        from jvspatial.storage import create_storage

        file_interface = create_storage(provider="local", root_dir=".files")

        # Get file content
        content = await file_interface.get_file(self.file_path)

        if content is None:
            return await self.endpoint.not_found(message="File not found")

        # Get file metadata
        metadata = await file_interface.get_metadata(self.file_path)

        # Convert metadata keys to strings to ensure consistent typing
        cleaned_metadata = {
            str(k): str(v) if not isinstance(v, dict) else v
            for k, v in (metadata or {}).items()
        }

        return await self.endpoint.success(
            data={
                "file_path": str(self.file_path),
                "size": len(content),
                "metadata": cleaned_metadata,
                "content_preview": (
                    content[:100].decode("utf-8", errors="ignore")
                    if len(content) > 0
                    else ""
                ),
            },
            message="File processed successfully",
        )


# Example 5: Walker that Lists Files
@endpoint("/list-files")
class ListFiles(Walker):
    """Walker that lists files in a directory."""

    directory: str = ""

    @on_visit(Root)
    async def list_directory(self, here: Root):
        """List all files in a directory."""
        from jvspatial.storage import create_storage

        file_interface = create_storage(provider="local", root_dir=".files")

        try:
            files = await file_interface.list_files(self.directory)
            return await self.endpoint.success(
                data={
                    "directory": self.directory,
                    "files": files,
                    "count": len(files),
                },
                message="Files listed successfully",
            )
        except Exception as e:
            return await self.endpoint.error(message=str(e), status_code=500)


# Example 6: Walker that Manages File Lifecycle
@endpoint("/file-lifecycle")
class FileLifecycle(Walker):
    """Demonstrate complete file lifecycle: upload, share, access, delete."""

    file_name: str
    file_content: bytes

    @on_visit(Root)
    async def manage_lifecycle(self, here: Root):
        """Demonstrate full file management lifecycle."""
        from jvspatial.storage import create_storage, get_proxy_manager

        file_interface = create_storage(provider="local", root_dir=".files")
        proxy_manager = get_proxy_manager()

        steps = []

        # Step 1: Upload file
        upload_path = f"lifecycle/{self.file_name}"
        await file_interface.save_file(upload_path, self.file_content)
        steps.append(
            {
                "step": "upload",
                "status": "success",
                "path": upload_path,
                "url": await file_interface.get_file_url(upload_path),
            }
        )

        # Step 2: Create temporary share link (1 hour)
        temp_proxy = await proxy_manager.create_proxy(
            file_path=upload_path, expires_in=3600, metadata={"type": "temporary"}
        )
        steps.append(
            {
                "step": "create_temp_link",
                "status": "success",
                "proxy_url": f"/p/{temp_proxy.code}",
                "expires_in": 3600,  # type: ignore[dict-item]
            }
        )

        # Step 3: Create one-time share link
        onetime_proxy = await proxy_manager.create_proxy(
            file_path=upload_path,
            expires_in=7200,
            one_time=True,
            metadata={"type": "one_time"},
        )
        steps.append(
            {
                "step": "create_onetime_link",
                "status": "success",
                "proxy_url": f"/p/{onetime_proxy.code}",
                "one_time": True,  # type: ignore[dict-item]
            }
        )

        # Step 4: Get file metadata
        metadata = await file_interface.get_metadata(upload_path)
        steps.append(
            {"step": "get_metadata", "status": "success", "metadata": metadata}  # type: ignore[dict-item]
        )

        # Step 5: Verify file exists
        exists = await file_interface.file_exists(upload_path)
        steps.append({"step": "verify_exists", "status": "success", "exists": exists})  # type: ignore[dict-item]

        return await self.endpoint.success(
            data={
                "lifecycle_demo": "complete",
                "file_path": upload_path,
                "steps": steps,
            },
            message="File lifecycle demo completed successfully",
        )


# Main execution
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("🚀 File Storage Demo Server")
    print("=" * 70)
    print("\n📁 File Storage Configuration:")
    print(f"   Provider: {server.config.file_storage_provider}")
    print(f"   Root: {server.config.file_storage_root}")
    print(f"   Max Size: {server.config.file_storage_max_size / (1024*1024):.1f}MB")
    print(f"   Proxy Enabled: {server.config.proxy_enabled}")

    print("\n🔗 Available Endpoints:")
    print("   POST   /api/storage/upload")
    print("   GET    /api/storage/files/{path}")
    print("   DELETE /api/storage/files/{path}")
    print("   POST   /api/storage/proxy")
    print("   GET    /p/{code}")
    print("   DELETE /api/storage/proxy/{code}")
    print("   GET    /api/storage/proxy/{code}/stats")

    print("\n🎯 Walker Endpoints:")
    print("   POST   /api/upload-document")
    print("   POST   /api/create-share-link")
    print("   POST   /api/process-file")
    print("   POST   /api/list-files")
    print("   POST   /api/file-lifecycle")

    print("\n📖 Example cURL Commands:")
    print(
        """
    # Upload a file
    curl -X POST -F "file=@document.pdf" \\
         http://localhost:8000/api/storage/upload

    # Upload with auto proxy
    curl -X POST -F "file=@document.pdf" \\
         "http://localhost:8000/api/storage/upload?create_proxy=true&proxy_expires_in=7200"

    # Create share link for existing file
    curl -X POST http://localhost:8000/api/storage/proxy \\
         -H "Content-Type: application/json" \\
         -d '{"file_path": "uploads/document.pdf", "expires_in": 7200}'

    # Access via proxy
    curl http://localhost:8000/p/abc123XY

    # Get proxy statistics
    curl http://localhost:8000/api/storage/proxy/abc123XY/stats

    # Use Walker to create share link
    curl -X POST http://localhost:8000/api/create-share-link \\
         -H "Content-Type: application/json" \\
         -d '{"file_path": "document.pdf", "expires_in": 3600, "one_time": true}'

    # Process a file with Walker
    curl -X POST http://localhost:8000/api/process-file \\
         -H "Content-Type: application/json" \\
         -d '{"file_path": "document.pdf"}'

    # List files in directory
    curl -X POST http://localhost:8000/api/list-files \\
         -H "Content-Type: application/json" \\
         -d '{"directory": "uploads"}'

    # Complete lifecycle demo
    curl -X POST http://localhost:8000/api/file-lifecycle \\
         -H "Content-Type: application/json" \\
         -d '{"file_name": "test.txt", "file_content": "SGVsbG8gV29ybGQ="}'
    """
    )

    print("=" * 70 + "\n")

    # Run server
    server.run(port=8000)
