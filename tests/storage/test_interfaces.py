"""Comprehensive test suite for storage interface implementations.

Tests LocalFileInterface and S3FileInterface with full coverage of all
methods, error handling, security integration, and edge cases.
"""

import asyncio
import hashlib
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from jvspatial.storage.exceptions import (
    AccessDeniedError,
    FileNotFoundError,
    FileSizeLimitError,
    InvalidMimeTypeError,
    PathTraversalError,
    StorageProviderError,
)
from jvspatial.storage.interfaces import (
    FileStorageInterface,
    LocalFileInterface,
    S3FileInterface,
)
from jvspatial.storage.security import FileValidator, PathSanitizer

# Check if boto3 is available for S3 tests
try:
    from jvspatial.storage.interfaces.s3 import HAS_BOTO3
except ImportError:
    HAS_BOTO3 = False

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def temp_storage_dir():
    """Create temporary directory for local storage tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def local_storage(temp_storage_dir):
    """Create LocalFileInterface instance for testing."""
    # Use permissive validator for testing
    validator = FileValidator(
        max_size_mb=100,
        allowed_mime_types=None,  # Allow all MIME types
        blocked_extensions=set(),  # Don't block any extensions
    )
    return LocalFileInterface(
        root_dir=temp_storage_dir, base_url="http://localhost:8000", validator=validator
    )


@pytest.fixture
def custom_validator():
    """Create FileValidator with custom settings."""
    return FileValidator(
        max_size_mb=5,
        allowed_mime_types={"text/plain", "application/pdf", "image/jpeg"},
    )


@pytest.fixture
def sample_files():
    """Provide sample file contents for testing."""
    return {
        "text": b"Hello, World! This is a text file.",
        "pdf": b"%PDF-1.4\nSample PDF content for testing",
        "jpeg": b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00",
        "png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
        "empty": b"",
        "large": b"x" * (1024 * 1024),  # 1 MB
        "json": b'{"key": "value", "number": 42}',
        "html": b"<!DOCTYPE html><html><body><h1>Test</h1></body></html>",
    }


@pytest.fixture
def mock_s3_client():
    """Create mock boto3 S3 client."""
    mock_client = MagicMock()

    # Mock successful operations by default
    mock_client.put_object.return_value = {"ETag": '"abc123"'}
    mock_client.get_object.return_value = {
        "Body": MagicMock(read=MagicMock(return_value=b"test content"))
    }
    mock_client.head_object.return_value = {
        "ContentLength": 12,
        "ContentType": "text/plain",
        "LastModified": datetime.now(),
        "ETag": '"abc123"',
    }
    mock_client.delete_object.return_value = {}
    mock_client.list_objects_v2.return_value = {
        "Contents": [
            {
                "Key": "test.txt",
                "Size": 12,
                "LastModified": datetime.now(),
                "ETag": '"abc123"',
            }
        ]
    }
    mock_client.generate_presigned_url.return_value = (
        "https://s3.amazonaws.com/bucket/file?signed=true"
    )

    return mock_client


# ============================================================================
# LocalFileInterface Tests
# ============================================================================


class TestLocalFileInterfaceInit:
    """Tests for LocalFileInterface initialization."""

    async def test_init_with_defaults(self, temp_storage_dir):
        """Test initialization with default settings."""
        storage = LocalFileInterface(root_dir=temp_storage_dir)

        assert storage.root_dir == Path(temp_storage_dir).resolve()
        assert storage.base_url is None
        assert isinstance(storage.validator, FileValidator)

    async def test_init_with_base_url(self, temp_storage_dir):
        """Test initialization with base URL."""
        storage = LocalFileInterface(
            root_dir=temp_storage_dir, base_url="http://example.com/"
        )

        assert storage.base_url == "http://example.com"

    async def test_init_with_custom_validator(self, temp_storage_dir, custom_validator):
        """Test initialization with custom validator."""
        storage = LocalFileInterface(
            root_dir=temp_storage_dir, validator=custom_validator
        )

        assert storage.validator == custom_validator

    async def test_init_creates_root_directory(self):
        """Test that root directory is created if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_root = os.path.join(tmpdir, "new_storage")
            storage = LocalFileInterface(root_dir=new_root, create_root=True)

            assert os.path.exists(new_root)

    async def test_init_fails_for_missing_directory(self):
        """Test that initialization fails if root doesn't exist and create_root=False."""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_root = os.path.join(tmpdir, "missing")

            with pytest.raises(StorageProviderError) as exc_info:
                LocalFileInterface(root_dir=missing_root, create_root=False)

            assert "does not exist" in str(exc_info.value).lower()


class TestLocalFileSaveOperations:
    """Tests for local file save operations."""

    @pytest.mark.asyncio
    async def test_save_simple_text_file(self, local_storage, sample_files):
        """Test saving a simple text file."""
        result = await local_storage.save_file("test.txt", sample_files["text"])

        assert result["path"] == "test.txt"
        assert result["size"] == len(sample_files["text"])
        assert "checksum" in result
        assert result["checksum"] == hashlib.md5(sample_files["text"]).hexdigest()

    @pytest.mark.asyncio
    async def test_save_pdf_file(self, local_storage, sample_files):
        """Test saving a PDF file."""
        result = await local_storage.save_file("document.pdf", sample_files["pdf"])

        assert result["path"] == "document.pdf"
        assert "storage_url" in result
        assert "document.pdf" in result["storage_url"]

    @pytest.mark.asyncio
    async def test_save_to_nested_directory(self, local_storage, sample_files):
        """Test saving file in nested directory."""
        result = await local_storage.save_file(
            "uploads/documents/report.pdf", sample_files["pdf"]
        )

        assert result["path"] == "uploads/documents/report.pdf"

        # Verify directory was created
        full_path = local_storage.root_dir / "uploads" / "documents"
        assert full_path.exists()

    @pytest.mark.asyncio
    async def test_save_with_metadata(self, local_storage, sample_files):
        """Test saving file with metadata."""
        metadata = {"user": "test_user", "tags": ["important", "draft"]}

        result = await local_storage.save_file(
            "test.txt", sample_files["text"], metadata=metadata
        )

        assert result["metadata"] == metadata

    @pytest.mark.asyncio
    async def test_save_empty_file(self, local_storage, sample_files):
        """Test saving an empty file."""
        result = await local_storage.save_file("empty.txt", sample_files["empty"])

        assert result["size"] == 0
        assert result["checksum"] == hashlib.md5(b"").hexdigest()

    @pytest.mark.asyncio
    async def test_save_large_file(self, local_storage, sample_files):
        """Test saving a large file."""
        result = await local_storage.save_file("large.txt", sample_files["large"])

        assert result["size"] == len(sample_files["large"])

    @pytest.mark.asyncio
    async def test_save_overwrites_existing(self, local_storage, sample_files):
        """Test that saving overwrites existing file."""
        # Save initial file
        await local_storage.save_file("test.txt", b"original content")

        # Overwrite with new content
        new_content = b"new content"
        result = await local_storage.save_file("test.txt", new_content)

        # Verify new content
        retrieved = await local_storage.get_file("test.txt")
        assert retrieved == new_content

    @pytest.mark.asyncio
    async def test_save_rejects_path_traversal(self, local_storage, sample_files):
        """Test that path traversal attempts are rejected."""
        # Path traversal errors are wrapped in StorageProviderError
        with pytest.raises((PathTraversalError, StorageProviderError)):
            await local_storage.save_file("../../../etc/passwd", sample_files["text"])

    @pytest.mark.asyncio
    async def test_save_validates_file_size(self, temp_storage_dir):
        """Test that file size validation works."""
        # Create storage with small size limit
        validator = FileValidator(
            max_size_mb=0.001,  # 1 KB limit
            allowed_mime_types=None,  # Allow all MIME types
            blocked_extensions=set(),  # Don't block any extensions
        )
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        # Try to save file larger than limit
        large_content = b"x" * 2048  # 2 KB
        # Size limit errors are wrapped in StorageProviderError
        with pytest.raises(StorageProviderError) as exc_info:
            await storage.save_file("large.txt", large_content)
        assert "exceeds limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_save_validates_mime_type(self, temp_storage_dir):
        """Test that MIME type validation works."""
        # Create storage that only allows text files
        validator = FileValidator(allowed_mime_types={"text/plain"})
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        # Try to save PDF (should fail) - wrapped in StorageProviderError
        with pytest.raises(StorageProviderError) as exc_info:
            await storage.save_file("doc.pdf", b"%PDF-1.4\ncontent")
        assert (
            "not in allowed types" in str(exc_info.value).lower()
            or "not allowed" in str(exc_info.value).lower()
        )


class TestLocalFileRetrievalOperations:
    """Tests for local file retrieval operations."""

    @pytest.mark.asyncio
    async def test_get_existing_file(self, local_storage, sample_files):
        """Test retrieving an existing file."""
        # Save file first
        await local_storage.save_file("test.txt", sample_files["text"])

        # Retrieve it
        content = await local_storage.get_file("test.txt")

        assert content == sample_files["text"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_file(self, local_storage):
        """Test retrieving a non-existent file returns None."""
        content = await local_storage.get_file("missing.txt")

        assert content is None

    @pytest.mark.asyncio
    async def test_get_file_from_nested_directory(self, local_storage, sample_files):
        """Test retrieving file from nested directory."""
        # Save file
        await local_storage.save_file("a/b/c/deep.txt", sample_files["text"])

        # Retrieve it
        content = await local_storage.get_file("a/b/c/deep.txt")

        assert content == sample_files["text"]

    @pytest.mark.asyncio
    async def test_file_exists_returns_true(self, local_storage, sample_files):
        """Test file_exists returns True for existing file."""
        await local_storage.save_file("test.txt", sample_files["text"])

        exists = await local_storage.file_exists("test.txt")

        assert exists is True

    @pytest.mark.asyncio
    async def test_file_exists_returns_false(self, local_storage):
        """Test file_exists returns False for non-existent file."""
        exists = await local_storage.file_exists("missing.txt")

        assert exists is False

    @pytest.mark.asyncio
    async def test_file_exists_false_for_directory(self, local_storage, sample_files):
        """Test file_exists returns False for directories."""
        # Create a file in a directory
        await local_storage.save_file("dir/file.txt", sample_files["text"])

        # Check if directory is reported as file (should be False)
        exists = await local_storage.file_exists("dir")

        assert exists is False


class TestLocalFileStreamingOperations:
    """Tests for local file streaming operations."""

    @pytest.mark.asyncio
    async def test_stream_file_chunks(self, local_storage, sample_files):
        """Test streaming file in chunks."""
        # Save a file
        await local_storage.save_file("large.txt", sample_files["large"])

        # Stream it
        chunks = []
        async for chunk in local_storage.stream_file("large.txt", chunk_size=1024):
            chunks.append(chunk)

        # Verify content
        streamed_content = b"".join(chunks)
        assert streamed_content == sample_files["large"]

    @pytest.mark.asyncio
    async def test_stream_nonexistent_file(self, local_storage):
        """Test streaming non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            async for chunk in local_storage.stream_file("missing.txt"):
                pass

    @pytest.mark.asyncio
    async def test_serve_file(self, local_storage, sample_files):
        """Test serving file for HTTP response."""
        await local_storage.save_file("test.txt", sample_files["text"])

        chunks = []
        async for chunk in local_storage.serve_file("test.txt"):
            chunks.append(chunk)

        content = b"".join(chunks)
        assert content == sample_files["text"]

    @pytest.mark.asyncio
    async def test_serve_nonexistent_file(self, local_storage):
        """Test serving non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            async for chunk in local_storage.serve_file("missing.txt"):
                pass


class TestLocalFileDeletionOperations:
    """Tests for local file deletion operations."""

    @pytest.mark.asyncio
    async def test_delete_existing_file(self, local_storage, sample_files):
        """Test deleting an existing file."""
        # Save file
        await local_storage.save_file("test.txt", sample_files["text"])

        # Delete it
        deleted = await local_storage.delete_file("test.txt")

        assert deleted is True

        # Verify it's gone
        exists = await local_storage.file_exists("test.txt")
        assert exists is False

    @pytest.mark.asyncio
    async def test_delete_nonexistent_file(self, local_storage):
        """Test deleting non-existent file returns False."""
        deleted = await local_storage.delete_file("missing.txt")

        assert deleted is False

    @pytest.mark.asyncio
    async def test_delete_rejects_path_traversal(self, local_storage):
        """Test that path traversal is rejected in delete."""
        with pytest.raises(PathTraversalError):
            await local_storage.delete_file("../../etc/passwd")


class TestLocalFileMetadataOperations:
    """Tests for local file metadata operations."""

    @pytest.mark.asyncio
    async def test_get_metadata_for_existing_file(self, local_storage, sample_files):
        """Test getting metadata for existing file."""
        await local_storage.save_file("test.txt", sample_files["text"])

        metadata = await local_storage.get_metadata("test.txt")

        assert metadata is not None
        assert metadata["size"] == len(sample_files["text"])
        assert "created_at" in metadata
        assert "modified_at" in metadata
        assert "content_type" in metadata

    @pytest.mark.asyncio
    async def test_get_metadata_for_nonexistent_file(self, local_storage):
        """Test getting metadata for non-existent file returns None."""
        metadata = await local_storage.get_metadata("missing.txt")

        assert metadata is None

    @pytest.mark.asyncio
    async def test_get_file_url_with_base_url(self, local_storage, sample_files):
        """Test generating file URL when base_url is configured."""
        await local_storage.save_file("test.txt", sample_files["text"])

        url = await local_storage.get_file_url("test.txt")

        assert url is not None
        assert "http://localhost:8000/files/test.txt" == url

    @pytest.mark.asyncio
    async def test_get_file_url_without_base_url(self, temp_storage_dir, sample_files):
        """Test that get_file_url returns None without base_url."""
        storage = LocalFileInterface(root_dir=temp_storage_dir)
        await storage.save_file("test.txt", sample_files["text"])

        url = await storage.get_file_url("test.txt")

        assert url is None

    @pytest.mark.asyncio
    async def test_get_file_url_for_nonexistent_file(self, local_storage):
        """Test getting URL for non-existent file returns None."""
        url = await local_storage.get_file_url("missing.txt")

        assert url is None


class TestLocalFileListingOperations:
    """Tests for local file listing operations."""

    @pytest.mark.asyncio
    async def test_list_all_files(self, local_storage, sample_files):
        """Test listing all files."""
        # Save multiple files
        await local_storage.save_file("file1.txt", sample_files["text"])
        await local_storage.save_file("file2.txt", sample_files["text"])
        await local_storage.save_file("dir/file3.txt", sample_files["text"])

        # List all files
        files = await local_storage.list_files()

        assert len(files) >= 3
        paths = [f["path"] for f in files]
        assert any("file1.txt" in p for p in paths)
        assert any("file2.txt" in p for p in paths)
        assert any("file3.txt" in p for p in paths)

    @pytest.mark.asyncio
    async def test_list_files_with_prefix(self, local_storage, sample_files):
        """Test listing files with prefix filter."""
        await local_storage.save_file("uploads/doc1.txt", sample_files["text"])
        await local_storage.save_file("uploads/doc2.txt", sample_files["text"])
        await local_storage.save_file("images/pic.jpg", sample_files["jpeg"])

        # List only uploads
        files = await local_storage.list_files(prefix="uploads")

        assert len(files) >= 2
        for file in files:
            assert "uploads" in file["path"]

    @pytest.mark.asyncio
    async def test_list_files_respects_max_results(self, local_storage, sample_files):
        """Test that max_results limits the number of results."""
        # Save multiple files
        for i in range(10):
            await local_storage.save_file(f"file{i}.txt", sample_files["text"])

        # List with limit
        files = await local_storage.list_files(max_results=5)

        assert len(files) <= 5

    @pytest.mark.asyncio
    async def test_list_empty_directory(self, local_storage):
        """Test listing files in empty directory."""
        files = await local_storage.list_files()

        assert isinstance(files, list)


class TestLocalFileStorageInfo:
    """Tests for local storage info operations."""

    @pytest.mark.asyncio
    async def test_get_storage_info(self, local_storage):
        """Test getting storage information."""
        info = await local_storage.get_storage_info()

        assert info["provider"] == "LocalFileInterface"
        assert info["supports_streaming"] is True
        assert info["supports_signed_urls"] is False
        assert info["supports_metadata"] is True
        assert "root_dir" in info


class TestLocalFileEdgeCases:
    """Tests for edge cases and special scenarios."""

    @pytest.mark.asyncio
    async def test_save_file_with_special_chars_in_name(self, local_storage):
        """Test saving file with allowed special characters."""
        content = b"test content"
        result = await local_storage.save_file("file-name_123.txt", content)

        assert result["path"] == "file-name_123.txt"

    @pytest.mark.asyncio
    async def test_concurrent_saves(self, local_storage, sample_files):
        """Test concurrent file saves don't interfere."""
        # Save multiple files concurrently
        tasks = [
            local_storage.save_file(f"file{i}.txt", sample_files["text"])
            for i in range(5)
        ]

        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        for i, result in enumerate(results):
            assert result["path"] == f"file{i}.txt"


# ============================================================================
# S3FileInterface Tests (with mocking)
# ============================================================================

# Skip all S3 tests if boto3 is not available
pytestmark = pytest.mark.skipif(
    not HAS_BOTO3, reason="boto3 is required for S3 storage tests"
)


class TestS3FileInterfaceInit:
    """Tests for S3FileInterface initialization."""

    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_init_with_bucket_name(self, mock_boto3):
        """Test initialization with bucket name."""
        mock_boto3.client.return_value = MagicMock()

        storage = S3FileInterface(bucket_name="test-bucket", region_name="us-west-2")

        assert storage.bucket_name == "test-bucket"
        assert storage.region_name == "us-west-2"

    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_init_without_bucket_raises_error(self, mock_boto3):
        """Test that initialization without bucket name raises error."""
        with pytest.raises(ValueError) as exc_info:
            S3FileInterface()

        assert "bucket_name is required" in str(exc_info.value)

    @patch.dict(
        os.environ,
        {
            "JVSPATIAL_S3_BUCKET_NAME": "env-bucket",
            "JVSPATIAL_S3_REGION_NAME": "eu-west-1",
            "JVSPATIAL_S3_ACCESS_KEY_ID": "test-key",
            "JVSPATIAL_S3_SECRET_ACCESS_KEY": "test-secret",  # pragma: allowlist secret
        },
    )
    @patch("jvspatial.storage.interfaces.s3.boto3")
    def test_init_from_environment_variables(self, mock_boto3):
        """Test initialization from environment variables."""
        mock_boto3.client.return_value = MagicMock()

        storage = S3FileInterface()

        assert storage.bucket_name == "env-bucket"
        assert storage.region_name == "eu-west-1"
        assert storage.access_key_id == "test-key"  # pragma: allowlist secret
        assert storage.secret_access_key == "test-secret"  # pragma: allowlist secret

    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_init_with_custom_validator(self, mock_boto3, custom_validator):
        """Test initialization with custom validator."""
        mock_boto3.client.return_value = MagicMock()

        storage = S3FileInterface(bucket_name="test-bucket", validator=custom_validator)

        assert storage.validator == custom_validator

    async def test_init_fails_without_boto3(self):
        """Test that initialization fails if boto3 not installed."""
        # Since boto3 is now imported at module level, we need to patch HAS_BOTO3
        with patch("jvspatial.storage.interfaces.s3.HAS_BOTO3", False):
            with pytest.raises(ImportError) as exc_info:
                S3FileInterface(bucket_name="test-bucket")
            assert "boto3 is required" in str(exc_info.value)


class TestS3FileSaveOperations:
    """Tests for S3 file save operations."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_save_file_to_s3(self, mock_boto3, sample_files):
        """Test saving file to S3."""
        mock_client = MagicMock()
        mock_client.put_object.return_value = {"ETag": '"abc123"'}
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")

        result = await storage.save_file("test.txt", sample_files["text"])

        assert result["path"] == "test.txt"
        assert result["size"] == len(sample_files["text"])
        assert "checksum" in result
        assert "s3://" in result["storage_url"]

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_save_with_metadata(self, mock_boto3, sample_files):
        """Test saving file with metadata to S3."""
        mock_client = MagicMock()
        mock_client.put_object.return_value = {"ETag": '"abc123"'}
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")
        metadata = {"user": "test_user", "category": "documents"}

        result = await storage.save_file(
            "test.txt", sample_files["text"], metadata=metadata
        )

        # Verify metadata was passed to S3
        call_kwargs = mock_client.put_object.call_args[1]
        assert "Metadata" in call_kwargs

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_save_rejects_path_traversal(self, mock_boto3, sample_files):
        """Test that S3 save rejects path traversal."""
        mock_boto3.client.return_value = MagicMock()
        storage = S3FileInterface(bucket_name="test-bucket")

        # Path traversal wrapped in StorageProviderError
        with pytest.raises((PathTraversalError, StorageProviderError)):
            await storage.save_file("../../../etc/passwd", sample_files["text"])


class TestS3FileRetrievalOperations:
    """Tests for S3 file retrieval operations."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_get_file_from_s3(self, mock_boto3, sample_files):
        """Test retrieving file from S3."""
        mock_body = MagicMock()
        mock_body.read.return_value = sample_files["text"]

        mock_client = MagicMock()
        mock_client.get_object.return_value = {"Body": mock_body}
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")

        content = await storage.get_file("test.txt")

        assert content == sample_files["text"]

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_get_nonexistent_file_from_s3(self, mock_boto3):
        """Test getting non-existent file from S3 returns None."""
        from botocore.exceptions import ClientError

        # Patch ClientError at module level
        with patch("jvspatial.storage.interfaces.s3.ClientError", ClientError):
            mock_client = MagicMock()
            error_response = {"Error": {"Code": "NoSuchKey", "Message": "Not found"}}
            mock_client.get_object.side_effect = ClientError(
                error_response, "GetObject"
            )
            mock_boto3.client.return_value = mock_client

            storage = S3FileInterface(bucket_name="test-bucket")

            content = await storage.get_file("missing.txt")

            assert content is None

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_file_not_exists_in_s3(self, mock_boto3):
        """Test checking if file doesn't exist in S3."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        error_response = {"Error": {"Code": "404", "Message": "Not found"}}
        mock_client.head_object.side_effect = ClientError(error_response, "HeadObject")
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")
        storage._ClientError = ClientError

        exists = await storage.file_exists("missing.txt")

        assert exists is False


class TestS3FileStreamingOperations:
    """Tests for S3 file streaming operations."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_stream_file_from_s3(self, mock_boto3, sample_files):
        """Test streaming file from S3 in chunks."""
        mock_body = MagicMock()
        chunks = [sample_files["text"][:10], sample_files["text"][10:]]
        mock_body.read.side_effect = chunks + [b""]
        mock_body.close = MagicMock()

        mock_client = MagicMock()
        mock_client.get_object.return_value = {"Body": mock_body}
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")

        result_chunks = []
        async for chunk in storage.stream_file("test.txt"):
            result_chunks.append(chunk)

        content = b"".join(result_chunks)
        assert content == sample_files["text"]

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_serve_file_from_s3(self, mock_boto3, sample_files):
        """Test serving file from S3."""
        mock_body = MagicMock()
        mock_body.read.return_value = sample_files["text"]

        mock_client = MagicMock()
        mock_client.get_object.return_value = {"Body": mock_body}
        mock_client.head_object.return_value = {
            "ContentLength": len(sample_files["text"])
        }
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")

        chunks = []
        async for chunk in storage.serve_file("test.txt"):
            chunks.append(chunk)

        content = b"".join(chunks)
        assert content == sample_files["text"]


class TestS3FileDeletionOperations:
    """Tests for S3 file deletion operations."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_delete_file_from_s3(self, mock_boto3):
        """Test deleting file from S3."""
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": 100}
        mock_client.delete_object.return_value = {}
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")

        deleted = await storage.delete_file("test.txt")

        assert deleted is True

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_delete_nonexistent_file_from_s3(self, mock_boto3):
        """Test deleting non-existent file from S3 returns False."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        error_response = {"Error": {"Code": "404", "Message": "Not found"}}
        mock_client.head_object.side_effect = ClientError(error_response, "HeadObject")
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")
        storage._ClientError = ClientError

        deleted = await storage.delete_file("missing.txt")

        assert deleted is False


class TestS3FileMetadataOperations:
    """Tests for S3 file metadata operations."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_get_metadata_from_s3(self, mock_boto3):
        """Test getting file metadata from S3."""
        mock_client = MagicMock()
        mock_client.head_object.return_value = {
            "ContentLength": 1024,
            "ContentType": "text/plain",
            "LastModified": datetime.now(),
            "ETag": '"abc123"',
            "Metadata": {"user": "test"},
        }
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")

        metadata = await storage.get_metadata("test.txt")

        assert metadata is not None
        assert metadata["size"] == 1024
        assert metadata["content_type"] == "text/plain"
        assert "checksum" in metadata
        assert metadata["checksum"] == "abc123"

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_get_presigned_url(self, mock_boto3):
        """Test generating pre-signed URL for S3 file."""
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": 100}
        mock_client.generate_presigned_url.return_value = (
            "https://s3.amazonaws.com/signed-url"
        )
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")

        url = await storage.get_file_url("test.txt", expires_in=7200)

        assert url is not None
        assert "https://s3.amazonaws.com" in url

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_get_presigned_url_for_nonexistent_file(self, mock_boto3):
        """Test getting pre-signed URL for non-existent file returns None."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        error_response = {"Error": {"Code": "404", "Message": "Not found"}}
        mock_client.head_object.side_effect = ClientError(error_response, "HeadObject")
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")
        storage._ClientError = ClientError

        url = await storage.get_file_url("missing.txt")

        assert url is None


class TestS3FileListingOperations:
    """Tests for S3 file listing operations."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_list_files_from_s3(self, mock_boto3):
        """Test listing files from S3 bucket."""
        mock_client = MagicMock()
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "file1.txt",
                    "Size": 100,
                    "LastModified": datetime.now(),
                    "ETag": '"abc1"',
                },
                {
                    "Key": "file2.txt",
                    "Size": 200,
                    "LastModified": datetime.now(),
                    "ETag": '"abc2"',
                },
            ]
        }
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")

        files = await storage.list_files()

        assert len(files) == 2
        assert files[0]["path"] == "file1.txt"
        assert files[0]["size"] == 100

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_list_files_with_prefix(self, mock_boto3):
        """Test listing S3 files with prefix filter."""
        mock_client = MagicMock()
        mock_client.list_objects_v2.return_value = {
            "Contents": [
                {
                    "Key": "uploads/doc1.txt",
                    "Size": 100,
                    "LastModified": datetime.now(),
                    "ETag": '"abc"',
                }
            ]
        }
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")

        files = await storage.list_files(prefix="uploads")

        # Verify prefix was used in API call
        call_kwargs = mock_client.list_objects_v2.call_args[1]
        assert "Prefix" in call_kwargs


class TestS3FileStorageInfo:
    """Tests for S3 storage info operations."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_get_s3_storage_info(self, mock_boto3):
        """Test getting S3 storage information."""
        mock_boto3.client.return_value = MagicMock()

        storage = S3FileInterface(bucket_name="test-bucket", region_name="us-west-2")

        info = await storage.get_storage_info()

        assert info["provider"] == "S3FileInterface"
        assert info["bucket_name"] == "test-bucket"
        assert info["region_name"] == "us-west-2"
        assert info["supports_streaming"] is True
        assert info["supports_signed_urls"] is True


class TestS3FileEdgeCases:
    """Tests for S3 edge cases and error handling."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_s3_access_denied_error(self, mock_boto3, sample_files):
        """Test handling of S3 access denied error."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
        mock_client.put_object.side_effect = ClientError(error_response, "PutObject")
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")
        storage._ClientError = ClientError

        with pytest.raises(AccessDeniedError):
            await storage.save_file("test.txt", sample_files["text"])

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_s3_generic_error_handling(self, mock_boto3, sample_files):
        """Test handling of generic S3 errors."""
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        error_response = {"Error": {"Code": "InternalError", "Message": "Server error"}}
        mock_client.put_object.side_effect = ClientError(error_response, "PutObject")
        mock_boto3.client.return_value = mock_client

        storage = S3FileInterface(bucket_name="test-bucket")
        storage._ClientError = ClientError

        with pytest.raises(StorageProviderError):
            await storage.save_file("test.txt", sample_files["text"])

    @pytest.mark.asyncio
    @patch("jvspatial.storage.interfaces.s3.boto3")
    async def test_s3_validates_file_size(self, mock_boto3):
        """Test that S3 storage validates file size."""
        mock_boto3.client.return_value = MagicMock()

        validator = FileValidator(max_size_mb=0.001)  # 1 KB limit
        storage = S3FileInterface(bucket_name="test-bucket", validator=validator)

        large_content = b"x" * 2048  # 2 KB
        # Wrapped in StorageProviderError
        with pytest.raises(StorageProviderError) as exc_info:
            await storage.save_file("large.txt", large_content)
        assert "exceeds limit" in str(exc_info.value).lower()


# ============================================================================
# Integration Tests
# ============================================================================


class TestStorageInterfaceIntegration:
    """Integration tests combining security and storage operations."""

    @pytest.mark.asyncio
    async def test_local_storage_full_workflow(self, local_storage, sample_files):
        """Test complete workflow with local storage."""
        # Save file
        save_result = await local_storage.save_file(
            "docs/report.pdf", sample_files["pdf"], metadata={"author": "test"}
        )

        assert save_result["path"] == "docs/report.pdf"

        # Check it exists
        exists = await local_storage.file_exists("docs/report.pdf")
        assert exists is True

        # Get metadata
        metadata = await local_storage.get_metadata("docs/report.pdf")
        assert metadata["size"] == len(sample_files["pdf"])

        # Retrieve content
        content = await local_storage.get_file("docs/report.pdf")
        assert content == sample_files["pdf"]

        # Stream content
        chunks = []
        async for chunk in local_storage.stream_file("docs/report.pdf"):
            chunks.append(chunk)
        streamed = b"".join(chunks)
        assert streamed == sample_files["pdf"]

        # Delete file
        deleted = await local_storage.delete_file("docs/report.pdf")
        assert deleted is True

        # Verify deletion
        exists = await local_storage.file_exists("docs/report.pdf")
        assert exists is False

    @pytest.mark.asyncio
    async def test_path_sanitizer_integration(self, temp_storage_dir, sample_files):
        """Test that path sanitizer is properly integrated."""
        # Create storage with permissive validator for this specific test
        validator = FileValidator(
            max_size_mb=100,
            allowed_mime_types={"text/plain", "application/octet-stream"},
            blocked_extensions=set(),
        )
        local_storage = LocalFileInterface(
            root_dir=temp_storage_dir, validator=validator
        )

        # Valid path should work
        result = await local_storage.save_file("valid/path.txt", sample_files["text"])
        assert result["path"] == "valid/path.txt"

        # Path traversal should fail - expect PathTraversalError or StorageProviderError
        with pytest.raises((PathTraversalError, StorageProviderError)):
            await local_storage.save_file("../../../etc/passwd", sample_files["text"])

        # Dangerous patterns should fail
        with pytest.raises((PathTraversalError, StorageProviderError)):
            await local_storage.save_file("file;rm -rf /", sample_files["text"])

    @pytest.mark.asyncio
    async def test_file_validator_integration(self, temp_storage_dir, sample_files):
        """Test that file validator is properly integrated."""
        # Create storage with strict validator
        validator = FileValidator(
            max_size_mb=1,
            allowed_mime_types={
                "text/plain",
                "application/pdf",
            },  # Allow both for this test
            blocked_extensions=set(),
        )
        storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

        # Text file should work
        result = await storage.save_file("test.txt", sample_files["text"])
        assert result["path"] == "test.txt"

        # PDF should also work now
        result = await storage.save_file("doc.pdf", sample_files["pdf"])
        assert result["path"] == "doc.pdf"

        # Oversized file should fail - wrapped in StorageProviderError
        huge_content = b"x" * (2 * 1024 * 1024)  # 2 MB
        with pytest.raises(StorageProviderError) as exc_info:
            await storage.save_file("huge.txt", huge_content)
        assert "exceeds limit" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    async def test_atomic_writes(self, local_storage, sample_files):
        """Test that atomic writes work correctly."""
        # Save file twice to same path
        await local_storage.save_file("atomic.txt", b"version 1")
        await local_storage.save_file("atomic.txt", b"version 2")

        # Should have version 2
        content = await local_storage.get_file("atomic.txt")
        assert content == b"version 2"

    @pytest.mark.asyncio
    async def test_md5_checksum_generation(self, local_storage, sample_files):
        """Test that MD5 checksums are correctly generated."""
        result = await local_storage.save_file("test.txt", sample_files["text"])

        expected_checksum = hashlib.md5(sample_files["text"]).hexdigest()
        assert result["checksum"] == expected_checksum


class TestLocalFileVersioning:
    """Test LocalFileInterface file versioning features."""

    @pytest.fixture
    def local_storage_with_versioning(self, temp_storage_dir):
        """Create LocalFileInterface instance with versioning for testing."""
        validator = FileValidator(
            max_size_mb=100,
            allowed_mime_types=None,
            blocked_extensions=set(),
        )
        return LocalFileInterface(
            root_dir=temp_storage_dir,
            base_url="http://localhost:8000",
            validator=validator,
        )

    @pytest.mark.asyncio
    async def test_create_version(self, local_storage_with_versioning, sample_files):
        """Test creating file versions."""
        # Save initial file
        await local_storage_with_versioning.save_file("test.txt", sample_files["text"])

        # Create version
        version = await local_storage_with_versioning.create_version(
            "test.txt", sample_files["text"]
        )

        assert version is not None
        assert "version_id" in version
        assert "path" in version
        assert version["path"] == "test.txt"

    @pytest.mark.asyncio
    async def test_get_version(self, local_storage_with_versioning, sample_files):
        """Test retrieving file versions."""
        # Save initial file
        await local_storage_with_versioning.save_file("test.txt", sample_files["text"])

        # Create version
        version = await local_storage_with_versioning.create_version(
            "test.txt", sample_files["text"]
        )
        version_id = version["version_id"]

        # Get version
        retrieved_version = await local_storage_with_versioning.get_version(
            "test.txt", version_id
        )

        assert retrieved_version is not None
        assert retrieved_version["version_id"] == version_id
        assert retrieved_version["path"] == "test.txt"

    @pytest.mark.asyncio
    async def test_list_versions(self, local_storage_with_versioning, sample_files):
        """Test listing file versions."""
        # Save initial file
        await local_storage_with_versioning.save_file("test.txt", sample_files["text"])

        # Create multiple versions
        version1 = await local_storage_with_versioning.create_version(
            "test.txt", sample_files["text"]
        )
        version2 = await local_storage_with_versioning.create_version(
            "test.txt", sample_files["text"]
        )

        # List versions
        versions = await local_storage_with_versioning.list_versions("test.txt")

        assert len(versions) >= 2
        version_ids = [v["version_id"] for v in versions]
        assert version1["version_id"] in version_ids
        assert version2["version_id"] in version_ids

    @pytest.mark.asyncio
    async def test_get_latest_version(
        self, local_storage_with_versioning, sample_files
    ):
        """Test getting the latest file version."""
        # Save initial file
        await local_storage_with_versioning.save_file("test.txt", sample_files["text"])

        # Create versions
        version1 = await local_storage_with_versioning.create_version(
            "test.txt", sample_files["text"]
        )
        version2 = await local_storage_with_versioning.create_version(
            "test.txt", sample_files["text"]
        )

        # Get latest version
        latest = await local_storage_with_versioning.get_latest_version("test.txt")

        assert latest is not None
        assert latest["version_id"] == version2["version_id"]

    @pytest.mark.asyncio
    async def test_delete_version(self, local_storage_with_versioning, sample_files):
        """Test deleting file versions."""
        # Save initial file
        await local_storage_with_versioning.save_file("test.txt", sample_files["text"])

        # Create version
        version = await local_storage_with_versioning.create_version(
            "test.txt", sample_files["text"]
        )
        version_id = version["version_id"]

        # Delete version
        deleted = await local_storage_with_versioning.delete_version(
            "test.txt", version_id
        )

        assert deleted is True

        # Verify version is gone
        retrieved_version = await local_storage_with_versioning.get_version(
            "test.txt", version_id
        )
        assert retrieved_version is None

    @pytest.mark.asyncio
    async def test_version_metadata(self, local_storage_with_versioning, sample_files):
        """Test version metadata tracking."""
        # Save initial file
        await local_storage_with_versioning.save_file("test.txt", sample_files["text"])

        # Create version with metadata
        version = await local_storage_with_versioning.create_version(
            "test.txt", sample_files["text"]
        )

        assert "created_at" in version
        assert "size" in version
        assert version["size"] == len(sample_files["text"])

    @pytest.mark.asyncio
    async def test_version_nonexistent_file(
        self, local_storage_with_versioning, sample_files
    ):
        """Test versioning operations on non-existent files."""
        # Try to create version for non-existent file
        version = await local_storage_with_versioning.create_version(
            "missing.txt", sample_files["text"]
        )

        # Should still work (creates the file)
        assert version is not None

        # Try to get version for non-existent file
        retrieved = await local_storage_with_versioning.get_version(
            "missing.txt", "fake_id"
        )
        assert retrieved is None

        # Try to list versions for non-existent file
        versions = await local_storage_with_versioning.list_versions("missing.txt")
        assert len(versions) >= 1  # Should have the version we just created


# ============================================================================
# Performance Tests
# ============================================================================


class TestStoragePerformance:
    """Performance and stress tests."""

    @pytest.mark.asyncio
    async def test_many_small_files(self, local_storage):
        """Test handling many small file operations."""
        content = b"small file content"

        # Save many files
        tasks = [local_storage.save_file(f"file{i}.txt", content) for i in range(50)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 50
        for result in results:
            assert result["size"] == len(content)

    @pytest.mark.asyncio
    async def test_concurrent_operations(self, local_storage, sample_files):
        """Test concurrent read/write operations."""
        # Save initial file
        await local_storage.save_file("concurrent.txt", sample_files["text"])

        # Perform concurrent reads
        tasks = [local_storage.get_file("concurrent.txt") for _ in range(10)]
        results = await asyncio.gather(*tasks)

        # All should succeed
        assert all(r == sample_files["text"] for r in results)


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestStorageErrorHandling:
    """Tests for error handling and edge cases."""

    @pytest.mark.asyncio
    async def test_handle_permission_errors(self, temp_storage_dir):
        """Test handling of permission errors."""
        # This test is platform-specific and may not work on all systems
        # It's here to demonstrate the intention
        pass

    @pytest.mark.asyncio
    async def test_handle_disk_full_errors(self, local_storage):
        """Test handling of disk full scenarios."""
        # This is difficult to test without actually filling a disk
        # It's here to demonstrate the intention
        pass

    @pytest.mark.asyncio
    async def test_handle_invalid_unicode_paths(self, local_storage):
        """Test handling of invalid unicode in paths."""
        # PathSanitizer should reject invalid unicode characters
        # This test expects PathTraversalError or StorageProviderError
        with pytest.raises((PathTraversalError, StorageProviderError)):
            await local_storage.save_file("文件.txt", b"content")


# ============================================================================
# Cleanup and Summary
# ============================================================================


async def test_module_imports():
    """Test that all required modules can be imported."""
    from jvspatial.storage.exceptions import (
        FileNotFoundError,
        PathTraversalError,
        StorageProviderError,
    )
    from jvspatial.storage.interfaces import (
        FileStorageInterface,
        LocalFileInterface,
        S3FileInterface,
    )
    from jvspatial.storage.security import FileValidator, PathSanitizer

    # All imports successful
    assert FileStorageInterface is not None
    assert LocalFileInterface is not None
    assert S3FileInterface is not None
    assert PathSanitizer is not None
    assert FileValidator is not None
