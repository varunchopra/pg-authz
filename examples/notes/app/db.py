from flask import g, session
from postkit.authn import AuthnClient
from postkit.authz import AuthzClient
from postkit.config import ConfigClient
from postkit.meter import MeterClient
from psycopg_pool import ConnectionPool

from .config import Config

# Connection pool - shared across requests
_pool: ConnectionPool | None = None

# Global namespace for user identity (authn)
# All users, sessions, passwords live here regardless of which org they're in
AUTHN_NAMESPACE = "global"


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        _pool = ConnectionPool(
            Config.DATABASE_URL,
            min_size=2,
            max_size=10,
            kwargs={"autocommit": True},  # SDK manages transactions internally
        )
    return _pool


def get_db():
    """Get a database connection for the current request."""
    if "db" not in g:
        g.db = get_pool().getconn()
    return g.db


def get_authn() -> AuthnClient:
    """Get AuthnClient - always uses global namespace for identity.

    User identity (accounts, sessions, passwords, MFA) is global,
    not scoped to any organization.
    """
    if "authn" not in g:
        g.authn = AuthnClient(get_db().cursor(), AUTHN_NAMESPACE)
    return g.authn


def get_current_org_id() -> str | None:
    """Get current org_id from session."""
    return session.get("current_org_id")


def get_authz(org_id: str | None = None) -> AuthzClient:
    """Get AuthzClient for a specific org's permissions.

    Each organization has its own authz namespace (org_{org_id}) which
    isolates permissions between organizations.

    Args:
        org_id: Organization ID. If None, uses current_org_id from session.

    Returns:
        AuthzClient scoped to the organization's namespace.

    Raises:
        ValueError: If no org_id provided and none in session.
    """
    effective_org_id = org_id or get_current_org_id()

    if not effective_org_id:
        raise ValueError("No org context available for authz")

    # Cache per org within request (allows switching orgs in same request)
    cache_key = f"authz_{effective_org_id}"
    if cache_key not in g:
        namespace = f"org:{effective_org_id}"
        setattr(g, cache_key, AuthzClient(get_db().cursor(), namespace))

    return getattr(g, cache_key)


def get_authz_for_org(org_id: str) -> AuthzClient:
    """Get AuthzClient for a specific org (explicit version of get_authz).

    Use this when you need to access a specific org's permissions,
    not necessarily the current session's org.
    """
    return get_authz(org_id)


def get_system_config() -> ConfigClient:
    """Get ConfigClient for system-wide config (plan definitions).

    System config stores global settings like plan definitions that
    apply across all organizations.
    """
    if "system_config" not in g:
        g.system_config = ConfigClient(get_db().cursor(), "system")
    return g.system_config


def get_org_config(org_id: str) -> ConfigClient:
    """Get ConfigClient for org-specific config (plan assignment, settings).

    Each organization has its own config namespace (org:{org_id}) which
    stores the org's plan, feature flags, and preferences.

    Args:
        org_id: Organization ID.

    Returns:
        ConfigClient scoped to the organization's config namespace.
    """
    cache_key = f"org_config_{org_id}"
    if cache_key not in g:
        namespace = f"org:{org_id}"
        setattr(g, cache_key, ConfigClient(get_db().cursor(), namespace))
    return getattr(g, cache_key)


def get_meter(org_id: str) -> MeterClient:
    """Get MeterClient for org (per-org isolation via RLS).

    Each organization has its own metering namespace (org:{org_id}) which
    tracks seat and storage usage with per-user breakdown.

    Args:
        org_id: Organization ID.

    Returns:
        MeterClient scoped to the organization's metering namespace.
    """
    cache_key = f"meter_{org_id}"
    if cache_key not in g:
        namespace = f"org:{org_id}"
        setattr(g, cache_key, MeterClient(get_db().cursor(), namespace))
    return getattr(g, cache_key)


def reset_context():
    """Reset all PostgreSQL session context variables.

    CRITICAL: Must be called at end of request to prevent context leakage
    between requests when using connection pooling. Without this, the next
    request might inherit org context from a previous request's connection.
    """
    db = g.get("db")
    if db:
        with db.cursor() as cur:
            # Use set_config with empty string to reset (RESET doesn't work in transactions)
            cur.execute("SELECT set_config('authz.tenant_id', '', true)")
            cur.execute("SELECT set_config('authz.user_id', '', true)")


def get_note_org_id(note_id: str) -> str | None:
    """Get the org_id for a note without RLS filtering.

    This is used for cross-org access: when a user has been granted access
    to a note in another org, we need to look up which org owns the note
    BEFORE we can switch context to check permissions.

    SECURITY: This only returns the org_id, not the note content.
    Access must still be verified via authz.check() before reading data.
    """
    with get_db().cursor() as cur:
        cur.execute("SELECT org_id FROM notes WHERE note_id = %s", (note_id,))
        row = cur.fetchone()
        return row[0] if row else None


def close_db(exc=None):
    """Return connection to pool at end of request."""
    # CRITICAL: Reset context before returning connection to pool
    reset_context()

    db = g.pop("db", None)
    if db is not None:
        get_pool().putconn(db)


def init_app(app):
    app.teardown_appcontext(close_db)
