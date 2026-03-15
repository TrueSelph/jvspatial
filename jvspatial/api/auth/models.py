"""Authentication models for user management and JWT tokens."""

from datetime import datetime, timezone
from typing import Any, List, Optional

from pydantic import BaseModel, EmailStr, Field

from jvspatial.core.entities.object import Object


class UserCreate(BaseModel):
    """Model for creating a new user (public registration)."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ..., min_length=6, description="User password (min 6 characters)"
    )


class UserCreateAdmin(BaseModel):
    """Model for admin creating a user with roles and permissions."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ..., min_length=6, description="User password (min 6 characters)"
    )
    roles: List[str] = Field(
        default_factory=lambda: ["user"],
        description="Roles to assign to the user",
    )
    permissions: Optional[List[str]] = Field(
        default=None,
        description="Direct permissions to assign (optional)",
    )


class UserRolesUpdate(BaseModel):
    """Model for updating user roles."""

    roles: List[str] = Field(..., description="New roles for the user")


class UserPermissionsUpdate(BaseModel):
    """Model for updating user direct permissions."""

    permissions: List[str] = Field(..., description="New direct permissions")


class UserLogin(BaseModel):
    """Model for user login."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class UserResponse(BaseModel):
    """Model for user response data."""

    id: str = Field(..., description="User ID")
    email: str = Field(..., description="User email")
    name: str = Field(..., description="User name")
    created_at: datetime = Field(..., description="User creation timestamp")
    is_active: bool = Field(default=True, description="Whether user is active")
    roles: List[str] = Field(
        default_factory=lambda: ["user"],
        description="User roles",
    )
    permissions: List[str] = Field(
        default_factory=list,
        description="Effective permissions (roles + direct)",
    )


class TokenResponse(BaseModel):
    """Model for authentication token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    refresh_token: Optional[str] = Field(
        None, description="Refresh token for obtaining new access tokens"
    )
    refresh_expires_in: Optional[int] = Field(
        None, description="Refresh token expiration time in seconds"
    )
    user: UserResponse = Field(..., description="User information")


class TokenRefreshRequest(BaseModel):
    """Request model for refreshing access token."""

    refresh_token: str = Field(..., description="Refresh token to exchange")


class User(Object):
    """User entity model for authentication.

    User is an Object entity (not a Node) as authentication entities are
    fundamental data objects that are not connected to the graph by edges.
    Users are stored in the database and managed through standard Object
    CRUD operations (create, find, get, save, delete).
    """

    email: str = Field(..., description="User email address")
    password_hash: str = Field(..., description="Hashed password")
    name: str = Field(default="", description="User full name (optional)")
    is_active: bool = Field(default=True, description="Whether user is active")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="User creation timestamp",
    )
    last_accessed: Optional[datetime] = Field(
        default=None, description="Last time the user authenticated on the platform"
    )
    roles: List[str] = Field(
        default_factory=lambda: ["user"],
        description="User roles",
    )
    permissions: List[str] = Field(
        default_factory=list,
        description="Direct permissions (union with role-derived at runtime)",
    )

    @classmethod
    async def create(cls, **kwargs: Any) -> "User":
        """Create and save a new user instance with email validation.

        Args:
            **kwargs: User attributes including 'email' which must be a valid email format

        Returns:
            Created and saved user instance

        Raises:
            ValueError: If email format is invalid
        """
        from pydantic import ValidationError

        # Validate email if provided
        if "email" in kwargs:
            email = kwargs["email"]
            try:
                # Use Pydantic's email validator to validate email format
                # Create a temporary model to leverage Pydantic's EmailStr validation
                class EmailValidator(BaseModel):
                    email: EmailStr

                # This will raise ValidationError if email is invalid
                validator = EmailValidator(email=email)
                kwargs["email"] = validator.email
            except ValidationError as e:
                raise ValueError(f"Invalid email format: {email}") from e

        # Call parent create method
        return await super().create(**kwargs)


class TokenBlacklist(Object):
    """Token blacklist entity for logout functionality.

    TokenBlacklist is stored as an Object entity (not Node) as it is a fundamental
    authentication lookup table that doesn't need graph relationships.
    Blacklist entries are used to track revoked JWT tokens and don't require
    graph connections via edges.
    """

    token_id: str = Field(..., description="JWT token ID")
    user_id: str = Field(..., description="User ID who owns the token")
    expires_at: datetime = Field(..., description="Token expiration time")
    blacklisted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When token was blacklisted",
    )


class APIKeyCreateRequest(BaseModel):
    """Request model for creating an API key."""

    name: str = Field(..., description="Descriptive name for the key")
    permissions: List[str] = Field(
        default_factory=list, description="List of permissions granted to this key"
    )
    rate_limit_override: Optional[int] = Field(
        None, description="Custom rate limit (requests per minute), None uses default"
    )
    expires_in_days: Optional[int] = Field(
        None, description="Number of days until key expires, None for no expiration"
    )
    allowed_ips: List[str] = Field(
        default_factory=list,
        description="IP whitelist (empty list allows all IPs)",
    )
    allowed_endpoints: List[str] = Field(
        default_factory=list,
        description="Endpoint whitelist (empty list allows all endpoints)",
    )


class APIKeyCreateResponse(BaseModel):
    """Response model for API key creation."""

    key: str = Field(..., description="Full API key (shown ONCE only)")
    key_id: str = Field(..., description="API key ID")
    key_prefix: str = Field(..., description="Key prefix for display")
    name: str = Field(..., description="Key name")
    message: str = Field(
        default="Store this key securely. It won't be shown again.",
        description="Warning message",
    )


class APIKeyResponse(BaseModel):
    """Response model for API key listing."""

    id: str = Field(..., description="API key ID")
    name: str = Field(..., description="Key name")
    key_prefix: str = Field(..., description="Key prefix for display")
    created_at: datetime = Field(..., description="Creation timestamp")
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")
    is_active: bool = Field(..., description="Whether key is active")
    permissions: List[str] = Field(..., description="Granted permissions")
    rate_limit_override: Optional[int] = Field(
        None, description="Custom rate limit override"
    )


class APIKey(Object):
    """API Key entity for authentication.

    API keys are stored as Object entities (not Node) as they are fundamental
    authentication objects that don't need graph relationships.
    Keys are hashed (never stored in plaintext) for security.
    """

    key_hash: str = Field(..., description="SHA-256 hash of the API key")
    key_prefix: str = Field(
        ..., description="First 8-12 chars for display (e.g., 'sk_live_abc12345...')"
    )
    name: str = Field(..., description="Descriptive name for the key")
    user_id: str = Field(..., description="Owner user ID")
    permissions: List[str] = Field(
        default_factory=list, description="Granted permissions"
    )
    rate_limit_override: Optional[int] = Field(
        None, description="Custom rate limit (requests per minute)"
    )

    is_active: bool = Field(default=True, description="Whether key is active")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")
    expires_at: Optional[datetime] = Field(None, description="Expiration timestamp")

    # Security restrictions
    allowed_ips: List[str] = Field(
        default_factory=list, description="IP whitelist (empty = all IPs allowed)"
    )
    allowed_endpoints: List[str] = Field(
        default_factory=list,
        description="Endpoint whitelist (empty = all endpoints allowed)",
    )


class RefreshToken(Object):
    """Refresh Token entity for authentication.

    Refresh tokens are stored as Object entities (not Node) as they are fundamental
    authentication objects that don't need graph relationships.
    Tokens are hashed (never stored in plaintext) for security.
    """

    token_hash: str = Field(..., description="Hashed refresh token (never plaintext)")
    user_id: str = Field(..., description="Owner user ID")
    access_token_jti: str = Field(
        ..., description="JTI of associated access token for tracking"
    )
    expires_at: datetime = Field(..., description="Token expiration timestamp")
    is_active: bool = Field(default=True, description="Whether token is active")
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Creation timestamp",
    )
    last_used_at: Optional[datetime] = Field(None, description="Last usage timestamp")
    device_info: Optional[str] = Field(None, description="Optional device identifier")
    ip_address: Optional[str] = Field(None, description="Optional IP address")
