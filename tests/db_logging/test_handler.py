"""Tests for jvspatial.logging.handler (DBLogHandler)."""

import asyncio
import logging
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from jvspatial.db.jsondb import JsonDB
from jvspatial.logging.handler import DBLogHandler
from jvspatial.runtime.serverless import reset_serverless_mode_cache


class TestDBLogHandlerBackgroundProcessing:
    """Test DBLogHandler behavior in serverless mode."""

    def test_persists_logs_in_serverless_mode(self):
        """DBLogHandler persists logs when serverless mode is enabled.

        jvagent gates DB log handler setup via JVSPATIAL_DB_LOGGING_ENABLED.
        In serverless mode, the handler uses synchronous save in a thread instead of skipping.
        """
        with patch.dict(os.environ, {"SERVERLESS_MODE": "true"}):
            reset_serverless_mode_cache()
            try:
                with patch(
                    "jvspatial.core.entities.object.Object.save",
                    new_callable=AsyncMock,
                ) as mock_save:
                    mock_db = MagicMock()
                    with patch(
                        "jvspatial.logging.handler.get_database_manager"
                    ) as mock_mgr:
                        mock_mgr.return_value.list_databases.return_value = [
                            "test_logs"
                        ]
                        mock_mgr.return_value.get_database.return_value = mock_db

                        handler = DBLogHandler(
                            database_name="test_logs",
                            enabled=True,
                            log_levels={logging.ERROR},
                        )

                        record = logging.LogRecord(
                            name="test",
                            level=logging.ERROR,
                            pathname="",
                            lineno=0,
                            msg="Test error when serverless mode enabled",
                            args=(),
                            exc_info=None,
                        )
                        record.args = ()
                        record.getMessage = lambda: record.msg

                        handler.emit(record)

                        mock_save.assert_called_once()
            finally:
                reset_serverless_mode_cache()


class TestDBLogHandlerJsonDBServerless:
    """JsonDB + serverless thread path must persist (no asyncio.Lock loop mismatch)."""

    def test_persists_via_jsondb_side_thread_after_main_loop_warmup(self):
        """Warm JsonDB on loop A; emit from sync context uses thread+asyncio.run (loop B)."""
        with tempfile.TemporaryDirectory() as tmp:
            jdb = JsonDB(base_path=tmp)

            async def warmup():
                await jdb.save("object", {"id": "o.warmup.test", "entity": "Warmup"})

            asyncio.run(warmup())

            with patch.dict(os.environ, {"SERVERLESS_MODE": "true"}):
                reset_serverless_mode_cache()
                try:
                    handler = DBLogHandler(
                        database_name="logs",
                        enabled=True,
                        log_levels={logging.ERROR},
                        database=jdb,
                    )
                    record = logging.LogRecord(
                        name="test",
                        level=logging.ERROR,
                        pathname="",
                        lineno=0,
                        msg="serverless jsondb cross-loop",
                        args=(),
                        exc_info=None,
                    )
                    record.event_code = "test_error"
                    handler.emit(record)
                finally:
                    reset_serverless_mode_cache()

            obj_dir = Path(tmp) / "object"
            json_files = list(obj_dir.glob("*.json"))
            assert len(json_files) >= 2
            assert any("DBLog" in p.name for p in json_files)
