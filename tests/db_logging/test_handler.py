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

        DB logging is enabled via JVSPATIAL_DB_LOGGING_ENABLED (or app initialization).
        In serverless mode, the default path completes the save in a worker thread (blocking join).
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


class TestDBLogHandlerServerlessBlockingDefault:
    """Serverless must not use fire-and-forget create_task unless explicitly opted in."""

    def test_default_no_create_task_even_with_running_loop(self):
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
                            msg="blocking serverless",
                            args=(),
                            exc_info=None,
                        )
                        record.args = ()
                        record.getMessage = lambda: record.msg

                        def _no_create_task(*_a, **_k):
                            raise AssertionError(
                                "create_task must not run in serverless unless "
                                "JVSPATIAL_DB_LOG_SERVERLESS_ASYNC is enabled"
                            )

                        async def emit_from_async_context():
                            with patch(
                                "jvspatial.logging.handler.asyncio.create_task",
                                side_effect=_no_create_task,
                            ):
                                handler.emit(record)

                        asyncio.run(emit_from_async_context())
                        mock_save.assert_called_once()
            finally:
                reset_serverless_mode_cache()

    def test_async_opt_in_uses_create_task_when_loop_running(self):
        env = {
            "SERVERLESS_MODE": "true",
            "JVSPATIAL_DB_LOG_SERVERLESS_ASYNC": "true",
        }
        with patch.dict(os.environ, env, clear=False):
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
                            msg="async opt-in serverless",
                            args=(),
                            exc_info=None,
                        )
                        record.args = ()
                        record.getMessage = lambda: record.msg

                        async def emit_and_drain():
                            handler.emit(record)
                            await asyncio.sleep(0.05)

                        asyncio.run(emit_and_drain())
                        mock_save.assert_called_once()
            finally:
                reset_serverless_mode_cache()
