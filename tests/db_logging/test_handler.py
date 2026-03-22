"""Tests for jvspatial.logging.handler (DBLogHandler)."""

import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.logging.handler import DBLogHandler
from jvspatial.runtime.serverless import reset_serverless_mode_cache


class TestDBLogHandlerBackgroundProcessing:
    """Test DBLogHandler behavior in serverless mode."""

    def test_persists_logs_in_serverless_mode(self):
        """DBLogHandler persists logs when serverless mode is enabled.

        Logging should only be controlled by JVAGENT_LOGGING_ENABLED. In serverless mode, the handler
        uses synchronous save in a thread instead of skipping.
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
