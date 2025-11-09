"""Authentication service for user management and JWT token handling."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import jwt

from jvspatial.api.auth.models import (
    TokenBlacklist,
    TokenResponse,
    User,
    UserCreate,
    UserLogin,
    UserResponse,
)
from jvspatial.core.context import GraphContext
from jvspatial.db import get_prime_database


class AuthenticationService:
    """Service for handling user authentication and JWT tokens.

    Always uses the prime database for authentication and session management
    to ensure core persistence operations are isolated.
    """

    def __init__(self, context: Optional[GraphContext] = None):
        """Initialize the authentication service.

        Args:
            context: GraphContext instance for database operations.
                    If None, creates a context using the prime database.
        """
        if context is None:
            # Always use prime database for authentication
            prime_db = get_prime_database()
            self.context = GraphContext(database=prime_db)
        else:
            # Ensure context uses prime database for auth operations
            prime_db = get_prime_database()
            # Create new context with prime database to ensure isolation
            self.context = GraphContext(database=prime_db)
        self.jwt_secret = (
            "jvspatial-secret-key-change-in-production"  # TODO: Make configurable
        )
        self.jwt_algorithm = "HS256"
        self.jwt_expire_minutes = 30

    def _hash_password(self, password: str) -> str:
        """Hash a password using SHA-256 with salt.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}:{password_hash}"

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash.

        Args:
            password: Plain text password
            password_hash: Stored password hash

        Returns:
            True if password matches, False otherwise
        """
        try:
            salt, stored_hash = password_hash.split(":", 1)
            password_hash_check = hashlib.sha256((password + salt).encode()).hexdigest()
            return password_hash_check == stored_hash
        except (ValueError, AttributeError):
            return False

    def _generate_jwt_token(self, user_id: str, email: str) -> Tuple[str, datetime]:
        """Generate a JWT token for a user.

        Args:
            user_id: User ID
            email: User email

        Returns:
            Tuple of (token_string, expiration_datetime)
        """
        now = datetime.utcnow()
        expires_at = now + timedelta(minutes=self.jwt_expire_minutes)

        payload = {
            "user_id": user_id,
            "email": email,
            "iat": now,
            "exp": expires_at,
            "jti": str(uuid.uuid4()),  # JWT ID for token tracking
        }

        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token, expires_at

    def _decode_jwt_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            Token payload if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token, self.jwt_secret, algorithms=[self.jwt_algorithm]
            )
            return payload
        except jwt.ExpiredSignatureError:
            return None
        except jwt.InvalidTokenError:
            return None

    async def _is_token_blacklisted(self, token: str) -> bool:
        """Check if a token is blacklisted.

        Args:
            token: JWT token string

        Returns:
            True if token is blacklisted, False otherwise
        """
        try:
            payload = self._decode_jwt_token(token)
            if not payload:
                return True  # Invalid or expired tokens are considered blacklisted

            token_id = payload.get("jti")
            if not token_id:
                return True  # Token without JTI cannot be blacklisted

            blacklisted_tokens = await self.context.find_nodes(
                TokenBlacklist, {"context.token_id": token_id}
            )

            return len(blacklisted_tokens) > 0
        except Exception:
            return True

    async def _blacklist_token(self, token: str) -> bool:
        """Add a token to the blacklist.

        Args:
            token: JWT token string

        Returns:
            True if successfully blacklisted, False otherwise
        """
        try:
            payload = self._decode_jwt_token(token)
            if not payload:
                return False

            token_id = payload.get("jti")
            user_id = payload.get("user_id")
            expires_at = datetime.fromtimestamp(payload.get("exp", 0))

            if not token_id or not user_id:
                return False

            # Create blacklist entry
            blacklist_entry = TokenBlacklist(
                token_id=token_id, user_id=user_id, expires_at=expires_at
            )

            await self.context.save_node(blacklist_entry)
            return True
        except Exception:
            return False

    async def register_user(self, user_data: UserCreate) -> UserResponse:
        """Register a new user.

        Args:
            user_data: User creation data

        Returns:
            UserResponse with user information

        Raises:
            ValueError: If user already exists or validation fails
        """
        # Check if user already exists
        existing_users = await self.context.find_nodes(
            User, {"context.email": user_data.email}
        )

        if existing_users:
            raise ValueError("User with this email already exists")

        # Create new user
        user = User(
            email=user_data.email,
            password_hash=self._hash_password(user_data.password),
            name="",  # No name required
            is_active=True,
            created_at=datetime.utcnow(),
        )

        # Save user to database
        await self.context.save_node(user)

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
            is_active=user.is_active,
        )

    async def login_user(self, login_data: UserLogin) -> TokenResponse:
        """Authenticate a user and return JWT token.

        Args:
            login_data: User login data

        Returns:
            TokenResponse with JWT token and user information

        Raises:
            ValueError: If authentication fails
        """
        # Find user by email
        users = await self.context.find_nodes(User, {"context.email": login_data.email})

        if not users:
            raise ValueError("Invalid email or password")

        user = users[0]

        # Verify password
        if not self._verify_password(login_data.password, user.password_hash):
            raise ValueError("Invalid email or password")

        # Check if user is active
        if not user.is_active:
            raise ValueError("User account is deactivated")

        # Generate JWT token
        token, expires_at = self._generate_jwt_token(user.id, user.email)

        return TokenResponse(
            access_token=token,
            token_type="bearer",
            expires_in=self.jwt_expire_minutes * 60,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                created_at=user.created_at,
                is_active=user.is_active,
            ),
        )

    async def logout_user(self, token: str) -> bool:
        """Logout a user by blacklisting their token.

        Args:
            token: JWT token to blacklist

        Returns:
            True if successfully logged out, False otherwise
        """
        return await self._blacklist_token(token)

    async def validate_token(self, token: str) -> Optional[UserResponse]:
        """Validate a JWT token and return user information.

        Args:
            token: JWT token string

        Returns:
            UserResponse if token is valid, None otherwise
        """
        # Check if token is blacklisted
        if await self._is_token_blacklisted(token):
            return None

        # Decode token
        payload = self._decode_jwt_token(token)
        if not payload:
            return None

        # Get user information
        user_id = payload.get("user_id")
        if not user_id:
            return None

        # Find user by ID using get() method for direct ID lookup
        user = await User.get(user_id)

        if not user:
            return None

        # Check if user is still active
        if not user.is_active:
            return None

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
            is_active=user.is_active,
        )

    async def get_user_by_id(self, user_id: str) -> Optional[UserResponse]:
        """Get user information by ID.

        Args:
            user_id: User ID

        Returns:
            UserResponse if user exists, None otherwise
        """
        user = await User.get(user_id)

        if not user:
            return None

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
            is_active=user.is_active,
        )
