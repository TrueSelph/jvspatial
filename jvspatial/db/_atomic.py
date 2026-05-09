"""Crash-safe filesystem write helpers.

These helpers implement the standard ``write tmp + fsync + rename + fsync(dir)``
pattern so that a process crash, kernel panic, or power loss can never leave
a half-written record behind on disk. The destination is always either the
previous fully-formed contents or the new fully-formed contents; never a
truncated mix of the two.

The helpers are intentionally synchronous: callers schedule them through
``asyncio.to_thread`` (or call them from a sync context) so that they do
the right thing whether the event loop is alive or not. This matches
``JsonDB``'s existing pattern of running file IO in worker threads via
``threading.Lock``-protected helpers, and keeps the side-thread / serverless
``asyncio.run``-from-a-different-thread call sites working unchanged.

In serverless mode (``is_serverless_mode()`` returns True) we still perform
``fsync`` of the file because that's needed for crash safety inside the
sandbox itself, but we *skip* directory ``fsync`` -- on most managed
runtimes the writable filesystem is ``tmpfs``-backed and the directory
``fsync`` is either a no-op or unavailable, and we don't want to pay for
the syscall on every write of an ephemeral artifact.
"""

from __future__ import annotations

import contextlib
import logging
import os
import secrets
from pathlib import Path
from typing import Iterable, Union

from jvspatial.runtime.serverless import is_serverless_mode

logger = logging.getLogger(__name__)

# Suffix for in-flight temp files. Includes ``.jvtmp`` so an operator
# (or our own startup sweep) can safely identify and reap orphans without
# false-positives against user data that happens to end in ``.tmp``.
TMP_SUFFIX = ".jvtmp"


def _make_temp_path(target: Path) -> Path:
    """Construct a per-write temp path adjacent to ``target``.

    Adjacency matters: ``os.replace`` is only guaranteed atomic when source
    and destination live on the same filesystem. Putting the temp file in
    the same directory as the destination guarantees that.
    """
    # ``secrets.token_hex(6)`` keeps the suffix short (12 hex chars) while
    # making collisions between concurrent writers astronomically unlikely.
    return target.with_name(
        f"{target.name}.{os.getpid()}.{secrets.token_hex(6)}{TMP_SUFFIX}"
    )


def _fsync_directory(directory: Path) -> None:
    """Best-effort ``fsync`` of a directory entry.

    Required after ``os.replace`` to guarantee the rename is visible after
    a crash. Some platforms (Windows, certain network filesystems) don't
    support directory fsync and raise ``OSError`` -- we swallow that since
    those filesystems either don't need it or can't honor it anyway.
    """
    try:
        fd = os.open(str(directory), os.O_RDONLY)
    except OSError:
        # Windows / unsupported filesystems
        return
    try:
        # Some FUSE / network filesystems return EINVAL here; we've
        # already fsync'd the file itself, which is the important part.
        with contextlib.suppress(OSError):
            os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write_bytes(
    target: Union[str, Path],
    data: bytes,
    *,
    fsync_dir: bool = True,
) -> None:
    """Atomically write ``data`` to ``target``.

    On return, ``target`` either contains exactly ``data`` or its previous
    contents (or doesn't exist, if it didn't before). Never a partial write.

    The implementation:
        1. Writes payload to ``target.<pid>.<rand>.jvtmp`` in the same dir.
        2. Flushes the file's user-space buffers and ``fsync``s the file.
        3. ``os.replace`` is the atomic publish step.
        4. Optionally ``fsync``s the parent directory so the rename
           survives a crash.

    Args:
        target: Destination path.
        data: Bytes to write.
        fsync_dir: If True (default), fsync the parent directory after the
            rename. Skipped automatically in serverless mode where the
            writable FS is tmpfs and the syscall is wasted work.
    """
    target_path = Path(target)
    parent = target_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    tmp_path = _make_temp_path(target_path)

    try:
        # Open with explicit fd so we can fsync before close.
        fd = os.open(
            str(tmp_path),
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o644,
        )
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
        except Exception:
            # Make best effort to remove the temp file before re-raising.
            with contextlib.suppress(OSError):
                tmp_path.unlink()
            raise

        # Atomic publish.
        os.replace(str(tmp_path), str(target_path))

        if fsync_dir and not is_serverless_mode():
            _fsync_directory(parent)
    except Exception:
        # ``os.replace`` failed (extremely rare) -- remove the leftover tmp.
        if tmp_path.exists():
            with contextlib.suppress(OSError):
                tmp_path.unlink()
        raise


def atomic_write_text(
    target: Union[str, Path],
    data: str,
    *,
    encoding: str = "utf-8",
    fsync_dir: bool = True,
) -> None:
    """UTF-8 (or specified encoding) variant of :func:`atomic_write_bytes`."""
    atomic_write_bytes(
        target,
        data.encode(encoding),
        fsync_dir=fsync_dir,
    )


def cleanup_orphan_tmp_files(roots: Iterable[Union[str, Path]]) -> int:
    """Remove ``*.jvtmp`` files left behind by a previously-crashed process.

    Safe to call at startup. Skipped automatically in serverless mode --
    cold starts don't share the same filesystem instance with prior
    invocations on most platforms, and the warning about ephemerality
    in :class:`~jvspatial.db.jsondb.JsonDB` already covers this case.

    Args:
        roots: One or more directories to scan recursively.

    Returns:
        Number of orphan files removed.
    """
    if is_serverless_mode():
        return 0

    removed = 0
    for root in roots:
        root_path = Path(root)
        if not root_path.exists() or not root_path.is_dir():
            continue
        for orphan in root_path.rglob(f"*{TMP_SUFFIX}"):
            try:
                orphan.unlink()
                removed += 1
                logger.info("Reaped orphan temp file: %s", orphan)
            except OSError as exc:
                # Another process may have cleaned it up between rglob and
                # unlink, or we might lack permission. Either way, log and
                # continue so the sweep doesn't abort the whole startup.
                logger.debug("Could not reap orphan %s: %s", orphan, exc)
    return removed


__all__ = [
    "TMP_SUFFIX",
    "atomic_write_bytes",
    "atomic_write_text",
    "cleanup_orphan_tmp_files",
]
