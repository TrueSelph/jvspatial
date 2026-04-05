"""Authentication service for user management and JWT token handling."""

import asyncio
import hashlib
import logging
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import jwt

from jvspatial.api.auth.models import (
    PasswordResetToken,
    RefreshToken,
    TokenBlacklist,
    TokenResponse,
    User,
    UserCreate,
    UserCreateAdmin,
    UserLogin,
    UserPermissionsUpdate,
    UserResponse,
    UserRolesUpdate,
)
from jvspatial.api.auth.rbac import get_effective_permissions
from jvspatial.api.exceptions import RegistrationDisabledError
from jvspatial.core.context import GraphContext
from jvspatial.db import get_prime_database
from jvspatial.env import env, parse_bool
from jvspatial.runtime.serverless import is_serverless_mode

_argon2_hasher_singleton = None


def _get_argon2_hasher():
    global _argon2_hasher_singleton
    if _argon2_hasher_singleton is None:
        from argon2 import PasswordHasher

        _argon2_hasher_singleton = PasswordHasher(
            time_cost=env("JVSPATIAL_ARGON2_TIME_COST", default=2, parse=int) or 2,
            memory_cost=env("JVSPATIAL_ARGON2_MEMORY_COST", default=19456, parse=int)
            or 19456,
            parallelism=env("JVSPATIAL_ARGON2_PARALLELISM", default=2, parse=int) or 2,
        )
    return _argon2_hasher_singleton


# Try to import secure hashing libraries for refresh tokens
try:
    import bcrypt

    _HASHING_AVAILABLE = True
    _HASHING_LIB = "bcrypt"
except ImportError:
    try:
        import argon2  # noqa: F401

        _HASHING_AVAILABLE = True
        _HASHING_LIB = "argon2"
    except ImportError:
        try:
            from passlib.context import CryptContext

            _HASHING_AVAILABLE = True
            _HASHING_LIB = "passlib"
            _passlib_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
        except ImportError:
            _HASHING_AVAILABLE = False
            _HASHING_LIB = None

# Insecure default secrets - must not be used when auth is enabled
_INSECURE_JWT_SECRETS = frozenset(
    {
        "",
        "jvspatial-secret-key-change-in-production",
        "your-secret-key",
    }
)


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
        password_reset_token_expiry_minutes: Optional[int] = None,
        role_permission_mapping: Optional[Dict[str, List[str]]] = None,
        admin_role: str = "admin",
        default_role: str = "user",
        registration_open: bool = True,
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
            # Fallback: use prime database for authentication
            prime_db = get_prime_database()
            self.context = GraphContext(database=prime_db)
        else:
            # Use the passed-in context (e.g. server._graph_context) to respect
            # the configured database rather than calling get_prime_database()
            self.context = context

        resolved_secret = jwt_secret or "jvspatial-secret-key-change-in-production"
        if resolved_secret in _INSECURE_JWT_SECRETS:
            raise ValueError(
                "JWT secret must be set explicitly when authentication is enabled. "
                "Set JVSPATIAL_JWT_SECRET_KEY in your environment or pass jwt_secret "
                "to Server(auth=dict(jwt_secret='your-secure-secret')). "
                "Never use the default placeholder in production."
            )
        self.jwt_secret = resolved_secret
        self.jwt_algorithm = jwt_algorithm or "HS256"
        self.jwt_expire_minutes = jwt_expire_minutes or 30
        self.refresh_expire_days = refresh_expire_days or 7
        self.refresh_token_rotation = refresh_token_rotation or False
        self.blacklist_cache_ttl_seconds = blacklist_cache_ttl_seconds or 3600
        self.password_reset_token_expiry_minutes = (
            password_reset_token_expiry_minutes or 60
        )
        self.role_permission_mapping = role_permission_mapping or {
            "admin": ["*"],
            "user": [],
        }
        self.admin_role = admin_role
        self.default_role = default_role
        self.registration_open = registration_open

        # In-memory cache for blacklist checks: {jti: (is_blacklisted, timestamp)}
        self._blacklist_cache: Dict[str, Tuple[bool, float]] = {}
        self._logger = logging.getLogger(__name__)
        self._serverless_mode = is_serverless_mode()
        self._bcrypt_rounds = (
            env("JVSPATIAL_BCRYPT_ROUNDS_SERVERLESS", default=10, parse=int)
            if self._serverless_mode
            else env("JVSPATIAL_BCRYPT_ROUNDS", default=12, parse=int)
        )
        self._bcrypt_rounds = self._bcrypt_rounds or 12
        if self._serverless_mode:
            self._logger.info(
                "AuthenticationService using serverless hashing profile (bcrypt rounds=%s).",
                self._bcrypt_rounds,
            )

    def _get_user_roles(self, user: User) -> List[str]:
        """Get user roles with backward compatibility for existing users."""
        roles = getattr(user, "roles", None)
        if roles is None or not isinstance(roles, list):
            return [self.default_role]
        return roles if roles else [self.default_role]

    def _get_user_permissions(self, user: User) -> List[str]:
        """Get user direct permissions with backward compatibility."""
        perms = getattr(user, "permissions", None)
        if perms is None or not isinstance(perms, list):
            return []
        return perms

    def _get_effective_permissions_for_user(self, user: User) -> List[str]:
        """Compute effective permissions for a user (roles + direct)."""
        roles = self._get_user_roles(user)
        direct = self._get_user_permissions(user)
        return list(
            get_effective_permissions(roles, direct, self.role_permission_mapping)
        )

    async def _user_count(self) -> int:
        """Count users in the prime database using service context."""
        collection, final_query = await User._build_database_query(self.context, {}, {})
        return await self.context.database.count(collection, final_query)

    async def count_users(self) -> int:
        """Return the number of users in the auth database (public API)."""
        return await self._user_count()

    async def find_user_by_email(self, email: str) -> Optional[User]:
        """Find a user by email (public API)."""
        return await self._find_user_by_email(email)

    def _hash_password(self, password: str) -> str:
        """Hash a password using bcrypt when available, else SHA-256 with salt.

        Prefers bcrypt for security. Falls back to SHA-256 only when no hashing
        library is available.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        if _HASHING_AVAILABLE and _HASHING_LIB == "bcrypt":
            salt = bcrypt.gensalt(rounds=self._bcrypt_rounds)
            hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
            return hashed.decode("utf-8")
        if _HASHING_AVAILABLE and _HASHING_LIB == "argon2":
            return _get_argon2_hasher().hash(password)
        if _HASHING_AVAILABLE and _HASHING_LIB == "passlib":
            return _passlib_context.hash(password)
        # Fallback when no secure library available
        if env("JVSPATIAL_AUTH_STRICT_HASHING", default=False, parse=parse_bool):
            raise RuntimeError(
                "Secure hashing library required but unavailable. "
                "Install bcrypt/argon2/passlib or disable JVSPATIAL_AUTH_STRICT_HASHING."
            )
        self._logger.warning(
            "No secure hashing library (bcrypt/argon2/passlib). "
            "Using SHA-256 fallback for passwords. This is not recommended for production."
        )
        salt = secrets.token_hex(16)
        password_hash = hashlib.sha256((password + salt).encode()).hexdigest()
        return f"{salt}:{password_hash}"

    def _verify_password(self, password: str, password_hash: str) -> bool:
        """Verify a password against its hash.

        Supports bcrypt, argon2, passlib, and legacy SHA-256 (salt:hash) formats.

        Args:
            password: Plain text password
            password_hash: Stored password hash

        Returns:
            True if password matches, False otherwise
        """
        if not password_hash:
            return False
        try:
            # Bcrypt format: $2b$... or $2a$...
            if password_hash.startswith(("$2b$", "$2a$")):
                if _HASHING_AVAILABLE and _HASHING_LIB == "bcrypt":
                    return bcrypt.checkpw(
                        password.encode("utf-8"), password_hash.encode("utf-8")
                    )
                return False
            # Argon2 format: $argon2...
            if password_hash.startswith("$argon2"):
                if _HASHING_AVAILABLE and _HASHING_LIB == "argon2":
                    try:
                        _get_argon2_hasher().verify(password_hash, password)
                        return True
                    except Exception:
                        return False
                return False
            # Passlib/bcrypt format
            if _HASHING_AVAILABLE and _HASHING_LIB == "passlib":
                return _passlib_context.verify(password, password_hash)
            # Legacy SHA-256 format: salt:hash
            salt, stored_hash = password_hash.split(":", 1)
            password_hash_check = hashlib.sha256((password + salt).encode()).hexdigest()
            return password_hash_check == stored_hash
        except Exception:
            return False

    def _is_legacy_password_hash(self, password_hash: str) -> bool:
        """Check if hash is legacy SHA-256 format (salt:hex) and bcrypt upgrade is available."""
        if not password_hash or not _HASHING_AVAILABLE or _HASHING_LIB != "bcrypt":
            return False
        return ":" in password_hash and not password_hash.startswith("$")

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
                salt = bcrypt.gensalt(rounds=self._bcrypt_rounds)
                hashed = bcrypt.hashpw(token_bytes, salt)
                return hashed.decode("utf-8")
            elif _HASHING_LIB == "argon2":
                return _get_argon2_hasher().hash(token)
            elif _HASHING_LIB == "passlib":
                return _passlib_context.hash(token)
        else:
            if env("JVSPATIAL_AUTH_STRICT_HASHING", default=False, parse=parse_bool):
                raise RuntimeError(
                    "Secure hashing library required but unavailable. "
                    "Install bcrypt/argon2/passlib or disable JVSPATIAL_AUTH_STRICT_HASHING."
                )
            self._logger.warning(
                "No secure hashing library available (bcrypt/argon2/passlib). "
                "Using SHA-256 fallback for refresh tokens. "
                "Install bcrypt for production: pip install bcrypt"
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
                    _get_argon2_hasher().verify(hashed, token)
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

    def _generate_jwt_token(
        self,
        user_id: str,
        email: str,
        roles: Optional[List[str]] = None,
        permissions: Optional[List[str]] = None,
    ) -> Tuple[str, datetime]:
        """Generate a JWT token for a user.

        Args:
            user_id: User ID
            email: User email
            roles: User roles (included in payload)
            permissions: Effective permissions (included in payload)

        Returns:
            Tuple of (token_string, expiration_datetime)
        """
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.jwt_expire_minutes)

        payload = {
            "user_id": user_id,
            "email": email,
            "iat": now,
            "exp": expires_at,
            "jti": str(uuid.uuid4()),  # JWT ID for token tracking
        }
        if roles is not None:
            payload["roles"] = roles
        if permissions is not None:
            payload["permissions"] = list(permissions)

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
        except Exception as e:
            # Fail-open for availability; operators must see failures in logs.
            self._logger.error(
                "JWT blacklist check failed (fail-open; token not treated as blacklisted): %s",
                e,
                exc_info=True,
            )
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
            # Fail-open for availability
            self._logger.error(
                "Error checking blacklist for token %s (fail-open): %s",
                token_id,
                e,
                exc_info=True,
            )
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
            # TokenBlacklist is an Object, so we need to use our context
            from jvspatial.core.utils import generate_id

            blacklist_id = generate_id("o", "TokenBlacklist")
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
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=self.refresh_expire_days
        )

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
            created_at=datetime.now(timezone.utc),
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
                if refresh_token_entity.expires_at < datetime.now(timezone.utc):
                    continue

                # Verify the token against the stored hash
                if self._verify_refresh_token(token, refresh_token_entity.token_hash):
                    # Update last_used_at
                    refresh_token_entity.last_used_at = datetime.now(timezone.utc)
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

        # When registration_open is False, disable public registration entirely
        if not self.registration_open:
            raise RegistrationDisabledError()

        # Bootstrap: first user gets admin role; others get default role
        user_count = await self._user_count()
        initial_roles = [self.admin_role] if user_count == 0 else [self.default_role]

        # Create new user
        from jvspatial.core.utils import generate_id

        user_id = generate_id("o", "User")
        user = User(
            id=user_id,
            email=user_data.email,
            password_hash=self._hash_password(user_data.password),
            name="",  # No name required
            is_active=True,
            created_at=datetime.now(timezone.utc),
            roles=initial_roles,
            permissions=[],
        )
        user._graph_context = self.context
        await self.context.save(user)

        final_user_id = user.id
        effective_perms = self._get_effective_permissions_for_user(user)

        return UserResponse(
            id=final_user_id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
            is_active=user.is_active,
            roles=user.roles,
            permissions=effective_perms,
        )

    async def bootstrap_admin(
        self,
        email: str,
        password: str,
        name: str = "",
    ) -> Optional[UserResponse]:
        """Create an admin user if none exists.

        Use at startup to ensure an admin exists. If a user with the given email
        already exists, or any user has the admin role, no user is created.

        Args:
            email: Admin email address
            password: Admin password (min 6 characters)
            name: Optional display name (defaults to email)

        Returns:
            UserResponse if admin was created, None if admin already exists
        """
        if len(password) < 6:
            raise ValueError("Password must be at least 6 characters")

        existing = await self._find_user_by_email(email)
        if existing:
            return None

        user_count = await self._user_count()
        if user_count > 0:
            # Check if any user has admin role
            collection, final_query = await User._build_database_query(
                self.context, {}, {}
            )
            results = await self.context.database.find(collection, final_query)
            for data in results:
                try:
                    user = await self.context._deserialize_entity(User, data)
                    if user and self.admin_role in (user.roles or []):
                        return None
                except Exception:
                    continue

        from jvspatial.core.utils import generate_id

        user_id = generate_id("o", "User")
        user = User(
            id=user_id,
            email=email,
            password_hash=self._hash_password(password),
            name=name or email,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            roles=[self.admin_role],
            permissions=[],
        )
        user._graph_context = self.context
        await self.context.save(user)

        effective_perms = self._get_effective_permissions_for_user(user)
        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
            is_active=user.is_active,
            roles=user.roles,
            permissions=effective_perms,
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

        # Transparent migration: upgrade legacy SHA-256 hash to bcrypt on successful login
        if self._is_legacy_password_hash(user.password_hash):
            try:
                user.password_hash = self._hash_password(login_data.password)
            except Exception as e:
                self._logger.warning(
                    f"Failed to migrate password hash for user {user.id}: {e}"
                )

        # Check if user is active
        if not user.is_active:
            raise ValueError("User account is deactivated")

        # Update last_accessed timestamp and save (includes password migration if applied)
        user._graph_context = self.context
        user.last_accessed = datetime.now(timezone.utc)
        await user.save()

        user_roles = self._get_user_roles(user)
        effective_perms = self._get_effective_permissions_for_user(user)

        # Generate JWT access token with roles and permissions
        access_token, access_expires_at = self._generate_jwt_token(
            user.id, user.email, roles=user_roles, permissions=effective_perms
        )
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
                (refresh_expires_at - datetime.now(timezone.utc)).total_seconds()
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
                roles=user_roles,
                permissions=effective_perms,
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
            self._logger.warning(
                "[validate_token] failed: token decode failed (invalid or expired)"
            )
            return None

        # Get token ID for blacklist check
        token_id = payload.get("jti")
        if not token_id:
            self._logger.warning("[validate_token] failed: token missing JTI")
            return None

        # Check if token is blacklisted (only for valid, non-expired tokens)
        if await self._is_token_blacklisted_by_jti(token_id):
            self._logger.warning(
                "[validate_token] failed: token %s is blacklisted", token_id
            )
            return None

        # Get user information
        user_id = payload.get("user_id")
        if not user_id:
            self._logger.warning("[validate_token] failed: token missing user_id")
            return None

        # Find user by ID using service's context
        user = None
        got_db_error = False
        try:
            user = await self._get_user_by_id(user_id)
        except Exception as e:
            got_db_error = True
            self._logger.warning("[validate_token] _get_user_by_id error: %s", e)

        # Fallback: lookup by email when get-by-id fails (e.g. context/db path mismatch).
        if not user:
            email = payload.get("email")
            if email:
                try:
                    user = await self._find_user_by_email(email)
                    if user and user.id != user_id:
                        user = None
                except Exception:
                    pass

        # Fallback: direct db.find by id (bypasses context.get which may fail)
        if not user:
            try:
                db = self.context.database
                if hasattr(db, "find"):
                    results = await db.find("object", {"id": user_id})
                    if results:
                        user = await self.context._deserialize_entity(User, results[0])
                        if user:
                            user._graph_context = self.context
            except Exception:
                pass

        # Fallback: build UserResponse from payload only when DB raised an error (e.g. path
        # mismatch). When user simply doesn't exist (None), return None for security.
        if not user and user_id and got_db_error:
            return UserResponse(
                id=user_id,
                email=payload.get("email", ""),
                name=payload.get("name", ""),
                created_at=datetime.now(timezone.utc),
                is_active=True,
                roles=payload.get("roles") or [self.default_role],
                permissions=list(payload.get("permissions") or []),
            )

        if not user:
            db_path = getattr(
                getattr(self.context, "database", None), "base_path", None
            )
            self._logger.warning(
                "[validate_token] failed: user %s not found in database (db_path=%s)",
                user_id,
                db_path,
            )
            return None

        # Check if user is still active
        if not user.is_active:
            self._logger.warning(
                "[validate_token] failed: user %s is inactive", user_id
            )
            return None

        # Use roles/permissions from JWT payload if present, else compute from user
        roles = payload.get("roles")
        permissions = payload.get("permissions")
        if roles is None or permissions is None:
            roles = self._get_user_roles(user)
            permissions = self._get_effective_permissions_for_user(user)

        # Update last_accessed timestamp on token validation (user is authenticating).
        # Non-blocking: do not fail auth if save fails (e.g. SQLite lock under concurrent load).
        try:
            user._graph_context = self.context
            user.last_accessed = datetime.now(timezone.utc)
            await self.context.save(user)
        except Exception as e:
            self._logger.debug("last_accessed update skipped: %s", e)

        self._logger.debug(f"Token validation successful for user {user_id}")
        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
            is_active=user.is_active,
            roles=roles or [self.default_role],
            permissions=list(permissions) if permissions else [],
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

        roles = self._get_user_roles(user)
        permissions = self._get_effective_permissions_for_user(user)

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
            is_active=user.is_active,
            roles=roles,
            permissions=permissions,
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

        user_roles = self._get_user_roles(user)
        effective_perms = self._get_effective_permissions_for_user(user)

        # Generate new access token with roles and permissions
        access_token, access_expires_at = self._generate_jwt_token(
            user.id, user.email, roles=user_roles, permissions=effective_perms
        )
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
                (refresh_expires_at - datetime.now(timezone.utc)).total_seconds()
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
                roles=user_roles,
                permissions=effective_perms,
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

            blacklist_id = generate_id("o", "TokenBlacklist")
            # Estimate expiration (access tokens expire in minutes, refresh in days)
            # Use a reasonable default expiration
            estimated_expires_at = datetime.now(timezone.utc) + timedelta(
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

        estimated_expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.jwt_expire_minutes
        )

        for jti in access_token_jtis:
            try:
                blacklist_id = generate_id("o", "TokenBlacklist")
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

    async def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> bool:
        """Change password for an authenticated user.

        Args:
            user_id: User ID
            current_password: Current password for verification
            new_password: New password (min 6 characters)

        Returns:
            True on success

        Raises:
            ValueError: If current password is wrong or user not found
        """
        user = await self._get_user_by_id(user_id)
        if not user:
            raise ValueError("User not found")

        if not self._verify_password(current_password, user.password_hash):
            raise ValueError("Current password is incorrect")

        user.password_hash = self._hash_password(new_password)
        user._graph_context = self.context
        await self.context.save(user)

        await self.revoke_all_user_tokens(user_id)
        return True

    async def request_password_reset(
        self,
        email: str,
        on_reset_requested: Optional[Callable[[str, str, str], Any]] = None,
        reset_base_url: str = "",
    ) -> bool:
        """Request a password reset for a user by email.

        Always returns True to prevent email enumeration. If user exists and is
        active, generates a token, stores it hashed, and invokes the callback.

        Args:
            email: User email address
            on_reset_requested: Optional callback (email, token, reset_url)
            reset_base_url: Base URL for building reset link (e.g. https://app.example.com)

        Returns:
            True always (no email enumeration)
        """
        user = await self._find_user_by_email(email)
        if not user or not user.is_active:
            return True

        token = secrets.token_urlsafe(32)
        token_hash = self._hash_refresh_token(token)
        expires_at = datetime.now(timezone.utc) + timedelta(
            minutes=self.password_reset_token_expiry_minutes
        )

        from jvspatial.core.utils import generate_id

        await self.context.ensure_indexes(PasswordResetToken)
        reset_token_id = generate_id("o", "PasswordResetToken")
        reset_token = PasswordResetToken(
            id=reset_token_id,
            token_hash=token_hash,
            user_id=user.id,
            email=user.email,
            expires_at=expires_at,
            used_at=None,
        )
        reset_token._graph_context = self.context
        await self.context.save(reset_token)

        reset_url = ""
        if reset_base_url:
            base = reset_base_url.rstrip("/")
            reset_url = f"{base}/reset-password?token={token}"

        if on_reset_requested:
            try:
                if asyncio.iscoroutinefunction(on_reset_requested):
                    await on_reset_requested(email, token, reset_url)
                else:
                    on_reset_requested(email, token, reset_url)
            except Exception as e:
                self._logger.exception(
                    "on_password_reset_requested callback failed: %s", e
                )

        return True

    async def reset_password_with_token(self, token: str, new_password: str) -> bool:
        """Reset password using a valid reset token.

        Args:
            token: Plaintext reset token from email
            new_password: New password (min 6 characters)

        Returns:
            True on success

        Raises:
            ValueError: If token is invalid, expired, or already used
        """
        now = datetime.now(timezone.utc)
        await self.context.ensure_indexes(PasswordResetToken)
        collection, final_query = await PasswordResetToken._build_database_query(
            self.context,
            {"context.used_at": None},
            {},
        )
        results = await self.context.database.find(collection, final_query)

        for data in results:
            try:
                entity = await self.context._deserialize_entity(
                    PasswordResetToken, data
                )
                if not entity:
                    continue
                entity._graph_context = self.context

                if entity.expires_at < now:
                    continue

                if not self._verify_refresh_token(token, entity.token_hash):
                    continue

                user = await self._get_user_by_id(entity.user_id)
                if not user:
                    raise ValueError("Invalid or expired token")

                user.password_hash = self._hash_password(new_password)
                await self.context.save(user)

                entity.used_at = now
                await self.context.save(entity)

                await self.revoke_all_user_tokens(entity.user_id)
                return True
            except ValueError:
                raise
            except Exception:
                continue

        raise ValueError("Invalid or expired token")

    async def create_user_with_roles(self, user_data: UserCreateAdmin) -> UserResponse:
        """Create a user with specified roles and permissions (admin-only).

        Args:
            user_data: User creation data with roles and optional permissions

        Returns:
            UserResponse with user information

        Raises:
            ValueError: If user already exists or validation fails
        """
        existing_user = await self._find_user_by_email(user_data.email)
        if existing_user:
            raise ValueError("User with this email already exists")

        from jvspatial.core.utils import generate_id

        user_id = generate_id("o", "User")
        roles = user_data.roles if user_data.roles else [self.default_role]
        permissions = user_data.permissions or []

        user = User(
            id=user_id,
            email=user_data.email,
            password_hash=self._hash_password(user_data.password),
            name=user_data.name or user_data.email,
            is_active=True,
            created_at=datetime.now(timezone.utc),
            roles=roles,
            permissions=permissions,
        )
        user._graph_context = self.context
        await self.context.save(user)

        effective_perms = self._get_effective_permissions_for_user(user)

        return UserResponse(
            id=user.id,
            email=user.email,
            name=user.name,
            created_at=user.created_at,
            is_active=user.is_active,
            roles=user.roles,
            permissions=effective_perms,
        )

    async def update_user_roles(
        self, user_id: str, roles_update: UserRolesUpdate
    ) -> Optional[UserResponse]:
        """Update a user's roles (admin-only).

        Args:
            user_id: User ID
            roles_update: New roles

        Returns:
            UserResponse if user exists, None otherwise
        """
        user = await self._get_user_by_id(user_id)
        if not user:
            return None

        user.roles = roles_update.roles
        user._graph_context = self.context
        await self.context.save(user)

        return await self.get_user_by_id(user_id)

    async def update_user_permissions(
        self, user_id: str, permissions_update: UserPermissionsUpdate
    ) -> Optional[UserResponse]:
        """Update a user's direct permissions (admin-only).

        Args:
            user_id: User ID
            permissions_update: New direct permissions

        Returns:
            UserResponse if user exists, None otherwise
        """
        user = await self._get_user_by_id(user_id)
        if not user:
            return None

        user.permissions = permissions_update.permissions
        user._graph_context = self.context
        await self.context.save(user)

        return await self.get_user_by_id(user_id)

    async def list_users(self) -> List[UserResponse]:
        """List all users with roles and permissions (admin-only).

        Returns:
            List of UserResponse
        """
        await self.context.ensure_indexes(User)
        collection, final_query = await User._build_database_query(self.context, {}, {})
        results = await self.context.database.find(collection, final_query)
        users = []
        for data in results:
            try:
                user = await self.context._deserialize_entity(User, data)
                if user:
                    user._graph_context = self.context
                    roles = self._get_user_roles(user)
                    permissions = self._get_effective_permissions_for_user(user)
                    users.append(
                        UserResponse(
                            id=user.id,
                            email=user.email,
                            name=user.name,
                            created_at=user.created_at,
                            is_active=user.is_active,
                            roles=roles,
                            permissions=permissions,
                        )
                    )
            except Exception:
                continue
        return users
