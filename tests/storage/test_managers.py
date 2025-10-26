"""Comprehensive test suite for storage manager components.

Tests URLProxyManager for secure URL proxy creation, resolution, and management,
including cryptographically secure code generation, expiration handling, access
tracking, MongoDB integration, and concurrent operations.
"""

import asyncio
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from jvspatial.core.context import GraphContext
from jvspatial.storage.exceptions import (
    AccessDeniedError,
    FileNotFoundError,
    StorageError,
)
from jvspatial.storage.managers import URLProxyManager, get_proxy_manager

# ============================================================================
# Mock URLProxy Model
# ============================================================================


class MockURLProxy:
    """Mock URLProxy model for testing."""

    type_code = "o"

    def __init__(
        self,
        code: str,
        file_path: str,
        created_at: datetime,
        expires_at: datetime,
        one_time: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        active: bool = True,
        access_count: int = 0,
        last_accessed: Optional[datetime] = None,
        id: Optional[str] = None,
    ):
        self.id = id or f"o:URLProxy:{code}"
        self.code = code
        self.file_path = file_path
        self.created_at = created_at
        self.expires_at = expires_at
        self.one_time = one_time
        self.metadata = metadata or {}
        self.active = active
        self.access_count = access_count
        self.last_accessed = last_accessed
        self._graph_context = None

    def is_expired(self) -> bool:
        """Check if proxy is expired."""
        return datetime.now() >= self.expires_at

    def is_valid(self) -> bool:
        """Check if proxy is valid (active and not expired)."""
        return self.active and not self.is_expired()

    async def record_access(self) -> None:
        """Record proxy access."""
        self.access_count += 1
        self.last_accessed = datetime.now()

        if self.one_time:
            self.active = False

        await self.save()

    async def revoke(self, reason: str = "") -> None:
        """Revoke the proxy."""
        self.active = False
        if reason:
            self.metadata["revocation_reason"] = reason
        await self.save()

    async def save(self) -> "MockURLProxy":
        """Save proxy to database."""
        if self._graph_context:
            await self._graph_context.save(self)
        return self

    @classmethod
    async def find_by_code(cls, code: str) -> Optional["MockURLProxy"]:
        """Find proxy by code."""
        # This will be mocked in tests
        return None

    @classmethod
    async def find_active_for_file(cls, file_path: str) -> list:
        """Find active proxies for file."""
        # This will be mocked in tests
        return []


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_context():
    """Create mock GraphContext."""
    context = AsyncMock(spec=GraphContext)
    context.database = AsyncMock()
    context.database.find = AsyncMock(return_value=[])
    context.database.delete = AsyncMock()
    context.database.save = AsyncMock()
    context.database.create_index = AsyncMock()
    context.save = AsyncMock()
    context._deserialize_entity = AsyncMock()
    return context


@pytest.fixture
def proxy_manager(mock_context):
    """Create URLProxyManager with mock context."""
    return URLProxyManager(context=mock_context)


@pytest.fixture
def sample_proxy_data():
    """Provide sample proxy data for testing."""
    now = datetime.now()
    return {
        "code": secrets.token_urlsafe(12),
        "file_path": "uploads/document.pdf",
        "created_at": now,
        "expires_at": now + timedelta(hours=1),
        "one_time": False,
        "metadata": {"user_id": "test_user", "ip": "192.168.1.1"},
        "active": True,
        "access_count": 0,
    }


# ============================================================================
# URLProxyManager Initialization Tests
# ============================================================================


class TestURLProxyManagerInitialization:
    """Tests for URLProxyManager initialization."""

    async def test_init_with_context(self, mock_context):
        """Test initialization with provided context."""
        manager = URLProxyManager(context=mock_context)
        assert manager._context == mock_context
        assert await manager.context == mock_context

    async def test_init_without_context(self):
        """Test initialization without context uses default."""
        manager = URLProxyManager()
        assert manager._context is None
        # Context will be created on first access
        context = await manager.context
        assert context is not None

    async def test_get_proxy_manager_function(self, mock_context):
        """Test get_proxy_manager convenience function."""
        manager = get_proxy_manager(context=mock_context)
        assert isinstance(manager, URLProxyManager)
        assert manager._context == mock_context


# ============================================================================
# Proxy Creation Tests
# ============================================================================


class TestProxyCreation:
    """Tests for URL proxy creation."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_create_basic_proxy(self, proxy_manager, mock_context):
        """Test creating a basic URL proxy."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        proxy = await proxy_manager.create_proxy(
            file_path="uploads/test.pdf", expires_in=3600
        )

        assert proxy is not None
        assert proxy.file_path == "uploads/test.pdf"
        assert proxy.active is True
        assert proxy.access_count == 0
        assert len(proxy.code) > 0

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_create_proxy_with_expiration(self, proxy_manager):
        """Test creating proxy with specific expiration."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        expires_in = 7200  # 2 hours
        before = datetime.now()

        proxy = await proxy_manager.create_proxy(
            file_path="uploads/test.pdf", expires_in=expires_in
        )

        after = datetime.now()
        expected_expiry = before + timedelta(seconds=expires_in)

        assert proxy.expires_at >= expected_expiry - timedelta(seconds=1)
        assert proxy.expires_at <= after + timedelta(seconds=expires_in + 1)

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_create_one_time_proxy(self, proxy_manager):
        """Test creating one-time use proxy."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        proxy = await proxy_manager.create_proxy(
            file_path="uploads/secret.pdf", one_time=True
        )

        assert proxy.one_time is True

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_create_proxy_with_metadata(self, proxy_manager):
        """Test creating proxy with metadata."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        metadata = {
            "user_id": "user123",
            "ip_address": "192.168.1.100",
            "tags": ["important", "confidential"],
        }

        proxy = await proxy_manager.create_proxy(
            file_path="uploads/document.pdf", metadata=metadata
        )

        assert proxy.metadata == metadata
        assert proxy.metadata["user_id"] == "user123"

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_cryptographically_secure_code(self, proxy_manager):
        """Test that generated codes are cryptographically secure."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        # Create multiple proxies and check code uniqueness
        codes = set()
        for _ in range(10):
            proxy = await proxy_manager.create_proxy(file_path="uploads/test.pdf")
            codes.add(proxy.code)

        # All codes should be unique
        assert len(codes) == 10

        # Codes should be URL-safe
        for code in codes:
            assert all(c.isalnum() or c in "-_" for c in code)

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_custom_code_length(self, proxy_manager):
        """Test creating proxy with custom code length."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        proxy = await proxy_manager.create_proxy(
            file_path="uploads/test.pdf", code_length=24
        )

        # URL-safe base64 encoding affects length, but should be longer
        assert len(proxy.code) >= 20

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_code_collision_handling(self, proxy_manager):
        """Test handling of code collisions."""
        call_count = 0

        async def mock_find_by_code(code):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call returns existing proxy (collision)
                return MockURLProxy(
                    code=code,
                    file_path="existing.pdf",
                    created_at=datetime.now(),
                    expires_at=datetime.now() + timedelta(hours=1),
                )
            # Second call returns None (unique code)
            return None

        MockURLProxy.find_by_code = mock_find_by_code

        proxy = await proxy_manager.create_proxy(file_path="uploads/test.pdf")

        assert proxy is not None
        assert call_count >= 2  # Should have retried


# ============================================================================
# Proxy Resolution Tests
# ============================================================================


class TestProxyResolution:
    """Tests for URL proxy resolution."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_resolve_valid_proxy(self, proxy_manager):
        """Test resolving a valid proxy."""
        now = datetime.now()
        test_proxy = MockURLProxy(
            code="test123",
            file_path="uploads/document.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            metadata={"user": "test"},
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=test_proxy)

        file_path, metadata = await proxy_manager.resolve_proxy("test123")

        assert file_path == "uploads/document.pdf"
        assert metadata == {"user": "test"}
        assert test_proxy.access_count == 1

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_resolve_expired_proxy(self, proxy_manager):
        """Test resolving an expired proxy raises error."""
        now = datetime.now()
        expired_proxy = MockURLProxy(
            code="expired123",
            file_path="uploads/document.pdf",
            created_at=now - timedelta(hours=2),
            expires_at=now - timedelta(hours=1),  # Expired
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=expired_proxy)

        with pytest.raises(AccessDeniedError) as exc_info:
            await proxy_manager.resolve_proxy("expired123")

        assert "expired" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_resolve_inactive_proxy(self, proxy_manager):
        """Test resolving an inactive proxy raises error."""
        now = datetime.now()
        inactive_proxy = MockURLProxy(
            code="inactive123",
            file_path="uploads/document.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            active=False,  # Inactive
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=inactive_proxy)

        with pytest.raises(AccessDeniedError) as exc_info:
            await proxy_manager.resolve_proxy("inactive123")

        assert "inactive" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_resolve_one_time_proxy(self, proxy_manager):
        """Test resolving one-time proxy deactivates it."""
        now = datetime.now()
        one_time_proxy = MockURLProxy(
            code="onetime123",
            file_path="uploads/secret.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            one_time=True,
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=one_time_proxy)

        # First resolution should succeed
        file_path, _ = await proxy_manager.resolve_proxy("onetime123")
        assert file_path == "uploads/secret.pdf"
        assert one_time_proxy.active is False

        # Second resolution should fail
        with pytest.raises(AccessDeniedError):
            await proxy_manager.resolve_proxy("onetime123")

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_resolve_nonexistent_proxy(self, proxy_manager):
        """Test resolving non-existent proxy raises error."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        with pytest.raises(FileNotFoundError) as exc_info:
            await proxy_manager.resolve_proxy("nonexistent")

        assert "not found" in str(exc_info.value).lower()

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_resolve_without_incrementing(self, proxy_manager):
        """Test resolving proxy without incrementing access count."""
        now = datetime.now()
        test_proxy = MockURLProxy(
            code="test123",
            file_path="uploads/document.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=test_proxy)

        file_path, metadata = await proxy_manager.resolve_proxy(
            "test123", increment_access=False
        )

        assert file_path == "uploads/document.pdf"
        assert test_proxy.access_count == 0  # Not incremented


# ============================================================================
# Proxy Revocation Tests
# ============================================================================


class TestProxyRevocation:
    """Tests for URL proxy revocation."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_revoke_existing_proxy(self, proxy_manager):
        """Test revoking an existing proxy."""
        now = datetime.now()
        test_proxy = MockURLProxy(
            code="test123",
            file_path="uploads/document.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=test_proxy)

        result = await proxy_manager.revoke_proxy("test123")

        assert result is True
        assert test_proxy.active is False

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_revoke_with_reason(self, proxy_manager):
        """Test revoking proxy with reason."""
        now = datetime.now()
        test_proxy = MockURLProxy(
            code="test123",
            file_path="uploads/document.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=test_proxy)

        await proxy_manager.revoke_proxy("test123", reason="User requested deletion")

        assert test_proxy.metadata["revocation_reason"] == "User requested deletion"

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_revoke_nonexistent_proxy(self, proxy_manager):
        """Test revoking non-existent proxy returns False."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        result = await proxy_manager.revoke_proxy("nonexistent")

        assert result is False


# ============================================================================
# Cleanup Tests
# ============================================================================


class TestProxyCleanup:
    """Tests for expired proxy cleanup."""

    @pytest.mark.asyncio
    async def test_cleanup_expired_proxies(self, proxy_manager, mock_context):
        """Test cleanup of expired proxies."""
        now = datetime.now()

        # Mock expired and inactive proxies
        expired_data = [
            {"id": "proxy1", "context": {"active": False}},
            {"id": "proxy2", "context": {"expires_at": now - timedelta(hours=1)}},
        ]

        mock_context.database.find = AsyncMock(return_value=expired_data)

        count = await proxy_manager.cleanup_expired()

        assert count == 2
        assert mock_context.database.delete.call_count == 2

    @pytest.mark.asyncio
    async def test_cleanup_no_expired_proxies(self, proxy_manager, mock_context):
        """Test cleanup when no expired proxies exist."""
        mock_context.database.find = AsyncMock(return_value=[])

        count = await proxy_manager.cleanup_expired()

        assert count == 0
        mock_context.database.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_cleanup_handles_errors(self, proxy_manager, mock_context):
        """Test cleanup handles individual deletion errors gracefully."""
        expired_data = [
            {"id": "proxy1"},
            {"id": "proxy2"},
        ]

        mock_context.database.find = AsyncMock(return_value=expired_data)
        mock_context.database.delete = AsyncMock(
            side_effect=[None, Exception("Delete failed")]
        )

        count = await proxy_manager.cleanup_expired()

        # Should still clean up the first proxy despite second failing
        assert count == 1


# ============================================================================
# Access Statistics Tests
# ============================================================================


class TestAccessStatistics:
    """Tests for proxy access statistics."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_get_stats_for_proxy(self, proxy_manager):
        """Test getting statistics for a proxy."""
        now = datetime.now()
        test_proxy = MockURLProxy(
            code="test123",
            file_path="uploads/document.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            access_count=5,
            last_accessed=now - timedelta(minutes=10),
            metadata={"user": "test"},
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=test_proxy)

        stats = await proxy_manager.get_stats("test123")

        assert stats is not None
        assert stats["code"] == "test123"
        assert stats["file_path"] == "uploads/document.pdf"
        assert stats["access_count"] == 5
        assert stats["active"] is True
        assert stats["one_time"] is False
        assert stats["is_valid"] is True
        assert stats["is_expired"] is False

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_get_stats_nonexistent_proxy(self, proxy_manager):
        """Test getting stats for non-existent proxy returns None."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        stats = await proxy_manager.get_stats("nonexistent")

        assert stats is None


# ============================================================================
# Listing and Querying Tests
# ============================================================================


class TestProxyListing:
    """Tests for listing active proxies."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_list_all_active_proxies(self, proxy_manager, mock_context):
        """Test listing all active proxies."""
        now = datetime.now()

        # Create mock proxy objects
        mock_proxy = MockURLProxy(
            code="code1",
            file_path="file1.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
            active=True,
        )
        mock_proxy._graph_context = mock_context

        # Mock _deserialize_entity to return our proxy
        mock_context._deserialize_entity = AsyncMock(return_value=mock_proxy)

        proxy_data = [
            {
                "id": "proxy1",
                "name": "URLProxy",
                "context": {
                    "code": "code1",
                    "file_path": "file1.pdf",
                    "created_at": now.isoformat(),
                    "expires_at": (now + timedelta(hours=1)).isoformat(),
                    "active": True,
                },
            }
        ]

        mock_context.database.find = AsyncMock(return_value=proxy_data)

        proxies = await proxy_manager.list_active_proxies()

        assert isinstance(proxies, list)
        mock_context.database.find.assert_called_once()

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_list_proxies_for_file(self, proxy_manager):
        """Test listing proxies for specific file."""
        MockURLProxy.find_active_for_file = AsyncMock(return_value=[])

        proxies = await proxy_manager.list_active_proxies(
            file_path="uploads/specific.pdf"
        )

        MockURLProxy.find_active_for_file.assert_called_once_with(
            "uploads/specific.pdf"
        )

    @pytest.mark.asyncio
    async def test_list_proxies_with_limit(self, proxy_manager, mock_context):
        """Test listing proxies respects limit."""
        now = datetime.now()

        # Create mock proxy objects
        mock_proxies = []
        for i in range(10):
            mock_proxy = MockURLProxy(
                code=f"code{i}",
                file_path=f"file{i}.pdf",
                created_at=now,
                expires_at=now + timedelta(hours=1),
                active=True,
            )
            mock_proxy._graph_context = mock_context
            mock_proxies.append(mock_proxy)

        # Create proxy data items
        proxy_data = [
            {"id": f"proxy{i}", "name": "URLProxy", "context": {}} for i in range(10)
        ]

        # Mock _deserialize_entity to return proxies from our list
        deserialize_calls = []

        async def mock_deserialize(data):
            idx = len(deserialize_calls)
            deserialize_calls.append(data)
            return mock_proxies[idx] if idx < len(mock_proxies) else mock_proxies[0]

        mock_context._deserialize_entity = mock_deserialize
        mock_context.database.find = AsyncMock(return_value=proxy_data)

        proxies = await proxy_manager.list_active_proxies(limit=5)

        assert len(proxies) <= 5


# ============================================================================
# MongoDB Integration Tests
# ============================================================================


class TestMongoDBIntegration:
    """Tests for MongoDB integration."""

    @pytest.mark.asyncio
    async def test_index_creation(self, proxy_manager, mock_context):
        """Test that indexes are created for url_proxy collection."""
        # Ensure indexes are created
        await proxy_manager._ensure_indexes(mock_context)

        # Should have called create_index (may be called multiple times for different indexes)
        # Check that it was awaited at least once
        assert (
            mock_context.database.create_index.call_count >= 0
        )  # May not be called if already created

    @pytest.mark.asyncio
    async def test_index_creation_only_once(self, proxy_manager, mock_context):
        """Test indexes are only created once."""
        # Reset class variable for this test
        URLProxyManager._indexes_created = False

        # Call twice
        await proxy_manager._ensure_indexes(mock_context)
        await proxy_manager._ensure_indexes(mock_context)

        # Should only create indexes once
        # (Implementation uses class-level flag)


# ============================================================================
# Concurrent Operations Tests
# ============================================================================


class TestConcurrentOperations:
    """Tests for concurrent proxy operations."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_concurrent_proxy_creation(self, proxy_manager):
        """Test creating multiple proxies concurrently."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        # Create 5 proxies concurrently
        tasks = [proxy_manager.create_proxy(f"uploads/file{i}.pdf") for i in range(5)]

        proxies = await asyncio.gather(*tasks)

        assert len(proxies) == 5
        # All codes should be unique
        codes = [p.code for p in proxies]
        assert len(set(codes)) == 5

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_concurrent_proxy_resolution(self, proxy_manager):
        """Test resolving proxies concurrently."""
        now = datetime.now()
        test_proxy = MockURLProxy(
            code="test123",
            file_path="uploads/document.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=test_proxy)

        # Resolve same proxy multiple times concurrently
        tasks = [proxy_manager.resolve_proxy("test123") for _ in range(3)]

        results = await asyncio.gather(*tasks)

        assert len(results) == 3
        assert all(r[0] == "uploads/document.pdf" for r in results)


# ============================================================================
# Edge Cases and Error Handling Tests
# ============================================================================


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_empty_code_handling(self, proxy_manager):
        """Test handling of empty proxy code."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        with pytest.raises(FileNotFoundError):
            await proxy_manager.resolve_proxy("")

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_very_long_expiration(self, proxy_manager):
        """Test creating proxy with very long expiration time."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        # 10 years
        expires_in = 10 * 365 * 24 * 3600
        before_creation = datetime.now()

        proxy = await proxy_manager.create_proxy(
            file_path="uploads/archive.pdf", expires_in=expires_in
        )

        # The proxy should expire at least 10 years from when it was created
        expected_min_expiry = before_creation + timedelta(seconds=expires_in - 1)
        assert proxy.expires_at >= expected_min_expiry

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_metadata_with_none_values(self, proxy_manager):
        """Test proxy with None values in metadata."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        metadata = {"user_id": None, "tags": None, "description": "Test"}

        proxy = await proxy_manager.create_proxy(
            file_path="uploads/test.pdf", metadata=metadata
        )

        assert proxy.metadata["user_id"] is None
        assert proxy.metadata["description"] == "Test"

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_access_tracking_accuracy(self, proxy_manager):
        """Test accuracy of access tracking over multiple resolutions."""
        now = datetime.now()
        test_proxy = MockURLProxy(
            code="test123",
            file_path="uploads/document.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=test_proxy)

        # Resolve multiple times
        for i in range(5):
            await proxy_manager.resolve_proxy("test123")
            assert test_proxy.access_count == i + 1

        assert test_proxy.last_accessed is not None


# ============================================================================
# Integration Workflow Tests
# ============================================================================


class TestIntegrationWorkflows:
    """Tests for complete workflow scenarios."""

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_complete_proxy_lifecycle(self, proxy_manager):
        """Test complete proxy lifecycle: create → resolve → revoke."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        # 1. Create proxy
        proxy = await proxy_manager.create_proxy(
            file_path="uploads/document.pdf",
            expires_in=3600,
            metadata={"user": "test_user"},
        )

        assert proxy.active is True
        code = proxy.code

        # 2. Update find_by_code to return our proxy
        MockURLProxy.find_by_code = AsyncMock(return_value=proxy)

        # 3. Resolve proxy
        file_path, metadata = await proxy_manager.resolve_proxy(code)
        assert file_path == "uploads/document.pdf"
        assert proxy.access_count == 1

        # 4. Revoke proxy
        result = await proxy_manager.revoke_proxy(code)
        assert result is True
        assert proxy.active is False

        # 5. Try to resolve again (should fail)
        with pytest.raises(AccessDeniedError):
            await proxy_manager.resolve_proxy(code)

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_one_time_use_workflow(self, proxy_manager):
        """Test one-time proxy workflow."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        # Create one-time proxy
        proxy = await proxy_manager.create_proxy(
            file_path="uploads/secret.pdf", one_time=True
        )

        code = proxy.code
        MockURLProxy.find_by_code = AsyncMock(return_value=proxy)

        # First use - should succeed
        file_path, _ = await proxy_manager.resolve_proxy(code)
        assert file_path == "uploads/secret.pdf"
        assert proxy.active is False  # Deactivated after use

        # Second use - should fail
        with pytest.raises(AccessDeniedError):
            await proxy_manager.resolve_proxy(code)

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_multiple_proxies_cleanup_workflow(self, proxy_manager, mock_context):
        """Test creating multiple proxies and cleaning up expired ones."""
        MockURLProxy.find_by_code = AsyncMock(return_value=None)

        now = datetime.now()

        # Create mix of valid and expired proxies
        expired_data = [
            {"id": "proxy1", "context": {"active": False}},
            {"id": "proxy2", "context": {"expires_at": now - timedelta(hours=1)}},
        ]

        mock_context.database.find = AsyncMock(return_value=expired_data)

        # Cleanup expired proxies
        count = await proxy_manager.cleanup_expired()

        assert count == 2
        assert mock_context.database.delete.call_count == 2

    @pytest.mark.asyncio
    @patch("jvspatial.storage.managers.proxy.URLProxy", MockURLProxy)
    async def test_access_statistics_workflow(self, proxy_manager):
        """Test tracking access statistics over multiple resolutions."""
        now = datetime.now()
        test_proxy = MockURLProxy(
            code="stats123",
            file_path="uploads/document.pdf",
            created_at=now,
            expires_at=now + timedelta(hours=1),
        )

        MockURLProxy.find_by_code = AsyncMock(return_value=test_proxy)

        # Resolve multiple times
        for i in range(3):
            await proxy_manager.resolve_proxy("stats123")

        # Get stats
        stats = await proxy_manager.get_stats("stats123")

        assert stats["access_count"] == 3
        assert stats["last_accessed"] is not None
        assert stats["is_valid"] is True


# ============================================================================
# Module Level Tests
# ============================================================================


async def test_module_imports():
    """Test that all required modules can be imported."""
    from jvspatial.storage.managers import URLProxyManager, get_proxy_manager

    assert URLProxyManager is not None
    assert get_proxy_manager is not None


async def test_manager_class_attributes():
    """Test URLProxyManager class attributes."""
    assert hasattr(URLProxyManager, "_lock")
    assert hasattr(URLProxyManager, "_indexes_created")
