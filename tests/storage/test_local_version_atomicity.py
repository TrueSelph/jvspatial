"""Tests that local file-storage version writes are crash-safe.

The new ``LocalFileInterface.create_version`` implementation:
* writes content, metadata, and the latest pointer through
  :func:`atomic_write_bytes`;
* does the writes in the order content -> metadata -> latest so that any
  intermediate crash leaves a recoverable state on disk.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from jvspatial.storage.interfaces.local import LocalFileInterface


@pytest.fixture
def storage(tmp_path):
    return LocalFileInterface(root_dir=str(tmp_path), create_root=True)


class TestVersionAtomicity:
    @pytest.mark.asyncio
    async def test_full_write_round_trip(self, storage):
        await storage.save_file("doc.txt", b"hello world")
        info = await storage.create_version("doc.txt", b"v1 content")

        version_id = info["version_id"]
        version_dir = Path(storage.root_dir) / "doc.txt.versions"
        latest_file = Path(storage.root_dir) / "doc.txt.latest"

        assert (version_dir / f"{version_id}.bin").read_bytes() == b"v1 content"
        meta = json.loads((version_dir / f"{version_id}.meta.json").read_text())
        assert meta["version"] == version_id
        assert meta["size"] == len(b"v1 content")
        assert latest_file.read_text() == version_id

    @pytest.mark.asyncio
    async def test_no_partial_metadata_when_metadata_write_fails(
        self, storage, tmp_path
    ):
        """If metadata write fails, the .bin already on disk is reachable
        only by version_id, which we report on success. We must not have
        a half-written .meta.json file or a stale .latest pointer."""
        from jvspatial.storage.interfaces import local as local_module

        original_atomic = local_module.atomic_write_text
        call_count = {"n": 0}

        def flaky_atomic_write_text(target, data, **kw):
            call_count["n"] += 1
            # 1st atomic_write_text call inside create_version is the
            # metadata write; explode there.
            if call_count["n"] == 1:
                raise OSError("disk full")
            return original_atomic(target, data, **kw)

        with patch.object(
            local_module, "atomic_write_text", side_effect=flaky_atomic_write_text
        ):
            with pytest.raises(OSError):
                await storage.create_version("doc.txt", b"v2 content")

        # No metadata sidecar
        version_dir = Path(storage.root_dir) / "doc.txt.versions"
        meta_files = list(version_dir.glob("*.meta.json"))
        assert meta_files == []

        # No latest pointer published
        latest = Path(storage.root_dir) / "doc.txt.latest"
        assert not latest.exists()

        # No leftover *.jvtmp files in the version dir
        assert list(version_dir.glob("*.jvtmp")) == []

    @pytest.mark.asyncio
    async def test_save_file_no_partial_on_failure(self, storage):
        """save_file uses atomic_write_bytes; a mid-write failure leaves
        no destination file and no temp residue."""
        from jvspatial.storage.interfaces import local as local_module

        with patch.object(
            local_module,
            "atomic_write_bytes",
            side_effect=OSError("disk full"),
        ):
            with pytest.raises(Exception):  # wrapped as StorageProviderError
                await storage.save_file("never.txt", b"abc")

        target = Path(storage.root_dir) / "never.txt"
        assert not target.exists()
        # No leftover temp residue at the root.
        assert list(Path(storage.root_dir).glob("*.jvtmp")) == []
