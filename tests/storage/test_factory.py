"""Test suite for storage factory.

Tests the simplified storage creation functionality.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jvspatial.storage import create_default_storage, create_storage
from jvspatial.storage.exceptions import StorageProviderError
from jvspatial.storage.interfaces.local import LocalFileInterface
from jvspatial.storage.interfaces.s3 import S3FileInterface

# Check if boto3 is available for S3 tests
try:
    from jvspatial.storage.interfaces.s3 import HAS_BOTO3
except ImportError:
    HAS_BOTO3 = False


class TestStorageFactory:
    """Test storage factory functions."""

    def test_create_storage_local(self):
        """Test creating local storage."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = create_storage("local", root_dir=temp_dir)
            assert isinstance(storage, LocalFileInterface)
            assert storage.root_dir.resolve() == Path(temp_dir).resolve()

    @pytest.mark.skipif(not HAS_BOTO3, reason="boto3 is required for S3 storage")
    def test_create_storage_s3(self):
        """Test creating S3 storage."""
        with patch("jvspatial.storage.interfaces.s3.boto3"):
            storage = create_storage("s3", bucket_name="test-bucket")
            assert isinstance(storage, S3FileInterface)

    def test_create_storage_invalid_provider(self):
        """Test error handling for invalid provider."""
        with pytest.raises(ValueError) as exc_info:
            create_storage("invalid_provider")

        assert "Unsupported storage provider" in str(exc_info.value)
        assert "invalid_provider" in str(exc_info.value)

    def test_create_default_storage(self):
        """Test default storage creation."""
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {"JVSPATIAL_FILE_INTERFACE": "local"}):
                storage = create_default_storage()
        assert isinstance(storage, LocalFileInterface)

    def test_create_storage_with_config(self):
        """Test creating storage with configuration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = {
                "root_dir": temp_dir,
                "create_root": True,
                "base_url": "http://localhost:8000/files",
            }
            storage = create_storage("local", **config)
            assert isinstance(storage, LocalFileInterface)
            assert storage.root_dir.resolve() == Path(temp_dir).resolve()

    @pytest.mark.skipif(not HAS_BOTO3, reason="boto3 is required for S3 storage")
    def test_create_storage_s3_with_config(self):
        """Test creating S3 storage with configuration."""
        with patch("jvspatial.storage.interfaces.s3.boto3"):
            config = {
                "bucket_name": "test-bucket",
                "region_name": "us-west-2",
                "access_key_id": "test-key",
                "secret_access_key": "test-secret",  # pragma: allowlist secret
            }
            storage = create_storage("s3", **config)
            assert isinstance(storage, S3FileInterface)

    @pytest.mark.asyncio
    async def test_storage_integration(self):
        """Test storage integration."""
        with tempfile.TemporaryDirectory() as temp_dir:
            storage = create_storage("local", root_dir=temp_dir)

            # Test basic operations
            file_path = "test/file.txt"
            content = b"Hello, World!"

            # Save file
            await storage.save_file(file_path, content)

            # Check if file exists
            assert await storage.file_exists(file_path)

            # Get file
            retrieved_content = await storage.get_file(file_path)
            assert retrieved_content == content

            # Delete file
            await storage.delete_file(file_path)
            assert not await storage.file_exists(file_path)
