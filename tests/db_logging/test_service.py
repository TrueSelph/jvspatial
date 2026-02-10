"""Tests for jvspatial.logging.service (BaseLoggingService, get_logging_service)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.logging.service import BaseLoggingService, get_logging_service


class TestBaseLoggingServiceNoDatabase:
    """Test BaseLoggingService when logging database is not available."""

    @pytest.fixture
    def service(self):
        """Service instance with no database (default _get_log_database returns None)."""
        with patch(
            "jvspatial.logging.service.get_database_manager",
            return_value=MagicMock(list_databases=MagicMock(return_value=[])),
        ):
            svc = BaseLoggingService(database_name="test_logs")
            svc._log_db = None
            return svc

    @pytest.mark.asyncio
    async def test_get_error_logs_returns_empty_when_no_db(self, service):
        """get_error_logs returns empty errors and pagination when database unavailable."""
        result = await service.get_error_logs(
            event_code=None,
            page=1,
            page_size=50,
        )
        assert result["errors"] == []
        assert result["pagination"]["page"] == 1
        assert result["pagination"]["page_size"] == 50
        assert result["pagination"]["total"] == 0

    @pytest.mark.asyncio
    async def test_get_error_logs_passes_event_code_filter_when_db_available(self):
        """get_error_logs builds query with event_code when database is available."""
        mock_db = MagicMock()
        mock_context = MagicMock()
        mock_context.database.find = AsyncMock(return_value=[])
        with patch(
            "jvspatial.logging.service.GraphContext",
            return_value=mock_context,
        ), patch(
            "jvspatial.logging.service.get_database_manager",
            return_value=MagicMock(
                list_databases=MagicMock(return_value=["logs"]),
                get_database=MagicMock(return_value=mock_db),
            ),
        ):
            svc = BaseLoggingService(database_name="logs")
            result = await svc.get_error_logs(
                event_code="validation_error",
                page=1,
                page_size=10,
            )
        assert result["errors"] == []
        assert result["pagination"]["total"] == 0
        # find("object", query) called with query containing event_code
        mock_context.database.find.assert_called_once()
        call_args = mock_context.database.find.call_args[0]
        assert call_args[0] == "object"
        query = call_args[1]
        assert query.get("context.event_code") == "validation_error"
        assert query.get("entity") == "DBLog"

    @pytest.mark.asyncio
    async def test_log_error_does_not_raise_when_no_db(self, service):
        """log_error completes without raising when database unavailable."""
        await service.log_error(
            event_code="test_error",
            message="Test message",
            status_code=500,
        )

    @pytest.mark.asyncio
    async def test_log_custom_calls_log_error_with_event_code(self, service):
        """log_custom passes event_code to log_error."""
        with patch.object(
            service,
            "log_error",
            new_callable=AsyncMock,
        ) as mock_log_error:
            await service.log_custom(
                event_code="user_action",
                message="User did something",
            )
            mock_log_error.assert_called_once()
            call_kw = mock_log_error.call_args[1]
            assert call_kw.get("event_code") == "user_action"
            assert call_kw.get("message") == "User did something"
            assert call_kw.get("log_level") == "CUSTOM"

    @pytest.mark.asyncio
    async def test_purge_error_logs_returns_deleted_zero_when_no_db(self, service):
        """purge_error_logs returns deleted=0 when database unavailable."""
        result = await service.purge_error_logs(event_code="old_event")
        assert result["deleted"] == 0
        assert "error" in result


class TestGetLoggingService:
    """Test get_logging_service factory."""

    def test_returns_base_logging_service_instance(self):
        """get_logging_service returns an instance of BaseLoggingService."""
        with patch("jvspatial.logging.service._logging_service", None):
            # Force new instance for this test
            svc = get_logging_service()
            assert isinstance(svc, BaseLoggingService)

    def test_accepts_database_name(self):
        """get_logging_service accepts database_name parameter."""
        with patch("jvspatial.logging.service._logging_service", None):
            svc = get_logging_service(database_name="custom_logs")
            assert svc._database_name == "custom_logs"
