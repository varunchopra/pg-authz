import hashlib
import secrets
from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from flask import g, jsonify, redirect, request, session, url_for

from .db import get_authn

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


def create_token() -> tuple[str, str]:
    """Returns (raw_token, hashed_token)."""
    raw = secrets.token_urlsafe(32)
    hashed = hashlib.sha256(raw.encode()).hexdigest()
    return raw, hashed


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _set_user_context(user_id: str) -> str:
    """Cache user_id and set actor context for audit trails."""
    g.current_user_id = user_id
    get_authn().set_actor(
        f"user:{user_id}",
        request_id=g.get("request_id"),
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:1024],
    )
    return user_id


def get_current_user() -> str | None:
    if hasattr(g, "current_user_id"):
        return g.current_user_id

    authn = get_authn()

    # Bearer token (session auth) takes precedence
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        sess = authn.validate_session(hash_token(auth_header[7:]))
        if sess:
            return _set_user_context(sess["user_id"])

    # Api-Key header for API key auth
    api_key = request.headers.get("Api-Key")
    if api_key:
        key_info = authn.validate_api_key(hash_token(api_key))
        if key_info:
            return _set_user_context(key_info["user_id"])

    g.current_user_id = None
    return None


def require_auth(f):
    """Decorator for API routes - returns 401 JSON if not authenticated."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = get_current_user()
        if not user_id:
            return jsonify({"error": "unauthorized"}), 401
        return f(*args, **kwargs)

    return decorated


# --- Session-based auth for browser views ---


def login_user(user_id: str) -> None:
    """Set user_id in Flask session (for browser-based auth)."""
    session["user_id"] = user_id


def logout_user() -> None:
    """Clear user_id from Flask session."""
    session.pop("user_id", None)


def get_session_user() -> str | None:
    """Get user_id from Flask session if the database session is still valid."""
    token_hash = session.get("token_hash")
    if not token_hash:
        return None

    # Validate session against database
    from .db import get_authn

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


def require_login(f):
    """Decorator for view routes - redirects to login if not authenticated."""

    @wraps(f)
    def decorated(*args, **kwargs):
        user_id = get_session_user()
        if not user_id:
            return redirect(url_for("views.auth.login"))
        g.current_user_id = user_id
        return f(*args, **kwargs)

    return decorated
