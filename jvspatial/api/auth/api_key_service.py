"""API Key service for managing API key authentication."""

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

from jvspatial.api.auth.models import APIKey
from jvspatial.core.context import GraphContext


class APIKeyService:
    """Service for managing API keys.

    Provides secure generation, validation, and management of API keys
    with hashing, expiration, and access restrictions.
    """

    def __init__(self, context: Optional[GraphContext] = None):
        """Initialize the API key service.

        Args:
            context: GraphContext instance for database operations.
                    If None, uses the default context.
        """
        from jvspatial.core.context import get_default_context

        self.context = context or get_default_context()
        self._logger = logging.getLogger(__name__)
        self.key_prefix = "sk_"  # Default prefix, can be configured
        self.key_length = 32  # Length of random part after prefix

    def _hash_key(self, key: str) -> str:
        """Hash an API key using SHA-256.

        API keys are high-entropy; SHA-256 enables O(1) lookup by hash.
        Industry standard for API keys (Stripe, GitHub, etc.).

        Args:
            key: Plaintext API key

        Returns:
            Hex-encoded SHA-256 hash
        """
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _verify_key(self, key: str, hashed: str) -> bool:
        """Verify an API key against its hash using constant-time comparison.

        Args:
            key: Plaintext API key to verify
            hashed: Stored SHA-256 hash (hex) to verify against

        Returns:
            True if key matches hash, False otherwise
        """
        computed = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return hmac.compare_digest(computed, hashed)

    def _generate_key_string(self, prefix: Optional[str] = None) -> str:
        """Generate a new API key string.

        Args:
            prefix: Optional custom prefix (defaults to self.key_prefix)

        Returns:
            Generated API key string (e.g., "sk_live_abc123...xyz789")
        """
        prefix = prefix or self.key_prefix
        # Generate random part
        random_part = secrets.token_urlsafe(self.key_length)
        return f"{prefix}{random_part}"

    def _get_key_prefix_display(self, key: str) -> str:
        """Extract display prefix from a key.

        Args:
            key: Full API key

        Returns:
            First 8-12 characters for display (e.g., "sk_live_abc12345...")
        """
        # Show prefix + first 8 chars of random part
        if len(key) > 20:
            return f"{key[:20]}..."
        return key

    async def generate_key(
        self,
        user_id: str,
        name: str,
        permissions: Optional[List[str]] = None,
        rate_limit_override: Optional[int] = None,
        expires_in_days: Optional[int] = None,
        allowed_ips: Optional[List[str]] = None,
        allowed_endpoints: Optional[List[str]] = None,
        key_prefix: Optional[str] = None,
    ) -> Tuple[str, APIKey]:
        """Generate a new API key.

        Args:
            user_id: User ID who owns the key
            name: Descriptive name for the key
            permissions: List of permissions granted to this key
            rate_limit_override: Custom rate limit (requests per minute)
            expires_in_days: Number of days until expiration (None = no expiration)
            allowed_ips: IP whitelist (None = all IPs allowed)
            allowed_endpoints: Endpoint whitelist (None = all endpoints allowed)
            key_prefix: Optional custom key prefix

        Returns:
            Tuple of (plaintext_key, api_key_entity)
            The plaintext key is shown ONCE to the user, then discarded.

        Raises:
            ValueError: If user_id is invalid or name is empty
        """
        if not user_id:
            raise ValueError("user_id is required")
        if not name or not name.strip():
            raise ValueError("name is required and cannot be empty")

        # Generate plaintext key
        plaintext_key = self._generate_key_string(key_prefix)

        # Hash the key (never store plaintext)
        key_hash = self._hash_key(plaintext_key)

        # Extract display prefix
        key_prefix_display = self._get_key_prefix_display(plaintext_key)

        # Calculate expiration
        expires_at = None
        if expires_in_days is not None and expires_in_days > 0:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_in_days)

        # Create API key entity using service's context
        # APIKey.create() uses get_default_context(), so we create it manually
        from jvspatial.core.utils import generate_id

        api_key_id = generate_id("o", "APIKey")
        api_key = APIKey(
            id=api_key_id,
            key_hash=key_hash,
            key_prefix=key_prefix_display,
            name=name.strip(),
            user_id=user_id,
            permissions=permissions or [],
            rate_limit_override=rate_limit_override,
            expires_at=expires_at,
            allowed_ips=allowed_ips or [],
            allowed_endpoints=allowed_endpoints or [],
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        # Set context and save using service's context
        api_key._graph_context = self.context
        await self.context.save(api_key)

        self._logger.info(
            f"Generated API key {api_key.id} for user {user_id} with prefix {key_prefix_display}"
        )

        return plaintext_key, api_key

    async def validate_key(self, key: str) -> Optional[APIKey]:
        """Validate an API key and return the entity if valid.

        O(1) lookup by SHA-256 hash. No iteration, no blocking.
        """
        if not key or len(key) < 10:
            return None

        key_hash = self._hash_key(key)
        await self.context.ensure_indexes(APIKey)
        collection, final_query = await APIKey._build_database_query(
            self.context,
            {"context.is_active": True, "key_hash": key_hash},
            {},
        )
        data = await self.context.database.find_one(collection, final_query)
        if not data:
            return None

        try:
            api_key = await self.context._deserialize_entity(APIKey, data)
        except Exception:
            return None

        if not api_key:
            return None

        if api_key.expires_at and api_key.expires_at < datetime.now(timezone.utc):
            self._logger.debug(f"API key {api_key.id} has expired")
            return None

        api_key._graph_context = self.context
        await self.update_key_usage(api_key)
        return api_key

    async def revoke_key(self, key_id: str, user_id: str) -> bool:
        """Revoke an API key.

        Args:
            key_id: API key ID to revoke
            user_id: User ID who owns the key (for authorization check)

        Returns:
            True if key was revoked, False if not found or unauthorized
        """
        # Use service's context instead of get_default_context()
        api_key = await self.context.get(APIKey, key_id)
        if api_key:
            api_key._graph_context = self.context

        if not api_key:
            return False

        # Verify ownership
        if api_key.user_id != user_id:
            self._logger.warning(
                f"User {user_id} attempted to revoke key {key_id} owned by {api_key.user_id}"
            )
            return False

        # Deactivate the key
        api_key.is_active = False
        # Ensure context is set before saving
        if not api_key._graph_context:
            api_key._graph_context = self.context
        await self.context.save(api_key)

        self._logger.info(f"Revoked API key {key_id} for user {user_id}")
        return True

    async def get_key(self, key_id: str) -> Optional[APIKey]:
        """Get API key by ID.

        Args:
            key_id: API key ID to retrieve

        Returns:
            APIKey entity if found, None otherwise
        """
        api_key = await self.context.get(APIKey, key_id)
        if api_key:
            api_key._graph_context = self.context
        return api_key

    async def get_user_keys(self, user_id: str) -> List[APIKey]:
        """Get all API keys for a user.

        Args:
            user_id: User ID

        Returns:
            List of APIKey entities
        """
        # Use service's context instead of get_default_context()
        await self.context.ensure_indexes(APIKey)
        collection, final_query = await APIKey._build_database_query(
            self.context, {"context.user_id": user_id}, {}
        )
        results = await self.context.database.find(collection, final_query)
        keys = []
        for data in results:
            try:
                key = await self.context._deserialize_entity(APIKey, data)
                if key:
                    key._graph_context = self.context
                    keys.append(key)
            except Exception:
                continue
        return keys

    async def update_key_usage(self, api_key: APIKey) -> None:
        """Update the last_used_at timestamp for an API key.

        Args:
            api_key: APIKey entity to update
        """
        api_key.last_used_at = datetime.now(timezone.utc)
        # Ensure context is set before saving
        if not api_key._graph_context:
            api_key._graph_context = self.context
        await self.context.save(api_key)


__all__ = ["APIKeyService"]
