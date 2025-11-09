
# File Storage Usage Guide

Complete guide to using file storage in jvspatial.

## Table of Contents
- [Introduction](#introduction)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Storage Providers](#storage-providers)
- [API Endpoints](#api-endpoints)
- [Walker Integration](#walker-integration)
- [URL Proxy System](#url-proxy-system)
- [Security Features](#security-features)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)
- [Advanced Usage](#advanced-usage)

---

## Introduction

The jvspatial file storage system provides secure, scalable file management with:
- **Multiple storage backends** - Local filesystem, AWS S3, with Azure/GCP support ready
- **URL proxy system** - MongoDB-backed short URLs for secure file sharing
- **Built-in security** - Path validation, MIME checking, size limits, access control
- **Async operations** - Non-blocking file operations and streaming support
- **Seamless integration** - Works with Server, Walker, and GraphContext

### Key Features

Security First
- Path traversal prevention
- MIME type validation
- File size limits
- Content verification

Multi-Backend Support
- Local filesystem storage
- AWS S3 with signed URLs
- Azure Blob Storage (coming soon)
- Google Cloud Storage (coming soon)

URL Proxy System
- Short URL generation
- Expiration control
- Access tracking
- MongoDB persistence

Performance
- Async/await operations
- Streaming support for large files
- Connection pooling
- Efficient caching

---

## Quick Start

### Basic Setup

```python
from jvspatial.api import Server

# Create server with file storage enabled
server = Server(
    title="My File API",
    file_storage_enabled=True,
    file_storage_provider="local",
    file_storage_root=".files",
    proxy_enabled=True
)

if __name__ == "__main__":
    server.run()
```

### Upload Your First File

```bash
# Upload a file
curl -X POST -F "file=@document.pdf" \
  http://localhost:8000/storage/upload

# Response:
{
  "success": true,
  "file_path": "2025/01/05/document-abc123.pdf",
  "file_url": "http://localhost:8000/storage/files/2025/01/05/document-abc123.pdf",
  "file_size": 102400,
  "content_type": "application/pdf"
}
```

### Create a Short URL

```bash
# Create shareable link (expires in 1 hour)
curl -X POST http://localhost:8000/storage/proxy \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "2025/01/05/document-abc123.pdf",
    "expires_in": 3600
  }'

# Response:
{
  "success": true,
  "proxy_code": "a1b2c3d4",
  "proxy_url": "http://localhost:8000/p/a1b2c3d4",
  "file_path": "2025/01/05/document-abc123.pdf",
  "expires_at": "2025-01-05T23:00:00Z"
}
```

---

## Configuration

### Server Configuration

Configure file storage when creating a Server instance:

```python
from jvspatial.api import Server

server = Server(
    title="File Storage API",

    # File Storage Settings
    file_storage_enabled=True,
    file_storage_provider="local",  # or "s3"
    file_storage_root=".files",
    file_storage_max_size=10485760,  # 10MB
    file_storage_allowed_types=[
        "image/jpeg",
        "image/png",
        "application/pdf",
        "text/plain"
    ],

    # URL Proxy Settings
    proxy_enabled=True,
    proxy_default_ttl=3600,  # 1 hour

    # Database (required for proxy)
    db_type="mongodb",
    db_connection_string="mongodb://localhost:27017",
    db_database_name="file_storage_db"
)
```

### Configuration Options

#### File Storage Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_storage_enabled` | `bool` | `False` | Enable file storage system |
| `file_storage_provider` | `str` | `"local"` | Storage provider (`"local"`, `"s3"`) |
| `file_storage_root` | `str` | `".files"` | Root directory for local storage |
| `file_storage_max_size` | `int` | `10485760` | Max file size in bytes (10MB) |
| `file_storage_allowed_types` | `List[str]` | `None` | Allowed MIME types (None = all) |
| `file_storage_blocked_types` | `List[str]` | `[]` | Blocked MIME types |

#### S3-Specific Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `file_storage_s3_bucket` | `str` | `None` | S3 bucket name |
| `file_storage_s3_region` | `str` | `"us-east-1"` | AWS region |
| `file_storage_s3_access_key` | `str` | `None` | AWS access key ID |
| `file_storage_s3_secret_key` | `str` | `None` | AWS secret access key |
| `file_storage_s3_endpoint` | `str` | `None` | Custom S3 endpoint (for MinIO, etc.) |

#### URL Proxy Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `proxy_enabled` | `bool` | `False` | Enable URL proxy system |
| `proxy_default_ttl` | `int` | `3600` | Default TTL in seconds |
| `proxy_code_length` | `int` | `8` | Length of proxy codes |

### Environment Variables

All configuration can be set via environment variables:

```env
# File Storage
JVSPATIAL_FILE_STORAGE_ENABLED=true
JVSPATIAL_FILE_STORAGE_PROVIDER=local
JVSPATIAL_FILE_STORAGE_ROOT=.files
JVSPATIAL_FILE_STORAGE_MAX_SIZE=10485760

# S3 Configuration
JVSPATIAL_FILE_STORAGE_S3_BUCKET=my-bucket
JVSPATIAL_FILE_STORAGE_S3_REGION=us-east-1
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key

# URL Proxy
JVSPATIAL_PROXY_ENABLED=true
JVSPATIAL_PROXY_DEFAULT_TTL=3600

# Database
JVSPATIAL_DB_TYPE=mongodb
JVSPATIAL_MONGODB_URI=mongodb://localhost:27017
JVSPATIAL_MONGODB_DB_NAME=file_storage_db
```

**Example `.env` file:**

```env
# Production File Storage Configuration
JVSPATIAL_FILE_STORAGE_ENABLED=true
JVSPATIAL_FILE_STORAGE_PROVIDER=s3
JVSPATIAL_FILE_STORAGE_S3_BUCKET=production-files
JVSPATIAL_FILE_STORAGE_S3_REGION=us-west-2
JVSPATIAL_FILE_STORAGE_MAX_SIZE=52428800  # 50MB
JVSPATIAL_PROXY_ENABLED=true
JVSPATIAL_PROXY_DEFAULT_TTL=7200  # 2 hours
```

---

## Storage Providers

### Local Storage

Local filesystem storage is the simplest option for development and small deployments.

#### Configuration

```python
server = Server(
    file_storage_enabled=True,
    file_storage_provider="local",
    file_storage_root=".files"  # Relative or absolute path
)
```

#### Features

- Simple setup, no external dependencies
- Fast for small files
- Good for development
- Not suitable for distributed deployments
- Limited scalability

#### Directory Structure

Files are organized by date:

```
.files/
├── 2025/
│   └── 01/
│       └── 05/
│           ├── document-abc123.pdf
│           ├── image-def456.jpg
│           └── data-ghi789.csv
```

#### Example

```python
from jvspatial.storage import create_storage

# Create local storage interface
storage = create_storage(
    provider="local",
    root_dir=".files"
)

# Save a file
await storage.save_file(
    file_path="uploads/test.txt",
    content=b"Hello, World!"
)

# Read a file
content = await storage.get_file("uploads/test.txt")
print(content.decode())  # "Hello, World!"

# Check if file exists
exists = await storage.file_exists("uploads/test.txt")
print(exists)  # True

# Delete a file
deleted = await storage.delete_file("uploads/test.txt")
print(deleted)  # True
```

---

### AWS S3 Storage

AWS S3 provides scalable, distributed file storage.

#### Configuration

```python
server = Server(
    file_storage_enabled=True,
    file_storage_provider="s3",
    file_storage_s3_bucket="my-bucket",
    file_storage_s3_region="us-east-1"
)
```

#### Credentials

**Option 1: Environment Variables (Recommended)**

```env
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

**Option 2: Server Configuration**

```python
server = Server(
    file_storage_provider="s3",
    file_storage_s3_bucket="my-bucket",
    file_storage_s3_region="us-east-1",
    file_storage_s3_access_key="AKIAIOSFODNN7EXAMPLE",
    file_storage_s3_secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
)
```

**Option 3: IAM Role (AWS EC2/ECS/Lambda)**

When running on AWS, credentials are automatically obtained from the instance IAM role.

#### Features

- Highly scalable
- Distributed and redundant
- Signed URL support
- Good for production
- Requires AWS account
- Additional costs

#### S3 Bucket Configuration

**Bucket Policy Example:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "AWS": "arn:aws:iam::ACCOUNT-ID:user/jvspatial-app"
      },
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-bucket/*",
        "arn:aws:s3:::my-bucket"
      ]
    }
  ]
}
```

#### Example

```python
from jvspatial.storage import get_file_interface

# Get S3 storage interface
storage = get_file_interface(
    provider="s3",
    bucket="my-bucket",
    region="us-east-1"
)

# Save a file to S3
await storage.save_file(
    file_path="documents/report.pdf",
    content=pdf_bytes,
    metadata={
        "uploaded_by": "user123",
        "department": "finance"
    }
)

# Get signed URL (temporary access)
signed_url = await storage.get_signed_url(
    file_path="documents/report.pdf",
    expires_in=3600  # 1 hour
)
print(f"Download URL: {signed_url}")

# Stream large file
async for chunk in storage.stream_file("documents/large-file.zip"):
    # Process chunk
    await process_chunk(chunk)
```

---

## API Endpoints

### Upload File

**Endpoint:** `POST /storage/upload`

Upload a file to storage.

**Request:**

```bash
curl -X POST -F "file=@document.pdf" \
  -F "custom_path=reports/Q1-2025.pdf" \
  http://localhost:8000/storage/upload
```

**With Proxy:**

```bash
curl -X POST -F "file=@document.pdf" \
  -F "create_proxy=true" \
  -F "proxy_ttl=7200" \
  http://localhost:8000/storage/upload
```

**Response:**

```json
{
  "success": true,
  "file_path": "reports/Q1-2025.pdf",
  "file_url": "http://localhost:8000/storage/files/reports/Q1-2025.pdf",
  "file_size": 245760,
  "content_type": "application/pdf",
  "checksum": "abc123def456",
  "proxy_code": "x7y8z9w0",
  "proxy_url": "http://localhost:8000/p/x7y8z9w0"
}
```

---

### Download File

**Endpoint:** `GET /storage/files/{path}`

Download or stream a file.

**Request:**

```bash
curl http://localhost:8000/storage/files/reports/Q1-2025.pdf \
  -o downloaded.pdf
```

**Response:**

File content with appropriate headers:
- `Content-Type`: File MIME type
- `Content-Length`: File size
- `Content-Disposition`: Attachment with filename

---

### Delete File

**Endpoint:** `DELETE /storage/files/{path}`

Delete a file from storage.

**Request:**

```bash
curl -X DELETE \
  http://localhost:8000/storage/files/reports/Q1-2025.pdf
```

**Response:**

```json
{
  "success": true,
  "message": "File deleted successfully",
  "file_path": "reports/Q1-2025.pdf"
}
```

---

### List Files

**Endpoint:** `GET /storage/files`

List files in storage.

**Request:**

```bash
# List all files
curl http://localhost:8000/storage/files

# List with prefix filter
curl "http://localhost:8000/storage/files?prefix=reports/"

# List with pagination
curl "http://localhost:8000/storage/files?page=1&page_size=20"
```

**Response:**

```json
{
  "success": true,
  "files": [
    {
      "path": "reports/Q1-2025.pdf",
      "size": 245760,
      "content_type": "application/pdf",
      "modified": "2025-01-05T20:30:00Z"
    },
    {
      "path": "reports/Q2-2025.pdf",
      "size": 189440,
      "content_type": "application/pdf",
      "modified": "2025-04-05T14:20:00Z"
    }
  ],
  "total": 2,
  "page": 1,
  "page_size": 20
}
```

---

### Get File Metadata

**Endpoint:** `GET /storage/files/{path}/metadata`

Get file metadata without downloading.

**Request:**

```bash
curl http://localhost:8000/storage/files/reports/Q1-2025.pdf/metadata
```

**Response:**

```json
{
  "file_path": "reports/Q1-2025.pdf",
  "original_name": "Q1-2025.pdf",
  "content_type": "application/pdf",
  "size_bytes": 245760,
  "checksum": "abc123def456",
  "created_at": "2025-01-05T20:30:00Z",
  "last_accessed": "2025-01-05T21:15:00Z",
  "metadata": {
    "uploaded_by": "user123",
    "department": "finance"
  }
}
```

---

## Walker Integration

Use file storage within Walker classes for graph-based file processing.

### Basic Walker Usage

```python
from jvspatial.storage import get_file_interface
from jvspatial.core import Walker, on_visit, Node

@server.walker("/process-document")
class DocumentProcessor(Walker):
    file_path: str

    @on_visit(Node)
    async def process(self, here: Node):
        # Get storage interface
        storage = get_file_interface(
            provider="local",
            root_dir=".files"
        )

        # Check file exists
        if not await storage.file_exists(self.file_path):
            self.report({"error": "File not found"})
            return

        # Read file content
        content = await storage.get_file(self.file_path)

        # Process file
        result = await self.analyze_content(content)

        # Report results
        self.report({
            "file_path": self.file_path,
            "analysis": result,
            "status": "complete"
        })

    async def analyze_content(self, content: bytes) -> dict:
        """Analyze file content."""
        return {
            "size": len(content),
            "type": "document",
            "word_count": len(content.decode().split())
        }
```

### Walker with File Validation

```python
@server.walker("/validate-upload")
class UploadValidator(Walker):
    file_path: str
    max_size: int = 5242880  # 5MB

    @on_visit(Node)
    async def validate(self, here: Node):
        storage = get_file_interface()

        # Get file metadata
        metadata = await storage.get_metadata(self.file_path)

        if not metadata:
            self.report({"valid": False, "error": "File not found"})
            return

        # Validate size
        if metadata.get("size", 0) > self.max_size:
            self.report({
                "valid": False,
                "error": "File too large",
                "size": metadata["size"],
                "max_size": self.max_size
            })
            return

        # Validate type
        allowed_types = ["application/pdf", "image/jpeg", "image/png"]
        if metadata.get("content_type") not in allowed_types:
            self.report({
                "valid": False,
                "error": "Invalid file type",
                "content_type": metadata["content_type"]
            })
            return

        self.report({
            "valid": True,
            "file_path": self.file_path,
            "metadata": metadata
        })
```

### Walker with Streaming

```python
@server.walker("/process-large-file")
class LargeFileProcessor(Walker):
    file_path: str
    chunk_size: int = 1048576  # 1MB chunks

    @on_visit(Node)
    async def process(self, here: Node):
        storage = get_file_interface()

        total_size = 0
        chunk_count = 0

        # Stream file in chunks
        async for chunk in storage.stream_file(self.file_path):
            # Process each chunk
            await self.process_chunk(chunk, chunk_count)

            total_size += len(chunk)
            chunk_count += 1

        self.report({
            "file_path": self.file_path,
            "total_size": total_size,
            "chunks_processed": chunk_count,
            "status": "complete"
        })

    async def process_chunk(self, chunk: bytes, index: int):
        """Process individual chunk."""
        # Your chunk processing logic
        pass
```

---

## URL Proxy System

The URL proxy system provides secure, temporary file access through short URLs.

### Creating Proxy URLs

#### Via API Endpoint

```bash
curl -X POST http://localhost:8000/storage/proxy \
  -H "Content-Type: application/json" \
  -d '{
    "file_path": "documents/report.pdf",
    "expires_in": 3600,
    "max_accesses": 10
  }'
```

**Response:**

```json
{
  "success": true,
  "proxy_code": "a1b2c3d4",
  "proxy_url": "http://localhost:8000/p/a1b2c3d4",
  "file_path": "documents/report.pdf",
  "expires_at": "2025-01-05T23:00:00Z",
  "max_accesses": 10
}
```

#### Programmatically

```python
from jvspatial.storage.managers import URLProxyManager
from jvspatial.core import GraphContext

# Initialize proxy manager
ctx = GraphContext()
proxy_manager = URLProxyManager(ctx)

# Create proxy with 1-hour expiration
code = await proxy_manager.create_proxy(
    file_path="documents/report.pdf",
    ttl_hours=1,
    max_accesses=5,
    metadata={"created_by": "user123"}
)

print(f"Proxy URL: http://yoursite.com/p/{code}")
```

### Using Proxy URLs

Access files via short code:

```bash
# Direct access
curl http://localhost:8000/p/a1b2c3d4 -o report.pdf

# Browser access
http://localhost:8000/p/a1b2c3d4
```

The proxy system:
1. Validates the code
2. Checks expiration
3. Checks access limits
4. Increments access counter
5. Serves the file
6. Automatically deletes expired/depleted proxies

### Managing Proxies

#### Get Proxy Info

```bash
curl http://localhost:8000/storage/proxy/a1b2c3d4/info
```

**Response:**

```json
{
  "code": "a1b2c3d4",
  "file_path": "documents/report.pdf",
  "created_at": "2025-01-05T22:00:00Z",
  "expires_at": "2025-01-05T23:00:00Z",
  "access_count": 3,
  "max_accesses": 10,
  "remaining_accesses": 7
}
```

#### Delete Proxy

```bash
curl -X DELETE http://localhost:8000/storage/proxy/a1b2c3d4
```

#### Cleanup Expired Proxies

```python
# Automatic cleanup
deleted_count = await proxy_manager.cleanup_expired()
print(f"Deleted {deleted_count} expired proxies")
```

### Proxy Use Cases

**1. Temporary File Sharing**

```python
# Share report for 24 hours
code = await proxy_manager.create_proxy(
    file_path="reports/monthly-2025-01.pdf",
    ttl_hours=24
)
share_link = f"https://myapp.com/p/{code}"
```

**2. Limited Access Downloads**

```python
# Allow 3 downloads only
code = await proxy_manager.create_proxy(
    file_path="downloads/software-installer.exe",
    max_accesses=3
)
```

**3. Time-Limited Access**

```python
# Expire in 15 minutes
code = await proxy_manager.create_proxy(
    file_path="temp/session-data.json",
    ttl_hours=0.25  # 15 minutes
)
```

---

## Security Features

### Path Traversal Prevention

All file paths are sanitized to prevent directory traversal attacks:

```python
# Dangerous paths are blocked
dangerous_paths = [
    "../../../etc/passwd",
    "..\\..\\windows\\system32",
    "/etc/shadow",
    "~/.ssh/id_rsa"
]

# Safe paths are allowed
safe_paths = [
    "documents/report.pdf",
    "images/2025/photo.jpg",
    "uploads/data.csv"
]
```

**Security Measures:**
- Removes `..` sequences
- Blocks absolute paths
- Validates each path component
- Enforces base directory restrictions
- Checks maximum path depth

### MIME Type Validation

Configure allowed and blocked file types:

```python
server = Server(
    file_storage_allowed_types=[
        "image/jpeg",
        "image/png",
        "application/pdf",
        "text/plain"
    ],
    file_storage_blocked_types=[
        "application/x-executable",
        "application/x-sh",
        "text/x-script.python"
    ]
)
```

**Validation Process:**
1. Checks file extension
2. Detects actual MIME type from content
3. Compares against allowed/blocked lists
4. Rejects mismatched files

### File Size Limits

Prevent resource exhaustion:

```python
server = Server(
    file_storage_max_size=10485760  # 10MB limit
)
```

**Enforcement:**
- Checked before upload starts
- Validated during upload
- Rejected if exceeded
- Per-file and cumulative limits

### Access Control

Integration with jvspatial authentication:

```python
from jvspatial.api.auth import require_permissions

@server.endpoint("/storage/upload", methods=["POST"])
@require_permissions(["upload_files"])
async def upload_file(file: UploadFile):
    # Only users with 'upload_files' permission can upload
    pass
```

### Signed URLs (S3)

Generate time-limited access URLs:

```python
# Create signed URL (valid for 1 hour)
signed_url = await storage.get_signed_url(
    file_path="private/document.pdf",
    expires_in=3600
)

# Share URL - expires automatically
send_email(recipient, signed_url)
```

---

## Best Practices

### 1. Use Environment Variables

Bad:
```python
server = Server(
    file_storage_s3_access_key="AKIAIOSFODNN7EXAMPLE",
    file_storage_s3_secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
)
```

Good:
```python
from dotenv import load_dotenv
load_dotenv()

server = Server(
    file_storage_provider="s3",
    # Credentials from AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY
)
```

### 2. Validate Before Processing

Bad:
```python
@server.walker("/process-file")
class FileProcessor(Walker):
    file_path: str

    @on_visit(Node)
    async def process(self, here: Node):
        # No validation - could fail
        content = await storage.get_file(self.file_path)
        result = process_content(content)
```

Good:
```python
@server.walker("/process-file")
class FileProcessor(Walker):
    file_path: str

    @on_visit(Node)
    async def process(self, here: Node):
        # Validate first
        if not await storage.file_exists(self.file_path):
            self.report({"error": "File not found"})
            return

        metadata = await storage.get_metadata(self.file_path)
        if metadata["size"] > 10485760:  # 10MB
            self.report({"error": "File too large"})
            return

        # Now process
        content = await storage.get_file(self.file_path)
        result = await self.process_content(content)
        self.report({"result": result})
```

### 3. Use Streaming for Large Files

**Bad:**
```python
# Loads entire file into memory
content = await storage.get_file("large-file.zip")
process_file(content)
```

**Good:**
```python
# Streams file in chunks
async for chunk in storage.stream_file("large-file.zip"):
    await process_chunk(chunk)
```

### 4. Set Appropriate Proxy Expiration

Bad:
```python
# Never expires - security risk
code = await proxy_manager.create_proxy(
    file_path="sensitive-data.pdf",
    ttl_hours=None
)
```

**Good:**
```python
# Expires in 1 hour
code = await proxy_manager.create_proxy(
    file_path="sensitive-data.pdf",
    ttl_hours=1
)
```

### 5. Clean Up Temporary Files

```python
# Schedule cleanup task
@on_schedule("every 1 hour")
async def cleanup_temp_files():
    storage = get_file_interface()

    # Delete files older than 24 hours
    temp_files = await storage.list_files(prefix="temp/")
    for file in temp_files:
        if file.age_hours > 24:
            await storage.delete_file(file.path)
```

### 6. Use Metadata for Tracking

```python
# Save file with metadata
await storage.save_file(
    file_path="uploads/document.pdf",
    content=file_bytes,
    metadata={
        "uploaded_by": user.id,
        "upload_time": datetime.now().isoformat(),
        "department": user.department,
        "classification": "internal"
    }
)
```

### 7. Handle Errors Gracefully

```python
from jvspatial.storage.exceptions import (
    StorageError,
    PathTraversalError,
    FileSizeError
)

try:
    await storage.save_file(file_path, content)
except PathTraversalError:
    return {"error": "Invalid file path"}
except FileSizeError:
    return {"error": "File too large"}
except StorageError as e:
    logger.error(f"Storage error: {e}")
    return {"error": "Failed to save file"}
```

---

## Troubleshooting

### Common Issues

#### Issue: File Not Found

**Problem:**
```python
content = await storage.get_file("documents/report.pdf")
# Returns None
```

**Solutions:**
1. Check file path is correct
2. Verify file was uploaded successfully
3. Check storage provider configuration
4. Ensure file hasn't been deleted

**Debug:**
```python
# List all files to verify
files = await storage.list_files(prefix="documents/")
print([f.path
 for f in files])

# Check if file exists
exists = await storage.file_exists("documents/report.pdf")
print(f"File exists: {exists}")
```

---

#### Issue: Path Traversal Error

**Problem:**
```python
await storage.save_file("../../../etc/passwd", content)
# Raises PathTraversalError
```

**Solutions:**
1. Use relative paths only
2. Don't use `..` in paths
3. Use forward slashes `/` not backslashes
4. Ensure paths are within storage root

**Correct Usage:**
```python
# Good paths
await storage.save_file("documents/report.pdf", content)
await storage.save_file("2025/01/data.csv", content)

# Bad paths
await storage.save_file("../data.csv", content)  # Error
await storage.save_file("/etc/passwd", content)  # Error
```

---

#### Issue: File Size Exceeded

**Problem:**
```bash
curl -X POST -F "file=@huge-file.zip" \
  http://localhost:8000/storage/upload
# Error: File size exceeds maximum allowed
```

**Solutions:**
1. Increase `file_storage_max_size` limit
2. Compress file before upload
3. Use chunked upload for large files
4. Contact administrator for limit increase

**Configuration:**
```python
# Increase limit to 50MB
server = Server(
    file_storage_max_size=52428800  # 50MB
)
```

---

#### Issue: Proxy Code Not Working

**Problem:**
```bash
curl http://localhost:8000/p/abc123
# 404 Not Found
```

**Solutions:**
1. Check code is correct (case-sensitive)
2. Verify proxy hasn't expired
3. Check max accesses not exceeded
4. Ensure proxy system is enabled

**Debug:**
```python
# Check proxy status
proxy_info = await proxy_manager.get_proxy_info("abc123")
if not proxy_info:
    print("Proxy not found or expired")
else:
    print(f"Proxy valid, expires: {proxy_info['expires_at']}")
    print(f"Accesses: {proxy_info['access_count']}/{proxy_info['max_accesses']}")
```

---

#### Issue: S3 Connection Failed

**Problem:**
```
StorageError: Unable to connect to S3 bucket
```

**Solutions:**
1. Verify AWS credentials are correct
2. Check bucket name and region
3. Ensure bucket exists and is accessible
4. Verify IAM permissions

**Debug:**
```bash
# Test AWS credentials
aws s3 ls s3://my-bucket --region us-east-1

# Check IAM permissions
aws iam get-user
```

**Required IAM Permissions:**
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject",
        "s3:ListBucket"
      ],
      "Resource": [
        "arn:aws:s3:::my-bucket/*",
        "arn:aws:s3:::my-bucket"
      ]
    }
  ]
}
```

---

#### Issue: MongoDB Proxy Storage Failed

**Problem:**
```
DatabaseError: Unable to save proxy to MongoDB
```

**Solutions:**
1. Verify MongoDB connection
2. Check database permissions
3. Ensure database is running
4. Verify connection string

**Debug:**
```python
# Test MongoDB connection
from jvspatial.core import GraphContext

ctx = GraphContext()
# If this succeeds, MongoDB is connected

# Check database
from motor.motor_asyncio import AsyncIOMotorClient

client = AsyncIOMotorClient("mongodb://localhost:27017")
db = client.file_storage_db
# Test connection
await db.command("ping")
```

---

### Performance Optimization

#### 1. Use Streaming for Large Files

```python
# Instead of loading entire file
content = await storage.get_file("large-video.mp4")  # Slow

# Stream in chunks
async for chunk in storage.stream_file("large-video.mp4"):
    await process_chunk(chunk)  # Fast
```

#### 2. Enable Caching

```python
from functools import lru_cache

@lru_cache(maxsize=100)
async def get_file_metadata(file_path: str):
    """Cache metadata lookups."""
    return await storage.get_metadata(file_path)
```

#### 3. Batch Operations

```python
# Instead of uploading one by one
for file in files:
    await storage.save_file(file.path, file.content)  # Slow

# Batch upload
import asyncio
await asyncio.gather(
    *[storage.save_file(f.path, f.content) for f in files]
)  # Fast
```

#### 4. Use Signed URLs for S3

```python
# Instead of proxying through server
file_content = await storage.get_file(path)
return Response(content=file_content)  # Server overhead

# Generate signed URL (client downloads directly from S3)
signed_url = await storage.get_signed_url(path, expires_in=3600)
return {"download_url": signed_url}  # No server overhead
```

---

## Advanced Usage

### Custom Storage Provider

Implement your own storage backend:

```python
from jvspatial.storage.interfaces import FileStorageInterface
from typing import AsyncIterator, Optional, Dict, Any

class CustomStorageProvider(FileStorageInterface):
    """Custom storage provider implementation."""

    def __init__(self, **config):
        self.config = config
        # Initialize your storage backend

    async def save_file(
        self,
        file_path: str,
        content: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Save file to custom storage."""
        # Your implementation
        return {
            "path": file_path,
            "size": len(content),
            "checksum": self._calculate_checksum(content)
        }

    async def get_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file from custom storage."""
        # Your implementation
        pass

    async def stream_file(
        self,
        file_path: str
    ) -> AsyncIterator[bytes]:
        """Stream file from custom storage."""
        # Your implementation
        chunk_size = 1048576  # 1MB
        # Yield chunks
        pass

    async def delete_file(self, file_path: str) -> bool:
        """Delete file from custom storage."""
        # Your implementation
        pass

    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists."""
        # Your implementation
        pass

    async def get_file_info(
        self,
        file_path: str
    ) -> Optional[Dict[str, Any]]:
        """Get file metadata."""
        # Your implementation
        pass

    async def get_signed_url(
        self,
        file_path: str,
        expires_in: int = 3600
    ) -> Optional[str]:
        """Generate signed URL (if supported)."""
        # Your implementation or return None
        return None

    def _calculate_checksum(self, content: bytes) -> str:
        """Calculate file checksum."""
        import hashlib
        return hashlib.sha256(content).hexdigest()

# Register custom provider
from jvspatial.storage.interfaces.factory import register_provider

register_provider("custom", CustomStorageProvider)

# Use custom provider
server = Server(
    file_storage_enabled=True,
    file_storage_provider="custom",
    file_storage_custom_config={
        "endpoint": "https://custom-storage.example.com",
        "api_key": "your-api-key"
    }
)
```

---

### File Processing Pipeline

Create a complete file processing workflow:

```python
from jvspatial.core import Walker, on_visit, Node
from jvspatial.storage import get_file_interface
import asyncio

@server.walker("/process-pipeline")
class FileProcessingPipeline(Walker):
    """Complete file processing pipeline."""

    input_path: str
    output_path: str

    @on_visit(Node)
    async def run_pipeline(self, here: Node):
        storage = get_file_interface()

        # Stage 1: Validate
        self.report({"stage": "validation", "status": "started"})
        valid = await self.validate_file(storage, self.input_path)
        if not valid:
            self.report({"stage": "validation", "status": "failed"})
            return
        self.report({"stage": "validation", "status": "complete"})

        # Stage 2: Process
        self.report({"stage": "processing", "status": "started"})
        processed_content = await self.process_file(storage, self.input_path)
        self.report({"stage": "processing", "status": "complete"})

        # Stage 3: Save
        self.report({"stage": "saving", "status": "started"})
        await storage.save_file(self.output_path, processed_content)
        self.report({"stage": "saving", "status": "complete"})

        # Stage 4: Create proxy
        self.report({"stage": "proxy", "status": "started"})
        from jvspatial.storage.managers import URLProxyManager
        proxy_manager = URLProxyManager(here.context)
        code = await proxy_manager.create_proxy(
            file_path=self.output_path,
            ttl_hours=24
        )
        self.report({
            "stage": "proxy",
            "status": "complete",
            "proxy_code": code
        })

        # Final report
        self.report({
            "pipeline": "complete",
            "input": self.input_path,
            "output": self.output_path,
            "proxy_url": f"http://localhost:8000/p/{code}"
        })

    async def validate_file(self, storage, path: str) -> bool:
        """Validate file."""
        if not await storage.file_exists(path):
            return False

        metadata = await storage.get_metadata(path)
        if metadata["size"] > 10485760:  # 10MB
            return False

        return True

    async def process_file(self, storage, path: str) -> bytes:
        """Process file content."""
        content = await storage.get_file(path)

        # Your processing logic here
        # Example: Convert to uppercase
        processed = content.decode().upper().encode()

        return processed
```

---

### Scheduled File Cleanup

Automatically clean up old files:

```python
from jvspatial.api.scheduler import on_schedule
from datetime import datetime, timedelta

@on_schedule("every 1 hour", description="Clean up old files")
async def cleanup_old_files():
    """Remove files older than 30 days."""
    from jvspatial.storage import get_file_interface

    storage = get_file_interface()
    cutoff_date = datetime.now() - timedelta(days=30)

    # List all files
    files = await storage.list_files()

    deleted_count = 0
    for file in files:
        # Check file age
        file_date = datetime.fromisoformat(file.modified)
        if file_date < cutoff_date:
            await storage.delete_file(file.path)
            deleted_count += 1

    print(f"Cleaned up {deleted_count} old files")

# Also cleanup expired proxies
@on_schedule("every 6 hours")
async def cleanup_expired_proxies():
    """Remove expired URL proxies."""
    from jvspatial.storage.managers import URLProxyManager
    from jvspatial.core import GraphContext

    ctx = GraphContext()
    proxy_manager = URLProxyManager(ctx)

    deleted_count = await proxy_manager.cleanup_expired()
    print(f"Cleaned up {deleted_count} expired proxies")
```

---

### Multi-User File Access

Implement user-specific file access:

```python
from jvspatial.api import endpoint
from jvspatial.api.auth import get_current_user, require_permissions

@endpoint("/api/users/files", methods=["GET"])
@require_permissions(["view_files"])
async def list_user_files(endpoint):
    """List files for current user."""
    user = get_current_user()
    storage = get_file_interface()

    # List files in user's directory
    user_prefix = f"users/{user.id}/"
    files = await storage.list_files(prefix=user_prefix)

    return endpoint.success(
        data={
            "user_id": user.id,
            "files": [
                {
                    "path": f.path.replace(user_prefix, ""),
                    "size": f.size,
                    "modified": f.modified
                }
                for f in files
            ]
        }
    )

@endpoint("/api/users/files/upload", methods=["POST"])
@require_permissions(["upload_files"])
async def upload_user_file(file: UploadFile, endpoint):
    """Upload file to user's directory."""
    user = get_current_user()
    storage = get_file_interface()

    # Save to user-specific path
    user_path = f"users/{user.id}/{file.filename}"
    content = await file.read()

    await storage.save_file(
        file_path=user_path,
        content=content,
        metadata={"uploaded_by": user.id}
    )

    return endpoint.created(
        data={
            "path": user_path,
            "size": len(content),
            "file_url": f"/storage/files/{user_path}"
        }
    )
```

---

## Additional Resources

### Related Documentation

- [File Storage Architecture](file-storage-architecture.md) - Technical architecture details
- [Server Configuration](server-configuration.md) - Complete server setup guide
- [Walker Guide](walker-guide.md) - Walker development documentation
- [API Reference](api-reference.md) - Complete API documentation

### Example Projects

- [`examples/file_storage_demo.py`](../../examples/file_storage_demo.py) - Complete working example
- [`examples/s3_storage_example.py`](../../examples/s3_storage_example.py) - S3 integration example

### External Resources

- [AWS S3 Documentation](https://docs.aws.amazon.com/s3/)
- [MongoDB Documentation](https://docs.mongodb.com/)
- [FastAPI File Uploads](https://fastapi.tiangolo.com/tutorial/request-files/)

---

## Summary

The jvspatial file storage system provides:

**Multiple Storage Backends** - Local, S3, with more coming
**URL Proxy System** - Secure temporary file sharing
**Built-in Security** - Path validation, MIME checking, size limits
**Walker Integration** - Process files within graph traversal
**Production Ready** - Streaming, caching, error handling

**Next Steps:**

1. Review [Configuration](#configuration) for your deployment
2. Choose a [Storage Provider](#storage-providers)
3. Implement [Security Features](#security-features)
4. Follow [Best Practices](#best-practices)
5. Check [Troubleshooting](#troubleshooting) if issues arise

For technical architecture details, see [File Storage Architecture](file-storage-architecture.md).

---

**Last Updated:** 2025-01-05
**Version:** 1.0.0