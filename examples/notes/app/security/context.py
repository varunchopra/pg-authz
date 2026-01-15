"""
Request context - single source of truth for authentication state.

Usage:
    from app.security import get_context, RequestContext

    def my_route(ctx: RequestContext):
        print(ctx.user_id)      # User whose permissions apply
        print(ctx.org_id)       # Current org context
        print(ctx.actor_id)     # Who's actually doing it (for audit)
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from flask import g, has_request_context


@dataclass(frozen=True)
class AuthMethod:
    """How the user authenticated."""

    type: str  # "session", "bearer", "api_key"
    credential_id: str  # session_id or api_key_id


@dataclass(frozen=True)
class ImpersonationContext:
    """Present when admin is impersonating a user in the same org."""

    impersonator_id: str
    impersonator_email: str
    reason: str


@dataclass(frozen=True)
class OperatorAccessContext:
    """Present when platform operator is acting as a customer user."""

    operator_id: str
    operator_email: str
    target_user_id: str
    target_user_email: str
    reason: str
    ticket_id: Optional[str] = None
    expires_at: Optional[datetime] = None


@dataclass(frozen=True)
class RequestContext:
    """
    Immutable request context. Single source of truth.

    Created once during request lifecycle, never mutated.
    Access via get_context() or as first argument to @authenticated routes.
    """

    # The user whose permissions apply (target user in impersonation/operator cases)
    user_id: str
    auth_method: AuthMethod

    # Organization context (set when org=True in decorator)
    org_id: Optional[str] = None

    # Impersonation (admin -> user in same org)
    impersonation: Optional[ImpersonationContext] = None

    # Operator access (platform user -> user in any org)
    operator_access: Optional[OperatorAccessContext] = None

    # Request metadata
    request_id: str = ""
    ip_address: str = ""
    user_agent: str = ""

    @property
    def is_impersonating(self) -> bool:
        """True if admin is impersonating another user."""
        return self.impersonation is not None

    @property
    def is_operator(self) -> bool:
        """True if platform operator is accessing customer account."""
        return self.operator_access is not None

    @property
    def session_id(self) -> Optional[str]:
        """Session ID if authenticated via session/bearer token."""
        if self.auth_method.type in ("session", "bearer"):
            return self.auth_method.credential_id
        return None

    @property
    def api_key_id(self) -> Optional[str]:
        """API key ID if authenticated via API key."""
        if self.auth_method.type == "api_key":
            return self.auth_method.credential_id
        return None

    @property
    def actor_id(self) -> str:
        """Who is actually performing the action (for audit)."""
        if self.operator_access:
            return f"operator:{self.operator_access.operator_id}"
        if self.impersonation:
            return f"user:{self.impersonation.impersonator_id}"
        if self.api_key_id:
            return f"api_key:{self.api_key_id}"
        return f"user:{self.user_id}"

    @property
    def on_behalf_of(self) -> Optional[str]:
        """Who is being acted on behalf of (for audit)."""
        if self.operator_access or self.impersonation:
            return f"user:{self.user_id}"
        if self.api_key_id:
            return f"user:{self.user_id}"
        return None


# Type aliases for route signatures
UserContext = RequestContext  # user_id guaranteed
OrgContext = RequestContext  # user_id + org_id guaranteed


def get_context() -> Optional[RequestContext]:
    """Get current request context. Returns None if not authenticated."""
    if not has_request_context():
        return None
    return getattr(g, "_security_context", None)


def set_context(ctx: RequestContext) -> None:
    """
    Set context for current request. Internal use only.

    Raises RuntimeError if context already set (prevents mutation).
    """
    if hasattr(g, "_security_context") and g._security_context is not None:
        raise RuntimeError("Security context already set for this request")
    g._security_context = ctx


def clear_context() -> None:
    """Clear context. Called in request teardown."""
    if has_request_context() and hasattr(g, "_security_context"):
        g._security_context = None
