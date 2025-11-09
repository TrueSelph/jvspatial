"""URL proxy manager for secure file access.

This module provides the URLProxyManager class for creating and managing
URL proxies that provide temporary, secure access to files.
"""

import asyncio
import logging
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, cast

from jvspatial.core.context import GraphContext, get_default_context

from ..exceptions import (
    AccessDeniedError,
    FileNotFoundError,
    StorageError,
)
from ..models import URLProxy

logger = logging.getLogger(__name__)


class URLProxyManager:
    """Manager for URL proxy operations.

    Provides high-level operations for creating, managing, and accessing
    URL proxies for secure file access. Uses the jvspatial database system
    for persistence and the URLProxy entity for data modeling.

    Features:
        - Cryptographically secure code generation
        - Automatic expiration handling
        - Access tracking and statistics
        - One-time URL support
        - Metadata storage

    Example:
        >>> from jvspatial.storage.managers import URLProxyManager
        >>> from datetime import timedelta
        >>>
        >>> manager = URLProxyManager()
        >>>
        >>> # Create a proxy
        >>> proxy = manager.create_proxy(
        ...     file_path="uploads/document.pdf",
        ...     expires_in=3600,  # 1 hour
        ...     metadata={"user_id": "user123"}
        ... )
        >>> print(f"Access via: /p/{proxy.code}")
        >>>
        >>> # Resolve a proxy
        >>> file_path, metadata = manager.resolve_proxy(proxy.code)
        >>>
        >>> # Revoke a proxy
        >>> await manager.revoke_proxy(proxy.code)
    """

    _lock = asyncio.Lock()
    _indexes_created = False

    def __init__(self, context: Optional[GraphContext] = None):
        """Initialize URL proxy manager.

        Args:
            context: GraphContext instance. If None, uses default context.
        """
        self._context = context

    @property
    async def context(self) -> GraphContext:
        """Get the GraphContext instance.

        Returns:
            GraphContext instance for database operations
        """
        if self._context is None:
            self._context = get_default_context()
        return self._context

    @classmethod
    async def _ensure_indexes(cls, context: GraphContext) -> None:
        """Ensure MongoDB indexes are created for url_proxy collection.

        Creates indexes for:
        - Unique index on code
        - Index on active status and code
        - TTL index on expires_at for automatic cleanup

        Args:
            context: GraphContext instance
        """
        if cls._indexes_created:
            return

        async with cls._lock:
            if cls._indexes_created:
                return  # Double-check locking

            try:
                db = context.database

                # Check if database has create_index method
                if hasattr(db, "create_index"):
                    # Create unique index on code
                    await db.create_index("url_proxy", "context.code", unique=True)

                    # Create compound index for active queries
                    await db.create_index(
                        "url_proxy", [("context.active", 1), ("context.code", 1)]
                    )

                    # Create TTL index for automatic expiration
                    # Note: TTL indexes work at document level, not nested fields
                    # This may need database-specific implementation
                    await db.create_index(
                        "url_proxy", "context.expires_at", expireAfterSeconds=0
                    )

                    logger.info("Created indexes for url_proxy collection")

                cls._indexes_created = True

            except Exception as e:
                logger.warning(f"Could not create indexes for url_proxy: {e}")
                # Don't fail if indexes can't be created

    async def create_proxy(
        self,
        file_path: str,
        expires_in: int = 3600,
        one_time: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        code_length: int = 12,
    ) -> URLProxy:
        """Create a new URL proxy for a file.

        Generates a cryptographically secure random code and creates
        a new URLProxy entity in the database.

        Args:
            file_path: Path to the file to proxy
            expires_in: Expiration time in seconds (default: 3600 = 1 hour)
            one_time: If True, proxy is deactivated after first access
            metadata: Optional metadata dict (user_id, IP, tags, etc.)
            code_length: Length of the generated code (default: 12)

        Returns:
            Created URLProxy instance

        Raises:
            StorageError: If proxy creation fails

        Example:
            >>> proxy = manager.create_proxy(
            ...     file_path="uploads/doc.pdf",
            ...     expires_in=7200,
            ...     one_time=True,
            ...     metadata={"user": "alice", "ip": "192.168.1.1"}
            ... )
        """
        # Ensure indexes are created
        context = await self.context
        await self._ensure_indexes(context)

        # Generate unique code
        max_attempts = 5
        code = None

        for attempt in range(max_attempts):
            # Generate cryptographically secure code
            code = secrets.token_urlsafe(code_length)

            # Check if code already exists (extremely rare but handle it)
            existing = await URLProxy.find_by_code(code)
            if not existing:
                break

            logger.warning(f"Code collision detected (attempt {attempt + 1}): {code}")
            code = None

        if code is None:
            raise StorageError(
                "Failed to generate unique proxy code after multiple attempts",
                details={"attempts": max_attempts},
            )

        # Calculate expiration time
        created_at = datetime.now()
        expires_at = created_at + timedelta(seconds=expires_in)

        # Create proxy entity
        try:
            proxy = URLProxy(
                code=code,
                file_path=file_path,
                created_at=created_at,
                expires_at=expires_at,
                one_time=one_time,
                metadata=metadata or {},
                active=True,
                access_count=0,
            )

            # Save to database
            proxy._graph_context = context
            await proxy.save()

            logger.info(
                f"Created URL proxy: code={code}, file={file_path}, "
                f"expires={expires_at.isoformat()}, one_time={one_time}"
            )

            return proxy

        except Exception as e:
            logger.error(f"Failed to create URL proxy: {e}")
            raise StorageError(
                f"Failed to create URL proxy: {e}",
                details={"file_path": file_path, "code": code},
            )

    async def get_proxy(self, code: str) -> Optional[URLProxy]:
        """Get a URL proxy by code.

        Retrieves the proxy but does not validate or increment access count.
        Use resolve_proxy() for accessing files through proxies.

        Args:
            code: Proxy code to retrieve

        Returns:
            URLProxy instance if found, None otherwise

        Example:
            >>> proxy = manager.get_proxy("abc123XY")
            >>> if proxy:
            ...     print(f"Proxy for: {proxy.file_path}")
        """
        try:
            proxy = cast(Optional[URLProxy], await URLProxy.find_by_code(code))

            if proxy and proxy.is_expired() and proxy.active:
                # Auto-deactivate expired proxies
                proxy.active = False
                await proxy.save()
                logger.debug(f"Auto-deactivated expired proxy: {code}")

            return proxy

        except Exception as e:
            logger.error(f"Error retrieving proxy {code}: {e}")
            return None

    async def resolve_proxy(
        self, code: str, increment_access: bool = True
    ) -> Tuple[str, Dict[str, Any]]:
        """Resolve a proxy code to a file path.

        Validates the proxy (active, not expired) and optionally increments
        the access count. Handles one-time URLs by deactivating after access.

        Args:
            code: Proxy code to resolve
            increment_access: If True, increment access count and handle one-time URLs

        Returns:
            Tuple of (file_path, metadata)

        Raises:
            FileNotFoundError: If proxy not found
            AccessDeniedError: If proxy is invalid (expired/inactive)

        Example:
            >>> try:
            ...     file_path, metadata = manager.resolve_proxy("abc123XY")
            ...     # Serve file at file_path
            ... except AccessDeniedError:
            ...     # Proxy expired or invalid
            ...     pass
        """
        logger.debug(f"Resolving proxy: {code}")

        # Get proxy
        proxy = await self.get_proxy(code)

        if not proxy:
            logger.warning(f"Proxy not found: {code}")
            raise FileNotFoundError(f"Proxy not found: {code}", file_path=code)

        # Validate proxy
        if not proxy.is_valid():
            reason = "expired" if proxy.is_expired() else "inactive"
            logger.warning(f"Proxy {code} is {reason}")
            raise AccessDeniedError(f"Proxy is {reason}", file_path=proxy.file_path)

        # Increment access if requested
        if increment_access:
            try:
                await proxy.record_access()
                logger.debug(
                    f"Proxy access recorded: {code}, "
                    f"count={proxy.access_count}, one_time={proxy.one_time}"
                )
            except Exception as e:
                logger.error(f"Failed to record proxy access: {e}")
                # Don't fail the resolution if access recording fails

        return proxy.file_path, proxy.metadata

    async def revoke_proxy(self, code: str, reason: str = "") -> bool:
        """Revoke a URL proxy.

        Sets the proxy as inactive and optionally records the reason.

        Args:
            code: Proxy code to revoke
            reason: Optional reason for revocation

        Returns:
            True if proxy was revoked, False if not found

        Example:
            >>> success = manager.revoke_proxy(
            ...     "abc123XY",
            ...     reason="User requested deletion"
            ... )
        """
        try:
            proxy = await URLProxy.find_by_code(code)

            if not proxy:
                logger.warning(f"Cannot revoke - proxy not found: {code}")
                return False

            await proxy.revoke(reason=reason)
            logger.info(f"Revoked proxy: {code}, reason={reason}")
            return True

        except Exception as e:
            logger.error(f"Failed to revoke proxy {code}: {e}")
            return False

    async def cleanup_expired(self) -> int:
        """Clean up expired and inactive proxies.

        Deletes proxies that are expired or inactive. Can be run as
        a background task for maintenance.

        Returns:
            Number of proxies cleaned up

        Example:
            >>> # Run periodic cleanup
            >>> count = manager.cleanup_expired()
            >>> print(f"Cleaned up {count} expired proxies")
        """
        try:
            # Find expired or inactive proxies
            now = datetime.now()

            # Query for expired or inactive proxies
            ctx = await self.context
            results = await ctx.database.find(
                "url_proxy",
                {
                    "$or": [
                        {"context.active": False},
                        {"context.expires_at": {"$lt": now}},
                    ]
                },
            )

            count = 0
            for data in results:
                try:
                    # Delete the proxy document
                    await ctx.database.delete("url_proxy", data["id"])
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to delete proxy {data.get('id')}: {e}")

            if count > 0:
                logger.info(f"Cleaned up {count} expired/inactive proxies")

            return count

        except Exception as e:
            logger.error(f"Failed to cleanup expired proxies: {e}")
            return 0

    async def get_stats(self, code: str) -> Optional[Dict[str, Any]]:
        """Get access statistics for a proxy.

        Args:
            code: Proxy code to get stats for

        Returns:
            Dict with statistics or None if proxy not found

        Example:
            >>> stats = manager.get_stats("abc123XY")
            >>> if stats:
            ...     print(f"Accessed {stats['access_count']} times")
        """
        try:
            proxy = await URLProxy.find_by_code(code)

            if not proxy:
                return None

            return {
                "code": proxy.code,
                "file_path": proxy.file_path,
                "created_at": proxy.created_at.isoformat(),
                "expires_at": proxy.expires_at.isoformat(),
                "access_count": proxy.access_count,
                "last_accessed": (
                    proxy.last_accessed.isoformat() if proxy.last_accessed else None
                ),
                "active": proxy.active,
                "one_time": proxy.one_time,
                "is_expired": proxy.is_expired(),
                "is_valid": proxy.is_valid(),
                "metadata": proxy.metadata,
            }

        except Exception as e:
            logger.error(f"Failed to get stats for proxy {code}: {e}")
            return None

    async def list_active_proxies(
        self, file_path: Optional[str] = None, limit: int = 100
    ) -> List[URLProxy]:
        """List active proxies, optionally filtered by file path.

        Args:
            file_path: Optional file path to filter by
            limit: Maximum number of results (default: 100)

        Returns:
            List of active URLProxy instances

        Example:
            >>> # List all active proxies
            >>> proxies = manager.list_active_proxies()
            >>>
            >>> # List proxies for specific file
            >>> proxies = manager.list_active_proxies("uploads/doc.pdf")
        """
        try:
            if file_path:
                # Use the URLProxy method for file-specific search
                file_proxies = await URLProxy.find_active_for_file(file_path)
                return cast(List[URLProxy], file_proxies[:limit])
            else:
                # Query for all active, non-expired proxies
                ctx = await self.context
                results = await ctx.database.find("url_proxy", {"context.active": True})

                active_proxies: List[URLProxy] = []
                for data in results[:limit]:
                    try:
                        proxy = await ctx._deserialize_entity(URLProxy, data)
                        if proxy and not proxy.is_expired():
                            active_proxies.append(cast(URLProxy, proxy))
                    except Exception:
                        continue

                return active_proxies

        except Exception as e:
            logger.error(f"Failed to list active proxies: {e}")
            return []


# Convenience function to get a URLProxyManager instance
def get_proxy_manager(context: Optional[GraphContext] = None) -> URLProxyManager:
    """Get a URLProxyManager instance.

    Args:
        context: Optional GraphContext instance

    Returns:
        URLProxyManager instance

    Example:
        >>> from jvspatial.storage.managers import get_proxy_manager
        >>>
        >>> manager = get_proxy_manager()
        >>> proxy = manager.create_proxy("uploads/file.pdf")
    """
    return URLProxyManager(context=context)
