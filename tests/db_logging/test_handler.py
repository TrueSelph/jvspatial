"""Tests for jvspatial.logging.handler (DBLogHandler)."""

import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.logging.handler import DBLogHandler


class TestDBLogHandlerBackgroundProcessing:
    """Test DBLogHandler behavior with BACKGROUND_PROCESSING."""

    def test_persists_logs_when_background_processing_disabled(self):
        """DBLogHandler persists logs when BACKGROUND_PROCESSING=false (e.g. Lambda).

        Logging should only be controlled by JVAGENT_LOGGING_ENABLED, not
        BACKGROUND_PROCESSING. When BACKGROUND_PROCESSING is false, the handler
        uses synchronous save in a thread instead of skipping.
        """
        with patch.dict(os.environ, {"BACKGROUND_PROCESSING": "false"}):
            with patch(
                "jvspatial.core.entities.object.Object.save",
                new_callable=AsyncMock,
            ) as mock_save:
                mock_db = MagicMock()
                with patch(
                    "jvspatial.logging.handler.get_database_manager"
                ) as mock_mgr:
                    mock_mgr.return_value.list_databases.return_value = ["test_logs"]
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
                        msg="Test error when BACKGROUND_PROCESSING disabled",
                        args=(),
                        exc_info=None,
                    )
                    record.args = ()
                    record.getMessage = lambda: record.msg

                    handler.emit(record)

                    mock_save.assert_called_once()
