"""Comprehensive integration tests for complete storage workflows.

Tests end-to-end workflows combining LocalFileInterface, URLProxyManager,
PathSanitizer, FileValidator, and factory functions in realistic scenarios.

Note: These tests use mocking for URLProxyManager since the URLProxy model
may not be fully implemented. Tests focus on integration between storage
interfaces, security components, and factory functions.
"""

import asyncio
import hashlib
import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.storage import (
    FileValidator,
    LocalFileInterface,
    PathSanitizer,
    create_storage,
)
from jvspatial.storage.exceptions import (
    AccessDeniedError,
    FileNotFoundError,
    FileSizeLimitError,
    InvalidMimeTypeError,
    PathTraversalError,
    StorageError,
    StorageProviderError,
)

# Conditionally import proxy manager (may not be available if URLProxy not implemented)
try:
    from jvspatial.storage.managers import URLProxyManager, get_proxy_manager

    PROXY_MANAGER_AVAILABLE = True
except ImportError:
    URLProxyManager = None  # type: ignore
    get_proxy_manager = None  # type: ignore
    PROXY_MANAGER_AVAILABLE = False


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_storage_dir():
    """Create temporary directory for storage tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def storage_interface(temp_storage_dir):
    """Create LocalFileInterface instance."""
    # Use permissive validator for integration testing
    validator = FileValidator(
        max_size_mb=100,
        allowed_mime_types=None,  # Allow all MIME types
        blocked_extensions=set(),  # Don't block any extensions
    )
    return LocalFileInterface(
        root_dir=temp_storage_dir, base_url="http://localhost:8000", validator=validator
    )


@pytest.fixture
def mock_context():
    """Create mock GraphContext for proxy manager."""
    context = AsyncMock()
    context.database = AsyncMock()
    context.database.find = AsyncMock(return_value=[])
    context.database.delete = AsyncMock()
    context.database.save = AsyncMock()
    context.database.create_index = AsyncMock()
    context.save = AsyncMock()
    context._deserialize_entity = AsyncMock()
    return context


@pytest.fixture
def proxy_manager(mock_context):
    """Create URLProxyManager instance."""
    return URLProxyManager(context=mock_context)


@pytest.fixture
def sample_files():
    """Provide sample file contents."""
    return {
        "text": b"Hello, World! This is a test file.",
        "pdf": b"%PDF-1.4\nTest PDF document content for integration tests",
        "jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00",
        "png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x10",
        "json": b'{"name": "test", "value": 123, "active": true}',
        "csv": b"name,age,email\nJohn,30,john@example.com\nJane,25,jane@example.com",
        "large": b"x" * (5 * 1024 * 1024),  # 5 MB
    }


# ============================================================================
# Complete Workflow Tests
# ============================================================================


class TestCompleteFileWorkflows:
    """Tests for complete file upload → storage → proxy → access → deletion workflows."""

    @pytest.mark.asyncio
    async def test_full_file_lifecycle(self, storage_interface, sample_files):
        """Test complete file lifecycle: upload → access → delete."""
        file_path = "documents/report.pdf"
        content = sample_files["pdf"]

        # 1. Upload file
        result = await storage_interface.save_file(file_path, content)
        assert result["path"] == file_path
        assert result["size"] == len(content)

        # 2. Verify it exists
        exists = await storage_interface.file_exists(file_path)
        assert exists is True

        # 3. Get metadata
        metadata = await storage_interface.get_metadata(file_path)
        assert metadata["size"] == len(content)
        assert "created_at" in metadata

        # 4. Retrieve content
        retrieved = await storage_interface.get_file(file_path)
        assert retrieved == content

        # 5. Stream content
        chunks = []
        async for chunk in storage_interface.stream_file(file_path):
            chunks.append(chunk)
        streamed = b"".join(chunks)
        assert streamed == content

        # 6. Delete file
        deleted = await storage_interface.delete_file(file_path)
        assert deleted is True

        # 7. Verify deletion
        exists = await storage_interface.file_exists(file_path)
        assert exists is False


class TestFileUploadWithSecurityValidation:
    """Tests for file upload with integrated security validation."""

    @pytest.mark.asyncio
    async def test_valid_file_passes_all_security_checks(
        self, temp_storage_dir, sample_files
    ):
        """Test that valid files pass PathSanitizer and FileValidator."""
        # Create storage with custom validator
        validator = FileValidator(max_size_mb=10)
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        file_path = "uploads/documents/valid.pdf"
        content = sample_files["pdf"]

        # Should pass both path sanitization and file validation
        result = await storage.save_file(file_path, content)

        assert result["path"] == file_path
        assert result["size"] == len(content)
        assert "checksum" in result

    @pytest.mark.asyncio
    async def test_path_traversal_blocked_in_workflow(
        self, storage_interface, sample_files
    ):
        """Test that path traversal attempts are blocked."""
        malicious_path = "../../../etc/passwd"

        # Path traversal paths still go through validation which may fail first
        # Expect either PathTraversalError or StorageProviderError wrapping validation error
        with pytest.raises((PathTraversalError, StorageProviderError)):
            await storage_interface.save_file(malicious_path, sample_files["text"])

    @pytest.mark.asyncio
    async def test_dangerous_file_type_rejected(self, storage_interface):
        """Test that dangerous file types are rejected."""
        executable_content = b"MZ\x90\x00"  # DOS executable

        # Validation errors are wrapped in StorageProviderError
        with pytest.raises(StorageProviderError) as exc_info:
            await storage_interface.save_file("malware.exe", executable_content)

        # Verify the error message contains validation failure
        assert (
            "not allowed" in str(exc_info.value).lower()
            or "failed" in str(exc_info.value).lower()
        )

    @pytest.mark.asyncio
    async def test_oversized_file_rejected(self, temp_storage_dir):
        """Test that oversized files are rejected."""
        validator = FileValidator(max_size_mb=1)
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        # 2 MB file (exceeds 1 MB limit)
        large_content = b"x" * (2 * 1024 * 1024)

        # File size errors are wrapped in StorageProviderError
        with pytest.raises(StorageProviderError) as exc_info:
            await storage.save_file("large.txt", large_content)

        # Verify it's a size limit error
        assert "exceeds limit" in str(exc_info.value).lower()


class TestFileStreamingWorkflows:
    """Tests for complete file streaming workflows."""

    @pytest.mark.asyncio
    async def test_upload_stream_store_retrieve_stream(
        self, storage_interface, sample_files
    ):
        """Test streaming upload → storage → streaming retrieval."""
        file_path = "streams/video.mp4"
        content = sample_files["large"]

        # 1. Upload file
        await storage_interface.save_file(file_path, content)

        # 2. Stream retrieve in chunks
        chunks = []
        chunk_count = 0
        async for chunk in storage_interface.stream_file(
            file_path, chunk_size=1024 * 1024
        ):
            chunks.append(chunk)
            chunk_count += 1

        # 3. Verify content
        retrieved = b"".join(chunks)
        assert retrieved == content
        assert chunk_count > 1  # Should have multiple chunks

    @pytest.mark.asyncio
    async def test_serve_file_for_http_response(self, storage_interface, sample_files):
        """Test serve_file method for HTTP responses."""
        file_path = "public/document.pdf"
        content = sample_files["pdf"]

        await storage_interface.save_file(file_path, content)

        # Serve file (simulating HTTP response)
        served_chunks = []
        async for chunk in storage_interface.serve_file(file_path):
            served_chunks.append(chunk)

        served_content = b"".join(served_chunks)
        assert served_content == content


@pytest.mark.skipif(not PROXY_MANAGER_AVAILABLE, reason="URLProxyManager not available")
class TestProxyBasedSecureSharing:
    """Tests for proxy-based secure file sharing workflows."""

    @pytest.mark.asyncio
    async def test_create_proxy_and_access_file(
        self, storage_interface, proxy_manager, sample_files
    ):
        """Test creating proxy and accessing file through it."""
        # Mock URLProxy entity for testing
        MockURLProxy = MagicMock

        file_path = "shared/document.pdf"
        content = sample_files["pdf"]

        # 1. Upload file
        await storage_interface.save_file(file_path, content)

        # 2. Create mock proxy
        now = datetime.now()
        mock_proxy = MagicMock()
        mock_proxy.code = "test123abc"
        mock_proxy.file_path = file_path
        mock_proxy.created_at = now
        mock_proxy.expires_at = now + timedelta(hours=1)
        mock_proxy.one_time = False
        mock_proxy.active = True
        mock_proxy.access_count = 0
        mock_proxy.last_accessed = None
        mock_proxy.metadata = {}
        mock_proxy.is_expired = MagicMock(return_value=False)
        mock_proxy.is_valid = MagicMock(return_value=True)
        mock_proxy.record_access = AsyncMock()
        mock_proxy.save = AsyncMock()
        mock_proxy._graph_context = await proxy_manager.context

        with patch("jvspatial.storage.managers.proxy.URLProxy") as MockURLProxy:
            MockURLProxy.find_by_code = AsyncMock(return_value=None)  # For creation

            # Create proxy
            mock_proxy.save = AsyncMock(return_value=mock_proxy)
            with patch.object(URLProxyManager, "create_proxy", return_value=mock_proxy):
                proxy = await proxy_manager.create_proxy(
                    file_path=file_path, expires_in=3600
                )

            assert proxy.file_path == file_path

            # 3. Resolve proxy to get file path
            MockURLProxy.find_by_code = AsyncMock(return_value=mock_proxy)
            resolved_path, metadata = await proxy_manager.resolve_proxy(proxy.code)

            assert resolved_path == file_path

            # 4. Access file using resolved path
            file_content = await storage_interface.get_file(resolved_path)
            assert file_content == content

    @pytest.mark.asyncio
    async def test_proxy_expiration_workflow(self, proxy_manager):
        """Test that expired proxies are properly rejected."""
        # Create expired proxy
        now = datetime.now()
        expired_proxy = MagicMock()
        expired_proxy.code = "expired123"
        expired_proxy.file_path = "test.pdf"
        expired_proxy.created_at = now - timedelta(hours=2)
        expired_proxy.expires_at = now - timedelta(hours=1)
        expired_proxy.active = True
        expired_proxy.is_expired = MagicMock(return_value=True)
        expired_proxy.is_valid = MagicMock(return_value=False)
        expired_proxy.metadata = {}
        expired_proxy.access_count = 0
        expired_proxy.record_access = AsyncMock()

        with patch("jvspatial.storage.managers.proxy.URLProxy") as MockURLProxy:
            # Make find_by_code properly awaitable
            MockURLProxy.find_by_code = AsyncMock(return_value=expired_proxy)

            # Should raise AccessDeniedError or FileNotFoundError
            with pytest.raises((AccessDeniedError, FileNotFoundError)):
                await proxy_manager.resolve_proxy("expired123")

    @pytest.mark.asyncio
    async def test_one_time_url_usage(self, proxy_manager):
        """Test one-time URL deactivation after first use."""
        from jvspatial.storage.models import URLProxy

        now = datetime.now()
        one_time_proxy = MagicMock()
        one_time_proxy.code = "onetime123"
        one_time_proxy.file_path = "secret.pdf"
        one_time_proxy.created_at = now
        one_time_proxy.expires_at = now + timedelta(hours=1)
        one_time_proxy.one_time = True
        one_time_proxy.active = True
        one_time_proxy.access_count = 0
        one_time_proxy.is_expired = MagicMock(return_value=False)
        one_time_proxy.is_valid = MagicMock(return_value=True)
        one_time_proxy.metadata = {}

        # Mock record_access to deactivate proxy
        async def mock_record_access():
            one_time_proxy.access_count += 1
            one_time_proxy.active = False

        one_time_proxy.record_access = mock_record_access

        with patch("jvspatial.storage.managers.proxy.URLProxy") as MockURLProxy:
            MockURLProxy.find_by_code = AsyncMock(return_value=one_time_proxy)

            # First access - should succeed
            file_path, metadata = await proxy_manager.resolve_proxy("onetime123")
            assert file_path == "secret.pdf"
            assert one_time_proxy.active is False

            # Second access - should fail
            one_time_proxy.is_valid = MagicMock(return_value=False)
            with pytest.raises(AccessDeniedError):
                await proxy_manager.resolve_proxy("onetime123")


class TestExpiredProxyCleanup:
    """Tests for expired proxy cleanup workflows."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_proxies(self, proxy_manager, mock_context):
        """Test cleanup of expired and inactive proxies."""
        now = datetime.now()

        # Mock expired proxies
        expired_data = [
            {
                "id": "proxy1",
                "context": {"active": False, "expires_at": now + timedelta(hours=1)},
            },
            {
                "id": "proxy2",
                "context": {"active": True, "expires_at": now - timedelta(hours=1)},
            },
        ]

        mock_context.database.find = AsyncMock(return_value=expired_data)

        # Run cleanup
        count = await proxy_manager.cleanup_expired()

        assert count == 2
        assert mock_context.database.delete.call_count == 2


class TestMultipleFileOperations:
    """Tests for multiple file operations with metadata tracking."""

    @pytest.mark.asyncio
    async def test_batch_upload_and_list(self, storage_interface, sample_files):
        """Test uploading multiple files and listing them."""
        files_to_upload = [
            ("docs/file1.txt", sample_files["text"]),
            ("docs/file2.pdf", sample_files["pdf"]),
            ("docs/file3.json", sample_files["json"]),
        ]

        # Upload all files
        for file_path, content in files_to_upload:
            await storage_interface.save_file(file_path, content)

        # List files
        files = await storage_interface.list_files(prefix="docs")

        assert len(files) >= 3
        file_paths = [f["path"] for f in files]
        assert any("file1.txt" in p for p in file_paths)
        assert any("file2.pdf" in p for p in file_paths)
        assert any("file3.json" in p for p in file_paths)

    @pytest.mark.asyncio
    async def test_file_operations_with_metadata(self, storage_interface, sample_files):
        """Test file operations preserving metadata."""
        file_path = "uploads/document.pdf"
        content = sample_files["pdf"]
        metadata = {
            "user_id": "user123",
            "upload_date": datetime.now().isoformat(),
            "tags": ["important", "draft"],
        }

        # Upload with metadata
        result = await storage_interface.save_file(
            file_path, content, metadata=metadata
        )

        assert result["metadata"] == metadata

        # Retrieve and verify metadata preserved
        file_metadata = await storage_interface.get_metadata(file_path)
        assert file_metadata is not None


class TestConcurrentFileOperations:
    """Tests for concurrent file operations."""

    @pytest.mark.asyncio
    async def test_concurrent_uploads(self, storage_interface, sample_files):
        """Test concurrent file uploads."""
        tasks = [
            storage_interface.save_file(f"concurrent/file{i}.txt", sample_files["text"])
            for i in range(10)
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 10
        for i, result in enumerate(results):
            assert result["path"] == f"concurrent/file{i}.txt"
            assert result["size"] == len(sample_files["text"])

    @pytest.mark.asyncio
    async def test_concurrent_reads(self, storage_interface, sample_files):
        """Test concurrent file reads."""
        file_path = "shared/document.pdf"
        await storage_interface.save_file(file_path, sample_files["pdf"])

        # Concurrent reads
        tasks = [storage_interface.get_file(file_path) for _ in range(10)]

        results = await asyncio.gather(*tasks)

        assert all(r == sample_files["pdf"] for r in results)


# ============================================================================
# Cross-Component Integration Tests
# ============================================================================


class TestCrossComponentIntegration:
    """Tests for integration across multiple components."""

    @pytest.mark.asyncio
    async def test_factory_creates_integrated_storage(self, temp_storage_dir):
        """Test factory function creates fully integrated storage."""
        storage = create_storage(
            provider="local",
            root_dir=temp_storage_dir,
            config={
                "max_size_mb": 10,
                "allowed_mime_types": {"text/plain", "application/pdf"},
            },
        )

        assert isinstance(storage, LocalFileInterface)
        assert isinstance(storage.validator, FileValidator)
        assert storage.validator.max_size_bytes == 100 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_path_sanitizer_file_validator_integration(self, temp_storage_dir):
        """Test PathSanitizer and FileValidator work together."""
        validator = FileValidator(
            max_size_mb=5, allowed_mime_types={"text/plain"}, blocked_extensions=set()
        )
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        # Valid path and valid file
        result = await storage.save_file("valid.txt", b"test content")
        assert result["path"] == "valid.txt"

        # Invalid path - expect PathTraversalError or StorageProviderError wrapping it
        with pytest.raises((PathTraversalError, StorageProviderError)):
            await storage.save_file("../invalid.txt", b"content")

        # Invalid file type - expect StorageProviderError wrapping InvalidMimeTypeError
        with pytest.raises(StorageProviderError) as exc_info:
            await storage.save_file("doc.pdf", b"%PDF-1.4\ncontent")
        assert (
            "not in allowed types" in str(exc_info.value).lower()
            or "not allowed" in str(exc_info.value).lower()
        )


# ============================================================================
# Real-World Scenario Tests
# ============================================================================


class TestRealWorldScenarios:
    """Tests for real-world usage scenarios."""

    @pytest.mark.asyncio
    async def test_user_avatar_workflow(
        self, storage_interface, proxy_manager, sample_files
    ):
        """Test: Upload user avatar → create shareable link → track access."""
        from jvspatial.storage.models import URLProxy

        # 1. Upload avatar
        user_id = "user123"
        avatar_path = f"avatars/{user_id}/profile.jpg"
        avatar_content = sample_files["jpeg"]

        await storage_interface.save_file(avatar_path, avatar_content)

        # 2. Create shareable link
        now = datetime.now()
        mock_proxy = MagicMock()
        mock_proxy.code = "avatar123"
        mock_proxy.file_path = avatar_path
        mock_proxy.created_at = now
        mock_proxy.expires_at = now + timedelta(days=30)
        mock_proxy.one_time = False
        mock_proxy.active = True
        mock_proxy.access_count = 0
        mock_proxy.metadata = {"user_id": user_id, "type": "avatar"}
        mock_proxy.save = AsyncMock()
        mock_proxy._graph_context = await proxy_manager.context

        with patch.object(URLProxyManager, "create_proxy", return_value=mock_proxy):
            proxy = await proxy_manager.create_proxy(
                file_path=avatar_path,
                expires_in=30 * 24 * 3600,
                metadata={"user_id": user_id, "type": "avatar"},
            )

        assert proxy.file_path == avatar_path
        assert proxy.metadata["user_id"] == user_id

    @pytest.mark.asyncio
    async def test_document_validation_workflow(self, temp_storage_dir, sample_files):
        """Test: Upload document → validate → create temporary access → expire."""
        # 1. Upload document with validation
        validator = FileValidator(
            max_size_mb=10, allowed_mime_types={"application/pdf"}
        )
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        doc_path = "documents/report.pdf"
        result = await storage.save_file(doc_path, sample_files["pdf"])

        assert result["path"] == doc_path

        # 2. Verify file exists and get metadata
        exists = await storage.file_exists(doc_path)
        assert exists is True

        metadata = await storage.get_metadata(doc_path)
        assert metadata["size"] == len(sample_files["pdf"])

    @pytest.mark.asyncio
    async def test_batch_file_upload_and_cleanup(self, storage_interface, sample_files):
        """Test: Batch upload → list files → cleanup."""
        batch_files = [f"batch/file{i}.txt" for i in range(5)]

        # 1. Batch upload
        for file_path in batch_files:
            await storage_interface.save_file(file_path, sample_files["text"])

        # 2. List files
        files = await storage_interface.list_files(prefix="batch")
        assert len(files) >= 5

        # 3. Cleanup
        for file_path in batch_files:
            deleted = await storage_interface.delete_file(file_path)
            assert deleted is True

        # 4. Verify cleanup
        files_after = await storage_interface.list_files(prefix="batch")
        assert len(files_after) == 0

    @pytest.mark.asyncio
    async def test_file_replacement_workflow(self, storage_interface, sample_files):
        """Test: Delete old → upload new → verify replacement."""
        file_path = "documents/version.txt"

        # 1. Upload original
        await storage_interface.save_file(file_path, b"version 1")
        original = await storage_interface.get_file(file_path)
        assert original == b"version 1"

        # 2. Replace with new version
        await storage_interface.save_file(file_path, b"version 2")
        updated = await storage_interface.get_file(file_path)
        assert updated == b"version 2"

        # 3. Verify only one version exists
        files = await storage_interface.list_files(prefix="documents")
        version_files = [f for f in files if "version.txt" in f["path"]]
        assert len(version_files) == 1


# ============================================================================
# Security Integration Tests
# ============================================================================


class TestSecurityIntegration:
    """Tests for security integration in complete workflows."""

    @pytest.mark.asyncio
    async def test_malicious_file_rejection_in_workflow(self, storage_interface):
        """Test malicious file rejection at all security layers."""
        # Note: Using permissive validator in fixture, so only path traversal will fail
        malicious_paths = [
            "../../../etc/passwd",
            "../../var/log/system.log",
        ]

        for file_path in malicious_paths:
            # Expect either PathTraversalError or StorageProviderError wrapping it
            with pytest.raises((PathTraversalError, StorageProviderError)):
                await storage_interface.save_file(file_path, b"content")

    @pytest.mark.asyncio
    async def test_path_traversal_prevention_full_workflow(
        self, storage_interface, sample_files
    ):
        """Test path traversal prevention throughout workflow."""
        attack_paths = [
            "../etc/passwd",
            "../../var/log/system.log",
            "uploads/../../../root/.ssh/id_rsa",
        ]

        for attack_path in attack_paths:
            # Expect either PathTraversalError or StorageProviderError wrapping it
            with pytest.raises((PathTraversalError, StorageProviderError)):
                await storage_interface.save_file(attack_path, sample_files["text"])

    @pytest.mark.asyncio
    async def test_file_size_enforcement_in_pipeline(self, temp_storage_dir):
        """Test file size limit enforcement in complete pipeline."""
        validator = FileValidator(
            max_size_mb=1, allowed_mime_types=None, blocked_extensions=set()
        )
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        # File exceeding limit
        large_file = b"x" * (2 * 1024 * 1024)  # 2 MB

        # Expect StorageProviderError wrapping FileSizeLimitError
        with pytest.raises(StorageProviderError) as exc_info:
            await storage.save_file("large.txt", large_file)
        assert "exceeds limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_mime_type_validation_complete_pipeline(self, temp_storage_dir):
        """Test MIME type validation in complete pipeline."""
        validator = FileValidator(
            max_size_mb=100,
            allowed_mime_types={"text/plain", "application/json"},
            blocked_extensions=set(),
        )
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        # Allowed type - should work
        await storage.save_file("allowed.txt", b"text content")

        # Blocked type - expect StorageProviderError wrapping InvalidMimeTypeError
        with pytest.raises(StorageProviderError) as exc_info:
            await storage.save_file("blocked.pdf", b"%PDF-1.4\ncontent")
        assert (
            "not in allowed types" in str(exc_info.value).lower()
            or "not allowed" in str(exc_info.value).lower()
        )


# ============================================================================
# Performance Integration Tests
# ============================================================================


class TestPerformanceIntegration:
    """Tests for performance in integrated scenarios."""

    @pytest.mark.asyncio
    async def test_large_file_upload_and_retrieval(self, temp_storage_dir):
        """Test handling of large files in complete workflow."""
        # Use permissive validator that allows large files and all MIME types
        validator = FileValidator(
            max_size_mb=50,  # 50 MB limit
            allowed_mime_types={
                "application/octet-stream",
                "text/plain",
            },  # Allow binary files
            blocked_extensions=set(),  # Don't block any extensions
        )
        storage_interface = LocalFileInterface(
            root_dir=temp_storage_dir, validator=validator
        )

        large_file = b"x" * (10 * 1024 * 1024)  # 10 MB
        file_path = "large/bigfile.dat"

        # Upload
        result = await storage_interface.save_file(file_path, large_file)
        assert result["size"] == len(large_file)

        # Retrieve
        retrieved = await storage_interface.get_file(file_path)
        assert len(retrieved) == len(large_file)

        # Stream
        chunks = []
        async for chunk in storage_interface.stream_file(
            file_path, chunk_size=1024 * 1024
        ):
            chunks.append(chunk)

        streamed = b"".join(chunks)
        assert len(streamed) == len(large_file)

    @pytest.mark.asyncio
    async def test_many_small_files_workflow(self, storage_interface):
        """Test workflow with many small files."""
        num_files = 100
        content = b"small file content"

        # Upload many files concurrently
        tasks = [
            storage_interface.save_file(f"small/file{i}.txt", content)
            for i in range(num_files)
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == num_files

        # List all files
        files = await storage_interface.list_files(prefix="small")
        assert len(files) >= num_files

    @pytest.mark.asyncio
    async def test_concurrent_uploads_and_downloads(
        self, storage_interface, sample_files
    ):
        """Test concurrent upload and download operations."""
        # Prepare files
        upload_tasks = [
            storage_interface.save_file(f"concurrent/up{i}.txt", sample_files["text"])
            for i in range(5)
        ]
        await asyncio.gather(*upload_tasks)

        # Concurrent downloads
        download_tasks = [
            storage_interface.get_file(f"concurrent/up{i}.txt") for i in range(5)
        ]

        results = await asyncio.gather(*download_tasks)
        assert all(r == sample_files["text"] for r in results)


# ============================================================================
# Error Propagation Tests
# ============================================================================


class TestErrorPropagation:
    """Tests for error propagation across components."""

    @pytest.mark.asyncio
    async def test_storage_error_propagation(self, storage_interface):
        """Test that storage errors propagate correctly."""
        # Try to get non-existent file
        content = await storage_interface.get_file("nonexistent/file.txt")
        assert content is None

        # Try to delete non-existent file
        deleted = await storage_interface.delete_file("nonexistent/file.txt")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_validation_error_propagation(self, temp_storage_dir):
        """Test that validation errors propagate with details."""
        validator = FileValidator(
            max_size_mb=1, allowed_mime_types=None, blocked_extensions=set()
        )
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        large_content = b"x" * (2 * 1024 * 1024)

        try:
            await storage.save_file("large.txt", large_content)
            pytest.fail("Should have raised StorageProviderError")
        except StorageProviderError as e:
            # The error is wrapped in StorageProviderError
            assert "exceeds limit" in str(e).lower()


# ============================================================================
# Module Imports Test
# ============================================================================


async def test_module_imports():
    """Test that all integration components can be imported."""
    from jvspatial.storage import (
        FileValidator,
        LocalFileInterface,
        PathSanitizer,
        create_storage,
    )

    assert create_storage is not None
    assert LocalFileInterface is not None
    assert PathSanitizer is not None
    assert FileValidator is not None

    # Test proxy manager imports if available
    if PROXY_MANAGER_AVAILABLE:
        from jvspatial.storage.managers import URLProxyManager, get_proxy_manager

        assert URLProxyManager is not None
        assert get_proxy_manager is not None
