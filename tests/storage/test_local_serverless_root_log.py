"""Tests for LocalFileInterface serverless + non-/tmp root messaging."""

import logging
from pathlib import Path

import pytest

from jvspatial.storage.interfaces import local as local_mod


class TestServerlessNonTmpRootLog:
    """_log_serverless_non_tmp_root levels and JVSPATIAL_FILE_STORAGE_SERVERLESS_SHARED."""

    def test_mnt_prefix_logs_info_not_warning(self, caplog):
        caplog.set_level(logging.INFO)
        local_mod._log_serverless_non_tmp_root(Path("/mnt/jvspatial/app_x/.files"))
        assert any(
            r.levelno == logging.INFO and "outside /tmp" in r.message
            for r in caplog.records
        )
        assert not any(r.levelno == logging.WARNING for r in caplog.records)

    def test_other_path_logs_warning(self, caplog):
        caplog.set_level(logging.WARNING)
        local_mod._log_serverless_non_tmp_root(Path("/opt/jvspatial/.files"))
        assert any(
            r.levelno == logging.WARNING and "outside /tmp" in r.message
            for r in caplog.records
        )

    def test_shared_env_suppresses_log(self, caplog, monkeypatch):
        caplog.set_level(logging.INFO)
        monkeypatch.setenv("JVSPATIAL_FILE_STORAGE_SERVERLESS_SHARED", "1")
        local_mod._log_serverless_non_tmp_root(Path("/opt/jvspatial/.files"))
        assert not caplog.records
