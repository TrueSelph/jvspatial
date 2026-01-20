"""Authentication service for user management and JWT token handling."""

import hashlib
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Tuple

import jwt

# Try to import secure hashing libraries for refresh tokens
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

from jvspatial.api.auth.models import (
    RefreshToken,
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
        refresh_expire_days: Optional[int] = None,
        refresh_token_rotation: Optional[bool] = None,
        blacklist_cache_ttl_seconds: Optional[int] = None,
    ):
        """Initialize the authentication service.

        Args:
            context: GraphContext instance for database operations.
                    If None, creates a context using the prime database.
            jwt_secret: JWT secret key (defaults to a placeholder if not provided)
            jwt_algorithm: JWT algorithm (defaults to "HS256")
            jwt_expire_minutes: JWT expiration time in minutes (defaults to 30)
            refresh_expire_days: Refresh token expiration time in days (defaults to 7)
            refresh_token_rotation: Enable refresh token rotation (defaults to False)
            blacklist_cache_ttl_seconds: Cache TTL for blacklist checks (defaults to 3600)
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
        self.refresh_expire_days = refresh_expire_days or 7
        self.refresh_token_rotation = refresh_token_rotation or False
        self.blacklist_cache_ttl_seconds = blacklist_cache_ttl_seconds or 3600

        # In-memory cache for blacklist checks: {jti: (is_blacklisted, timestamp)}
        self._blacklist_cache: Dict[str, Tuple[bool, float]] = {}
        self._logger = logging.getLogger(__name__)

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

    def _hash_refresh_token(self, token: str) -> str:
        """Hash a refresh token using secure password hashing.

        Uses bcrypt if available, falls back to argon2, then passlib.
        If none are available, falls back to SHA-256 with a warning.

        Args:
            token: Plaintext refresh token

        Returns:
            Hashed token string
        """
        if _HASHING_AVAILABLE:
            if _HASHING_LIB == "bcrypt":
                # Bcrypt has a 72-byte limit, so hash long tokens with SHA-256 first
                token_bytes = token.encode("utf-8")
                if len(token_bytes) > 72:
                    # Hash with SHA-256 first, then bcrypt the hash
                    token_hash = hashlib.sha256(token_bytes).hexdigest()
                    token_bytes = token_hash.encode("utf-8")
                salt = bcrypt.gensalt()
                hashed = bcrypt.hashpw(token_bytes, salt)
                return hashed.decode("utf-8")
            elif _HASHING_LIB == "argon2":
                return _argon2_hasher.hash(token)
            elif _HASHING_LIB == "passlib":
                return _passlib_context.hash(token)
        else:
            self._logger.warning(
                "No secure hashing library available (bcrypt/argon2/passlib). "
                "Using SHA-256 for refresh tokens. Install bcrypt for production: pip install bcrypt"
            )
            return hashlib.sha256(token.encode()).hexdigest()

    def _verify_refresh_token(self, token: str, hashed: str) -> bool:
        """Verify a refresh token against its hash.

        Args:
            token: Plaintext refresh token to verify
            hashed: Stored hash to verify against

        Returns:
            True if token matches hash, False otherwise
        """
        if _HASHING_AVAILABLE:
            if _HASHING_LIB == "bcrypt":
                try:
                    # Bcrypt has a 72-byte limit, so hash long tokens with SHA-256 first
                    token_bytes = token.encode("utf-8")
                    if len(token_bytes) > 72:
                        # Hash with SHA-256 first, then verify with bcrypt
                        token_hash = hashlib.sha256(token_bytes).hexdigest()
                        token_bytes = token_hash.encode("utf-8")
                    return bcrypt.checkpw(token_bytes, hashed.encode("utf-8"))
                except Exception:
                    return False
            elif _HASHING_LIB == "argon2":
                try:
                    _argon2_hasher.verify(hashed, token)
                    return True
                except Exception:
                    return False
            elif _HASHING_LIB == "passlib":
                try:
                    return _passlib_context.verify(token, hashed)
                except Exception:
                    return False
        else:
            return hashlib.sha256(token.encode()).hexdigest() == hashed

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

        DEPRECATED: Use _is_token_blacklisted_by_jti() instead.
        This method is kept for backward compatibility but decodes the token unnecessarily.

        Args:
            token: JWT token string

        Returns:
            True if token is blacklisted, False otherwise
        """
        try:
            payload = self._decode_jwt_token(token)
            if not payload:
                # Invalid or expired tokens - jwt.decode() already handled this
                return False  # Don't check blacklist for invalid tokens

            token_id = payload.get("jti")
            if not token_id:
                return False  # Token without JTI cannot be blacklisted

            return await self._is_token_blacklisted_by_jti(token_id)
        except Exception:
            # If there's an error checking blacklist, assume not blacklisted
            # (fail open for availability)
            return False

    async def _is_token_blacklisted_by_jti(self, token_id: str) -> bool:
        """Check if a token is blacklisted by its JTI.

        Uses caching to reduce database queries. Checks cache first,
        then queries database on cache miss.

        Args:
            token_id: JWT token ID (jti claim)

        Returns:
            True if token is blacklisted, False otherwise
        """
        try:
            if not token_id:
                return False

            # Check cache first
            cache_key = f"blacklist:{token_id}"
            current_time = time.time()

            if cache_key in self._blacklist_cache:
                is_blacklisted, cache_timestamp = self._blacklist_cache[cache_key]
                # Check if cache entry is still valid
                if current_time - cache_timestamp < self.blacklist_cache_ttl_seconds:
                    self._logger.debug(
                        f"Blacklist cache hit for token {token_id}: {is_blacklisted}"
                    )
                    return is_blacklisted
                # Cache expired, remove it
                del self._blacklist_cache[cache_key]

            # Cache miss or expired - query database
            await self.context.ensure_indexes(TokenBlacklist)
            collection, final_query = await TokenBlacklist._build_database_query(
                self.context, {"context.token_id": token_id}, {}
            )

            results = await self.context.database.find(collection, final_query)
            is_blacklisted = len(results) > 0

            # Update cache
            self._blacklist_cache[cache_key] = (is_blacklisted, current_time)

            self._logger.debug(
                f"Blacklist check for token {token_id}: {is_blacklisted} (cache miss)"
            )
            return is_blacklisted
        except Exception as e:
            # If there's an error checking blacklist, assume not blacklisted
            # (fail open for availability)
            self._logger.warning(f"Error checking blacklist for token {token_id}: {e}")
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

            # Update cache
            cache_key = f"blacklist:{token_id}"
            self._blacklist_cache[cache_key] = (True, time.time())
            self._logger.debug(f"Token {token_id} blacklisted and cached")

            return True
        except Exception:
            return False

    def _generate_refresh_token_string(self) -> str:
        """Generate a new refresh token string.

        Returns:
            Generated refresh token string
        """
        # Generate secure random token (64 bytes = 512 bits)
        return secrets.token_urlsafe(64)

    async def _generate_and_store_refresh_token(
        self,
        user_id: str,
        access_token_jti: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Tuple[str, datetime]:
        """Generate and store a refresh token.

        Args:
            user_id: User ID
            access_token_jti: JTI of associated access token
            device_info: Optional device identifier
            ip_address: Optional IP address

        Returns:
            Tuple of (plaintext_token, expiration_datetime)
        """
        # Generate plaintext token
        plaintext_token = self._generate_refresh_token_string()

        # Hash the token
        token_hash = self._hash_refresh_token(plaintext_token)

        # Calculate expiration
        expires_at = datetime.utcnow() + timedelta(days=self.refresh_expire_days)

        # Ensure indexes exist before saving
        await self.context.ensure_indexes(RefreshToken)

        # Create refresh token entity
        from jvspatial.core.utils import generate_id

        refresh_token_id = generate_id("o", "RefreshToken")
        refresh_token = RefreshToken(
            id=refresh_token_id,
            token_hash=token_hash,
            user_id=user_id,
            access_token_jti=access_token_jti,
            expires_at=expires_at,
            device_info=device_info,
            ip_address=ip_address,
            is_active=True,
            created_at=datetime.utcnow(),
        )

        # Set context and save
        refresh_token._graph_context = self.context
        await self.context.save(refresh_token)

        return plaintext_token, expires_at

    async def _validate_refresh_token(self, token: str) -> Optional[RefreshToken]:
        """Validate a refresh token and return the entity if valid.

        Args:
            token: Plaintext refresh token

        Returns:
            RefreshToken entity if valid, None otherwise
        """
        if not token or len(token) < 10:
            return None

        # Get all active refresh tokens for validation
        # We need to check all tokens because we can't reverse the hash
        await self.context.ensure_indexes(RefreshToken)
        collection, final_query = await RefreshToken._build_database_query(
            self.context, {"context.is_active": True}, {}
        )
        results = await self.context.database.find(collection, final_query)

        for data in results:
            try:
                refresh_token_entity = await self.context._deserialize_entity(
                    RefreshToken, data
                )
                if not refresh_token_entity:
                    continue

                refresh_token_entity._graph_context = self.context

                # Check expiration
                if refresh_token_entity.expires_at < datetime.utcnow():
                    continue

                # Verify the token against the stored hash
                if self._verify_refresh_token(token, refresh_token_entity.token_hash):
                    # Update last_used_at
                    refresh_token_entity.last_used_at = datetime.utcnow()
                    await self.context.save(refresh_token_entity)
                    return refresh_token_entity
            except Exception:
                continue

        return None

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

    async def login_user(
        self,
        login_data: UserLogin,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        """Authenticate a user and return JWT token and refresh token.

        Args:
            login_data: User login data
            device_info: Optional device identifier
            ip_address: Optional IP address

        Returns:
            TokenResponse with JWT token, refresh token, and user information

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

        # Generate JWT access token
        access_token, access_expires_at = self._generate_jwt_token(user.id, user.email)
        access_token_jti = (
            self._decode_jwt_token(access_token).get("jti") if access_token else None
        )

        # Generate and store refresh token (non-blocking - login succeeds even if this fails)
        refresh_token = None
        refresh_expires_in = None
        try:
            refresh_token, refresh_expires_at = (
                await self._generate_and_store_refresh_token(
                    user.id, access_token_jti or "", device_info, ip_address
                )
            )
            refresh_expires_in = int(
                (refresh_expires_at - datetime.utcnow()).total_seconds()
            )
        except Exception as e:
            # Log warning but don't fail login if refresh token generation fails
            self._logger.warning(
                f"Failed to generate refresh token for user {user.id}: {e}. "
                "Login will proceed without refresh token."
            )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=self.jwt_expire_minutes * 60,
            refresh_token=refresh_token,
            refresh_expires_in=refresh_expires_in,
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
        # Decode token first - jwt.decode() handles expiration validation
        payload = self._decode_jwt_token(token)
        if not payload:
            self._logger.debug(
                "Token validation failed: token decode failed (invalid or expired)"
            )
            return None

        # Get token ID for blacklist check
        token_id = payload.get("jti")
        if not token_id:
            self._logger.debug("Token validation failed: token missing JTI")
            return None

        # Check if token is blacklisted (only for valid, non-expired tokens)
        if await self._is_token_blacklisted_by_jti(token_id):
            self._logger.debug(
                f"Token validation failed: token {token_id} is blacklisted"
            )
            return None

        # Get user information
        user_id = payload.get("user_id")
        if not user_id:
            self._logger.debug("Token validation failed: token missing user_id")
            return None

        # Find user by ID using service's context
        user = await self._get_user_by_id(user_id)

        if not user:
            self._logger.debug(f"Token validation failed: user {user_id} not found")
            return None

        # Check if user is still active
        if not user.is_active:
            self._logger.debug(f"Token validation failed: user {user_id} is inactive")
            return None

        # Update last_accessed timestamp on token validation (user is authenticating)
        # Ensure context is set before saving
        user._graph_context = self.context
        user.last_accessed = datetime.utcnow()
        # Use context.save() directly to ensure it uses the correct context
        await self.context.save(user)

        self._logger.debug(f"Token validation successful for user {user_id}")
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

    async def refresh_access_token(
        self,
        refresh_token: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> TokenResponse:
        """Refresh an access token using a refresh token.

        Args:
            refresh_token: Refresh token string
            device_info: Optional device identifier
            ip_address: Optional IP address

        Returns:
            TokenResponse with new access token and optionally new refresh token

        Raises:
            ValueError: If refresh token is invalid or expired
        """
        # Validate refresh token
        refresh_token_entity = await self._validate_refresh_token(refresh_token)
        if not refresh_token_entity:
            raise ValueError("Invalid or expired refresh token")

        # Get user
        user = await self._get_user_by_id(refresh_token_entity.user_id)
        if not user or not user.is_active:
            raise ValueError("User not found or inactive")

        # Generate new access token
        access_token, access_expires_at = self._generate_jwt_token(user.id, user.email)
        access_token_jti = (
            self._decode_jwt_token(access_token).get("jti") if access_token else None
        )

        # Handle refresh token rotation
        new_refresh_token = None
        refresh_expires_in = None

        if self.refresh_token_rotation:
            # Revoke old refresh token
            refresh_token_entity.is_active = False
            refresh_token_entity._graph_context = self.context
            await self.context.save(refresh_token_entity)

            # Generate new refresh token
            new_refresh_token, refresh_expires_at = (
                await self._generate_and_store_refresh_token(
                    user.id, access_token_jti or "", device_info, ip_address
                )
            )
            refresh_expires_in = int(
                (refresh_expires_at - datetime.utcnow()).total_seconds()
            )

        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=self.jwt_expire_minutes * 60,
            refresh_token=new_refresh_token,
            refresh_expires_in=refresh_expires_in,
            user=UserResponse(
                id=user.id,
                email=user.email,
                name=user.name,
                created_at=user.created_at,
                is_active=user.is_active,
            ),
        )

    async def revoke_refresh_token(self, refresh_token: str) -> bool:
        """Revoke a refresh token.

        Args:
            refresh_token: Refresh token to revoke

        Returns:
            True if token was revoked, False if not found
        """
        refresh_token_entity = await self._validate_refresh_token(refresh_token)
        if not refresh_token_entity:
            return False

        # Deactivate the refresh token
        refresh_token_entity.is_active = False
        refresh_token_entity._graph_context = self.context
        await self.context.save(refresh_token_entity)

        # Optionally blacklist the associated access token
        if refresh_token_entity.access_token_jti:
            # Try to blacklist the access token (may fail if already expired)
            # We can't decode it without the token string, but we can add to blacklist by JTI
            from jvspatial.core.utils import generate_id

            blacklist_id = generate_id("n", "TokenBlacklist")
            # Estimate expiration (access tokens expire in minutes, refresh in days)
            # Use a reasonable default expiration
            estimated_expires_at = datetime.utcnow() + timedelta(
                minutes=self.jwt_expire_minutes
            )

            blacklist_entry = TokenBlacklist(
                id=blacklist_id,
                token_id=refresh_token_entity.access_token_jti,
                user_id=refresh_token_entity.user_id,
                expires_at=estimated_expires_at,
            )
            blacklist_entry._graph_context = self.context
            try:
                await self.context.save(blacklist_entry)
                # Update cache
                cache_key = f"blacklist:{refresh_token_entity.access_token_jti}"
                self._blacklist_cache[cache_key] = (True, time.time())
            except Exception:
                # Ignore errors - token may already be expired or blacklisted
                pass

        return True

    async def revoke_all_user_tokens(self, user_id: str) -> int:
        """Revoke all refresh tokens for a user.

        Args:
            user_id: User ID

        Returns:
            Number of tokens revoked
        """
        # Get all active refresh tokens for the user
        await self.context.ensure_indexes(RefreshToken)
        collection, final_query = await RefreshToken._build_database_query(
            self.context, {"context.user_id": user_id, "context.is_active": True}, {}
        )
        results = await self.context.database.find(collection, final_query)

        revoked_count = 0
        access_token_jtis = []

        for data in results:
            try:
                refresh_token_entity = await self.context._deserialize_entity(
                    RefreshToken, data
                )
                if refresh_token_entity:
                    refresh_token_entity._graph_context = self.context
                    refresh_token_entity.is_active = False
                    await self.context.save(refresh_token_entity)
                    revoked_count += 1

                    if refresh_token_entity.access_token_jti:
                        access_token_jtis.append(refresh_token_entity.access_token_jti)
            except Exception:
                continue

        # Blacklist all associated access tokens
        from jvspatial.core.utils import generate_id

        estimated_expires_at = datetime.utcnow() + timedelta(
            minutes=self.jwt_expire_minutes
        )

        for jti in access_token_jtis:
            try:
                blacklist_id = generate_id("n", "TokenBlacklist")
                blacklist_entry = TokenBlacklist(
                    id=blacklist_id,
                    token_id=jti,
                    user_id=user_id,
                    expires_at=estimated_expires_at,
                )
                blacklist_entry._graph_context = self.context
                await self.context.save(blacklist_entry)

                # Update cache
                cache_key = f"blacklist:{jti}"
                self._blacklist_cache[cache_key] = (True, time.time())
            except Exception:
                # Ignore errors - token may already be expired or blacklisted
                pass

        return revoked_count
