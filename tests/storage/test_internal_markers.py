"""Internal storage markers must bypass strict MIME allowlists (empty body → octet-stream)."""

import tempfile
from pathlib import Path

import pytest

from jvspatial.storage.interfaces.local import LocalFileInterface
from jvspatial.storage.security.validator import FileValidator


@pytest.fixture
def temp_storage_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.mark.asyncio
async def test_save_internal_markers_skip_mime_allowlist(temp_storage_dir):
    validator = FileValidator(allowed_mime_types={"text/plain"})
    storage = LocalFileInterface(root_dir=temp_storage_dir, validator=validator)

    await storage.save_file(
        "agent/user/output/.jvdirectory",
        b"",
        metadata={"type": "directory"},
    )
    assert (Path(temp_storage_dir) / "agent/user/output/.jvdirectory").is_file()

    await storage.save_file(
        "agent/user/.jvagent_sandbox",
        b"",
        metadata={"sandbox": "1"},
    )
    assert (Path(temp_storage_dir) / "agent/user/.jvagent_sandbox").is_file()
