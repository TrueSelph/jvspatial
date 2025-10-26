"""Authentication entities for the jvspatial framework.

This module provides User, APIKey, and Session entities that integrate
with the existing jvspatial entity system but are stored in separate
collections from spatial data for security and performance isolation.
"""

import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, cast

from pydantic import Field

from jvspatial.core.entities import Object


class User(Object):
    """User entity for authentication and authorization.

    Extends Object to integrate with the jvspatial database system and
    is stored in the 'object' collection. Users represent system actors
    who can authenticate and access spatial data.
    """

    type_code: str = Field(default="o")  # 'o' for object collection

    # Basic user information
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
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_login: Optional[str] = Field(default=None)
    login_count: int = Field(default=0)

    # Rate limiting
    rate_limit_per_hour: int = Field(
        default=1000, description="API requests per hour limit"
    )

    def get_collection_name(self, cls=None) -> str:
        """Override to use 'object' collection."""
        return "object"

    def __init__(self, **kwargs):
        """Initialize User with proper ID generation."""
        # Ensure type_code is set for ID generation
        if "type_code" not in kwargs:
            kwargs["type_code"] = "o"  # 'o' for object collection
        super().__init__(**kwargs)

    def export(self, exclude_transient: bool = True, **kwargs) -> Dict[str, Any]:
        """Export user data with datetime serialization for JSON database compatibility.

        Args:
            exclude_transient: Whether to exclude transient fields
            **kwargs: Additional arguments passed to model_dump()

        Returns:
            Dictionary representation with datetime fields converted to ISO strings
        """
        # Get the base export from parent class
        data = super().export(exclude_transient=exclude_transient, **kwargs)

        # Convert datetime fields to ISO strings for JSON serialization
        if "created_at" in data and isinstance(data["created_at"], datetime):
            data["created_at"] = data["created_at"].isoformat()

        if (
            "last_login" in data
            and data["last_login"] is not None
            and isinstance(data["last_login"], datetime)
        ):
            data["last_login"] = data["last_login"].isoformat()

        return data

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
        self.last_login = datetime.now().isoformat()
        self.login_count += 1
        await self.save()

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
        results = await ctx.database.find("user", {"email": email})

        if not results:
            return None

        # Create a new instance from the database result
        user_data = results[0]
        user = cls(**user_data)
        return user

    @classmethod
    async def create_user(
        cls, email: str, password_hash: str, created_at: str
    ) -> "User":
        """Create a new user.

        Args:
            email: Email address for the user
            password_hash: Hashed password
            created_at: Creation timestamp (ISO string)

        Returns:
            Created User instance
        """
        user = cls(
            email=email,
            password_hash=password_hash,
            created_at=created_at,
            is_active=True,
            is_verified=False,
            is_admin=False,
            roles=[],
            permissions=[],
            allowed_regions=[],
            allowed_node_types=[],
            max_traversal_depth=10,
            login_count=0,
            last_login=None,
        )

        await user.save()
        return user

    @classmethod
    async def find_users(
        cls, active_only: bool = False, limit: int = 50, offset: int = 0
    ) -> List["User"]:
        """Find users with optional filtering and pagination."""
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()

        # Build query filters
        filters = {}
        if active_only:
            filters["is_active"] = True

        # Find users with filters
        users_data = await ctx.database.find("user", filters)

        # Convert to User objects
        users = []
        for user_data in users_data[offset : offset + limit]:
            user = cls(**user_data)
            users.append(user)

        return users

    @classmethod
    async def find_by_id(cls, user_id: str) -> Optional["User"]:
        """Find a user by their ID."""
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()
        user_data = await ctx.database.find("user", {"id": user_id})
        if user_data:
            return cls(**user_data[0])
        return None

    @classmethod
    async def count(cls, active_only: bool = False) -> int:
        """Count users with optional filtering."""
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()

        # Build query filters
        filters = {}
        if active_only:
            filters["is_active"] = True

        # Count users with filters
        users_data = await ctx.database.find("user", filters)
        return len(users_data)


class APIKey(Object):
    """API Key entity for service-to-service authentication.

    Extends Object and is stored in the 'object' collection.
    Provides long-lived authentication tokens for automated systems
    and service integrations with jvspatial APIs.
    """

    type_code: str = Field(default="o")  # 'o' for object collection

    # Key identification
    name: str = Field(..., description="Human-readable name for the API key")
    key_id: str = Field(..., description="Public identifier for the key")
    key_hash: str = Field(..., description="Hashed secret key")

    # Associated user
    user_id: str = Field(..., description="ID of the user who owns this key")

    # Key status and lifetime
    is_active: bool = Field(default=True)
    expires_at: Optional[str] = Field(default=None)

    # Usage tracking
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    last_used: Optional[str] = Field(default=None)
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
        """Override to use 'object' collection."""
        return "object"

    def export(self, exclude_transient: bool = True, **kwargs) -> Dict[str, Any]:
        """Export API key data with datetime serialization for JSON database compatibility.

        Args:
            exclude_transient: Whether to exclude transient fields
            **kwargs: Additional arguments passed to model_dump()

        Returns:
            Dictionary representation with datetime fields converted to ISO strings
        """
        # Get the base export from parent class
        data = super().export(exclude_transient=exclude_transient, **kwargs)

        # Convert datetime fields to ISO strings for JSON serialization
        if "created_at" in data and isinstance(data["created_at"], datetime):
            data["created_at"] = data["created_at"].isoformat()

        if (
            "last_used" in data
            and data["last_used"] is not None
            and isinstance(data["last_used"], datetime)
        ):
            data["last_used"] = data["last_used"].isoformat()

        if (
            "expires_at" in data
            and data["expires_at"] is not None
            and isinstance(data["expires_at"], datetime)
        ):
            data["expires_at"] = data["expires_at"].isoformat()

        return data

    @classmethod
    async def find(cls, query: Dict[str, Any]) -> List["APIKey"]:  # type: ignore[override]
        """Find API keys matching the query.

        Args:
            query: Query dictionary to match against

        Returns:
            List of APIKey instances matching the query
        """
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()
        results = await ctx.database.find("object", query)

        if not results:
            return []

        api_keys = []
        for result in results:
            api_key = await ctx._deserialize_entity(cls, result)
            if api_key is not None:
                api_keys.append(api_key)

        return api_keys

    @classmethod
    async def find_by_user(cls, user_id: str) -> List["APIKey"]:
        """Find API keys for a specific user.

        Args:
            user_id: ID of the user to find keys for

        Returns:
            List of APIKey instances for the user
        """
        return await cls.find({"context.user_id": user_id})

    @classmethod
    async def find_by_id(cls, key_id: str) -> Optional["APIKey"]:
        """Find an API key by ID.

        Args:
            key_id: ID of the API key to find

        Returns:
            APIKey instance if found, None otherwise
        """
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()
        results = await ctx.database.find("apikey", {"context.key_id": key_id})

        if not results:
            return None

        return await ctx._deserialize_entity(cls, results[0])

    @classmethod
    async def create_api_key(
        cls,
        name: str,
        key_id: str,
        key_hash: str,
        user_id: str,
        expires_at: Optional[datetime] = None,
        allowed_operations: Optional[List[str]] = None,
        allowed_endpoints: Optional[List[str]] = None,
        rate_limit_per_hour: int = 10000,
        allowed_ips: Optional[List[str]] = None,
    ) -> "APIKey":
        """Create a new API key.

        Args:
            name: Human-readable name for the API key
            key_id: Public identifier for the key
            key_hash: Hashed secret key
            user_id: ID of the user who owns this key
            expires_at: Optional expiration time
            allowed_operations: List of allowed operations
            allowed_endpoints: List of allowed endpoint patterns
            rate_limit_per_hour: Requests per hour limit
            allowed_ips: List of allowed IP addresses

        Returns:
            Created APIKey instance
        """
        api_key = cls(
            name=name,
            key_id=key_id,
            key_hash=key_hash,
            user_id=user_id,
            expires_at=expires_at.isoformat() if expires_at else None,
            allowed_operations=allowed_operations or [],
            allowed_endpoints=allowed_endpoints or [],
            rate_limit_per_hour=rate_limit_per_hour,
            allowed_ips=allowed_ips or [],
            is_active=True,
            usage_count=0,
            last_used=None,
        )

        await api_key.save()
        return api_key

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

        if self.expires_at and datetime.now() > datetime.fromisoformat(self.expires_at):
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
        self.last_used = datetime.now().isoformat()
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
        results = await ctx.database.find("apikey", {"key_id": key_id})

        if not results:
            return None

        return await ctx._deserialize_entity(cls, results[0])

    @classmethod
    async def find_all(cls, active_only: bool = False) -> List["APIKey"]:
        """Find API keys with optional filtering."""
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()

        # Build query filters
        filters = {}
        if active_only:
            filters["is_active"] = True

        # Find API keys with filters
        keys_data = await ctx.database.find("apikey", filters)

        # Convert to APIKey objects
        keys = []
        for key_data in keys_data:
            key = cls(**key_data)
            keys.append(key)

        return keys

    @classmethod
    async def count(cls, active_only: bool = False) -> int:
        """Count API keys with optional filtering."""
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()

        # Build query filters
        filters = {}
        if active_only:
            filters["is_active"] = True

        # Count API keys with filters
        keys_data = await ctx.database.find("apikey", filters)
        return len(keys_data)


class Session(Object):
    """Session entity for JWT token management.

    Extends Object and is stored in the 'object' collection.
    Tracks active user sessions with JWT tokens for web-based authentication.
    """

    type_code: str = Field(default="o")  # 'o' for object collection

    # Session identification
    session_id: str = Field(..., description="Unique session identifier")
    user_id: str = Field(..., description="ID of the authenticated user")

    # JWT token information
    jwt_token: str = Field(..., description="The JWT token string")
    refresh_token: str = Field(..., description="Refresh token for extending session")

    # Session metadata
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    expires_at: str = Field(..., description="Session expiration time")
    last_activity: str = Field(default_factory=lambda: datetime.now().isoformat())

    # Session context
    client_ip: str = Field(default="", description="Client IP address")
    user_agent: str = Field(default="", description="Client user agent")

    # Status
    is_active: bool = Field(default=True)
    revoked_at: Optional[str] = Field(default=None)
    revoked_reason: str = Field(default="", description="Reason for revocation")

    def get_collection_name(self, cls=None) -> str:
        """Override to use 'object' collection."""
        return "object"

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

        if self.expires_at and datetime.now() > datetime.fromisoformat(self.expires_at):
            return False

        return True

    def extend_session(self, duration_hours: int = 24) -> None:
        """Extend the session expiration time.

        Args:
            duration_hours: Hours to extend the session by
        """
        self.expires_at = (datetime.now() + timedelta(hours=duration_hours)).isoformat()
        self.last_activity = datetime.now().isoformat()

    async def revoke(self, reason: str = "Manual revocation") -> None:
        """Revoke the session.

        Args:
            reason: Reason for revoking the session
        """
        self.is_active = False
        self.revoked_at = datetime.now().isoformat()
        self.revoked_reason = reason
        await self.save()

    async def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now().isoformat()
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

    @classmethod
    async def find_sessions(cls, active_only: bool = False) -> List["Session"]:
        """Find sessions with optional filtering."""
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()

        # Build query filters
        filters = {}
        if active_only:
            filters["is_active"] = True

        # Find sessions with filters
        sessions_data = await ctx.database.find("session", filters)

        # Convert to Session objects
        sessions = []
        for session_data in sessions_data:
            session = cls(**session_data)
            sessions.append(session)

        return sessions

    @classmethod
    async def count(cls, active_only: bool = False) -> int:
        """Count sessions with optional filtering."""
        from jvspatial.core.context import get_default_context

        ctx = get_default_context()

        # Build query filters
        filters = {}
        if active_only:
            filters["is_active"] = True

        # Count sessions with filters
        sessions_data = await ctx.database.find("session", filters)
        return len(sessions_data)


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
