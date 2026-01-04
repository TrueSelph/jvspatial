"""Authentication models for user management and JWT tokens."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, EmailStr, Field

from jvspatial.core.entities.node import Node
from jvspatial.core.entities.object import Object


class UserCreate(BaseModel):
    """Model for creating a new user."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(
        ..., min_length=6, description="User password (min 6 characters)"
    )


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


class TokenResponse(BaseModel):
    """Model for authentication token response."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: UserResponse = Field(..., description="User information")


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
        default_factory=datetime.utcnow, description="User creation timestamp"
    )
    last_accessed: Optional[datetime] = Field(
        default=None, description="Last time the user authenticated on the platform"
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


class TokenBlacklist(Node):
    """Token blacklist entity for logout functionality."""

    token_id: str = Field(..., description="JWT token ID")
    user_id: str = Field(..., description="User ID who owns the token")
    expires_at: datetime = Field(..., description="Token expiration time")
    blacklisted_at: datetime = Field(
        default_factory=datetime.utcnow, description="When token was blacklisted"
    )
