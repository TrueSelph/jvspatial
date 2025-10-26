"""Storage models for URL proxy management.

This module defines the URLProxy model for managing temporary file access URLs.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import Field

from jvspatial.core import Object


class URLProxy(Object):
    """Model representing a URL proxy for secure file access.

    A URL proxy provides temporary, optionally one-time access to files
    through a secure randomly-generated code.

    Attributes:
        code: Unique random code for accessing the file
        file_path: Path to the file being proxied
        created_at: When the proxy was created
        expires_at: When the proxy expires
        one_time: If True, proxy is deactivated after first access
        metadata: Additional metadata (user_id, IP, tags, etc.)
        active: Whether the proxy is currently active
        access_count: Number of times proxy has been accessed
        last_accessed: Last access timestamp
    """

    type_code: str = Field(default="o")

    code: str = ""
    file_path: str = ""
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime = Field(default_factory=datetime.now)
    one_time: bool = False
    metadata: Dict[str, Any] = Field(default_factory=dict)
    active: bool = True
    access_count: int = 0
    last_accessed: Optional[datetime] = None

    def is_expired(self) -> bool:
        """Check if proxy is expired.

        Returns:
            True if current time is past expires_at
        """
        return datetime.now() >= self.expires_at

    def is_valid(self) -> bool:
        """Check if proxy is valid for access.

        Returns:
            True if proxy is active and not expired
        """
        return self.active and not self.is_expired()

    async def record_access(self) -> None:
        """Record an access to this proxy.

        Increments access count, updates last accessed time,
        and deactivates if one-time use.
        """
        self.access_count += 1
        self.last_accessed = datetime.now()

        if self.one_time:
            self.active = False

        await self.save()

    async def revoke(self, reason: str = "") -> None:
        """Revoke the proxy.

        Args:
            reason: Optional reason for revocation
        """
        self.active = False
        if reason:
            self.metadata["revocation_reason"] = reason
        await self.save()

    @classmethod
    async def find_by_code(cls, code: str) -> Optional["URLProxy"]:
        """Find a proxy by its code.

        Args:
            code: The proxy code to search for

        Returns:
            URLProxy instance if found, None otherwise
        """
        proxies = await cls.find({"context.code": code})
        return proxies[0] if proxies else None

    @classmethod
    async def find_active_for_file(cls, file_path: str) -> List["URLProxy"]:
        """Find all active proxies for a specific file.

        Args:
            file_path: The file path to search for

        Returns:
            List of active URLProxy instances for the file
        """
        return await cls.find({"context.file_path": file_path, "context.active": True})
