from flask import g
from postkit.authn import AuthnClient
from psycopg_pool import ConnectionPool

from .config import Config

# Connection pool - shared across requests
_pool: ConnectionPool | None = None


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
    """Get an AuthnClient for the current request."""
    if "authn" not in g:
        g.authn = AuthnClient(get_db().cursor(), "default")
    return g.authn


def close_db(exc=None):
    """Return connection to pool at end of request."""
    db = g.pop("db", None)
    if db is not None:
        get_pool().putconn(db)


def init_app(app):
    app.teardown_appcontext(close_db)
