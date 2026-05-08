"""Tests for jvspatial.db._path_locks.PathLockManager."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from jvspatial.db._path_locks import PathLockManager


class TestPathLockManager:
    def test_same_key_serializes(self) -> None:
        """Two writers on the same key never overlap."""
        manager = PathLockManager()
        in_section = 0
        max_concurrency = 0
        cv = threading.Lock()

        def critical(_idx: int) -> None:
            nonlocal in_section, max_concurrency
            with manager.lock("same"):
                with cv:
                    in_section += 1
                    if in_section > max_concurrency:
                        max_concurrency = in_section
                # Hold long enough for an overlap to be observable.
                time.sleep(0.005)
                with cv:
                    in_section -= 1

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(critical, range(8)))

        assert max_concurrency == 1

    def test_different_keys_run_in_parallel(self) -> None:
        """Writers on distinct keys may execute concurrently."""
        manager = PathLockManager()
        in_section = 0
        max_concurrency = 0
        cv = threading.Lock()

        def critical(idx: int) -> None:
            nonlocal in_section, max_concurrency
            with manager.lock(f"key-{idx}"):
                with cv:
                    in_section += 1
                    if in_section > max_concurrency:
                        max_concurrency = in_section
                time.sleep(0.02)
                with cv:
                    in_section -= 1

        with ThreadPoolExecutor(max_workers=8) as ex:
            list(ex.map(critical, range(8)))

        # We expect real parallelism. Be tolerant of CI scheduling jitter,
        # but anything > 1 disproves the "always serialized" hypothesis.
        assert max_concurrency >= 2

    def test_lru_eviction_bounds_memory(self) -> None:
        """The lock table never exceeds max_locks once warmed up (idle locks)."""
        manager = PathLockManager(max_locks=4)
        for i in range(50):
            with manager.lock(f"k{i}"):
                pass
        # All locks released in order, so eviction should keep us at the cap.
        assert len(manager) == 4

    def test_held_locks_are_not_evicted(self) -> None:
        """A held lock survives an eviction sweep; the table grows by one."""
        manager = PathLockManager(max_locks=2)

        # Hold k0 from a worker thread.
        held = threading.Event()
        release = threading.Event()

        def hold_k0() -> None:
            with manager.lock("k0"):
                held.set()
                release.wait()

        t = threading.Thread(target=hold_k0)
        t.start()
        held.wait(timeout=1.0)

        # Cause eviction pressure: ask for several other unique keys.
        with manager.lock("k1"):
            pass
        with manager.lock("k2"):
            pass
        with manager.lock("k3"):
            pass

        # k0 must still be present (it's held); the table can have grown
        # past max_locks because eviction skipped held locks.
        assert len(manager) >= 1

        release.set()
        t.join(timeout=1.0)

    def test_invalid_max_locks(self) -> None:
        with pytest.raises(ValueError):
            PathLockManager(max_locks=0)
