"""Authentication entities for the jvspatial framework.

This module provides User, APIKey, and Session entities that integrate
with the existing jvspatial entity system but are stored in separate
collections from spatial data for security and performance isolation.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import ClassVar, List, Optional, Tuple, cast

from pydantic import Field

from jvspatial.core.entities import Object


class User(Object):
    """User entity for authentication and authorization.

    Extends Object to integrate with the jvspatial database system while
    being stored in a separate 'user' collection for security isolation.
    Users represent system actors who can authenticate and access spatial data.
    """

    type_code: ClassVar[str] = "u"  # 'u' for user collection

    # Basic user information
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    password_hash: str = Field(..., description="BCrypt hashed password")

    # User status and metadata
    is_active: bool = Field(default=True)
    is_verified: bool = Field(default=False)
    is_admin: bool = Field(default=False)

    # Spatial-specific permissions
    allowed_regions: List[str] = Field(
        default_factory=list, description="List of spatial region IDs user can access"
    )
    allowed_node_types: List[str] = Field(
        default_factory=list, description="List of node types user can interact with"
    )
    max_traversal_depth: int = Field(
        default=10, description="Maximum graph traversal depth for this user"
    )

    # Role-based permissions
    roles: List[str] = Field(
        default_factory=lambda: ["user"], description="List of role names"
    )
    permissions: List[str] = Field(
        default_factory=list, description="List of specific permissions"
    )

    # Metadata
    created_at: datetime = Field(default_factory=datetime.now)
    last_login: Optional[datetime] = Field(default=None)
    login_count: int = Field(default=0)

    # Rate limiting
    rate_limit_per_hour: int = Field(
        default=1000, description="API requests per hour limit"
    )

    def get_collection_name(self, cls=None) -> str:
        """Override to use 'user' collection."""
        return "user"

    @classmethod
    def hash_password(cls, password: str) -> str:
        """Hash a password using BCrypt.

        Args:
            password: Plain text password

        Returns:
            BCrypt hashed password
        """
        import bcrypt

        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        return cast(str, hashed.decode("utf-8"))

    def verify_password(self, password: str) -> bool:
        """Verify a password against the stored hash.

        Args:
            password: Plain text password to verify

        Returns:
            True if password matches, False otherwise
        """
        import bcrypt

        return cast(
            bool,
            bcrypt.checkpw(
                password.encode("utf-8"), self.password_hash.encode("utf-8")
            ),
        )

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission.

        Args:
            permission: Permission name to check

        Returns:
            True if user has permission, False otherwise
        """
        return (
            self.is_admin
            or permission in self.permissions
            or any(role in ["admin", "superuser"] for role in self.roles)
        )

    def has_role(self, role: str) -> bool:
        """Check if user has a specific role.

        Args:
            role: Role name to check

        Returns:
            True if user has role, False otherwise
        """
        return role in self.roles or (self.is_admin and role in ["admin", "superuser"])

    def can_access_region(self, region_id: str) -> bool:
        """Check if user can access a spatial region.

        Args:
            region_id: ID of the spatial region

        Returns:
            True if user can access region, False otherwise
        """
        return (
            self.is_admin
            or not self.allowed_regions
            or region_id in self.allowed_regions
        )

    def can_access_node_type(self, node_type: str) -> bool:
        """Check if user can interact with a node type.

        Args:
            node_type: Name of the node type

        Returns:
            True if user can access node type, False otherwise
        """
        return (
            self.is_admin
            or not self.allowed_node_types
            or node_type in self.allowed_node_types
        )

    async def record_login(self) -> None:
        """Record a successful login."""
        self.last_login = datetime.now()
        self.login_count += 1
        await self.save()

    @classmethod
    async def find_by_username(cls, username: str) -> Optional["User"]:
        """Find a user by username.

        Args:
            username: Username to search for

        Returns:
            User instance if found, None otherwise
        """
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()
        results = await ctx.database.find("user", {"context.username": username})

        if not results:
            return None

        return await ctx._deserialize_entity(cls, results[0])

    @classmethod
    async def find_by_email(cls, email: str) -> Optional["User"]:
        """Find a user by email.

        Args:
            email: Email to search for

        Returns:
            User instance if found, None otherwise
        """
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()
        results = await ctx.database.find("user", {"context.email": email})

        if not results:
            return None

        return await ctx._deserialize_entity(cls, results[0])


class APIKey(Object):
    """API Key entity for service-to-service authentication.

    Extends Object to be stored in separate 'apikey' collection.
    Provides long-lived authentication tokens for automated systems
    and service integrations with jvspatial APIs.
    """

    type_code: ClassVar[str] = "k"  # 'k' for key collection

    # Key identification
    name: str = Field(..., description="Human-readable name for the API key")
    key_id: str = Field(..., description="Public identifier for the key")
    key_hash: str = Field(..., description="Hashed secret key")

    # Associated user
    user_id: str = Field(..., description="ID of the user who owns this key")

    # Key status and lifetime
    is_active: bool = Field(default=True)
    expires_at: Optional[datetime] = Field(default=None)

    # Usage tracking
    created_at: datetime = Field(default_factory=datetime.now)
    last_used: Optional[datetime] = Field(default=None)
    usage_count: int = Field(default=0)

    # Permissions (can be more restrictive than user permissions)
    allowed_operations: List[str] = Field(
        default_factory=list, description="List of allowed operations"
    )
    allowed_endpoints: List[str] = Field(
        default_factory=list, description="List of allowed endpoint patterns"
    )
    rate_limit_per_hour: int = Field(
        default=10000, description="Requests per hour limit for this key"
    )

    # IP restrictions
    allowed_ips: List[str] = Field(
        default_factory=list, description="List of allowed IP addresses/ranges"
    )

    # HMAC verification
    hmac_secret: Optional[str] = Field(
        default=None, description="Shared secret for HMAC payload verification"
    )

    def get_collection_name(self, cls=None) -> str:
        """Override to use 'apikey' collection."""
        return "apikey"

    @classmethod
    def generate_key_pair(cls) -> Tuple[str, str]:
        """Generate a new API key pair.

        Returns:
            Tuple of (key_id, secret_key)
        """
        key_id = secrets.token_urlsafe(16)
        secret_key = secrets.token_urlsafe(32)
        return key_id, secret_key

    @classmethod
    def hash_secret(cls, secret_key: str) -> str:
        """Hash an API secret key.

        Args:
            secret_key: The secret part of the API key

        Returns:
            SHA-256 hash of the secret key
        """
        return hashlib.sha256(secret_key.encode()).hexdigest()

    def verify_secret(self, secret_key: str) -> bool:
        """Verify a secret key against the stored hash.

        Args:
            secret_key: Secret key to verify

        Returns:
            True if secret matches, False otherwise
        """
        return self.key_hash == self.hash_secret(secret_key)

    def is_valid(self) -> bool:
        """Check if the API key is currently valid.

        Returns:
            True if key is active and not expired, False otherwise
        """
        if not self.is_active:
            return False

        if self.expires_at and datetime.now() > self.expires_at:
            return False

        return True

    def can_access_endpoint(self, endpoint: str) -> bool:
        """Check if this API key can access an endpoint.

        Args:
            endpoint: Endpoint path to check

        Returns:
            True if key can access endpoint, False otherwise
        """
        if not self.allowed_endpoints:
            return True  # No restrictions

        import fnmatch

        return any(
            fnmatch.fnmatch(endpoint, pattern) for pattern in self.allowed_endpoints
        )

    def can_perform_operation(self, operation: str) -> bool:
        """Check if this API key can perform an operation.

        Args:
            operation: Operation name to check

        Returns:
            True if key can perform operation, False otherwise
        """
        if not self.allowed_operations:
            return True  # No restrictions

        return operation in self.allowed_operations

    async def record_usage(self, endpoint: str = "", operation: str = "") -> None:
        """Record API key usage."""
        self.last_used = datetime.now()
        self.usage_count += 1
        await self.save()

    @classmethod
    async def find_by_key_id(cls, key_id: str) -> Optional["APIKey"]:
        """Find an API key by its public key ID.

        Args:
            key_id: Public key identifier

        Returns:
            APIKey instance if found, None otherwise
        """
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()
        results = await ctx.database.find("apikey", {"context.key_id": key_id})

        if not results:
            return None

        return await ctx._deserialize_entity(cls, results[0])


class Session(Object):
    """Session entity for JWT token management.

    Extends Object to be stored in separate 'session' collection.
    Tracks active user sessions with JWT tokens for web-based authentication.
    """

    type_code: ClassVar[str] = "s"  # 's' for session collection

    # Session identification
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="ID of the authenticated user")

    # JWT token information
    jwt_token: str = Field(..., description="The JWT token string")
    refresh_token: str = Field(..., description="Refresh token for extending session")

    # Session metadata
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: datetime = Field(..., description="Session expiration time")
    last_activity: datetime = Field(default_factory=datetime.now)

    # Session context
    client_ip: str = Field(default="", description="Client IP address")
    user_agent: str = Field(default="", description="Client user agent")

    # Status
    is_active: bool = Field(default=True)
    revoked_at: Optional[datetime] = Field(default=None)
    revoked_reason: str = Field(default="", description="Reason for revocation")

    def get_collection_name(self, cls=None) -> str:
        """Override to use 'session' collection."""
        return "session"

    @classmethod
    def create_session_id(cls) -> str:
        """Generate a new session ID.

        Returns:
            Unique session identifier
        """
        return secrets.token_urlsafe(32)

    def is_valid(self) -> bool:
        """Check if the session is currently valid.

        Returns:
            True if session is active and not expired, False otherwise
        """
        if not self.is_active or self.revoked_at:
            return False

        if datetime.now() > self.expires_at:
            return False

        return True

    def extend_session(self, duration_hours: int = 24) -> None:
        """Extend the session expiration time.

        Args:
            duration_hours: Hours to extend the session by
        """
        self.expires_at = datetime.now() + timedelta(hours=duration_hours)
        self.last_activity = datetime.now()

    async def revoke(self, reason: str = "Manual revocation") -> None:
        """Revoke the session.

        Args:
            reason: Reason for revoking the session
        """
        self.is_active = False
        self.revoked_at = datetime.now()
        self.revoked_reason = reason
        await self.save()

    async def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now()
        await self.save()

    @classmethod
    async def find_by_session_id(cls, session_id: str) -> Optional["Session"]:
        """Find a session by its session ID.

        Args:
            session_id: Session identifier

        Returns:
            Session instance if found, None otherwise
        """
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()
        results = await ctx.database.find("session", {"context.session_id": session_id})

        if not results:
            return None

        return await ctx._deserialize_entity(cls, results[0])


# Custom exceptions for authentication system
class AuthenticationError(Exception):
    """Base exception for authentication errors."""

    pass


class AuthorizationError(Exception):
    """Base exception for authorization errors."""

    pass


class RateLimitError(Exception):
    """Exception raised when rate limits are exceeded."""

    pass


class InvalidCredentialsError(AuthenticationError):
    """Exception raised when credentials are invalid."""

    pass


class UserNotFoundError(AuthenticationError):
    """Exception raised when user is not found."""

    pass


class SessionExpiredError(AuthenticationError):
    """Exception raised when session has expired."""

    pass


class APIKeyInvalidError(AuthenticationError):
    """Exception raised when API key is invalid."""

    pass
