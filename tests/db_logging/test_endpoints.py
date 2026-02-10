"""Tests for jvspatial.logging.endpoints (get_logs, response models)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.logging.endpoints import (
    LogEntry,
    LogsResponse,
    PaginationInfo,
    get_logs,
)


class TestLogEntryModel:
    """Test LogEntry and related response models."""

    def test_log_entry_valid_minimal(self):
        """LogEntry accepts minimal valid fields with event_code and log_data."""
        entry = LogEntry(
            log_id="log_1",
            log_level="ERROR",
            status_code=500,
            event_code="internal_error",
            message="Something failed",
            path="/api/test",
            method="POST",
            logged_at="2024-01-15T10:30:00Z",
            log_data={"message": "Something failed", "log_level": "ERROR"},
        )
        assert entry.log_id == "log_1"
        assert entry.event_code == "internal_error"
        assert entry.status_code == 500
        assert entry.log_data["log_level"] == "ERROR"

    def test_log_entry_with_optional_agent_id(self):
        """LogEntry accepts optional agent_id."""
        entry = LogEntry(
            log_id="log_2",
            log_level="INFO",
            status_code=200,
            event_code="action_done",
            message="OK",
            path="",
            method="",
            agent_id="agent_123",
            logged_at="2024-01-15T10:30:00Z",
            log_data={},
        )
        assert entry.agent_id == "agent_123"

    def test_log_entry_status_code_zero_allowed(self):
        """LogEntry accepts status_code 0 (e.g. non-HTTP logs)."""
        entry = LogEntry(
            log_id="log_3",
            log_level="INFO",
            status_code=0,
            event_code="task_done",
            message="Task completed",
            path="",
            method="",
            logged_at="2024-01-15T10:30:00Z",
            log_data={},
        )
        assert entry.status_code == 0


class TestPaginationInfo:
    """Test PaginationInfo model."""

    def test_pagination_info(self):
        """PaginationInfo stores page, page_size, total, total_pages."""
        p = PaginationInfo(page=2, page_size=10, total=95, total_pages=10)
        assert p.page == 2
        assert p.page_size == 10
        assert p.total == 95
        assert p.total_pages == 10


class TestGetLogsEndpoint:
    """Test get_logs endpoint with mocked service."""

    @pytest.fixture
    def mock_service(self):
        """Service mock with get_error_logs returning a known structure."""
        svc = MagicMock()
        svc.get_error_logs = AsyncMock(
            return_value={
                "errors": [
                    {
                        "log_id": "id_1",
                        "status_code": 500,
                        "event_code": "internal_error",
                        "message": "DB failed",
                        "path": "/api/users",
                        "method": "POST",
                        "logged_at": "2024-01-15T10:30:00Z",
                        "log_data": {
                            "message": "DB failed",
                            "log_level": "ERROR",
                            "details": {"db": "users"},
                        },
                    },
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total": 1,
                    "total_pages": 1,
                },
            }
        )
        return svc

    @pytest.mark.asyncio
    async def test_get_logs_returns_logs_and_pagination(self, mock_service):
        """get_logs returns LogsResponse with logs and pagination from service."""
        with patch(
            "jvspatial.logging.endpoints.get_logging_service",
            return_value=mock_service,
        ):
            response = await get_logs(
                category=None,
                start_date=None,
                end_date=None,
                agent_id=None,
                page=1,
                page_size=50,
            )
        assert isinstance(response, LogsResponse)
        assert len(response.logs) == 1
        assert response.logs[0].log_id == "id_1"
        assert response.logs[0].event_code == "internal_error"
        assert response.logs[0].status_code == 500
        assert response.logs[0].message == "DB failed"
        assert response.logs[0].log_data.get("details", {}).get("db") == "users"
        assert response.pagination.page == 1
        assert response.pagination.total == 1

    @pytest.mark.asyncio
    async def test_get_logs_coerces_none_status_code_to_zero(self, mock_service):
        """get_logs coerces None status_code from service to 0 for LogEntry."""
        mock_service.get_error_logs = AsyncMock(
            return_value={
                "errors": [
                    {
                        "log_id": "id_none_status",
                        "status_code": None,
                        "event_code": "custom_event",
                        "message": "Non-HTTP log",
                        "path": "",
                        "method": "",
                        "logged_at": "2024-01-15T10:30:00Z",
                        "log_data": {"message": "Non-HTTP log", "log_level": "INFO"},
                    },
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total": 1,
                    "total_pages": 1,
                },
            }
        )
        with patch(
            "jvspatial.logging.endpoints.get_logging_service",
            return_value=mock_service,
        ):
            response = await get_logs(
                category=None,
                start_date=None,
                end_date=None,
                agent_id=None,
                page=1,
                page_size=50,
            )
        assert len(response.logs) == 1
        assert response.logs[0].status_code == 0
        assert response.logs[0].event_code == "custom_event"

    @pytest.mark.asyncio
    async def test_get_logs_empty_result_when_no_errors(self, mock_service):
        """get_logs returns empty logs list when service returns no errors."""
        mock_service.get_error_logs = AsyncMock(
            return_value={
                "errors": [],
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total": 0,
                    "total_pages": 0,
                },
            }
        )
        with patch(
            "jvspatial.logging.endpoints.get_logging_service",
            return_value=mock_service,
        ):
            response = await get_logs(
                category=None,
                start_date=None,
                end_date=None,
                agent_id=None,
                page=1,
                page_size=50,
            )
        assert response.logs == []
        assert response.pagination.total == 0
        assert response.pagination.total_pages == 0

    @pytest.mark.asyncio
    async def test_get_logs_passes_filters_to_service(self, mock_service):
        """get_logs passes category, dates, agent_id, page, page_size to service."""
        with patch(
            "jvspatial.logging.endpoints.get_logging_service",
            return_value=mock_service,
        ):
            await get_logs(
                category="ERROR",
                start_date="2024-01-01T00:00:00Z",
                end_date="2024-01-31T23:59:59Z",
                agent_id="agent_456",
                page=2,
                page_size=25,
            )
        mock_service.get_error_logs.assert_called_once()
        call_kw = mock_service.get_error_logs.call_args[1]
        assert call_kw.get("log_level") == "ERROR"
        assert call_kw.get("agent_id") == "agent_456"
        assert call_kw.get("page") == 2
        assert call_kw.get("page_size") == 25
        assert call_kw.get("start_time") is not None
        assert call_kw.get("end_time") is not None

    @pytest.mark.asyncio
    async def test_get_logs_missing_keys_use_defaults(self, mock_service):
        """get_logs uses defaults for missing entry keys (log_data, event_code, etc.)."""
        mock_service.get_error_logs = AsyncMock(
            return_value={
                "errors": [
                    {
                        "log_id": "minimal",
                        "status_code": 200,
                        "event_code": "ok",
                        "message": "OK",
                        "path": "/x",
                        "method": "GET",
                        "logged_at": "2024-01-01T00:00:00Z",
                        "log_data": {},
                    },
                ],
                "pagination": {
                    "page": 1,
                    "page_size": 50,
                    "total": 1,
                    "total_pages": 1,
                },
            }
        )
        with patch(
            "jvspatial.logging.endpoints.get_logging_service",
            return_value=mock_service,
        ):
            response = await get_logs(
                category=None,
                start_date=None,
                end_date=None,
                agent_id=None,
                page=1,
                page_size=50,
            )
        assert len(response.logs) == 1
        assert response.logs[0].log_level == "ERROR"  # default when not in log_data
        assert response.logs[0].log_data == {}
        assert response.logs[0].agent_id is None

    @pytest.mark.asyncio
    async def test_get_logs_on_exception_returns_empty_response(self, mock_service):
        """get_logs returns empty LogsResponse with zero pagination on exception."""
        mock_service.get_error_logs = AsyncMock(
            side_effect=RuntimeError("DB unavailable")
        )
        with patch(
            "jvspatial.logging.endpoints.get_logging_service",
            return_value=mock_service,
        ):
            response = await get_logs(
                category=None,
                start_date=None,
                end_date=None,
                agent_id=None,
                page=1,
                page_size=50,
            )
        assert response.logs == []
        assert response.pagination.total == 0
        assert response.pagination.total_pages == 0
        assert response.pagination.page == 1
        assert response.pagination.page_size == 50
