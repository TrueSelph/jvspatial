"""Tests for the S3 multipart-threshold path.

We mock the boto3 client entirely so these tests don't require real
AWS credentials. The point is to verify the *routing* between
``put_object`` and ``upload_fileobj`` based on size, not to test
boto3's TransferManager itself.
"""

from unittest.mock import MagicMock, patch

import pytest

boto3 = pytest.importorskip("boto3")

from jvspatial.storage.interfaces.s3 import S3FileInterface  # noqa: E402


@pytest.fixture
def mock_client():
    """Patch S3FileInterface._init_client so __init__ doesn't touch boto3.

    Note:
        ``patch.object(cls, name)`` replaces the attribute with a MagicMock,
        which is *not* a descriptor and therefore does not auto-bind
        ``self`` when accessed via an instance. Assigning a real
        ``side_effect`` callable that expects ``self`` would fail because
        the mock invokes the side effect with the call's args (none, since
        ``self._init_client()`` passes nothing). We replace with a plain
        ``lambda`` -- which IS a descriptor -- so ``self`` binds normally,
        then assign ``s3_client`` on the resulting instance from the test
        fixture.
    """
    client = MagicMock()
    client.put_object.return_value = {}
    client.upload_fileobj.return_value = None
    with patch.object(S3FileInterface, "_init_client", lambda self: None):
        yield client


@pytest.fixture
def s3(mock_client, monkeypatch):
    monkeypatch.setenv("JVSPATIAL_S3_BUCKET_NAME", "test-bucket")
    storage = S3FileInterface(
        bucket_name="test-bucket",
        multipart_threshold=1024,  # 1 KiB threshold for fast tests
    )
    storage.s3_client = mock_client
    return storage


class TestRoutingByThreshold:
    @pytest.mark.asyncio
    async def test_small_object_uses_put_object(self, s3, mock_client):
        await s3.save_file("small.bin", b"x" * 100)
        assert mock_client.put_object.called
        assert not mock_client.upload_fileobj.called

    @pytest.mark.asyncio
    async def test_large_object_uses_upload_fileobj(self, s3, mock_client):
        await s3.save_file("big.bin", b"x" * 2048)
        assert mock_client.upload_fileobj.called
        assert not mock_client.put_object.called

    @pytest.mark.asyncio
    async def test_at_threshold_exactly_uses_multipart(self, s3, mock_client):
        # ``>=`` semantics: exactly threshold size triggers multipart.
        await s3.save_file("threshold.bin", b"x" * 1024)
        assert mock_client.upload_fileobj.called
        assert not mock_client.put_object.called


class TestExtraArgsForwarding:
    @pytest.mark.asyncio
    async def test_metadata_forwarded_to_extra_args_on_multipart(self, s3, mock_client):
        await s3.save_file(
            "big.bin",
            b"x" * 2048,
            metadata={"author": "test"},
        )
        call = mock_client.upload_fileobj.call_args
        extra_args = call.kwargs.get("ExtraArgs", {})
        assert extra_args.get("ContentType")
        assert "Metadata" in extra_args
        assert extra_args["Metadata"]["author"] == "test"

    @pytest.mark.asyncio
    async def test_metadata_forwarded_on_put_object_too(self, s3, mock_client):
        await s3.save_file(
            "small.bin",
            b"x" * 100,
            metadata={"author": "test"},
        )
        call = mock_client.put_object.call_args
        assert call.kwargs.get("ContentType")
        assert call.kwargs.get("Metadata", {}).get("author") == "test"


class TestThresholdConfiguration:
    @pytest.mark.asyncio
    async def test_env_var_threshold(self, mock_client, monkeypatch):
        monkeypatch.setenv("JVSPATIAL_S3_BUCKET_NAME", "test-bucket")
        monkeypatch.setenv("JVSPATIAL_S3_MULTIPART_THRESHOLD", "512")
        storage = S3FileInterface(bucket_name="test-bucket")
        assert storage.multipart_threshold == 512

    @pytest.mark.asyncio
    async def test_explicit_arg_overrides_env(self, mock_client, monkeypatch):
        monkeypatch.setenv("JVSPATIAL_S3_BUCKET_NAME", "test-bucket")
        monkeypatch.setenv("JVSPATIAL_S3_MULTIPART_THRESHOLD", "999")
        storage = S3FileInterface(bucket_name="test-bucket", multipart_threshold=42)
        assert storage.multipart_threshold == 42

    @pytest.mark.asyncio
    async def test_default_is_8_mib(self, mock_client, monkeypatch):
        monkeypatch.setenv("JVSPATIAL_S3_BUCKET_NAME", "test-bucket")
        monkeypatch.delenv("JVSPATIAL_S3_MULTIPART_THRESHOLD", raising=False)
        storage = S3FileInterface(bucket_name="test-bucket")
        assert storage.multipart_threshold == 8 * 1024 * 1024
