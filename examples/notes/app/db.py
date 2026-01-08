from flask import g, session
from postkit.authn import AuthnClient
from postkit.authz import AuthzClient
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


def close_db(exc=None):
    """Return connection to pool at end of request."""
    db = g.pop("db", None)
    if db is not None:
        get_pool().putconn(db)


def init_app(app):
    app.teardown_appcontext(close_db)
