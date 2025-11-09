"""Authentication models for user management and JWT tokens."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from jvspatial.core.entities.node import Node


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


class User(Node):
    """User entity model for authentication."""

    email: str = Field(..., description="User email address")
    password_hash: str = Field(..., description="Hashed password")
    name: str = Field(default="", description="User full name (optional)")
    is_active: bool = Field(default=True, description="Whether user is active")
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="User creation timestamp"
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}


class TokenBlacklist(Node):
    """Token blacklist entity for logout functionality."""

    token_id: str = Field(..., description="JWT token ID")
    user_id: str = Field(..., description="User ID who owns the token")
    expires_at: datetime = Field(..., description="Token expiration time")
    blacklisted_at: datetime = Field(
        default_factory=datetime.utcnow, description="When token was blacklisted"
    )

    class Config:
        """Pydantic configuration."""

        json_encoders = {datetime: lambda v: v.isoformat()}
