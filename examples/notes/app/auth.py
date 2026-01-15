"""
Authentication and authorization helpers.

This module provides:
- Session management (login_user, logout_user, create_session_with_refresh)
- Org helpers (get_user_orgs, get_org, etc.)
- Permission helpers (check_permission, is_org_admin, is_org_owner)
- API key scope management

For authentication and crypto, import from app.security.
"""

from datetime import timedelta

from flask import g, session
from psycopg.rows import dict_row

from .config import Config
from .db import get_authn, get_authz, get_current_org_id, get_db
from .security import REFRESH_TOKEN_PREFIX, create_token

# =============================================================================
# SESSION MANAGEMENT
# =============================================================================


def create_session_with_refresh(
    user_id: str,
    ip_address: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """Create a session with associated refresh token.

    Args:
        user_id: The authenticated user's ID
        ip_address: Client IP address
        user_agent: Client user agent string

    Returns:
        Dict with access_token, refresh_token, session_id, and expiry info
    """
    authn = get_authn()

    # Generate both tokens
    access_token, access_hash = create_token()
    refresh_token, refresh_hash = create_token(prefix=REFRESH_TOKEN_PREFIX)

    # Create session with configurable expiry
    session_id = authn.create_session(
        user_id=user_id,
        token_hash=access_hash,
        expires_in=timedelta(hours=Config.ACCESS_TOKEN_EXPIRES_HOURS),
        ip_address=ip_address,
        user_agent=user_agent[:1024] if user_agent else None,
    )

    # Create associated refresh token
    authn.create_refresh_token(
        session_id=session_id,
        token_hash=refresh_hash,
        expires_in=timedelta(days=Config.REFRESH_TOKEN_EXPIRES_DAYS),
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "session_id": session_id,
        "expires_in": Config.ACCESS_TOKEN_EXPIRES_HOURS * 3600,
        "refresh_expires_in": Config.REFRESH_TOKEN_EXPIRES_DAYS * 86400,
    }


def login_user(user_id: str) -> None:
    """Set user_id in Flask session (for browser-based auth)."""
    session["user_id"] = user_id


def logout_user() -> None:
    """Clear authentication data from Flask session."""
    session.pop("user_id", None)
    session.pop("token_hash", None)
    session.pop("current_org_id", None)


def get_session_user() -> str | None:
    """Get user_id from Flask session if the database session is still valid."""
    token_hash = session.get("token_hash")
    if not token_hash:
        return None

    # Validate session against database
    db_session = get_authn().validate_session(token_hash)
    if not db_session:
        # Session revoked - clear Flask session
        session.clear()
        return None

    # Cache session_id for current session marking
    g.current_session_id = db_session.get("session_id")

    # Cache impersonation context for templates
    g.is_impersonating = db_session.get("is_impersonating", False)
    g.impersonator_id = db_session.get("impersonator_id")
    g.impersonator_email = db_session.get("impersonator_email")
    g.impersonation_reason = db_session.get("impersonation_reason")

    return db_session["user_id"]


def get_current_session_id() -> str | None:
    """Get the current session_id (call after get_session_user)."""
    return g.get("current_session_id")


def get_current_api_key_id() -> str | None:
    """Get the current api_key_id if request was authenticated via API key."""
    return getattr(g, "current_api_key_id", None)


# =============================================================================
# ORGANIZATION HELPERS
# =============================================================================


def get_user_orgs(user_id: str) -> list[dict]:
    """Get all organizations a user belongs to."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT o.org_id, o.name, o.slug, m.role, o.created_at
            FROM orgs o
            JOIN org_memberships m ON o.org_id = m.org_id
            WHERE m.user_id = %s
            ORDER BY o.name
            """,
            (user_id,),
        )
        return cur.fetchall()


def is_org_member(user_id: str, org_id: str) -> bool:
    """Check if user is a member of the organization."""
    with get_db().cursor() as cur:
        cur.execute(
            """
            SELECT 1 FROM org_memberships
            WHERE user_id = %s AND org_id = %s
            """,
            (user_id, org_id),
        )
        return cur.fetchone() is not None


def get_org_membership(user_id: str, org_id: str) -> dict | None:
    """Get user's membership in an organization."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT m.*, o.name as org_name, o.slug as org_slug
            FROM org_memberships m
            JOIN orgs o ON m.org_id = o.org_id
            WHERE m.user_id = %s AND m.org_id = %s
            """,
            (user_id, org_id),
        )
        return cur.fetchone()


def get_org(org_id: str) -> dict | None:
    """Get organization by ID."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM orgs WHERE org_id = %s",
            (org_id,),
        )
        return cur.fetchone()


def get_org_by_slug(slug: str) -> dict | None:
    """Get organization by slug."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            "SELECT * FROM orgs WHERE slug = %s",
            (slug,),
        )
        return cur.fetchone()


# =============================================================================
# PERMISSION HELPERS
# =============================================================================


def check_permission(permission: str, resource: tuple[str, str]) -> bool:
    """Check if current request has permission to perform action on resource.

    Uses g.current_user_id and g.current_org_id set by the @authenticated decorator.
    """
    user_id = g.get("current_user_id")
    org_id = g.get("current_org_id") or g.get("org_id") or get_current_org_id()

    if not user_id or not org_id:
        return False

    authz = get_authz(org_id)

    # User must have permission
    if not authz.check(("user", user_id), permission, resource):
        return False

    # If API key auth, key must also have scope
    api_key_id = get_current_api_key_id()
    if api_key_id:
        resource_type, resource_id = resource

        has_specific = authz.check(("api_key", api_key_id), permission, resource)
        has_wildcard = authz.check(
            ("api_key", api_key_id), permission, (resource_type, "*")
        )

        if not (has_specific or has_wildcard):
            return False

    return True


def is_org_admin(user_id: str | None = None, org_id: str | None = None) -> bool:
    """Check if user has admin permission on the organization."""
    user_id = user_id or g.get("current_user_id")
    org_id = (
        org_id or g.get("current_org_id") or g.get("org_id") or get_current_org_id()
    )

    if not user_id or not org_id:
        return False

    return get_authz(org_id).check(("user", user_id), "admin", ("org", org_id))


def is_org_owner(user_id: str | None = None, org_id: str | None = None) -> bool:
    """Check if user is the owner of the organization."""
    user_id = user_id or g.get("current_user_id")
    org_id = (
        org_id or g.get("current_org_id") or g.get("org_id") or get_current_org_id()
    )

    if not user_id or not org_id:
        return False

    return get_authz(org_id).check(("user", user_id), "owner", ("org", org_id))


# =============================================================================
# API KEY SCOPE MANAGEMENT
# =============================================================================

API_KEY_LEVEL_PERMISSIONS = {
    "read": ["view"],
    "write": ["view", "edit"],
    "admin": ["view", "edit", "delete", "share"],
}


def grant_api_key_scopes(
    key_id: str,
    org_id: str,
    notes_access: str,
    notes_level: str = "read",
    selected_note_ids: list[str] | None = None,
) -> None:
    """Grant authz permissions for API key scopes within an org."""
    if notes_access == "none":
        return

    authz = get_authz(org_id)
    permissions = API_KEY_LEVEL_PERMISSIONS.get(notes_level, [])

    if notes_access == "all":
        for perm in permissions:
            authz.grant(perm, resource=("note", "*"), subject=("api_key", key_id))
    elif notes_access == "selected" and selected_note_ids:
        for note_id in selected_note_ids:
            for perm in permissions:
                authz.grant(
                    perm, resource=("note", note_id), subject=("api_key", key_id)
                )


def revoke_all_api_key_grants(key_id: str, org_id: str) -> int:
    """Revoke ALL authz grants for an API key within an org."""
    authz = get_authz(org_id)
    return authz.revoke_all_grants(("api_key", key_id))


def get_api_key_scopes(key_id: str, org_id: str) -> dict:
    """Get machine-readable scope summary for an API key in an org."""
    authz = get_authz(org_id)

    if authz.check(("api_key", key_id), "delete", ("note", "*")):
        return {"notes": "admin"}
    if authz.check(("api_key", key_id), "edit", ("note", "*")):
        return {"notes": "write"}
    if authz.check(("api_key", key_id), "view", ("note", "*")):
        return {"notes": "read"}

    grants = authz.list_grants(("api_key", key_id), resource_type="note")
    relations = {g["relation"] for g in grants}

    if "delete" in relations or "share" in relations:
        return {"notes": "selected:admin"}
    if "edit" in relations:
        return {"notes": "selected:write"}
    if "view" in relations:
        return {"notes": "selected:read"}

    return {"notes": "none"}


def get_api_key_scope_display(key_id: str, org_id: str) -> dict:
    """Get display-friendly scope summary for UI."""
    scopes = get_api_key_scopes(key_id, org_id)

    display_map = {
        "admin": "Admin (full control)",
        "write": "Read and write",
        "read": "Read-only",
        "selected:admin": "Selected notes (admin)",
        "selected:write": "Selected notes (read/write)",
        "selected:read": "Selected notes (read-only)",
        "none": "No access",
    }

    return {"notes": display_map.get(scopes.get("notes", "none"), "No access")}
