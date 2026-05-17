"""Enhanced authentication system with additional security features.

This module provides enhanced authentication capabilities including
rate limiting, brute force protection, and session management.
"""

import asyncio
import hashlib
import logging
import time
from typing import Any, Dict, List, Optional, Set

from jvspatial.api.auth.config import AuthConfig


class RateLimiter:
    """Rate limiter for authentication attempts.

    Provides configurable rate limiting to prevent brute force attacks
    and excessive authentication requests.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 300):
        """Initialize the rate limiter.

        Args:
            max_attempts: Maximum attempts allowed in the time window
            window_seconds: Time window in seconds
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, List[float]] = {}
        self._logger = logging.getLogger(__name__)

    def _get_client_key(self, client_ip: str, user_agent: str = "") -> str:
        """Generate a unique key for the client.

        Args:
            client_ip: Client IP address
            user_agent: Client user agent string

        Returns:
            Unique client identifier
        """
        return hashlib.sha256(f"{client_ip}:{user_agent}".encode()).hexdigest()[:16]

    async def is_rate_limited(self, client_ip: str, user_agent: str = "") -> bool:
        """Check if the client is rate limited.

        Args:
            client_ip: Client IP address
            user_agent: Client user agent string

        Returns:
            True if rate limited, False otherwise
        """
        client_key = self._get_client_key(client_ip, user_agent)
        now = time.time()

        # Clean old attempts
        if client_key in self._attempts:
            self._attempts[client_key] = [
                attempt_time
                for attempt_time in self._attempts[client_key]
                if now - attempt_time < self.window_seconds
            ]

        # Check if rate limited
        if (
            client_key in self._attempts
            and len(self._attempts[client_key]) >= self.max_attempts
        ):
            self._logger.warning(f"Rate limit exceeded for client {client_ip}")
            return True

        return False

    async def record_attempt(
        self, client_ip: str, user_agent: str = "", success: bool = True
    ) -> None:
        """Record an authentication attempt.

        Args:
            client_ip: Client IP address
            user_agent: Client user agent string
            success: Whether the attempt was successful
        """
        if success:
            return  # Don't record successful attempts

        client_key = self._get_client_key(client_ip, user_agent)
        now = time.time()

        if client_key not in self._attempts:
            self._attempts[client_key] = []

        self._attempts[client_key].append(now)

    async def get_remaining_attempts(self, client_ip: str, user_agent: str = "") -> int:
        """Get remaining attempts for the client.

        Args:
            client_ip: Client IP address
            user_agent: Client user agent string

        Returns:
            Number of remaining attempts
        """
        client_key = self._get_client_key(client_ip, user_agent)

        if client_key not in self._attempts:
            return self.max_attempts

        now = time.time()
        recent_attempts = [
            attempt_time
            for attempt_time in self._attempts[client_key]
            if now - attempt_time < self.window_seconds
        ]

        return max(0, self.max_attempts - len(recent_attempts))


class BruteForceProtection:
    """Brute force protection system.

    Provides advanced protection against brute force attacks with
    progressive delays and account lockout mechanisms.
    """

    def __init__(self, max_failed_attempts: int = 10, lockout_duration: int = 3600):
        """Initialize brute force protection.

        Args:
            max_failed_attempts: Maximum failed attempts before lockout
            lockout_duration: Lockout duration in seconds
        """
        self.max_failed_attempts = max_failed_attempts
        self.lockout_duration = lockout_duration
        self._failed_attempts: Dict[str, List[float]] = {}
        self._locked_accounts: Dict[str, float] = {}
        self._logger = logging.getLogger(__name__)

    async def is_account_locked(self, username: str) -> bool:
        """Check if an account is locked due to brute force attempts.

        Args:
            username: Username to check

        Returns:
            True if account is locked, False otherwise
        """
        if username not in self._locked_accounts:
            return False

        lockout_time = self._locked_accounts[username]
        if time.time() - lockout_time > self.lockout_duration:
            # Lockout expired
            del self._locked_accounts[username]
            if username in self._failed_attempts:
                del self._failed_attempts[username]
            return False

        return True

    async def record_failed_attempt(self, username: str) -> None:
        """Record a failed authentication attempt.

        Args:
            username: Username that failed authentication
        """
        now = time.time()

        if username not in self._failed_attempts:
            self._failed_attempts[username] = []

        self._failed_attempts[username].append(now)

        # Check if account should be locked
        recent_failures = [
            attempt_time
            for attempt_time in self._failed_attempts[username]
            if now - attempt_time < self.lockout_duration
        ]

        if len(recent_failures) >= self.max_failed_attempts:
            self._locked_accounts[username] = now
            self._logger.warning(
                f"Account {username} locked due to brute force attempts"
            )

    async def record_successful_attempt(self, username: str) -> None:
        """Record a successful authentication attempt.

        Args:
            username: Username that succeeded authentication
        """
        # Clear failed attempts on successful login
        if username in self._failed_attempts:
            del self._failed_attempts[username]

        if username in self._locked_accounts:
            del self._locked_accounts[username]

    async def get_lockout_remaining(self, username: str) -> int:
        """Get remaining lockout time for an account.

        Args:
            username: Username to check

        Returns:
            Remaining lockout time in seconds, 0 if not locked
        """
        if username not in self._locked_accounts:
            return 0

        lockout_time = self._locked_accounts[username]
        remaining = self.lockout_duration - (time.time() - lockout_time)
        return max(0, int(remaining))


class SessionManager:
    """Enhanced session management system.

    Provides secure session management with configurable timeouts,
    session invalidation, and security features.

    **CSRF note:** Sessions managed here are server-side only (session IDs are
    generated but not automatically attached as cookies). If cookie-based session
    delivery is added in the future, CSRF protection (double-submit cookie or
    Synchronizer Token Pattern) MUST be implemented to prevent cross-site request
    forgery. JWT in the Authorization header is naturally CSRF-resistant because
    browsers do not auto-attach it.
    """

    def __init__(self, session_timeout: int = 3600, max_sessions_per_user: int = 5):
        """Initialize session manager.

        Args:
            session_timeout: Session timeout in seconds
            max_sessions_per_user: Maximum sessions per user
        """
        self.session_timeout = session_timeout
        self.max_sessions_per_user = max_sessions_per_user
        self._sessions: Dict[str, Dict[str, Any]] = {}
        self._user_sessions: Dict[str, Set[str]] = {}
        self._logger = logging.getLogger(__name__)
        # Single lock guards both ``_sessions`` and ``_user_sessions`` so
        # concurrent create/invalidate/cleanup cannot raise
        # ``RuntimeError: dictionary changed size during iteration`` and
        # ``max_sessions_per_user`` enforcement is not racy (audit §4.8).
        self._lock = asyncio.Lock()

    async def create_session(self, user_id: str, user_data: Dict[str, Any]) -> str:
        """Create a new session for a user.

        Args:
            user_id: User identifier
            user_data: User data to store in session

        Returns:
            Session ID
        """
        import uuid

        session_id = str(uuid.uuid4())
        now = time.time()

        async with self._lock:
            # Inline expired-session sweep under the lock so the cap
            # check below sees a coherent set.
            self._sweep_user_sessions_locked(user_id, now)

            # Enforce per-user cap.
            existing = self._user_sessions.get(user_id, set())
            while len(existing) >= self.max_sessions_per_user:
                # Drop the oldest by last_accessed.
                oldest = min(
                    (s for s in existing if s in self._sessions),
                    key=lambda s: self._sessions[s].get("last_accessed", 0),
                    default=None,
                )
                if oldest is None:
                    break
                self._invalidate_session_locked(oldest)
                existing = self._user_sessions.get(user_id, set())

            self._sessions[session_id] = {
                "user_id": user_id,
                "created_at": now,
                "last_accessed": now,
                "user_data": user_data,
                "is_active": True,
            }
            self._user_sessions.setdefault(user_id, set()).add(session_id)

        self._logger.info(f"Created session {session_id} for user {user_id}")
        return session_id

    async def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Validate a session and return user data.

        Args:
            session_id: Session ID to validate

        Returns:
            User data if session is valid, None otherwise
        """
        async with self._lock:
            if session_id not in self._sessions:
                return None

            session = self._sessions[session_id]
            now = time.time()

            # Check if session is expired
            if now - session["last_accessed"] > self.session_timeout:
                self._invalidate_session_locked(session_id)
                return None

            # Update last accessed time
            session["last_accessed"] = now

            return session["user_data"]

    async def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a session.

        Args:
            session_id: Session ID to invalidate

        Returns:
            True if session was invalidated, False otherwise
        """
        async with self._lock:
            return self._invalidate_session_locked(session_id)

    def _invalidate_session_locked(self, session_id: str) -> bool:
        """Remove ``session_id`` from internal maps. Caller holds ``_lock``."""
        if session_id not in self._sessions:
            return False

        session = self._sessions[session_id]
        user_id = session["user_id"]

        # Remove from sessions
        del self._sessions[session_id]

        # Remove from user sessions
        if user_id in self._user_sessions:
            self._user_sessions[user_id].discard(session_id)
            if not self._user_sessions[user_id]:
                del self._user_sessions[user_id]

        self._logger.info(f"Invalidated session {session_id} for user {user_id}")
        return True

    async def invalidate_user_sessions(self, user_id: str) -> int:
        """Invalidate all sessions for a user.

        Args:
            user_id: User ID to invalidate sessions for

        Returns:
            Number of sessions invalidated
        """
        async with self._lock:
            session_ids = list(self._user_sessions.get(user_id, set()))
            count = 0
            for session_id in session_ids:
                if self._invalidate_session_locked(session_id):
                    count += 1
            return count

    def _sweep_user_sessions_locked(self, user_id: str, now: float) -> None:
        """Drop expired sessions for ``user_id``. Caller holds ``_lock``."""
        if user_id not in self._user_sessions:
            return

        # Iterate a snapshot — _invalidate_session_locked mutates the set.
        for session_id in list(self._user_sessions[user_id]):
            session = self._sessions.get(session_id)
            if session is None:
                continue
            if now - session["last_accessed"] > self.session_timeout:
                self._invalidate_session_locked(session_id)

    async def _cleanup_user_sessions(self, user_id: str) -> None:
        """Clean up old sessions for a user (acquires the lock)."""
        async with self._lock:
            self._sweep_user_sessions_locked(user_id, time.time())

    async def cleanup_expired_sessions(self) -> int:
        """Clean up all expired sessions.

        Returns:
            Number of sessions cleaned up
        """
        async with self._lock:
            now = time.time()
            # Snapshot keys so the locked invalidate helper can mutate.
            expired = [
                sid
                for sid, s in self._sessions.items()
                if now - s["last_accessed"] > self.session_timeout
            ]
            for sid in expired:
                self._invalidate_session_locked(sid)
            return len(expired)


class AuthenticationEnhancer:
    """Enhanced authentication system with additional security features.

    Combines rate limiting, brute force protection, and session management
    to provide comprehensive authentication security.
    """

    def __init__(self, auth_config: AuthConfig):
        """Initialize the authentication enhancer.

        Args:
            auth_config: Authentication configuration
        """
        self.auth_config = auth_config
        self.rate_limiter = RateLimiter()
        self.brute_force_protection = BruteForceProtection()
        self.session_manager = SessionManager()
        self._logger = logging.getLogger(__name__)

    async def authenticate_with_enhanced_protection(
        self, credentials: Dict[str, str], client_ip: str, user_agent: str = ""
    ) -> Optional[Dict[str, Any]]:
        """Authenticate with enhanced security protection.

        Args:
            credentials: Authentication credentials
            client_ip: Client IP address
            user_agent: Client user agent string

        Returns:
            User data if authentication successful, None otherwise
        """
        username = credentials.get("username", "")

        # Check rate limiting
        if await self.rate_limiter.is_rate_limited(client_ip, user_agent):
            self._logger.warning(f"Rate limit exceeded for IP {client_ip}")
            return None

        # Check account lockout
        if await self.brute_force_protection.is_account_locked(username):
            self._logger.warning(
                f"Account {username} is locked due to brute force attempts"
            )
            return None

        # Perform authentication (this would integrate with existing auth system)
        user_data = await self._perform_authentication(credentials)

        if user_data:
            # Record successful attempt
            await self.brute_force_protection.record_successful_attempt(username)

            # Create session
            session_id = await self.session_manager.create_session(
                user_data.get("id", username), user_data
            )
            user_data["session_id"] = session_id

            self._logger.info(f"Successful authentication for user {username}")
            return user_data
        else:
            # Record failed attempt
            await self.rate_limiter.record_attempt(client_ip, user_agent, success=False)
            await self.brute_force_protection.record_failed_attempt(username)

            self._logger.warning(f"Failed authentication attempt for user {username}")
            return None

    async def _perform_authentication(
        self, credentials: Dict[str, str]
    ) -> Optional[Dict[str, Any]]:
        """Perform the actual authentication.

        This method would integrate with the existing authentication system.

        Args:
            credentials: Authentication credentials

        Returns:
            User data if authentication successful, None otherwise
        """
        # This would integrate with existing JWT/API key authentication
        # For now, return None to indicate authentication failure
        return None

    async def validate_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Validate a session.

        Args:
            session_id: Session ID to validate

        Returns:
            User data if session is valid, None otherwise
        """
        return await self.session_manager.validate_session(session_id)

    async def invalidate_session(self, session_id: str) -> bool:
        """Invalidate a session.

        Args:
            session_id: Session ID to invalidate

        Returns:
            True if session was invalidated, False otherwise
        """
        return await self.session_manager.invalidate_session(session_id)


__all__ = [
    "RateLimiter",
    "BruteForceProtection",
    "SessionManager",
    "AuthenticationEnhancer",
]
