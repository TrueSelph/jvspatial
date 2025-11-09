
# File Storage System Architecture for jvspatial

## Executive Summary

This document defines the complete architecture for integrating a secure, scalable file storage system into jvspatial. The design addresses identified security vulnerabilities, provides MongoDB-backed URL proxy management, supports multiple storage backends (local, S3, Azure, GCP), and integrates seamlessly with the existing Server and GraphContext infrastructure.

**Version:** 1.0
**Status:** Design Phase
**Author:** Architecture Team
**Date:** 2025-10-05

---

## Table of Contents

1. [Current State Analysis](#1-current-state-analysis)
2. [Architecture Overview](#2-architecture-overview)
3. [Directory Structure](#3-directory-structure)
4. [Module Design](#4-module-design)
5. [Class Hierarchy](#5-class-hierarchy)
6. [API Specification](#6-api-specification)
7. [Security Architecture](#7-security-architecture)
8. [Configuration Schema](#8-configuration-schema)
9. [Migration Path](#9-migration-path)
10. [Integration Points](#10-integration-points)

---

## 1. Current State Analysis

### 1.1 Existing Implementation

**Location:** `jvspatial/jvspatial/api/file_interface.py`

**Components:**
- `FileInterface` - Abstract base class
- `LocalFileInterface` - Filesystem storage
- `S3FileInterface` - AWS S3 storage
- `get_file_interface()` - Factory function

### 1.2 Identified Security Vulnerabilities

| Vulnerability | Location | Risk Level | Impact |
|--------------|----------|------------|---------|
| **Path Traversal** | `LocalFileInterface.get_file()` line 55 | **CRITICAL** | Arbitrary file read access |
| **Path Traversal** | `LocalFileInterface.save_file()` line 63 | **CRITICAL** | Write files anywhere on filesystem |
| **No Input Validation** | All methods | **HIGH** | Malicious filenames accepted |
| **No MIME Type Checking** | `save_file()` | **MEDIUM** | Upload of executable files |
| **No Size Limits** | `save_file()` | **MEDIUM** | Disk space exhaustion |
| **Predictable URLs** | `get_file_url()` | **MEDIUM** | Unauthorized file access |

### 1.3 Architectural Issues

1. **Location:** Currently in `jvspatial/api/` - should be in dedicated `jvspatial/storage/` module
2. **Code Duplication:** Nearly identical implementation exists in `jv/jvagent/lib/file_interface.py`
3. **No URL Proxy:** Missing short URL generation with MongoDB backend
4. **Limited Integration:** Not integrated with Server or GraphContext
5. **No Streaming:** All files loaded into memory
6. **Missing Features:** No metadata tracking, access control, or audit logging

---

## 2. Architecture Overview

### 2.1 Design Principles

1. **Security First:** Path sanitization, validation, access control at every layer
2. **Separation of Concerns:** Clear boundaries between storage, proxy, and API layers
3. **Extensibility:** Plugin architecture for new storage providers
4. **Performance:** Streaming support, caching, connection pooling
5. **Integration:** Seamless integration with GraphContext and Server

### 2.2 System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Server Layer                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │          File Storage Endpoints                      │   │
│  │  • /files/upload    • /files/{path}                 │   │
│  │  • /files/delete    • /p/{code}  (proxy)            │   │
│  └─────────────────────────────────────────────────────┘   │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────────┐
│              Storage Manager Layer                           │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │  File Manager    │  │  URL Proxy       │                │
│  │  • Validation    │  │  • Code Gen      │                │
│  │  • Sanitization  │  │  • MongoDB Store │                │
│  │  • Metadata      │  │  • TTL Support   │                │
│  └──────────────────┘  └──────────────────┘                │
└───────────────────────┬─────────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────────┐
│           Storage Interface Layer                            │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐ ┌──────────┐│
│  │   Local    │ │     S3     │ │   Azure    │ │   GCP    ││
│  │ FileStore  │ │ FileStore  │ │ FileStore  │ │FileStore ││
│  └────────────┘ └────────────┘ └────────────┘ └──────────┘│
└─────────────────────────────────────────────────────────────┘
                        │
┌───────────────────────┴─────────────────────────────────────┐
│              GraphContext & MongoDB                          │
│  • File Metadata Storage   • URL Proxy Mappings             │
│  • Access Control Records  • Audit Logs                     │
└─────────────────────────────────────────────────────────────┘
```

### 2.3 Core Components

1. **Storage Interface Layer** (`jvspatial/storage/interfaces/`)
   - Abstract base classes
   - Provider implementations (Local, S3, Azure, GCP)
   - Streaming support

2. **Management Layer** (`jvspatial/storage/managers/`)
   - File manager with security
   - URL proxy manager
   - Metadata manager

3. **API Layer** (`jvspatial/storage/api/`)
   - RESTful endpoints
   - Request/response models
   - Authentication integration

4. **Configuration** (`jvspatial/storage/config.py`)
   - Provider configuration
   - Security settings
   - Resource limits

---

## 3. Directory Structure

### 3.1 New Module Organization

```
jvspatial/storage/
├── __init__.py                 # Module initialization, public API
├── config.py                   # Configuration classes and schemas
├── exceptions.py               # Custom exceptions
│
├── interfaces/                 # Storage provider interfaces
│   ├── __init__.py
│   ├── base.py                # FileStorageInterface (abstract)
│   ├── local.py               # LocalFileStorage
│   ├── s3.py                  # S3FileStorage
│   ├── azure.py               # AzureFileStorage
│   ├── gcp.py                 # GCPFileStorage
│   └── factory.py             # Storage provider factory
│
├── managers/                   # Business logic layer
│   ├── __init__.py
│   ├── file_manager.py        # Core file management with security
│   ├── url_proxy.py           # URL proxy with MongoDB backend
│   ├── metadata.py            # File metadata management
│   └── validator.py           # Validation and sanitization
│
├── models/                     # Data models
│   ├── __init__.py
│   ├── file_metadata.py       # FileMetadata entity
│   ├── url_proxy.py           # URLProxy entity
│   ├── requests.py            # API request models
│   └── responses.py           # API response models
│
├── api/                        # REST API endpoints
│   ├── __init__.py
│   ├── endpoints.py           # File operation endpoints
│   ├── routes.py              # FastAPI route definitions
│   └── dependencies.py        # FastAPI dependencies
│
├── security/                   # Security utilities
│   ├── __init__.py
│   ├── path_sanitizer.py      # Path traversal prevention
│   ├── validators.py          # File validation
│   ├── access_control.py      # Access control logic
│   └── mime_types.py          # MIME type handling
│
└── utils/                      # Utility functions
    ├── __init__.py
    ├── streaming.py           # Streaming utilities
    ├── compression.py         # Compression support
    └── hash.py                # Hashing utilities
```

### 3.2 File Placement Strategy

| File Category | Location | Purpose |
|--------------|----------|---------|
| **Base Abstractions** | `interfaces/base.py` | Define contracts |
| **Provider Implementations** | `interfaces/*.py` | Concrete storage backends |
| **Security Logic** | `security/*.py` | All security features isolated |
| **Business Logic** | `managers/*.py` | File operations, proxy, metadata |
| **Data Models** | `models/*.py` | Pydantic models, entities |
| **API Layer** | `api/*.py` | HTTP endpoints, routing |

---

## 4. Module Design

### 4.1 Core Interfaces

#### 4.1.1 FileStorageInterface (Base)

```python
# jvspatial/storage/interfaces/base.py

from abc import ABC, abstractmethod
from typing import AsyncIterator, Optional, Dict, Any
from pathlib import Path


class FileStorageInterface(ABC):
    """Abstract base class for file storage backends.

    All storage providers must implement these methods with proper
    security, validation, and error handling.
    """

    @abstractmethod
    async def save_file(
        self,
        file_path: str,
        content: bytes,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Save file to storage.

        Args:
            file_path: Sanitized, validated file path
            content: File content as bytes
            metadata: Optional file metadata

        Returns:
            Dict with storage details (size, checksum, etc.)

        Raises:
            StorageError: If save fails
            ValidationError: If file fails validation
        """
        pass

    @abstractmethod
    async def get_file(self, file_path: str) -> Optional[bytes]:
        """Retrieve file content.

        Args:
            file_path: Sanitized file path

        Returns:
            File content or None if not found
        """
        pass

    @abstractmethod
    async def stream_file(
        self,
        file_path: str
    ) -> AsyncIterator[bytes]:
        """Stream file content in chunks.

        Args:
            file_path: Sanitized file path

        Yields:
            File content in chunks
        """
        pass

    @abstractmethod
    async def delete_file(self, file_path: str) -> bool:
        """Delete file from storage.

        Args:
            file_path: Sanitized file path

        Returns:
            True if deleted, False if not found
        """
        pass

    @abstractmethod
    async def file_exists(self, file_path: str) -> bool:
        """Check if file exists.

        Args:
            file_path: Sanitized file path

        Returns:
            True if file exists
        """
        pass

    @abstractmethod
    async def get_file_info(
        self,
        file_path: str
    ) -> Optional[Dict[str, Any]]:
        """Get file metadata.

        Args:
            file_path: Sanitized file path

        Returns:
            File info dict or None if not found
        """
        pass

    @abstractmethod
    async def get_signed_url(
        self,
        file_path: str,
        expires_in: int = 3600
    ) -> Optional[str]:
        """Generate signed URL for file access.

        Args:
            file_path: Sanitized file path
            expires_in: URL expiration in seconds

        Returns:
            Signed URL or None if not supported
        """
        pass
```

### 4.2 Security Layer

#### 4.2.1 Path Sanitizer

```python
# jvspatial/storage/security/path_sanitizer.py

import os
import re
from pathlib import Path
from typing import Optional
from ..exceptions import PathTraversalError, InvalidPathError


class PathSanitizer:
    """Secure path sanitization to prevent path traversal attacks."""

    # Allowed filename characters (alphanumeric, dash, underscore, dot)
    SAFE_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-\.]+$')

    # Dangerous patterns
    DANGEROUS_PATTERNS = [
        r'\.\.',      # Parent directory
        r'~',         # Home directory
        r'\$',        # Shell variables
        r'`',         # Command substitution
        r'\|',        # Pipe
        r';',         # Command separator
        r'&',         # Background execution
        r'>',         # Redirection
        r'<',         # Redirection
    ]

    # Maximum path depth
    MAX_PATH_DEPTH = 10

    # Maximum filename length
    MAX_FILENAME_LENGTH = 255

    @classmethod
    def sanitize_path(
        cls,
        file_path: str,
        base_dir: Optional[str] = None
    ) -> str:
        """Sanitize and validate file path.

        Args:
            file_path: Raw file path from user
            base_dir: Base directory to confine paths within

        Returns:
            Sanitized safe path

        Raises:
            PathTraversalError: If path traversal detected
            InvalidPathError: If path is invalid
        """
        if not file_path:
            raise InvalidPathError("File path cannot be empty")

        # Remove null bytes
        file_path = file_path.replace('\0', '')

        # Check for dangerous patterns
        for pattern in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, file_path):
                raise PathTraversalError(
                    f"Dangerous pattern detected: {pattern}"
                )

        # Normalize path
        normalized = os.path.normpath(file_path)

        # Check for parent directory references after normalization
        if normalized.startswith('..') or '/..' in normalized:
            raise PathTraversalError(
                "Path traversal attempt detected"
            )

        # Convert to Path object for validation
        path = Path(normalized)

        # Check path depth
        if len(path.parts) > cls.MAX_PATH_DEPTH:
            raise InvalidPathError(
                f"Path depth exceeds maximum ({cls.MAX_PATH_DEPTH})"
            )

        # Validate each path component
        for part in path.parts:
            if not cls.SAFE_FILENAME_PATTERN.match(part):
                raise InvalidPathError(
                    f"Invalid path component: {part}"
                )

            if len(part) > cls.MAX_FILENAME_LENGTH:
                raise InvalidPathError(
                    f"Filename too long: {part}"
                )

        # If base_dir provided, ensure path stays within it
        if base_dir:
            base = Path(base_dir).resolve()
            full_path = (base / normalized).resolve()

            # Check if resolved path is within base directory
            try:
                full_path.relative_to(base)
            except ValueError:
                raise PathTraversalError(
                    "Path escapes base directory"
                )

            return str(full_path.relative_to(base))

        return normalized

    @classmethod
    def sanitize_filename(cls, filename: str) -> str:
        """Sanitize a single filename.

        Args:
            filename: Raw filename

        Returns:
            Sanitized filename

        Raises:
            InvalidPathError: If filename is invalid
        """
        if not filename:
            raise InvalidPathError("Filename cannot be empty")

        # Remove path separators
        filename = filename.replace('/', '_').replace('\\', '_')

        # Check pattern
        if not cls.SAFE_FILENAME_PATTERN.match(filename):
            # Remove invalid characters
            filename = re.sub(r'[^a-zA-Z0-9_\-\.]', '_', filename)

        if len(filename) > cls.MAX_FILENAME_LENGTH:
            # Preserve extension
            name, ext = os.path.splitext(filename)
            max_name_len = cls.MAX_FILENAME_LENGTH - len(ext)
            filename = name[:max_name_len] + ext

        return filename
```

### 4.3 URL Proxy Manager

#### 4.3.1 URL Proxy with MongoDB

```python
# jvspatial/storage/managers/url_proxy.py

import secrets
import string
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
from jvspatial.core.entities import Object
from jvspatial.core.context import GraphContext


class URLProxy(Object):
    """URL proxy entity for short URL mappings.

    Stored in MongoDB for persistence and quick lookup.
    """

    code: str                    # Short code (e.g., "abc123")
    file_path: str              # Target file path
    created_at: str             # ISO timestamp
    expires_at: Optional[str]   # ISO timestamp or None
    access_count: int = 0       # Track usage
    max_accesses: Optional[int] # Limit accesses
    metadata: Dict[str, Any] = {}  # Additional data


class URLProxyManager:
    """Manages short URL proxies with MongoDB backend."""

    CODE_LENGTH = 8
    CODE_ALPHABET = string.ascii_letters + string.digits
    DEFAULT_TTL_HOURS = 24

    def __init__(self, context: GraphContext):
        """Initialize with GraphContext.

        Args:
            context: GraphContext for database operations
        """
        self.context = context

    async def create_proxy(
        self,
        file_path: str,
        ttl_hours: Optional[int] = None,
        max_accesses: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create URL proxy for a file.

        Args:
            file_path: Target file path
            ttl_hours: Time-to-live in hours (None = never expires)
            max_accesses: Maximum number of accesses
            metadata: Optional metadata

        Returns:
            Generated short code
        """
        code = self._generate_code()
        created_at = datetime.utcnow()

        # Calculate expiration
        expires_at = None
        if ttl_hours:
            expires_at = created_at + timedelta(hours=ttl_hours)

        # Create proxy entity
        proxy = await self.context.create(
            URLProxy,
            code=code,
            file_path=file_path,
            created_at=created_at.isoformat(),
            expires_at=expires_at.isoformat() if expires_at else None,
            max_accesses=max_accesses,
            metadata=metadata or {}
        )

        return code

    async def resolve_proxy(
        self,
        code: str,
        increment_access: bool = True
    ) -> Optional[str]:
        """Resolve proxy code to file path.

        Args:
            code: Short code
            increment_access: Whether to increment access count

        Returns:
            File path or None if invalid/expired
        """
        # Find proxy by code using MongoDB query
        proxies = await self.context.find_nodes(
            URLProxy,
            {"code": code},
            limit=1
        )

        if not proxies:
            return None

        proxy = proxies[0]

        # Check expiration
        if proxy.expires_at:
            expires = datetime.fromisoformat(proxy.expires_at)
            if datetime.utcnow() > expires:
                # Expired - delete proxy
                await self.context.delete(proxy)
                return None

        # Check access limit
        if proxy.max_accesses:
            if proxy.access_count >= proxy.max_accesses:
                # Limit reached - delete proxy
                await self.context.delete(proxy)
                return None

        # Increment access count
        if increment_access:
            proxy.access_count += 1
            await self.context.save(proxy)

        return proxy.file_path

    async def delete_proxy(self, code: str) -> bool:
        """Delete a proxy mapping.

        Args:
            code: Short code

        Returns:
            True if deleted, False if not found
        """
        proxies = await self.context.find_nodes(
            URLProxy,
            {"code": code},
            limit=1
        )

        if proxies:
            await self.context.delete(proxies[0])
            return True

        return False

    async def cleanup_expired(self) -> int:
        """Remove expired proxies.

        Returns:
            Number of proxies deleted
        """
        now = datetime.utcnow().isoformat()

        # Find all expired proxies
        all_proxies = await self.context.find_nodes(
            URLProxy,
            {}  # Get all
        )

        deleted_count = 0
        for proxy in all_proxies:
            if proxy.expires_at and proxy.expires_at < now:
                await self.context.delete(proxy)
                deleted_count += 1

        return deleted_count

    def _generate_code(self) -> str:
        """Generate random short code.

        Returns:
            Random code string
        """
        return ''.join(
            secrets.choice(self.CODE_ALPHABET)
            for _ in range(self.CODE_LENGTH)
        )
```

---

## 5. Class Hierarchy

### 5.1 Class Relationship Diagram

```
FileStorageInterface (ABC)
    ├── LocalFileStorage
    ├── S3FileStorage
    ├── AzureFileStorage
    └── GCPFileStorage

FileManager
    ├── uses: FileStorageInterface
    ├── uses: PathSanitizer
    ├── uses: FileValidator
    └── uses: MetadataManager

URLProxyManager
    ├── uses: GraphContext
    └── manages: URLProxy (Object)

FileMetadata (Node)
    ├── file_path: str
    ├── original_name: str
    ├── content_type: str
    ├── size_bytes: int
    └── checksum: str

URLProxy (Object)
    ├── code: str
    ├── file_path: str
    ├── expires_at: Optional[str]
    └── access_count: int

StorageConfig (BaseModel)
    ├── provider: str
    ├── security: SecurityConfig
    └── limits: ResourceLimits
```

### 5.2 Key Relationships

| Component | Depends On | Relationship |
|-----------|------------|--------------|
| `FileManager` | `FileStorageInterface` | Composition |
| `FileManager` | `PathSanitizer` | Uses |
| `FileManager` | `MetadataManager` | Uses |
| `URLProxyManager` | `GraphContext` | Composition |
| `URLProxy` | `Object` | Inheritance |
| `FileMetadata` | `Node` | Inheritance |
| `StorageEndpoints` | `FileManager` | Dependency Injection |
| `StorageEndpoints` | `URLProxyManager` | Dependency Injection |

---

## 6. API Specification

### 6.1 RESTful Endpoints

#### 6.1.1 File Operations

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `/api/files/upload` | POST | Upload file | Yes |
| `/api/files/{path:path}` | GET | Download/stream file | Optional |
| `/api/files/{path:path}` | DELETE | Delete file | Yes |
| `/api/files/{path:path}/metadata` | GET | Get file metadata | Optional |
| `/api/files/list` | GET | List files | Yes |

#### 6.1.2 URL Proxy Operations

| Endpoint | Method | Purpose | Auth Required |
|----------|--------|---------|---------------|
| `/api/proxy/create` | POST | Create short URL | Yes |
| `/p/{code}` | GET | Access via proxy | No |
| `/api/proxy/{code}` | DELETE | Delete proxy | Yes |
| `/api/proxy/{code}/info` | GET | Get proxy info | Yes |

### 6.2 Request/Response Models

#### 6.2.1 Upload Request

```python
# jvspatial/storage/models/requests.py

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field
from fastapi import UploadFile


class FileUploadRequest(BaseModel):
    """File upload request model."""

    file: UploadFile = Field(..., description="File to upload")
    path: Optional[str] = Field(
        None,
        description="Target path (auto-generated if not provided)"
    )
    create_proxy: bool = Field(
        False,
        description="Create short URL proxy"
    )
    proxy_ttl_hours: Optional[int] = Field(
        24,
        description="Proxy TTL in hours",
        ge=1,
        le=720  # 30 days max
    )
    metadata: Optional[Dict[str, Any]] = Field(
        None,
        description="Additional file metadata"
    )


class ProxyCreateRequest(BaseModel):
    """URL proxy creation request."""

    file_path: str = Field(..., description="File path to proxy")
    ttl_hours: Optional[int] = Field(
        24,
        description="Time-to-live in hours"
    )
    max_accesses: Optional[int] = Field(
        None,
        description="Maximum number of accesses"
    )
```

#### 6.2.2 Response Models

```python
# jvspatial/storage/models/responses.py

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class FileUploadResponse(BaseModel):
    """File upload response."""

    success: bool
    file_path: str
    file_url: str
    proxy_code: Optional[str] = None
    proxy_url: Optional[str] = None
    metadata: Dict[str, Any]
    message: str


class ProxyCreateResponse(BaseModel):
    """Proxy creation response."""

    success: bool
    code: str
    url: str
    file_path: str
    expires_at: Optional[str] = None
    message: str


class FileInfoResponse(BaseModel):
    """File information response."""

    file_path: str
    original_name: str
    content_type: str
    size_bytes: int
    checksum: str
    created_at: str
    last_accessed: Optional[str] = None
```

### 6.3 Error Responses

```python
# Standard error response format
{
    "error": "PathTraversalError",
    "message": "Path traversal attempt detected",
    "details": {
        "path": "../../../etc/passwd",
        "sanitized": "etc/passwd"
    },
    "status_code": 400
}
```

---

## 7. Security Architecture

### 7.1 Multi-Layer Security Model

```
┌─────────────────────────────────────────────────┐
│         Layer 1: Input Validation               │
│  • Path sanitization                            │
│  • Filename validation                          │
│  • File type checking                           │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────┐
│         Layer 2: Access Control                 │
│  • Authentication verification                  │
│  • Permission checking                          │
│  • Rate limiting                                │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────┐
│         Layer 3: Resource Management            │
│  • Size limits                                  │
│  • Quota enforcement                            │
│  • Disk space monitoring                        │
└────────────────┬────────────────────────────────┘
                 │
┌────────────────┴────────────────────────────────┐
│         Layer 4: Storage Security               │
│  • Encrypted storage (optional)                 │
│  • Checksum verification                        │
│  • Signed URLs                                  │
└─────────────────────────────────────────────────┘
```

### 7.2 Path Traversal Prevention

**Strategy:** Multi-stage validation and sanitization

1. **Input Sanitization:**
   - Remove null bytes and dangerous characters
   - Normalize path using `os.path.normpath()`
   - Check for `..` sequences

2. **Pattern Matching:**
   - Whitelist safe characters: `[a-zA-Z0-9_\-\.]`
   - Blacklist dangerous patterns: `..`, `~`, `$`, backticks, pipes

3. **Path Resolution:**
   - Resolve to absolute path using `Path.resolve()`
   - Verify resolved path is within base directory
   - Use `Path.relative_to()` for validation

4. **Component Validation:**
   - Validate each path component separately
   - Check maximum path depth
   - Enforce filename length limits

### 7.3 File Validation

```python
# jvspatial/storage/security/validators.py

from typing import Set, Optional
import magic  # python-magic for MIME detection


class FileValidator:
    """Comprehensive file validation."""

    # Allowed MIME types (example - configure per deployment)
    ALLOWED_MIME_TYPES: Set[str] = {
        'image/jpeg',
        'image/png',
        'image/gif',
        'image/webp',
        'application/pdf',
        'text/plain',
        'text/csv',
        'application/json',
        # Add more as needed
    }

    # Blocked MIME types (executables, scripts)
    BLOCKED_MIME_TYPES: Set[str] = {
        '

---

## Appendix A: Code Examples

### A.1 Complete Path Sanitizer Implementation

```python
# Example usage of PathSanitizer
from jvspatial.storage.security import PathSanitizer

sanitizer = PathSanitizer()

# Safe path
safe_path = sanitizer.sanitize_path("documents/report.pdf", base_dir="/var/files")
# Result: "documents/report.pdf"

# Dangerous path - raises PathTraversalError
try:
    sanitizer.sanitize_path("../../etc/passwd", base_dir="/var/files")
except PathTraversalError as e:
    print(f"Blocked: {e}")
```

### A.2 File Manager Usage

```python
# Example file upload with validation
from jvspatial.storage import FileManager

async def upload_file(file_content: bytes, filename: str):
    manager = FileManager(context=ctx, storage=storage)

    result = await manager.save_file(
        file_path=f"uploads/{filename}",
        content=file_content,
        metadata={
            "uploaded_by": "user123",
            "category": "documents"
        }
    )

    return result
```

## Appendix B: Test Strategy

### B.1 Security Tests

```python
# Test path traversal prevention
async def test_path_traversal_blocked():
    dangerous_paths = [
        "../../../etc/passwd",
        "..\\..\\windows\\system32",
        "/etc/shadow",
        "~/.ssh/id_rsa",
        "file|cat /etc/passwd"
    ]

    for path in dangerous_paths:
        with pytest.raises(PathTraversalError):
            sanitizer.sanitize_path(path)
```

### B.2 Performance Benchmarks

Target metrics:
- File upload (10MB): <2 seconds
- File download (10MB): <1 second
- Metadata retrieval: <50ms
- Proxy creation: <100ms
- Concurrent uploads (100): <30 seconds

## Appendix C: References

- OWASP File Upload Security: https://owasp.org/www-community/vulnerabilities/Unrestricted_File_Upload
- CWE-22 Path Traversal: https://cwe.mitre.org/data/definitions/22.html
- FastAPI File Uploads: https://fastapi.tiangolo.com/tutorial/request-files/
- MongoDB Best Practices: https://www.mongodb.com/docs/manual/administration/production-notes/
- AWS S3 Best Practices: https://docs.aws.amazon.com/AmazonS3/latest/userguide/security-best-practices.html

---

**Document Version:** 1.0
**Last Updated:** 2025-10-05
**Next Review:** 2025-10-12
**Status:** Ready for Implementation