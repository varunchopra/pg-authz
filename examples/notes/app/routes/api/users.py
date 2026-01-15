import logging
import os

from flask import Blueprint, jsonify, request
from postkit.base import UniqueViolationError
from pydantic import ValidationError
from werkzeug.exceptions import BadRequest

from ...auth import create_session_with_refresh
from ...config import Config
from ...db import get_authn, get_db
from ...schemas import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    RefreshTokenRequest,
    SignupRequest,
)
from ...security import (
    DUMMY_HASH,
    REFRESH_TOKEN_PREFIX,
    UserContext,
    authenticated,
    create_token,
    hash_password,
    hash_token,
    verify_password,
)

bp = Blueprint("api_users", __name__)
log = logging.getLogger(__name__)

# Only expose debug features in development
DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true")


def validate(model: type):
    """Validate request JSON against a Pydantic model."""
    if request.json is None:
        raise BadRequest("Request body required")
    return model.model_validate(request.json)


@bp.post("/signup")
def signup():
    try:
        data = validate(SignupRequest)
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 400

    authn = get_authn()

    try:
        user_id = authn.create_user(data.email, hash_password(data.password))
        log.info(f"User created: user_id={user_id[:8]}...")
        return jsonify({"user_id": user_id}), 201
    except UniqueViolationError:
        return jsonify({"error": "email already registered"}), 409
    except Exception:
        log.exception("Signup failed")
        return jsonify({"error": "signup failed"}), 500


@bp.post("/login")
def login():
    try:
        data = validate(LoginRequest)
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 400

    authn = get_authn()

    if authn.is_locked_out(data.email):
        log.warning("Locked out login attempt")
        return jsonify({"error": "too many attempts, try again later"}), 429

    creds = authn.get_credentials(data.email)

    # Constant-time password verification to prevent timing attacks
    password_hash = (
        creds["password_hash"] if creds and creds.get("password_hash") else DUMMY_HASH
    )
    password_valid = verify_password(data.password, password_hash)

    # Check if user exists, has password, is not disabled, and password is valid
    if (
        not creds
        or not creds.get("password_hash")
        or creds.get("disabled_at")
        or not password_valid
    ):
        authn.record_login_attempt(
            data.email, success=False, ip_address=request.remote_addr
        )
        log.warning("Failed login attempt")
        return jsonify({"error": "invalid credentials"}), 401

    authn.record_login_attempt(data.email, success=True, ip_address=request.remote_addr)

    tokens = create_session_with_refresh(
        user_id=creds["user_id"],
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", ""),
    )

    log.info(f"User logged in: user_id={creds['user_id'][:8]}...")
    return jsonify(
        {
            "token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_in": tokens["expires_in"],
            "refresh_expires_in": tokens["refresh_expires_in"],
        }
    )


@bp.post("/logout")
@authenticated
def logout(ctx: UserContext):
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token_hash = hash_token(auth_header[7:])
        get_authn().revoke_session(token_hash)
    return jsonify({"ok": True})


@bp.post("/token/refresh")
def refresh_token():
    """Exchange a valid refresh token for a new access/refresh token pair.

    On success, returns new tokens. The old refresh token is invalidated.
    If the old token was already used (reuse attack), the entire token family
    is revoked and the request fails.
    """
    try:
        data = validate(RefreshTokenRequest)
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 400

    authn = get_authn()
    old_refresh_hash = hash_token(data.refresh_token)

    # Generate new refresh token
    new_refresh_token, new_refresh_hash = create_token(prefix=REFRESH_TOKEN_PREFIX)

    # Attempt rotation (atomic: validates old + creates new)
    rotation_result = authn.rotate_refresh_token(
        old_token_hash=old_refresh_hash,
        new_token_hash=new_refresh_hash,
    )

    if rotation_result is None:
        # Token invalid, expired, already rotated (reuse), or user disabled
        log.warning("Refresh token rotation failed")
        return jsonify({"error": "invalid or expired refresh token"}), 401

    # Generate new access token and create new session
    new_access_token, new_access_hash = create_token()
    authn.create_session(
        user_id=rotation_result["user_id"],
        token_hash=new_access_hash,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:1024],
    )

    log.info(
        f"Token refreshed for user_id={rotation_result['user_id'][:8]}... "
        f"generation={rotation_result['generation']}"
    )

    return jsonify(
        {
            "token": new_access_token,
            "refresh_token": new_refresh_token,
            "expires_in": Config.ACCESS_TOKEN_EXPIRES_HOURS * 3600,
            "refresh_expires_in": Config.REFRESH_TOKEN_EXPIRES_DAYS * 86400,
        }
    )


@bp.get("/me")
@authenticated
def me(ctx: UserContext):
    user = get_authn().get_user(ctx.user_id)
    if not user:
        return jsonify({"error": "user not found"}), 404

    return jsonify(
        {
            "id": user["user_id"],
            "email": user["email"],
            "created_at": user["created_at"].isoformat(),
            "email_verified_at": user["email_verified_at"].isoformat()
            if user.get("email_verified_at")
            else None,
        }
    )


@bp.post("/forgot-password")
def forgot_password():
    try:
        data = validate(PasswordResetRequest)
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 400

    authn = get_authn()
    user = authn.get_user_by_email(data.email)

    # Always return success to prevent email enumeration
    if not user:
        log.info("Password reset for non-existent email")
        return jsonify({"ok": True})

    raw_token, token_hash = create_token()
    authn.create_token(
        user_id=user["user_id"],
        token_hash=token_hash,
        token_type="password_reset",
    )

    log.info(f"Password reset token created: user_id={user['user_id'][:8]}...")

    # Only return token in debug mode - in production, send email
    if DEBUG:
        return jsonify({"ok": True, "debug_token": raw_token})
    return jsonify({"ok": True})


@bp.post("/reset-password")
def reset_password():
    try:
        data = validate(PasswordResetConfirm)
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 400

    authn = get_authn()
    token_hash = hash_token(data.token)

    token_data = authn.consume_token(token_hash, "password_reset")
    if not token_data:
        return jsonify({"error": "invalid or expired token"}), 400

    # Atomic: update password and revoke all sessions/refresh tokens
    with get_db().transaction():
        authn.update_password(token_data["user_id"], hash_password(data.password))
        authn.revoke_all_sessions(token_data["user_id"])
        authn.revoke_all_refresh_tokens(token_data["user_id"])

    log.info(f"Password reset completed: user_id={token_data['user_id'][:8]}...")
    return jsonify({"ok": True})


@bp.get("/sessions")
@authenticated
def list_sessions(ctx: UserContext):
    sessions = get_authn().list_sessions(ctx.user_id)
    return jsonify(
        {
            "sessions": [
                {
                    "id": s["session_id"],
                    "ip_address": str(s["ip_address"]) if s.get("ip_address") else None,
                    "user_agent": s.get("user_agent"),
                    "created_at": s["created_at"].isoformat(),
                    "expires_at": s["expires_at"].isoformat(),
                }
                for s in sessions
            ]
        }
    )


@bp.delete("/sessions/<session_id>")
@authenticated
def revoke_session(ctx: UserContext, session_id: str):
    """Revoke a specific session by ID."""
    revoked = get_authn().revoke_session_by_id(session_id, ctx.user_id)

    if not revoked:
        return jsonify({"error": "session not found"}), 404

    log.info(f"Session revoked: session_id={session_id[:8]}...")
    return jsonify({"ok": True})


@bp.delete("/sessions")
@authenticated
def revoke_other_sessions(ctx: UserContext):
    """Revoke all sessions except the current one ('sign out other devices')."""
    if not ctx.session_id:
        return jsonify({"error": "requires session auth (Bearer token)"}), 400

    count = get_authn().revoke_other_sessions(ctx.user_id, ctx.session_id)

    log.info(f"Revoked {count} other sessions for user_id={ctx.user_id[:8]}...")
    return jsonify({"ok": True, "revoked": count})
