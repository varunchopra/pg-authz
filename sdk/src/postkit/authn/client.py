"""
postkit.authn - Authentication client for PostgreSQL-native auth.

This module provides:
- AuthnClient: SDK-style interface for authentication operations
- Exception classes: AuthnError, AuthnValidationError
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from postkit.base import BaseClient, PostkitError

__all__ = [
    "AuthnClient",
    "AuthnError",
    "AuthnValidationError",
]


class AuthnError(PostkitError):
    """Base exception for authn operations."""


class AuthnValidationError(AuthnError):
    """Raised when input validation fails."""


class AuthnClient(BaseClient):
    """
    SDK-style client for postkit/authn.

    This wraps the SQL functions with a Pythonic API.

    Example:
        authn = AuthnClient(cursor, namespace="production")

        # Create user
        user_id = authn.create_user("alice@example.com", "argon2_hash")

        # Create session
        session_id = authn.create_session(user_id, "sha256_token_hash")

        # Validate session
        user = authn.validate_session("sha256_token_hash")
        if user:
            print(f"Logged in as {user['email']}")
    """

    _schema = "authn"
    _error_class = AuthnError

    def __init__(self, cursor, namespace: str):
        super().__init__(cursor, namespace)
        # Extra actor fields specific to authn
        self._ip_address: str | None = None
        self._user_agent: str | None = None

    def _has_context(self) -> bool:
        """Check if any context field is set (includes authn-specific fields)."""
        return super()._has_context() or self._ip_address or self._user_agent

    def _apply_actor_context(self) -> None:
        """Apply actor context via authn.set_actor()."""
        self.cursor.execute(
            """SELECT authn.set_actor(
                p_actor_id := %s,
                p_request_id := %s,
                p_ip_address := %s,
                p_user_agent := %s,
                p_on_behalf_of := %s,
                p_reason := %s
            )""",
            (
                self._actor_id,
                self._request_id,
                self._ip_address,
                self._user_agent,
                self._on_behalf_of,
                self._reason,
            ),
        )

    def create_user(
        self,
        email: str,
        password_hash: str | None = None,
    ) -> str:
        """
        Create a new user.

        Args:
            email: User's email address (will be normalized to lowercase)
            password_hash: Pre-hashed password (None for SSO-only users)

        Returns:
            User ID (UUID string)
        """
        result = self._fetch_val(
            "SELECT authn.create_user(%s, %s, %s)",
            (email, password_hash, self.namespace),
            write=True,
        )
        return str(result)

    def get_user(self, user_id: str) -> dict | None:
        """Get user by ID. Does not return password_hash."""
        return self._fetch_one(
            "SELECT * FROM authn.get_user(%s::uuid, %s)",
            (user_id, self.namespace),
        )

    def get_user_by_email(self, email: str) -> dict | None:
        """Get user by email. Does not return password_hash."""
        return self._fetch_one(
            "SELECT * FROM authn.get_user_by_email(%s, %s)",
            (email, self.namespace),
        )

    def update_email(self, user_id: str, new_email: str) -> bool:
        """Update user's email. Clears email_verified_at."""
        return self._fetch_val(
            "SELECT authn.update_email(%s::uuid, %s, %s)",
            (user_id, new_email, self.namespace),
            write=True,
        )

    def disable_user(self, user_id: str) -> bool:
        """Disable user and revoke all their sessions."""
        return self._fetch_val(
            "SELECT authn.disable_user(%s::uuid, %s)",
            (user_id, self.namespace),
            write=True,
        )

    def enable_user(self, user_id: str) -> bool:
        """Re-enable a disabled user."""
        return self._fetch_val(
            "SELECT authn.enable_user(%s::uuid, %s)",
            (user_id, self.namespace),
            write=True,
        )

    def delete_user(self, user_id: str) -> bool:
        """Permanently delete a user and all associated data."""
        return self._fetch_val(
            "SELECT authn.delete_user(%s::uuid, %s)",
            (user_id, self.namespace),
            write=True,
        )

    def list_users(self, limit: int = 100, cursor: str | None = None) -> list[dict]:
        """List users with pagination."""
        return self._fetch_all(
            "SELECT * FROM authn.list_users(%s, %s, %s)",
            (self.namespace, limit, cursor),
        )

    def get_credentials(self, email: str) -> dict | None:
        """
        Get credentials for login verification.

        Returns user_id, password_hash, and disabled_at for caller to verify.
        This is the ONLY method that returns password_hash.
        """
        return self._fetch_one(
            "SELECT * FROM authn.get_credentials(%s, %s)",
            (email, self.namespace),
        )

    def update_password(self, user_id: str, new_password_hash: str) -> bool:
        """Update user's password hash."""
        return self._fetch_val(
            "SELECT authn.update_password(%s::uuid, %s, %s)",
            (user_id, new_password_hash, self.namespace),
            write=True,
        )

    def create_session(
        self,
        user_id: str,
        token_hash: str,
        expires_in: timedelta | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> str:
        """
        Create a new session.

        Args:
            user_id: User ID
            token_hash: Pre-hashed session token (SHA-256)
            expires_in: Session duration (default: 7 days)
            ip_address: Client IP
            user_agent: Client user agent

        Returns:
            Session ID (UUID string)
        """
        result = self._fetch_val(
            "SELECT authn.create_session(%s::uuid, %s, %s, %s::inet, %s, %s)",
            (user_id, token_hash, expires_in, ip_address, user_agent, self.namespace),
            write=True,
        )
        return str(result)

    def validate_session(self, token_hash: str) -> dict | None:
        """
        Validate a session token.

        Returns user info if valid, None otherwise.
        Does not log to audit (hot path).
        """
        return self._fetch_one(
            "SELECT * FROM authn.validate_session(%s, %s)",
            (token_hash, self.namespace),
        )

    def extend_session(
        self,
        token_hash: str,
        extend_by: timedelta | None = None,
    ) -> datetime | None:
        """Extend session expiration.

        Returns:
            New expires_at timestamp, or None if session invalid/expired/revoked.
        """
        return self._fetch_val(
            "SELECT authn.extend_session(%s, %s, %s)",
            (token_hash, extend_by, self.namespace),
            write=True,
        )

    def revoke_session(self, token_hash: str) -> bool:
        """Revoke a session."""
        return self._fetch_val(
            "SELECT authn.revoke_session(%s, %s)",
            (token_hash, self.namespace),
            write=True,
        )

    def revoke_session_by_id(self, session_id: str, user_id: str) -> bool:
        """Revoke a session by ID (for manage devices UI).

        **Parameters:**
        - `session_id`: Session ID to revoke
        - `user_id`: User ID (for ownership verification)

        **Returns:** True if revoked, False if not found or not owned by user
        """
        return self._fetch_val(
            "SELECT authn.revoke_session_by_id(%s::uuid, %s::uuid, %s)",
            (session_id, user_id, self.namespace),
            write=True,
        )

    def revoke_all_sessions(self, user_id: str) -> int:
        """Revoke all sessions for a user. Returns count revoked."""
        return self._fetch_val(
            "SELECT authn.revoke_all_sessions(%s::uuid, %s)",
            (user_id, self.namespace),
            write=True,
        )

    def revoke_other_sessions(self, user_id: str, except_session_id: str) -> int:
        """
        Revoke all sessions except the specified one ("sign out other devices").

        Use this when a user wants to log out of all other devices while staying
        logged in on the current device.

        Args:
            user_id: User whose sessions to revoke
            except_session_id: Session ID to preserve (the current session)

        Returns:
            Count of sessions revoked (excludes the preserved session)
        """
        return self._fetch_val(
            "SELECT authn.revoke_other_sessions(%s::uuid, %s::uuid, %s)",
            (user_id, except_session_id, self.namespace),
            write=True,
        )

    def list_sessions(self, user_id: str) -> list[dict]:
        """List active sessions for a user. Does not return token_hash."""
        return self._fetch_all(
            "SELECT * FROM authn.list_sessions(%s::uuid, %s)",
            (user_id, self.namespace),
        )

    def create_api_key(
        self,
        user_id: str,
        key_hash: str,
        name: str | None = None,
        expires_in: timedelta | None = None,
    ) -> str:
        """
        Create an API key for programmatic access.

        Args:
            user_id: User ID (owner of the key)
            key_hash: Pre-hashed API key (SHA-256)
            name: Optional friendly name ("Production", "CI/CD")
            expires_in: Optional expiration duration (None = never expires)

        Returns:
            API key ID (UUID string)
        """
        result = self._fetch_val(
            "SELECT authn.create_api_key(%s::uuid, %s, %s, %s, %s)",
            (user_id, key_hash, name, expires_in, self.namespace),
            write=True,
        )
        return str(result)

    def validate_api_key(self, key_hash: str) -> dict | None:
        """
        Validate an API key.

        Returns key info if valid, None otherwise.
        Updates last_used_at on successful validation.

        Returns:
            Dict with user_id, key_id, name, expires_at or None if invalid
        """
        return self._fetch_one(
            "SELECT * FROM authn.validate_api_key(%s, %s)",
            (key_hash, self.namespace),
        )

    def revoke_api_key(self, key_id: str) -> bool:
        """Revoke an API key."""
        return self._fetch_val(
            "SELECT authn.revoke_api_key(%s::uuid, %s)",
            (key_id, self.namespace),
            write=True,
        )

    def revoke_all_api_keys(self, user_id: str) -> int:
        """Revoke all API keys for a user. Returns count revoked."""
        return self._fetch_val(
            "SELECT authn.revoke_all_api_keys(%s::uuid, %s)",
            (user_id, self.namespace),
            write=True,
        )

    def list_api_keys(self, user_id: str) -> list[dict]:
        """List active API keys for a user. Does not return key_hash."""
        return self._fetch_all(
            "SELECT * FROM authn.list_api_keys(%s::uuid, %s)",
            (user_id, self.namespace),
        )

    def create_token(
        self,
        user_id: str,
        token_hash: str,
        token_type: str,
        expires_in: timedelta | None = None,
    ) -> str:
        """
        Create a one-time use token.

        Args:
            user_id: User ID
            token_hash: Pre-hashed token (SHA-256)
            token_type: 'password_reset', 'email_verify', or 'magic_link'
            expires_in: Token lifetime (defaults vary by type)

        Returns:
            Token ID (UUID string)
        """
        result = self._fetch_val(
            "SELECT authn.create_token(%s::uuid, %s, %s, %s, %s)",
            (user_id, token_hash, token_type, expires_in, self.namespace),
            write=True,
        )
        return str(result)

    def consume_token(self, token_hash: str, token_type: str) -> dict | None:
        """
        Consume a one-time token.

        Returns user info if valid, None otherwise.
        Token is marked as used after this call.
        """
        return self._fetch_one(
            "SELECT * FROM authn.consume_token(%s, %s, %s)",
            (token_hash, token_type, self.namespace),
            write=True,
        )

    def verify_email(self, token_hash: str) -> dict | None:
        """
        Verify email using a token.

        Convenience method that consumes email_verify token and sets email_verified_at.
        """
        return self._fetch_one(
            "SELECT * FROM authn.verify_email(%s, %s)",
            (token_hash, self.namespace),
            write=True,
        )

    def invalidate_tokens(self, user_id: str, token_type: str) -> int:
        """Invalidate all unused tokens of a type for a user."""
        return self._fetch_val(
            "SELECT authn.invalidate_tokens(%s::uuid, %s, %s)",
            (user_id, token_type, self.namespace),
            write=True,
        )

    def add_mfa(
        self,
        user_id: str,
        mfa_type: str,
        secret: str,
        name: str | None = None,
    ) -> str:
        """
        Add an MFA method for a user.

        Args:
            user_id: User ID
            mfa_type: 'totp', 'webauthn', or 'recovery_codes'
            secret: The MFA secret (caller stores this securely)
            name: Optional friendly name

        Returns:
            MFA ID (UUID string)
        """
        result = self._fetch_val(
            "SELECT authn.add_mfa(%s::uuid, %s, %s, %s, %s)",
            (user_id, mfa_type, secret, name, self.namespace),
            write=True,
        )
        return str(result)

    def get_mfa(self, user_id: str, mfa_type: str) -> list[dict]:
        """Get MFA secrets for verification. Returns secrets!"""
        return self._fetch_all(
            "SELECT * FROM authn.get_mfa(%s::uuid, %s, %s)",
            (user_id, mfa_type, self.namespace),
        )

    def list_mfa(self, user_id: str) -> list[dict]:
        """List MFA methods. Does NOT return secrets."""
        return self._fetch_all(
            "SELECT * FROM authn.list_mfa(%s::uuid, %s)",
            (user_id, self.namespace),
        )

    def remove_mfa(self, mfa_id: str) -> bool:
        """Remove an MFA method."""
        return self._fetch_val(
            "SELECT authn.remove_mfa(%s::uuid, %s)",
            (mfa_id, self.namespace),
            write=True,
        )

    def record_mfa_use(self, mfa_id: str) -> bool:
        """Record that an MFA method was used."""
        return self._fetch_val(
            "SELECT authn.record_mfa_use(%s::uuid, %s)",
            (mfa_id, self.namespace),
            write=True,
        )

    def has_mfa(self, user_id: str) -> bool:
        """Check if user has any MFA method enabled."""
        return self._fetch_val(
            "SELECT authn.has_mfa(%s::uuid, %s)",
            (user_id, self.namespace),
        )

    def record_login_attempt(
        self,
        email: str,
        success: bool,
        ip_address: str | None = None,
    ) -> None:
        """Record a login attempt."""
        self._fetch_val(
            "SELECT authn.record_login_attempt(%s, %s, %s::inet, %s)",
            (email, success, ip_address, self.namespace),
            write=True,
        )

    def is_locked_out(
        self,
        email: str,
        window: timedelta | None = None,
        max_attempts: int | None = None,
    ) -> bool:
        """Check if an email is locked out due to too many failed attempts."""
        return self._fetch_val(
            "SELECT authn.is_locked_out(%s, %s, %s, %s)",
            (email, self.namespace, window, max_attempts),
        )

    def get_recent_attempts(self, email: str, limit: int = 10) -> list[dict]:
        """Get recent login attempts for an email."""
        return self._fetch_all(
            "SELECT * FROM authn.get_recent_attempts(%s, %s, %s)",
            (email, self.namespace, limit),
        )

    def clear_attempts(self, email: str) -> int:
        """Clear login attempts for an email. Returns count deleted."""
        return self._fetch_val(
            "SELECT authn.clear_attempts(%s, %s)",
            (email, self.namespace),
            write=True,
        )

    def cleanup_expired(self) -> dict:
        """Clean up expired sessions, tokens, and old login attempts."""
        return (
            self._fetch_one(
                "SELECT * FROM authn.cleanup_expired(%s)",
                (self.namespace,),
                write=True,
            )
            or {}
        )

    def get_stats(self) -> dict:
        """Get namespace statistics."""
        result = self._fetch_one(
            "SELECT * FROM authn.get_stats(%s)",
            (self.namespace,),
        )
        return result or {}

    def set_actor(
        self,
        actor_id: str | None = None,
        request_id: str | None = None,
        on_behalf_of: str | None = None,
        reason: str | None = None,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        """Set actor context for audit logging. Only updates fields that are passed.

        Args:
            actor_id: The actor making changes (e.g., 'user:alice')
            request_id: Request/correlation ID for tracing
            on_behalf_of: Principal being represented
            reason: Reason for the action
            ip_address: Client IP address
            user_agent: Client user agent string

        Example:
            # In before_request: set HTTP context
            authn.clear_actor()
            authn.set_actor(request_id=req_id, ip_address=ip, user_agent=ua)

            # After authentication: add actor_id (preserves HTTP context)
            authn.set_actor(actor_id="user:alice")
        """
        super().set_actor(actor_id, request_id, on_behalf_of, reason)
        if ip_address is not None:
            self._ip_address = ip_address
        if user_agent is not None:
            self._user_agent = user_agent

    def clear_actor(self) -> None:
        """Clear actor context."""
        super().clear_actor()
        self._ip_address = None
        self._user_agent = None

    def get_audit_events(
        self,
        limit: int = 100,
        event_type: str | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
    ) -> list[dict]:
        """Query audit events.

        Args:
            limit: Maximum number of events to return (default 100)
            event_type: Filter by event type (e.g., 'user_created', 'session_revoked')
            resource_type: Filter by resource type (e.g., 'user', 'session')
            resource_id: Filter by resource ID

        Returns:
            List of audit event dictionaries
        """
        filters: dict[str, Any] = {}
        if resource_type is not None:
            filters["resource_type"] = resource_type
        if resource_id is not None:
            filters["resource_id"] = resource_id

        return self._get_audit_events(
            limit=limit, event_type=event_type, filters=filters
        )
