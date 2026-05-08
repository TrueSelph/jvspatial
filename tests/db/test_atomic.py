"""Tests for the crash-safe write helpers in jvspatial.db._atomic.

These tests cover:
* atomic_write_bytes never leaves a partial file (real fsync semantics).
* On a write failure, no temp file is left behind.
* cleanup_orphan_tmp_files reaps stale ``*.jvtmp`` files but skips work
  in serverless mode.
* The helpers preserve previous file contents when a write fails.
"""

import os
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from jvspatial.db._atomic import (
    TMP_SUFFIX,
    atomic_write_bytes,
    atomic_write_text,
    cleanup_orphan_tmp_files,
)
from jvspatial.db._path_locks import PathLockManager


class TestAtomicWriteBytes:
    """atomic_write_bytes should write fully or not at all."""

    def test_writes_complete_file(self, tmp_path: Path) -> None:
        target = tmp_path / "a.json"
        payload = b'{"hello": "world"}'

        atomic_write_bytes(target, payload)

        assert target.exists()
        assert target.read_bytes() == payload

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        target = tmp_path / "deep" / "nested" / "dir" / "rec.json"

        atomic_write_bytes(target, b"x")

        assert target.exists()
        assert target.read_bytes() == b"x"

    def test_overwrite_preserves_old_content_on_failure(self, tmp_path: Path) -> None:
        """If the rename step fails, the existing file is untouched."""
        target = tmp_path / "rec.json"
        target.write_bytes(b"OLD")

        # Force os.replace to raise after the temp file exists.
        with patch("jvspatial.db._atomic.os.replace", side_effect=OSError("boom")):
            with pytest.raises(OSError):
                atomic_write_bytes(target, b"NEW")

        # Old contents are intact.
        assert target.read_bytes() == b"OLD"
        # No leftover temp files.
        leftovers = list(tmp_path.glob(f"*{TMP_SUFFIX}"))
        assert leftovers == []

    def test_no_partial_file_on_write_failure(self, tmp_path: Path) -> None:
        """If the file write itself fails, the destination must not exist."""
        target = tmp_path / "rec.json"

        # Patch fsync so it raises mid-write -- this is what would happen
        # on a disk error during the write phase.
        with patch("jvspatial.db._atomic.os.fsync", side_effect=OSError("io err")):
            with pytest.raises(OSError):
                atomic_write_bytes(target, b"data")

        assert not target.exists()
        leftovers = list(tmp_path.glob(f"*{TMP_SUFFIX}"))
        assert leftovers == []

    def test_atomic_write_text_round_trip(self, tmp_path: Path) -> None:
        target = tmp_path / "v.latest"
        atomic_write_text(target, "v20260101_abc")
        assert target.read_text() == "v20260101_abc"

    def test_concurrent_writers_to_same_path_serialize_via_lock(
        self, tmp_path: Path
    ) -> None:
        """Without external serialization, last writer wins; with the
        PathLockManager wrapper, results are deterministic per path."""
        target = tmp_path / "rec.json"
        manager = PathLockManager()

        observed_finals: list = []

        def writer(payload: bytes) -> None:
            with manager.lock(str(target)):
                atomic_write_bytes(target, payload)
                # Read inside the lock to avoid racing with the other writer.
                observed_finals.append(target.read_bytes())

        threads = [
            threading.Thread(target=writer, args=(f"payload-{i}".encode(),))
            for i in range(8)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Each writer saw its own write inside its own critical section.
        assert sorted(observed_finals) == sorted(
            f"payload-{i}".encode() for i in range(8)
        )

        # File ends up containing the payload of *some* writer (no partial).
        assert target.read_bytes().startswith(b"payload-")


class TestCleanupOrphanTmpFiles:
    """cleanup_orphan_tmp_files reaps stale *.jvtmp files."""

    def test_removes_orphans(self, tmp_path: Path) -> None:
        good = tmp_path / "good.json"
        good.write_bytes(b"keep me")
        orphan_a = tmp_path / f"x.json.123.deadbeef{TMP_SUFFIX}"
        orphan_b = tmp_path / "nested" / f"y.json.99.f00d{TMP_SUFFIX}"
        orphan_b.parent.mkdir(parents=True, exist_ok=True)
        orphan_a.write_bytes(b"")
        orphan_b.write_bytes(b"")

        removed = cleanup_orphan_tmp_files([tmp_path])

        assert removed == 2
        assert good.exists()
        assert not orphan_a.exists()
        assert not orphan_b.exists()

    def test_no_op_in_serverless_mode(self, tmp_path: Path) -> None:
        orphan = tmp_path / f"x.json.1.aaaa{TMP_SUFFIX}"
        orphan.write_bytes(b"")

        with patch("jvspatial.db._atomic.is_serverless_mode", return_value=True):
            removed = cleanup_orphan_tmp_files([tmp_path])

        assert removed == 0
        assert orphan.exists()  # left in place

    def test_handles_missing_root(self, tmp_path: Path) -> None:
        nonexistent = tmp_path / "does_not_exist"
        removed = cleanup_orphan_tmp_files([nonexistent])
        assert removed == 0
