"""Tests for jvspatial.logging.models (DBLog)."""

from datetime import datetime, timezone

import pytest

from jvspatial.logging.models import DBLog


class TestDBLogModel:
    """Test DBLog model attributes and construction."""

    def test_dblog_has_event_code_and_log_data_fields(self):
        """DBLog model defines event_code and log_data in model_fields."""
        fields = DBLog.model_fields.keys()
        assert "event_code" in fields
        assert "log_data" in fields
        assert "status_code" in fields
        assert "log_level" in fields
        assert "path" in fields
        assert "method" in fields
        assert "logged_at" in fields

    def test_dblog_construction_with_event_code_and_log_data(self):
        """DBLog can be constructed with event_code and log_data."""
        log = DBLog(
            event_code="test_event",
            log_level="ERROR",
            log_data={
                "message": "Test message",
                "log_level": "ERROR",
                "details": {"key": "value"},
            },
            path="/api/test",
            method="POST",
            status_code=500,
            logged_at=datetime.now(timezone.utc),
        )
        assert log.event_code == "test_event"
        assert log.log_data["message"] == "Test message"
        assert log.log_data["details"]["key"] == "value"
        assert log.status_code == 500
        assert log.log_level == "ERROR"

    def test_dblog_accepts_none_status_code_for_non_http_logs(self):
        """DBLog accepts status_code=None for non-HTTP logs."""
        log = DBLog(
            event_code="background_task",
            log_level="INFO",
            log_data={"message": "Task done", "log_level": "INFO"},
            status_code=None,
            path="",
            method="",
            logged_at=datetime.now(timezone.utc),
        )
        assert log.status_code is None
        assert log.event_code == "background_task"
