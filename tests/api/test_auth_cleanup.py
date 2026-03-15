"""Tests for token cleanup service."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from jvspatial.api.auth.cleanup import (
    TokenCleanupService,
    cleanup_tokens_task,
    register_cleanup_task,
)
from jvspatial.api.auth.models import RefreshToken, TokenBlacklist
from jvspatial.core.context import GraphContext


@pytest.fixture
def cleanup_service():
    """Create cleanup service instance."""
    context = MagicMock(spec=GraphContext)
    return TokenCleanupService(context)


class TestTokenCleanupService:
    """Test token cleanup service functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_blacklist_entries(self, cleanup_service):
        """Test cleaning up expired blacklist entries."""
        now = datetime.now(timezone.utc)
        expired_time = now - timedelta(days=1)

        # Mock expired blacklist entry
        mock_entry = MagicMock()
        mock_entry.expires_at = expired_time
        mock_entry._graph_context = cleanup_service.context

        # Mock context methods
        cleanup_service.context.ensure_indexes = AsyncMock()
        cleanup_service.context.database.find = AsyncMock(
            return_value=[{"id": "entry1", "expires_at": expired_time}]
        )
        cleanup_service.context._deserialize_entity = AsyncMock(return_value=mock_entry)
        cleanup_service.context.delete = AsyncMock()

        removed_count = await cleanup_service.cleanup_expired_blacklist_entries()

        assert removed_count == 1
        cleanup_service.context.delete.assert_called_once_with(mock_entry)

    @pytest.mark.asyncio
    async def test_cleanup_expired_blacklist_entries_none_expired(
        self, cleanup_service
    ):
        """Test cleanup when no entries are expired."""
        # Mock context methods - no expired entries
        cleanup_service.context.ensure_indexes = AsyncMock()
        cleanup_service.context.database.find = AsyncMock(return_value=[])

        removed_count = await cleanup_service.cleanup_expired_blacklist_entries()

        assert removed_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_expired_refresh_tokens(self, cleanup_service):
        """Test cleaning up expired refresh tokens."""
        now = datetime.now(timezone.utc)
        expired_time = now - timedelta(days=1)

        # Mock expired refresh token
        mock_token = MagicMock()
        mock_token.expires_at = expired_time
        mock_token._graph_context = cleanup_service.context

        # Mock context methods
        cleanup_service.context.ensure_indexes = AsyncMock()
        cleanup_service.context.database.find = AsyncMock(
            return_value=[{"id": "token1", "expires_at": expired_time}]
        )
        cleanup_service.context._deserialize_entity = AsyncMock(return_value=mock_token)
        cleanup_service.context.delete = AsyncMock()

        removed_count = await cleanup_service.cleanup_expired_refresh_tokens()

        assert removed_count == 1
        cleanup_service.context.delete.assert_called_once_with(mock_token)

    @pytest.mark.asyncio
    async def test_cleanup_expired_refresh_tokens_none_expired(self, cleanup_service):
        """Test cleanup when no refresh tokens are expired."""
        # Mock context methods - no expired tokens
        cleanup_service.context.ensure_indexes = AsyncMock()
        cleanup_service.context.database.find = AsyncMock(return_value=[])

        removed_count = await cleanup_service.cleanup_expired_refresh_tokens()

        assert removed_count == 0

    @pytest.mark.asyncio
    async def test_cleanup_all(self, cleanup_service):
        """Test running all cleanup operations."""
        # Mock cleanup methods
        cleanup_service.cleanup_expired_blacklist_entries = AsyncMock(return_value=5)
        cleanup_service.cleanup_expired_refresh_tokens = AsyncMock(return_value=3)

        result = await cleanup_service.cleanup_all()

        assert result["blacklist_entries_removed"] == 5
        assert result["refresh_tokens_removed"] == 3
        assert result["total_removed"] == 8

    @pytest.mark.asyncio
    async def test_cleanup_handles_errors_gracefully(self, cleanup_service):
        """Test that cleanup handles errors gracefully."""
        # Mock context to raise an error
        cleanup_service.context.ensure_indexes = AsyncMock(
            side_effect=Exception("DB error")
        )

        # Should not raise, but return 0
        removed_count = await cleanup_service.cleanup_expired_blacklist_entries()
        assert removed_count == 0


class TestCleanupTask:
    """Test cleanup task function."""

    @pytest.mark.asyncio
    async def test_cleanup_tokens_task(self):
        """Test the cleanup task function."""
        # Mock the cleanup service
        with patch(
            "jvspatial.api.auth.cleanup.TokenCleanupService"
        ) as mock_service_class:
            mock_service = MagicMock()
            mock_service.cleanup_all = AsyncMock(
                return_value={
                    "blacklist_entries_removed": 2,
                    "refresh_tokens_removed": 1,
                    "total_removed": 3,
                }
            )
            mock_service_class.return_value = mock_service

            result = await cleanup_tokens_task()

            assert result["blacklist_entries_removed"] == 2
            assert result["refresh_tokens_removed"] == 1
            assert result["total_removed"] == 3


class TestCleanupTaskRegistration:
    """Test cleanup task registration with scheduler."""

    @pytest.mark.asyncio
    async def test_register_cleanup_task_success(self):
        """Test successful registration of cleanup task."""
        # Mock scheduler service
        mock_scheduler = MagicMock()
        mock_scheduler.is_running = False
        mock_scheduler.register_task = AsyncMock()
        mock_scheduler.start = MagicMock()

        with patch(
            "jvspatial.api.integrations.scheduler.scheduler.SchedulerService",
            return_value=mock_scheduler,
        ):
            result = await register_cleanup_task(mock_scheduler)

            assert result is True
            mock_scheduler.register_task.assert_called_once()
            mock_scheduler.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_cleanup_task_scheduler_not_available(self):
        """Test registration when scheduler is not available."""
        with patch(
            "jvspatial.api.integrations.scheduler.scheduler.SchedulerService",
            side_effect=ImportError,
        ):
            result = await register_cleanup_task()

            assert result is False

    @pytest.mark.asyncio
    async def test_register_cleanup_task_already_running(self):
        """Test registration when scheduler is already running."""
        # Mock scheduler service
        mock_scheduler = MagicMock()
        mock_scheduler.is_running = True  # Already running
        mock_scheduler.register_task = AsyncMock()
        mock_scheduler.start = MagicMock()

        with patch(
            "jvspatial.api.integrations.scheduler.scheduler.SchedulerService",
            return_value=mock_scheduler,
        ):
            result = await register_cleanup_task(mock_scheduler)

            assert result is True
            mock_scheduler.register_task.assert_called_once()
            mock_scheduler.start.assert_not_called()  # Should not start if already running
