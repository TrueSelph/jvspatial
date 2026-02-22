"""Token cleanup service for removing expired tokens and blacklist entries."""

import logging
from datetime import datetime
from typing import Optional

from jvspatial.api.auth.models import RefreshToken, TokenBlacklist
from jvspatial.core.context import GraphContext
from jvspatial.db import get_prime_database


class TokenCleanupService:
    """Service for cleaning up expired tokens and blacklist entries.

    Provides methods to remove expired refresh tokens and blacklist entries
    to prevent database bloat.
    """

    def __init__(self, context: Optional[GraphContext] = None):
        """Initialize the cleanup service.

        Args:
            context: GraphContext instance for database operations.
                    If None, creates a context using the prime database.
        """
        if context is None:
            prime_db = get_prime_database()
            self.context = GraphContext(database=prime_db)
        else:
            # Ensure context uses prime database for auth operations
            prime_db = get_prime_database()
            self.context = GraphContext(database=prime_db)
        self._logger = logging.getLogger(__name__)

    async def cleanup_expired_blacklist_entries(self) -> int:
        """Remove expired blacklist entries.

        Returns:
            Number of entries removed
        """
        try:
            await self.context.ensure_indexes(TokenBlacklist)
            now = datetime.utcnow()

            # Get all blacklist entries and filter expired ones
            # This approach works across all database backends
            collection, final_query = await TokenBlacklist._build_database_query(
                self.context, {}, {}
            )

            results = await self.context.database.find(collection, final_query)

            removed_count = 0
            for data in results:
                try:
                    blacklist_entry = await self.context._deserialize_entity(
                        TokenBlacklist, data
                    )
                    if blacklist_entry and blacklist_entry.expires_at < now:
                        blacklist_entry._graph_context = self.context
                        await self.context.delete(blacklist_entry)
                        removed_count += 1
                except Exception as e:
                    self._logger.warning(f"Error deleting blacklist entry: {e}")
                    continue

            if removed_count > 0:
                self._logger.info(
                    f"Cleaned up {removed_count} expired blacklist entries"
                )

            return removed_count
        except Exception as e:
            self._logger.error(f"Error cleaning up expired blacklist entries: {e}")
            return 0

    async def cleanup_expired_refresh_tokens(self) -> int:
        """Remove expired refresh tokens.

        Returns:
            Number of tokens removed
        """
        try:
            await self.context.ensure_indexes(RefreshToken)
            now = datetime.utcnow()

            # Get all refresh tokens and filter expired ones
            # This approach works across all database backends
            collection, final_query = await RefreshToken._build_database_query(
                self.context, {}, {}
            )

            results = await self.context.database.find(collection, final_query)

            removed_count = 0
            for data in results:
                try:
                    refresh_token = await self.context._deserialize_entity(
                        RefreshToken, data
                    )
                    if refresh_token and refresh_token.expires_at < now:
                        refresh_token._graph_context = self.context
                        await self.context.delete(refresh_token)
                        removed_count += 1
                except Exception as e:
                    self._logger.warning(f"Error deleting refresh token: {e}")
                    continue

            if removed_count > 0:
                self._logger.info(f"Cleaned up {removed_count} expired refresh tokens")

            return removed_count
        except Exception as e:
            self._logger.error(f"Error cleaning up expired refresh tokens: {e}")
            return 0

    async def cleanup_all(self) -> dict:
        """Run all cleanup operations.

        Returns:
            Dictionary with cleanup results
        """
        blacklist_removed = await self.cleanup_expired_blacklist_entries()
        refresh_tokens_removed = await self.cleanup_expired_refresh_tokens()

        return {
            "blacklist_entries_removed": blacklist_removed,
            "refresh_tokens_removed": refresh_tokens_removed,
            "total_removed": blacklist_removed + refresh_tokens_removed,
        }


async def cleanup_tokens_task() -> dict:
    """Async function for scheduled token cleanup.

    This function can be registered with the scheduler to run periodically.

    Returns:
        Dictionary with cleanup results
    """
    service = TokenCleanupService()
    return await service.cleanup_all()


async def register_cleanup_task(scheduler_service=None) -> bool:
    """Register the token cleanup task with the scheduler.

    Args:
        scheduler_service: Optional SchedulerService instance.
                          If None, attempts to get from app context.

    Returns:
        True if task was registered, False otherwise
    """
    try:
        from jvspatial.api.integrations.scheduler.models import (
            ScheduleConfig,
            ScheduledTask,
        )
        from jvspatial.api.integrations.scheduler.scheduler import SchedulerService

        # Get scheduler service if not provided
        if scheduler_service is None:
            # Try to get from app context (if available)
            # This is a best-effort approach
            scheduler_service = getattr(cleanup_tokens_task, "_scheduler_service", None)
            if scheduler_service is None:
                # Create a new scheduler service instance
                scheduler_service = SchedulerService()

        # Create scheduled task for daily cleanup
        task = ScheduledTask(
            task_id="token-cleanup",
            task_type="async_function",
            schedule=ScheduleConfig(schedule_spec="daily at 02:00"),
            enabled=True,
            description="Clean up expired refresh tokens and blacklist entries",
            function_ref=cleanup_tokens_task,
        )

        # Register the task
        await scheduler_service.register_task(task)

        # Start scheduler if not already running
        if not scheduler_service.is_running:
            scheduler_service.start()

        return True
    except ImportError:
        # Scheduler not available
        import logging

        logger = logging.getLogger(__name__)
        logger.warning(
            "Scheduler not available. Token cleanup task not registered. "
            "Install scheduler dependencies or register manually."
        )
        return False
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Failed to register token cleanup task: {e}")
        return False


__all__ = ["TokenCleanupService", "cleanup_tokens_task", "register_cleanup_task"]
