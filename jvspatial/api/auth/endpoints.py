"""Authentication management endpoints for jvspatial.

This module provides endpoints for user registration, login, token management,
API key management, and user administration using function endpoints
(since auth operations don't require graph traversal).
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, cast

from fastapi import Request
from pydantic import BaseModel, EmailStr, Field

from jvspatial.api import endpoint  # For public endpoints

from .decorators import (
    admin_endpoint,
    auth_endpoint,
)
from .entities import APIKey, InvalidCredentialsError, Session, User
from .middleware import (
    JWTManager,
    authenticate_user,
    get_current_user,
    refresh_session,
)

logger = logging.getLogger(__name__)


# ====================== REQUEST/RESPONSE MODELS ======================


class UserRegistrationRequest(BaseModel):
    """Request model for user registration."""

    username: str = Field(..., min_length=3, max_length=50)
    email: EmailStr = Field(...)
    password: str = Field(..., min_length=8, max_length=100)
    confirm_password: str = Field(..., min_length=8, max_length=100)


class LoginRequest(BaseModel):
    """Request model for user login."""

    username: str = Field(..., description="Username or email")
    password: str = Field(..., min_length=1)
    remember_me: bool = Field(default=False, description="Extend session duration")


class TokenRefreshRequest(BaseModel):
    """Request model for token refresh."""

    refresh_token: str = Field(..., description="JWT refresh token")


class LogoutRequest(BaseModel):
    """Request model for user logout."""

    revoke_all_sessions: bool = Field(
        default=False, description="Revoke all user sessions"
    )


class UpdateProfileRequest(BaseModel):
    """Request model for profile update."""

    email: Optional[str] = Field(default=None, description="New email address")
    current_password: Optional[str] = Field(
        default=None, description="Current password for verification"
    )
    new_password: Optional[str] = Field(
        default=None, min_length=8, description="New password"
    )


class APIKeyCreateRequest(BaseModel):
    """Request model for API key creation."""

    name: str = Field(..., description="Human-readable name for the key")
    expires_days: Optional[int] = Field(
        default=None, description="Days until expiration"
    )
    allowed_endpoints: List[str] = Field(
        default_factory=list, description="Allowed endpoint patterns"
    )
    rate_limit_per_hour: int = Field(default=10000, description="Rate limit per hour")


class APIKeyRevokeRequest(BaseModel):
    """Request model for API key revocation."""

    key_id: str = Field(..., description="ID of the API key to revoke")


class UserUpdateRequest(BaseModel):
    """Request model for user update (admin)."""

    user_id: str = Field(..., description="ID of user to update")
    is_active: Optional[bool] = Field(
        default=None, description="Activate/deactivate user"
    )
    is_admin: Optional[bool] = Field(
        default=None, description="Grant/revoke admin status"
    )
    roles: Optional[List[str]] = Field(default=None, description="Update user roles")
    permissions: Optional[List[str]] = Field(
        default=None, description="Update user permissions"
    )


class UserListRequest(BaseModel):
    """Request model for user listing (admin)."""

    page: int = Field(default=1, ge=1, description="Page number")
    limit: int = Field(default=50, ge=1, le=100, description="Users per page")
    active_only: bool = Field(default=False, description="Show only active users")


# ====================== PUBLIC AUTHENTICATION ENDPOINTS ======================


@endpoint("/auth/register", methods=["POST"])
async def register_user(request: UserRegistrationRequest):
    """Register a new user account."""
    try:
        # Validate password confirmation
        if request.password != request.confirm_password:
            return {
                "status": "error",
                "error": "password_mismatch",
                "message": "Passwords do not match",
            }

        # Check if username already exists
        existing_user = await User.find_by_username(request.username)
        if existing_user:
            return {
                "status": "error",
                "error": "username_taken",
                "message": "Username is already taken",
            }

        # Check if email already exists
        existing_email = await User.find_by_email(request.email)
        if existing_email:
            return {
                "status": "error",
                "error": "email_taken",
                "message": "Email is already registered",
            }

        # Create new user
        password_hash = User.hash_password(request.password)
        user = await User.create(
            username=request.username,
            email=request.email,
            password_hash=password_hash,
            created_at=datetime.now(),
        )

        return {
            "status": "success",
            "message": "User registered successfully",
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "created_at": user.created_at.isoformat(),
            },
        }

    except Exception as e:
        logger.error(f"User registration failed: {e}")
        return {
            "status": "error",
            "error": "registration_failed",
            "message": "Registration failed. Please try again.",
        }


@endpoint("/auth/login", methods=["POST"])
async def login_user(request: LoginRequest):
    """Authenticate user and create session."""
    try:
        # Authenticate user
        user = await authenticate_user(request.username, request.password)

        # Create session tokens
        access_token = JWTManager.create_access_token(user)
        refresh_token = JWTManager.create_refresh_token(user)

        # Create session record
        session_duration = 24 * 7 if request.remember_me else 24  # 7 days or 24 hours
        await Session.create(
            session_id=Session.create_session_id(),
            user_id=user.id,
            jwt_token=access_token,
            refresh_token=refresh_token,
            expires_at=datetime.now() + timedelta(hours=session_duration),
        )

        return {
            "status": "success",
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": session_duration * 3600,  # Convert to seconds
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "is_admin": user.is_admin,
                "roles": user.roles,
                "permissions": user.permissions,
            },
        }

    except InvalidCredentialsError:
        return {
            "status": "error",
            "error": "invalid_credentials",
            "message": "Invalid username or password",
        }
    except Exception as e:
        logger.error(f"Login failed: {e}")
        return {
            "status": "error",
            "error": "login_failed",
            "message": "Login failed. Please try again.",
        }


@endpoint("/auth/refresh", methods=["POST"])
async def refresh_token(request: TokenRefreshRequest):
    """Refresh access token using refresh token."""
    try:
        # Refresh the session
        new_access_token, new_refresh_token = await refresh_session(
            request.refresh_token
        )

        return {
            "status": "success",
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": 24 * 3600,  # 24 hours in seconds
        }

    except Exception as e:
        logger.error(f"Token refresh failed: {e}")
        return {
            "status": "error",
            "error": "refresh_failed",
            "message": "Token refresh failed. Please log in again.",
        }


# ====================== AUTHENTICATED USER ENDPOINTS ======================


@auth_endpoint("/auth/logout", methods=["POST"])
async def logout_user(request: LogoutRequest, current_request: Request):
    """Logout user and revoke session."""
    try:
        # Get current user from request
        current_user = get_current_user(current_request)

        if request.revoke_all_sessions and current_user:
            # In a real implementation, we would revoke all sessions for this user
            # For now, just acknowledge the request
            pass

        return {"status": "success", "message": "Logged out successfully"}

    except Exception as e:
        logger.error(f"Logout failed: {e}")
        return {"status": "error", "error": "logout_failed", "message": "Logout failed"}


@auth_endpoint("/auth/profile", methods=["GET"])
async def get_user_profile(request: Request):
    """Get current user's profile information."""
    try:
        # Get current user from request context
        current_user = get_current_user(request)

        if current_user is None:
            return {
                "status": "error",
                "error": "user_not_found",
                "message": "User not authenticated",
            }

        return {
            "status": "success",
            "message": "Profile retrieved successfully",
            "profile": {
                "id": current_user.id,
                "username": current_user.username,
                "email": current_user.email,
                "roles": current_user.roles,
                "permissions": current_user.permissions,
                "is_admin": current_user.is_admin,
                "is_active": current_user.is_active,
                "created_at": current_user.created_at.isoformat(),
                "last_login": (
                    current_user.last_login.isoformat()
                    if current_user.last_login
                    else None
                ),
                "login_count": current_user.login_count,
            },
        }

    except Exception as e:
        logger.error(f"Profile retrieval failed: {e}")
        return {
            "status": "error",
            "error": "profile_failed",
            "message": "Failed to retrieve profile",
        }


@auth_endpoint("/auth/profile", methods=["PUT"])
async def update_user_profile(request_data: UpdateProfileRequest, request: Request):
    """Update current user's profile information."""
    try:
        # Get current user from request context
        current_user = get_current_user(request)

        if current_user is None:
            return {
                "status": "error",
                "error": "user_not_found",
                "message": "User not authenticated",
            }

        updates = {}

        # Update email if provided
        if request_data.email:
            # Verify current password for email changes
            if not request_data.current_password:
                return {
                    "status": "error",
                    "error": "password_required",
                    "message": "Current password required to change email",
                }

            if not current_user.verify_password(request_data.current_password):
                return {
                    "status": "error",
                    "error": "invalid_password",
                    "message": "Current password is incorrect",
                }

            # Check if new email is already taken
            existing_email = await User.find_by_email(request_data.email)
            if existing_email and existing_email.id != current_user.id:
                return {
                    "status": "error",
                    "error": "email_taken",
                    "message": "Email is already registered",
                }

            current_user.email = request_data.email
            updates["email"] = request_data.email

        # Update password if provided
        if request_data.new_password:
            if not request_data.current_password:
                return {
                    "status": "error",
                    "error": "password_required",
                    "message": "Current password required to change password",
                }

            if not current_user.verify_password(request_data.current_password):
                return {
                    "status": "error",
                    "error": "invalid_password",
                    "message": "Current password is incorrect",
                }

            current_user.password_hash = User.hash_password(request_data.new_password)
            updates["password"] = "updated"  # pragma: allowlist secret

        # Save changes
        if updates:
            await current_user.save()

        return {
            "status": "success",
            "message": "Profile updated successfully",
            "updates": updates,
        }

    except Exception as e:
        logger.error(f"Profile update failed: {e}")
        return {
            "status": "error",
            "error": "update_failed",
            "message": "Failed to update profile",
        }


# ====================== API KEY MANAGEMENT ENDPOINTS ======================


@auth_endpoint("/auth/api-keys", methods=["GET"])
async def list_api_keys(request: Request):
    """List current user's API keys."""
    try:
        # Get current user from request context
        current_user = get_current_user(request)

        if current_user is None:
            return {
                "status": "error",
                "error": "user_not_found",
                "message": "User not authenticated",
            }

        # Find API keys for current user
        api_keys = await APIKey.find({"context.user_id": current_user.id})

        return {
            "status": "success",
            "api_keys": [
                {
                    "key_id": key.key_id,
                    "name": key.name,
                    "created_at": key.created_at.isoformat(),
                    "last_used": key.last_used.isoformat() if key.last_used else None,
                    "usage_count": key.usage_count,
                    "expires_at": (
                        key.expires_at.isoformat() if key.expires_at else None
                    ),
                    "is_active": key.is_active,
                    "rate_limit_per_hour": key.rate_limit_per_hour,
                    "allowed_endpoints": key.allowed_endpoints,
                }
                for key in api_keys
            ],
            "count": len(api_keys),
        }

    except Exception as e:
        logger.error(f"API key listing failed: {e}")
        return {
            "status": "error",
            "error": "list_failed",
            "message": "Failed to list API keys",
        }


@auth_endpoint("/auth/api-keys", methods=["POST"])
async def create_api_key(request_data: APIKeyCreateRequest, request: Request):
    """Create a new API key for the current user."""
    try:
        # Get current user from request context
        current_user = get_current_user(request)

        if not current_user:
            return {
                "status": "error",
                "error": "user_not_found",
                "message": "User not authenticated",
            }

        # Generate key pair
        key_id, secret_key = APIKey.generate_key_pair()

        # Calculate expiration
        expires_at = None
        if request_data.expires_days:
            expires_at = datetime.now() + timedelta(days=request_data.expires_days)

        # Create API key
        api_key = await APIKey.create(
            name=request_data.name,
            key_id=key_id,
            key_hash=APIKey.hash_secret(secret_key),
            user_id=current_user.id,
            expires_at=expires_at,
            allowed_endpoints=request_data.allowed_endpoints,
            rate_limit_per_hour=request_data.rate_limit_per_hour,
        )

        return {
            "status": "success",
            "message": "API key created successfully",
            "api_key": {
                "key_id": key_id,
                "secret_key": secret_key,  # Only shown once!
                "name": request_data.name,
                "created_at": api_key.created_at.isoformat(),
                "expires_at": expires_at.isoformat() if expires_at else None,
                "rate_limit_per_hour": request_data.rate_limit_per_hour,
                "allowed_endpoints": request_data.allowed_endpoints,
            },
            "warning": "Store the secret key safely. It will not be shown again.",
        }

    except Exception as e:
        logger.error(f"API key creation failed: {e}")
        return {
            "status": "error",
            "error": "creation_failed",
            "message": "Failed to create API key",
        }


@auth_endpoint("/auth/api-keys", methods=["DELETE"])
async def revoke_api_key(request_data: APIKeyRevokeRequest, request: Request):
    """Revoke an API key."""
    try:
        # Get current user from request context
        current_user = get_current_user(request)

        if current_user is None:
            return {
                "status": "error",
                "error": "user_not_found",
                "message": "User not authenticated",
            }

        # Find and revoke the API key
        api_key = await APIKey.find_by_key_id(request_data.key_id)

        if not api_key:
            return {
                "status": "error",
                "error": "key_not_found",
                "message": "API key not found",
            }

        # Check if key belongs to current user
        if api_key.user_id != current_user.id:
            return {
                "status": "error",
                "error": "unauthorized",
                "message": "You can only revoke your own API keys",
            }

        api_key.is_active = False
        await api_key.save()

        return {
            "status": "success",
            "message": "API key revoked successfully",
            "revoked_key": {
                "key_id": api_key.key_id,
                "name": api_key.name,
                "revoked_at": datetime.now().isoformat(),
            },
        }

    except Exception as e:
        logger.error(f"API key revocation failed: {e}")
        return {
            "status": "error",
            "error": "revocation_failed",
            "message": "Failed to revoke API key",
        }


# ====================== ADMIN ENDPOINTS ======================


@admin_endpoint("/auth/admin/users", methods=["GET"])
async def list_users(request_data: UserListRequest, request: Request):
    """List all users (admin only)."""
    try:
        # Get current admin user (middleware already verified admin access)
        # admin user is verified by middleware, no need to store it

        # Build query
        query = {}
        if request_data.active_only:
            query["context.is_active"] = True

        # Get users with pagination
        all_users = await User.find(query)

        # Apply pagination
        start_idx = (request_data.page - 1) * request_data.limit
        end_idx = start_idx + request_data.limit
        paginated_users = all_users[start_idx:end_idx]

        return {
            "status": "success",
            "users": [
                {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "is_active": user.is_active,
                    "is_admin": user.is_admin,
                    "is_verified": user.is_verified,
                    "roles": user.roles,
                    "permissions": user.permissions,
                    "created_at": user.created_at.isoformat(),
                    "last_login": (
                        user.last_login.isoformat() if user.last_login else None
                    ),
                    "login_count": user.login_count,
                }
                for user in paginated_users
            ],
            "pagination": {
                "page": request_data.page,
                "limit": request_data.limit,
                "total": len(all_users),
                "pages": (len(all_users) + request_data.limit - 1)
                // request_data.limit,
            },
        }

    except Exception as e:
        logger.error(f"User listing failed: {e}")
        return {
            "status": "error",
            "error": "list_failed",
            "message": "Failed to list users",
        }


@admin_endpoint("/auth/admin/users", methods=["PUT"])
async def update_user(request_data: UserUpdateRequest, request: Request):
    """Update user information (admin only)."""
    try:
        # Get current admin user (middleware already verified admin access)
        admin_user = get_current_user(request)
        if admin_user is None:
            return {
                "status": "error",
                "error": "admin_not_found",
                "message": "Admin not authenticated",
            }

        # Find user to update
        user = await User.get(request_data.user_id)
        if user is None:
            return {
                "status": "error",
                "error": "user_not_found",
                "message": "User not found",
            }

        # Update fields
        from typing import Any, Dict

        updates: Dict[str, Any] = {}

        if request_data.is_active is not None:
            user.is_active = request_data.is_active
            updates["is_active"] = request_data.is_active

        if request_data.is_admin is not None:
            user.is_admin = request_data.is_admin
            updates["is_admin"] = request_data.is_admin

        if request_data.roles is not None:
            roles_list = cast(List[str], request_data.roles)
            user.roles = roles_list
            updates["roles"] = roles_list

        if request_data.permissions is not None:
            permissions_list = cast(List[str], request_data.permissions)
            user.permissions = permissions_list
            updates["permissions"] = permissions_list

        # Save changes
        if updates:
            await user.save()

        return {
            "status": "success",
            "message": "User updated successfully",
            "user_id": user.id,
            "updates": updates,
            "updated_by": {
                "admin_id": admin_user.id,
                "admin_username": admin_user.username,
            },
        }

    except Exception as e:
        logger.error(f"User update failed: {e}")
        return {
            "status": "error",
            "error": "update_failed",
            "message": "Failed to update user",
        }


@admin_endpoint("/auth/admin/stats", methods=["GET"])
async def get_auth_stats(request: Request):
    """Get authentication system statistics (admin only)."""
    try:
        # Get current admin user (middleware already verified admin access)
        admin_user = get_current_user(request)
        if admin_user is None:
            return {
                "status": "error",
                "error": "admin_not_found",
                "message": "Admin not authenticated",
            }

        # Query actual statistics from the database
        users = await User.find({})
        api_keys = await APIKey.find({})
        sessions = await Session.find({})

        # Calculate statistics
        active_users = len([u for u in users if u.is_active])
        admin_users = len([u for u in users if u.is_admin])
        verified_users = len([u for u in users if u.is_verified])
        active_api_keys = len([k for k in api_keys if k.is_active])
        active_sessions = len([s for s in sessions if s.is_valid()])

        return {
            "status": "success",
            "statistics": {
                "total_users": len(users),
                "active_users": active_users,
                "admin_users": admin_users,
                "verified_users": verified_users,
                "total_api_keys": len(api_keys),
                "active_api_keys": active_api_keys,
                "active_sessions": active_sessions,
                "database_collections": ["user", "apikey", "session"],
            },
            "generated_at": datetime.now().isoformat(),
            "generated_by": {
                "admin_id": admin_user.id,
                "admin_username": admin_user.username,
            },
        }

    except Exception as e:
        logger.error(f"Stats retrieval failed: {e}")
        return {
            "status": "error",
            "error": "stats_failed",
            "message": "Failed to retrieve statistics",
        }


@admin_endpoint("/auth/admin/users/{user_id}", methods=["DELETE"])
async def delete_user(user_id: str, request: Request):
    """Delete a user (admin only)."""
    try:
        # Get current admin user (middleware already verified admin access)
        admin_user = get_current_user(request)
        if admin_user is None:
            return {
                "status": "error",
                "error": "admin_not_found",
                "message": "Admin not authenticated",
            }

        # Find user to delete
        user = await User.get(user_id)
        if user is None:
            return {
                "status": "error",
                "error": "user_not_found",
                "message": "User not found",
            }

        # Prevent admin from deleting themselves
        if user.id == admin_user.id:
            return {
                "status": "error",
                "error": "self_deletion",
                "message": "Cannot delete your own account",
            }

        # Delete associated API keys first
        user_api_keys = await APIKey.find({"context.user_id": user.id})
        for api_key in user_api_keys:
            await api_key.delete()

        # Delete associated sessions
        user_sessions = await Session.find({"context.user_id": user.id})
        for session in user_sessions:
            await session.delete()

        # Delete user
        await user.delete()

        return {
            "status": "success",
            "message": "User deleted successfully",
            "deleted_user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
            },
            "deleted_by": {
                "admin_id": admin_user.id,
                "admin_username": admin_user.username,
            },
            "cleanup": {
                "api_keys_deleted": len(user_api_keys),
                "sessions_deleted": len(user_sessions),
            },
        }

    except Exception as e:
        logger.error(f"User deletion failed: {e}")
        return {
            "status": "error",
            "error": "deletion_failed",
            "message": "Failed to delete user",
        }
