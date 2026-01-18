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

    def __init__(
        self,
        context: Optional[GraphContext] = None,
        jwt_secret: Optional[str] = None,
        jwt_algorithm: Optional[str] = None,
        jwt_expire_minutes: Optional[int] = None,
    ):
        """Initialize the authentication service.

        Args:
            context: GraphContext instance for database operations.
                    If None, creates a context using the prime database.
            jwt_secret: JWT secret key (defaults to a placeholder if not provided)
            jwt_algorithm: JWT algorithm (defaults to "HS256")
            jwt_expire_minutes: JWT expiration time in minutes (defaults to 30)
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
        self.jwt_secret = jwt_secret or "jvspatial-secret-key-change-in-production"
        self.jwt_algorithm = jwt_algorithm or "HS256"
        self.jwt_expire_minutes = jwt_expire_minutes or 30

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
        except jwt.InvalidTokenError as e:
            # Log the error for debugging (but don't expose it to users)
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(
                f"JWT token decode failed: {e}, secret length: {len(self.jwt_secret) if self.jwt_secret else 0}"
            )
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

            # Use service's context instead of get_default_context()
            await self.context.ensure_indexes(TokenBlacklist)
            collection, final_query = await TokenBlacklist._build_database_query(
                self.context, {"context.token_id": token_id}, {}
            )

            results = await self.context.database.find(collection, final_query)
            return len(results) > 0
        except Exception:
            # If there's an error checking blacklist, assume not blacklisted
            # (fail open for availability)
            return False

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

            # Create blacklist entry using service's context
            # TokenBlacklist is a Node, so we can use Node.create() but need to use our context
            from jvspatial.core.utils import generate_id

            blacklist_id = generate_id(
                "n", "TokenBlacklist"
            )  # TokenBlacklist is a Node
            blacklist_entry = TokenBlacklist(
                id=blacklist_id,
                token_id=token_id,
                user_id=user_id,
                expires_at=expires_at,
            )
            # Set context and save
            blacklist_entry._graph_context = self.context
            await self.context.save(blacklist_entry)
            return True
        except Exception:
            return False

    async def _find_user_by_email(self, email: str) -> Optional[User]:
        """Find a user by email using the service's context.

        Args:
            email: User email address

        Returns:
            User instance if found, else None
        """
        # Use service's context instead of get_default_context()
        await self.context.ensure_indexes(User)
        collection, final_query = await User._build_database_query(
            self.context, {"context.email": email}, {}
        )

        results = await self.context.database.find(collection, final_query)
        if results:
            try:
                user = await self.context._deserialize_entity(User, results[0])
                if user:
                    # Set context on user object for future operations
                    user._graph_context = self.context
                return user
            except Exception:
                return None
        return None

    async def _get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get a user by ID using the service's context.

        Args:
            user_id: User ID

        Returns:
            User instance if found, else None
        """
        # Use service's context instead of get_default_context()
        user = await self.context.get(User, user_id)
        if user:
            # Set context on user object for future operations
            user._graph_context = self.context
        return user

    async def register_user(self, user_data: UserCreate) -> UserResponse:
        """Register a new user.

        Args:
            user_data: User creation data

        Returns:
            UserResponse with user information

        Raises:
            ValueError: If user already exists or validation fails
        """
        # Check if user already exists using service's context
        existing_user = await self._find_user_by_email(user_data.email)

        if existing_user:
            raise ValueError("User with this email already exists")

        # Create new user - User.create() also uses get_default_context(),
        # so we need to create it manually using our context
        # Generate ID in correct format: type_code.ClassName.hex_id (e.g., o.User.abc123)
        from jvspatial.core.utils import generate_id

        user_id = generate_id("o", "User")
        user = User(
            id=user_id,
            email=user_data.email,
            password_hash=self._hash_password(user_data.password),
            name="",  # No name required
            is_active=True,
            created_at=datetime.utcnow(),
        )
        # Set the context on the user object so save() uses it
        user._graph_context = self.context
        # Save using our context directly to ensure it's saved to the right database
        # Note: context.save() may modify the user's ID if it doesn't match expected format
        await self.context.save(user)

        # Use the user's ID after save (in case it was modified)
        final_user_id = user.id

        return UserResponse(
            id=final_user_id,
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
        # Find user by email using service's context
        user = await self._find_user_by_email(login_data.email)

        if not user:
            raise ValueError("Invalid email or password")

        # Verify password
        if not self._verify_password(login_data.password, user.password_hash):
            raise ValueError("Invalid email or password")

        # Check if user is active
        if not user.is_active:
            raise ValueError("User account is deactivated")

        # Update last_accessed timestamp
        # Set the context on the user object so save() uses it
        user._graph_context = self.context
        user.last_accessed = datetime.utcnow()
        await user.save()

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

        # Find user by ID using service's context
        user = await self._get_user_by_id(user_id)

        if not user:
            return None

        # Check if user is still active
        if not user.is_active:
            return None

        # Update last_accessed timestamp on token validation (user is authenticating)
        # Ensure context is set before saving
        user._graph_context = self.context
        user.last_accessed = datetime.utcnow()
        # Use context.save() directly to ensure it uses the correct context
        await self.context.save(user)

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
        user = await self._get_user_by_id(user_id)

        if not user:
            return None

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
            is_active=user.is_active,
        )
