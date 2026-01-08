import hashlib
import secrets
from dataclasses import dataclass
from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import g, jsonify, redirect, request, session, url_for
from psycopg.rows import dict_row

from .db import get_authn, get_authz, get_current_org_id, get_db

# =============================================================================
# AUTH CONTEXT TYPES
# =============================================================================


@dataclass(frozen=True)
class UserContext:
    """Auth context for user-scoped operations (no org required)."""

    user_id: str
    session_id: str | None = None
    api_key_id: str | None = None


@dataclass(frozen=True)
class OrgContext(UserContext):
    """Auth context for org-scoped operations."""

    org_id: str = ""  # Required but has default for dataclass inheritance


ph = PasswordHasher()

# Pre-computed hash for timing-attack prevention on login
# Used when user doesn't exist to ensure constant-time response
DUMMY_HASH = ph.hash("dummy-password-for-timing-attack-prevention")


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        ph.verify(stored_hash, password)
        return True
    except VerifyMismatchError:
        return False


def create_token(prefix: str = "") -> tuple[str, str]:
    """Returns (raw_token, hashed_token).

    Args:
        prefix: Optional prefix to prepend to the raw token (e.g., "pk_")
    """
    raw = prefix + secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


# API key prefix - makes keys identifiable (like GitHub's gh_, Stripe's sk_)
API_KEY_PREFIX = "pk_"


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _set_user_context(
    user_id: str,
    session_id: str | None = None,
    api_key_id: str | None = None,
    org_id: str | None = None,
) -> str:
    """Cache user_id and set actor context for audit trails.

    Request context (IP, user_agent, request_id) is already set by before_request.
    This adds the actor_id after authentication.

    Args:
        user_id: The authenticated user's ID
        session_id: Database session ID (for session-based auth)
        api_key_id: API key ID (for API key auth)
        org_id: Organization ID (for org-scoped operations)
    """
    g.current_user_id = user_id
    if session_id:
        g.current_session_id = session_id
    if api_key_id:
        g.current_api_key_id = api_key_id
    if org_id:
        g.current_org_id = org_id

    # Determine actor
    if api_key_id:
        actor_id = f"api_key:{api_key_id}"
        on_behalf_of = f"user:{user_id}"
    else:
        actor_id = f"user:{user_id}"
        on_behalf_of = None

    # Set actor on authn (always global)
    authn = get_authn()
    if on_behalf_of:
        authn.set_actor(actor_id=actor_id, on_behalf_of=on_behalf_of)
    else:
        authn.set_actor(actor_id=actor_id)

    # Set actor on authz only if org context is available
    if org_id:
        authz = get_authz(org_id)
        if on_behalf_of:
            authz.set_actor(actor_id=actor_id, on_behalf_of=on_behalf_of)
        else:
            authz.set_actor(actor_id=actor_id)

    return user_id


def get_current_user() -> str | None:
    """Get authenticated user from request headers (API auth)."""
    if hasattr(g, "current_user_id"):
        return g.current_user_id

    authn = get_authn()

    # Bearer token (session auth) takes precedence
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        sess = authn.validate_session(hash_token(auth_header[7:]))
        if sess:
            return _set_user_context(sess["user_id"], sess.get("session_id"))

    # Api-Key header for API key auth
    api_key = request.headers.get("Api-Key")
    if api_key:
        key_info = authn.validate_api_key(hash_token(api_key))
        if key_info:
            # Get org from header if provided (for API key requests)
            org_id = request.headers.get("X-Org-Id") or get_current_org_id()
            return _set_user_context(
                key_info["user_id"], api_key_id=key_info["key_id"], org_id=org_id
            )

    g.current_user_id = None
    return None


# --- Session-based auth for browser views ---


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
# AUTH DECORATOR
# =============================================================================


def _is_api_request() -> bool:
    """Check if request expects JSON response."""
    accept = request.accept_mimetypes
    return accept.best == "application/json" or request.is_json


def _auth_failure_response():
    """Return 401 JSON or redirect based on request type."""
    if _is_api_request():
        return jsonify({"error": "unauthorized"}), 401
    return redirect(url_for("views.auth.login"))


def _org_required_response():
    """Return 400 JSON or redirect to org selection."""
    if _is_api_request():
        return jsonify({"error": "org_id required"}), 400
    return redirect(url_for("views.orgs.select"))


def _forbidden_response(message: str = "forbidden"):
    """Return 403 JSON or text based on request type."""
    if _is_api_request():
        return jsonify({"error": message}), 403
    return message, 403


def authenticated(f=None, *, org: bool = False, admin: bool = False):
    """
    Universal auth decorator with type-safe context.

    Usage:
        @authenticated              # User auth only → UserContext
        @authenticated(org=True)    # User + org auth → OrgContext
        @authenticated(org=True, admin=True)  # Requires org admin

    Auto-detects API vs browser requests:
        - API (Accept: application/json) → returns JSON errors
        - Browser → redirects to login/org-select

    Args:
        org: Require organization context
        admin: Require org admin permission (implies org=True)
    """
    # admin implies org
    require_org = org or admin

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try API auth first, then session auth
            user_id, session_id, api_key_id = _authenticate_request()

            if not user_id:
                return _auth_failure_response()

            if require_org:
                # Get org from various sources
                org_id = _get_org_from_request(kwargs)

                if not org_id:
                    return _org_required_response()

                if not is_org_member(user_id, org_id):
                    session.pop("current_org_id", None)
                    return _forbidden_response("not a member of this organization")

                # Check admin if required
                if admin and not is_org_admin(user_id, org_id):
                    return _forbidden_response("admin required")

                # Set user context and actor for audit trails (single source of truth)
                _set_user_context(user_id, session_id, api_key_id, org_id)

                ctx = OrgContext(
                    user_id=user_id,
                    session_id=session_id,
                    api_key_id=api_key_id,
                    org_id=org_id,
                )
            else:
                # Set user context without org
                _set_user_context(user_id, session_id, api_key_id)

                ctx = UserContext(
                    user_id=user_id,
                    session_id=session_id,
                    api_key_id=api_key_id,
                )

            return func(ctx, *args, **kwargs)

        return wrapper

    # Support both @authenticated and @authenticated(org=True)
    if f is not None:
        return decorator(f)
    return decorator


def _authenticate_request() -> tuple[str | None, str | None, str | None]:
    """
    Authenticate the request via API headers or session.

    Returns:
        (user_id, session_id, api_key_id) - user_id is None if not authenticated
    """
    authn = get_authn()

    # API auth: Bearer token
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        sess = authn.validate_session(hash_token(auth_header[7:]))
        if sess:
            return sess["user_id"], sess.get("session_id"), None

    # API auth: Api-Key header
    api_key = request.headers.get("Api-Key")
    if api_key:
        key_info = authn.validate_api_key(hash_token(api_key))
        if key_info:
            return key_info["user_id"], None, key_info["key_id"]

    # Session auth: Flask session cookie
    token_hash = session.get("token_hash")
    if token_hash:
        db_session = authn.validate_session(token_hash)
        if db_session:
            return db_session["user_id"], db_session.get("session_id"), None

    return None, None, None


def _get_org_from_request(kwargs: dict) -> str | None:
    """Get org_id from various sources."""
    return (
        request.headers.get("X-Org-Id")
        or kwargs.get("org_id")
        or session.get("current_org_id")
    )


# =============================================================================
# PERMISSION HELPERS
# =============================================================================


def check_permission(permission: str, resource: tuple[str, str]) -> bool:
    """Check if current request has permission to perform action on resource.

    Requires org context (either from session or g.current_org_id).

    For API key requests: checks BOTH user permission AND key scope.
    For session requests: checks only user permission.
    """
    user_id = g.get("current_user_id")
    org_id = g.get("current_org_id") or get_current_org_id()

    if not user_id or not org_id:
        return False

    authz = get_authz(org_id)

    # User must have permission
    if not authz.check(user_id, permission, resource):
        return False

    # If API key auth, key must also have scope
    api_key_id = get_current_api_key_id()
    if api_key_id:
        resource_type, resource_id = resource

        # 1. Check specific resource access: note:abc123
        has_specific = authz.check_subject("api_key", api_key_id, permission, resource)

        # 2. Check wildcard access: notes:* (pluralized type)
        wildcard_type = (
            resource_type + "s" if not resource_type.endswith("s") else resource_type
        )
        has_wildcard = authz.check_subject(
            "api_key", api_key_id, permission, (wildcard_type, "*")
        )

        if not (has_specific or has_wildcard):
            return False

    return True


def is_org_admin(user_id: str | None = None, org_id: str | None = None) -> bool:
    """Check if user has admin permission on the organization."""
    user_id = user_id or g.get("current_user_id")
    org_id = org_id or g.get("current_org_id") or get_current_org_id()

    if not user_id or not org_id:
        return False

    return get_authz(org_id).check(user_id, "admin", ("org", org_id))


def is_org_owner(user_id: str | None = None, org_id: str | None = None) -> bool:
    """Check if user is the owner of the organization."""
    user_id = user_id or g.get("current_user_id")
    org_id = org_id or g.get("current_org_id") or get_current_org_id()

    if not user_id or not org_id:
        return False

    return get_authz(org_id).check(user_id, "owner", ("org", org_id))


# =============================================================================
# API KEY SCOPE MANAGEMENT
# =============================================================================

# Permission level mappings for API key scopes
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
    """Grant authz permissions for API key scopes within an org.

    Args:
        key_id: The API key ID
        org_id: The organization ID (permissions scoped to this org)
        notes_access: "none", "all", or "selected"
        notes_level: "read", "write", or "admin"
        selected_note_ids: List of note IDs (only used when notes_access="selected")
    """
    if notes_access == "none":
        return

    authz = get_authz(org_id)
    permissions = API_KEY_LEVEL_PERMISSIONS.get(notes_level, [])

    if notes_access == "all":
        for perm in permissions:
            authz.grant(perm, resource=("notes", "*"), subject=("api_key", key_id))
    elif notes_access == "selected" and selected_note_ids:
        for note_id in selected_note_ids:
            for perm in permissions:
                authz.grant(
                    perm, resource=("note", note_id), subject=("api_key", key_id)
                )


def revoke_all_api_key_grants(key_id: str, org_id: str) -> int:
    """Revoke ALL authz grants for an API key within an org.

    Args:
        key_id: The API key ID to clean up
        org_id: The organization ID

    Returns:
        Number of grants revoked
    """
    authz = get_authz(org_id)
    return authz.revoke_subject_grants("api_key", key_id)


def get_api_key_scopes(key_id: str, org_id: str) -> dict:
    """Get machine-readable scope summary for an API key in an org.

    Returns dict like {"notes": "read"} or {"notes": "selected:write"}
    """
    authz = get_authz(org_id)

    # Check wildcard access first (notes:*)
    if authz.check_subject("api_key", key_id, "delete", ("notes", "*")):
        return {"notes": "admin"}
    if authz.check_subject("api_key", key_id, "edit", ("notes", "*")):
        return {"notes": "write"}
    if authz.check_subject("api_key", key_id, "view", ("notes", "*")):
        return {"notes": "read"}

    # Check for specific note grants using SDK
    grants = authz.list_subject_grants("api_key", key_id, resource_type="note")
    relations = {g["relation"] for g in grants}

    if "delete" in relations or "share" in relations:
        return {"notes": "selected:admin"}
    if "edit" in relations:
        return {"notes": "selected:write"}
    if "view" in relations:
        return {"notes": "selected:read"}

    return {"notes": "none"}


def get_api_key_scope_display(key_id: str, org_id: str) -> dict:
    """Get display-friendly scope summary for UI.

    Returns dict like {"notes": "Read-only"} or {"notes": "Selected notes (read/write)"}
    """
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
