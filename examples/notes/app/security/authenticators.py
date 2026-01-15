"""
Authentication strategies.

Supports:
- Bearer token (Authorization: Bearer <token>)
- API key (Api-Key: <key>)
- Session cookie (Flask session)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

from flask import request, session

from .context import AuthMethod, ImpersonationContext
from .crypto import hash_token


@dataclass
class AuthResult:
    """Result of successful authentication."""

    user_id: str
    auth_method: AuthMethod
    impersonation: Optional[ImpersonationContext] = None


class Authenticator(ABC):
    """Base class for authentication strategies."""

    @abstractmethod
    def authenticate(self, authn_client) -> Optional[AuthResult]:
        """
        Attempt to authenticate the current request.

        Args:
            authn_client: The authn SDK client

        Returns:
            AuthResult if successful, None if this method doesn't apply
        """
        pass

    @property
    @abstractmethod
    def priority(self) -> int:
        """Lower number = higher priority (tried first)."""
        pass


class BearerTokenAuthenticator(Authenticator):
    """Authenticate via Authorization: Bearer <token> header."""

    priority = 10

    def authenticate(self, authn_client) -> Optional[AuthResult]:
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None

        token_hash = hash_token(auth_header[7:])
        sess = authn_client.validate_session(token_hash)
        if not sess:
            return None

        impersonation = None
        if sess.get("is_impersonating"):
            impersonation = ImpersonationContext(
                impersonator_id=sess["impersonator_id"],
                impersonator_email=sess["impersonator_email"],
                reason=sess.get("impersonation_reason", ""),
            )

        return AuthResult(
            user_id=sess["user_id"],
            auth_method=AuthMethod("bearer", sess["session_id"]),
            impersonation=impersonation,
        )


class ApiKeyAuthenticator(Authenticator):
    """Authenticate via Api-Key header."""

    priority = 20

    def authenticate(self, authn_client) -> Optional[AuthResult]:
        api_key = request.headers.get("Api-Key")
        if not api_key:
            return None

        key_info = authn_client.validate_api_key(hash_token(api_key))
        if not key_info:
            return None

        return AuthResult(
            user_id=key_info["user_id"],
            auth_method=AuthMethod("api_key", key_info["key_id"]),
        )


class SessionCookieAuthenticator(Authenticator):
    """Authenticate via Flask session cookie."""

    priority = 30

    def authenticate(self, authn_client) -> Optional[AuthResult]:
        token_hash = session.get("token_hash")
        if not token_hash:
            return None

        db_session = authn_client.validate_session(token_hash)
        if not db_session:
            # Invalid session - clear it
            session.clear()
            return None

        impersonation = None
        if db_session.get("is_impersonating"):
            impersonation = ImpersonationContext(
                impersonator_id=db_session["impersonator_id"],
                impersonator_email=db_session["impersonator_email"],
                reason=db_session.get("impersonation_reason", ""),
            )

        return AuthResult(
            user_id=db_session["user_id"],
            auth_method=AuthMethod("session", db_session["session_id"]),
            impersonation=impersonation,
        )


class AuthenticationChain:
    """Try authenticators in priority order until one succeeds."""

    def __init__(self):
        self._authenticators = sorted(
            [
                BearerTokenAuthenticator(),
                ApiKeyAuthenticator(),
                SessionCookieAuthenticator(),
            ],
            key=lambda a: a.priority,
        )

    def authenticate(self, authn_client) -> Optional[AuthResult]:
        """
        Try each authenticator in priority order.

        Returns:
            AuthResult from first successful authenticator, or None
        """
        for authenticator in self._authenticators:
            result = authenticator.authenticate(authn_client)
            if result:
                return result
        return None


# Singleton chain instance
_auth_chain = AuthenticationChain()


def authenticate_request(authn_client) -> Optional[AuthResult]:
    """
    Authenticate the current request.

    Tries authenticators in order: Bearer > API Key > Session

    Args:
        authn_client: The authn SDK client

    Returns:
        AuthResult if authenticated, None otherwise
    """
    return _auth_chain.authenticate(authn_client)
