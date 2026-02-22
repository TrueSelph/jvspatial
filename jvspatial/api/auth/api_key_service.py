"""API Key service for managing API key authentication."""

import logging
import secrets
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from jvspatial.api.auth.models import APIKey
from jvspatial.core.context import GraphContext

# Try to import bcrypt, fallback to argon2, then to passlib
try:
    import bcrypt

    _HASHING_AVAILABLE = True
    _HASHING_LIB = "bcrypt"
except ImportError:
    try:
        from argon2 import PasswordHasher

        _HASHING_AVAILABLE = True
        _HASHING_LIB = "argon2"
        _argon2_hasher = PasswordHasher()
    except ImportError:
        try:
            from passlib.context import CryptContext

            _HASHING_AVAILABLE = True
            _HASHING_LIB = "passlib"
            _passlib_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        except ImportError:
            _HASHING_AVAILABLE = False
            _HASHING_LIB = None


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
        """Hash an API key using secure password hashing (bcrypt/argon2).

        Uses bcrypt if available, falls back to argon2, then passlib.
        If none are available, falls back to SHA-256 with a warning.

        Args:
            key: Plaintext API key

        Returns:
            Hashed key string
        """
        if _HASHING_AVAILABLE:
            if _HASHING_LIB == "bcrypt":
                # bcrypt requires bytes and returns bytes
                salt = bcrypt.gensalt()
                hashed = bcrypt.hashpw(key.encode("utf-8"), salt)
                return hashed.decode("utf-8")
            elif _HASHING_LIB == "argon2":
                # argon2 returns a string directly
                return _argon2_hasher.hash(key)
            elif _HASHING_LIB == "passlib":
                # passlib returns a string
                return _passlib_context.hash(key)
        else:
            # Fallback to SHA-256 if no secure hashing available
            import hashlib

            self._logger.warning(
                "No secure hashing library available (bcrypt/argon2/passlib). "
                "Using SHA-256. Install bcrypt for production: pip install bcrypt"
            )
            return hashlib.sha256(key.encode()).hexdigest()

    def _verify_key(self, key: str, hashed: str) -> bool:
        """Verify an API key against its hash.

        Args:
            key: Plaintext API key to verify
            hashed: Stored hash to verify against

        Returns:
            True if key matches hash, False otherwise
        """
        if _HASHING_AVAILABLE:
            if _HASHING_LIB == "bcrypt":
                try:
                    return bcrypt.checkpw(key.encode("utf-8"), hashed.encode("utf-8"))
                except Exception:
                    return False
            elif _HASHING_LIB == "argon2":
                try:
                    _argon2_hasher.verify(hashed, key)
                    return True
                except Exception:
                    return False
            elif _HASHING_LIB == "passlib":
                try:
                    return _passlib_context.verify(key, hashed)
                except Exception:
                    return False
        else:
            # Fallback to SHA-256 comparison
            import hashlib

            return hashlib.sha256(key.encode()).hexdigest() == hashed

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
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

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
            created_at=datetime.utcnow(),
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

        Args:
            key: Plaintext API key to validate

        Returns:
            APIKey entity if valid, None otherwise
        """
        if not key or len(key) < 10:
            return None

        # Store the plaintext key to avoid variable name collision
        plaintext_key = key

        # Get all active API keys for the user (we need to verify against all)
        # This is necessary because we can't reverse the hash to find the key
        # In production, you might want to add an index or use a different lookup strategy
        # Use service's context instead of get_default_context()
        await self.context.ensure_indexes(APIKey)
        collection, final_query = await APIKey._build_database_query(
            self.context, {"context.is_active": True}, {}
        )
        results = await self.context.database.find(collection, final_query)
        all_keys = []
        for data in results:
            try:
                api_key_entity = await self.context._deserialize_entity(APIKey, data)
                if api_key_entity:
                    api_key_entity._graph_context = self.context
                    all_keys.append(api_key_entity)
            except Exception:
                continue

        # Check each key's hash
        for api_key in all_keys:
            # Verify the plaintext key against the stored hash
            if self._verify_key(plaintext_key, api_key.key_hash):
                # Check expiration
                if api_key.expires_at and api_key.expires_at < datetime.utcnow():
                    self._logger.debug(f"API key {api_key.id} has expired")
                    continue

                # Update last used timestamp
                # Ensure context is set before saving
                api_key._graph_context = self.context
                await self.update_key_usage(api_key)
                return api_key

        return None

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
        api_key.last_used_at = datetime.utcnow()
        # Ensure context is set before saving
        if not api_key._graph_context:
            api_key._graph_context = self.context
        await self.context.save(api_key)


__all__ = ["APIKeyService"]
