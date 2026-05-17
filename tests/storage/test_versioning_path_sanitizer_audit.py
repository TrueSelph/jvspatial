"""Path-traversal coverage for ``LocalFileInterface`` versioning methods.

Audit §4.2 / SPEC §15.1: ``create_version`` / ``get_version`` /
``list_versions`` / ``delete_version`` / ``get_latest_version`` previously
computed ``self.root_dir / f"{file_path}.versions"`` without sanitizing
``file_path`` — a caller-supplied ``../../etc/passwd`` escaped the storage
root entirely.
"""

import tempfile

import pytest

from jvspatial.storage import create_storage
from jvspatial.storage.exceptions import PathTraversalError


@pytest.fixture
def local_storage():
    with tempfile.TemporaryDirectory() as tmpdir:
        storage = create_storage("local", root_dir=tmpdir)
        yield storage


@pytest.mark.asyncio
async def test_create_version_rejects_path_traversal(local_storage):
    with pytest.raises(PathTraversalError):
        await local_storage.create_version("../../etc/passwd", b"payload")


@pytest.mark.asyncio
async def test_get_version_rejects_path_traversal(local_storage):
    with pytest.raises(PathTraversalError):
        await local_storage.get_version("../../etc/passwd", "v1")


@pytest.mark.asyncio
async def test_list_versions_rejects_path_traversal(local_storage):
    with pytest.raises(PathTraversalError):
        await local_storage.list_versions("../../etc/passwd")


@pytest.mark.asyncio
async def test_delete_version_rejects_path_traversal(local_storage):
    with pytest.raises(PathTraversalError):
        await local_storage.delete_version("../../etc/passwd", "v1")


@pytest.mark.asyncio
async def test_get_latest_version_rejects_path_traversal(local_storage):
    with pytest.raises(PathTraversalError):
        await local_storage.get_latest_version("../../etc/passwd")


@pytest.mark.asyncio
async def test_create_version_then_get_round_trips_for_safe_path(local_storage):
    """Sanitizer must not break the happy path — legitimate paths still work."""
    res = await local_storage.create_version("safe/file.txt", b"hello")
    assert res["path"] == "safe/file.txt"
    fetched = await local_storage.get_version("safe/file.txt", res["version_id"])
    assert fetched is not None
    assert fetched["content"] == b"hello"
