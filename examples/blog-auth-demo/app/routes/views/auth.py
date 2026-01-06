"""Authentication views - login, signup, password reset."""

import logging
import os
import secrets
from urllib.parse import urlencode

import requests as http_requests
from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ...auth import (
    DUMMY_HASH,
    create_token,
    get_session_user,
    hash_password,
    hash_token,
    login_user,
    logout_user,
    verify_password,
)
from ...config import Config
from ...db import get_authn, get_db

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)

DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true")


@bp.get("/")
def index():
    """Redirect to dashboard if logged in, otherwise to login."""
    if get_session_user():
        return redirect(url_for("views.dashboard.index"))
    return redirect(url_for("views.auth.login"))


@bp.get("/login")
def login():
    if get_session_user():
        return redirect(url_for("views.dashboard.index"))
    return render_template(
        "auth/login.html", google_enabled=bool(Config.GOOGLE_CLIENT_ID)
    )


@bp.post("/login")
def login_post():
    email = request.form.get("email", "").lower().strip()
    password = request.form.get("password", "")

    if not email or not password:
        flash("Email and password are required", "error")
        return redirect(url_for("views.auth.login"))

    authn = get_authn()

    if authn.is_locked_out(email):
        flash("Too many attempts. Please try again later.", "error")
        return redirect(url_for("views.auth.login"))

    creds = authn.get_credentials(email)

    # Constant-time verification
    password_hash = (
        creds["password_hash"] if creds and creds.get("password_hash") else DUMMY_HASH
    )
    password_valid = verify_password(password, password_hash)

    if (
        not creds
        or not creds.get("password_hash")
        or creds.get("disabled_at")
        or not password_valid
    ):
        authn.record_login_attempt(email, success=False, ip_address=request.remote_addr)
        flash("Invalid email or password", "error")
        return redirect(url_for("views.auth.login"))

    authn.record_login_attempt(email, success=True, ip_address=request.remote_addr)

    # Create session in database
    raw_token, token_hash = create_token()
    authn.create_session(
        user_id=creds["user_id"],
        token_hash=token_hash,
        ip_address=request.remote_addr,
        user_agent=request.headers.get("User-Agent", "")[:1024],
    )

    # Store in Flask session for browser auth
    login_user(creds["user_id"])
    session["token_hash"] = token_hash  # Store for logout

    log.info(f"User logged in via form: user_id={creds['user_id'][:8]}...")
    return redirect(url_for("views.dashboard.index"))


@bp.get("/signup")
def signup():
    if get_session_user():
        return redirect(url_for("views.dashboard.index"))
    return render_template("auth/signup.html")


@bp.post("/signup")
def signup_post():
    email = request.form.get("email", "").lower().strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    if not email or not password:
        flash("Email and password are required", "error")
        return redirect(url_for("views.auth.signup"))

    if len(password) < 8:
        flash("Password must be at least 8 characters", "error")
        return redirect(url_for("views.auth.signup"))

    if password != confirm:
        flash("Passwords do not match", "error")
        return redirect(url_for("views.auth.signup"))

    authn = get_authn()

    try:
        user_id = authn.create_user(email, hash_password(password))
        log.info(f"User created via form: user_id={user_id[:8]}...")

        # Auto-login after signup
        raw_token, token_hash = create_token()
        authn.create_session(
            user_id=user_id,
            token_hash=token_hash,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", "")[:1024],
        )
        login_user(user_id)
        session["token_hash"] = token_hash

        flash("Account created successfully!", "success")
        return redirect(url_for("views.dashboard.index"))
    except Exception as e:
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            flash("Email already registered", "error")
        else:
            log.exception("Signup failed")
            flash("Signup failed. Please try again.", "error")
        return redirect(url_for("views.auth.signup"))


@bp.get("/logout")
def logout():
    # Revoke database session if we have the token
    token_hash = session.get("token_hash")
    if token_hash:
        try:
            get_authn().revoke_session(token_hash)
        except Exception:
            log.debug("Session revocation failed on logout", exc_info=True)

    logout_user()
    flash("You have been logged out", "success")
    return redirect(url_for("views.auth.login"))


@bp.get("/forgot-password")
def forgot_password():
    return render_template("auth/forgot.html")


@bp.post("/forgot-password")
def forgot_password_post():
    email = request.form.get("email", "").lower().strip()

    if not email:
        flash("Email is required", "error")
        return redirect(url_for("views.auth.forgot_password"))

    authn = get_authn()
    user = authn.get_user_by_email(email)

    # Always show success to prevent email enumeration
    if user:
        raw_token, token_hash = create_token()
        authn.create_token(
            user_id=user["user_id"],
            token_hash=token_hash,
            token_type="password_reset",
        )
        log.info(f"Password reset token created: user_id={user['user_id'][:8]}...")

        # In debug mode, show the token (in production, send email)
        if DEBUG:
            flash(f"Debug: Reset token is {raw_token}", "info")

    flash("If an account exists, a password reset link has been sent.", "success")
    return redirect(url_for("views.auth.login"))


@bp.get("/reset-password")
def reset_password():
    token = request.args.get("token", "")
    return render_template("auth/reset.html", token=token)


@bp.post("/reset-password")
def reset_password_post():
    token = request.form.get("token", "")
    password = request.form.get("password", "")
    confirm = request.form.get("confirm", "")

    if not token:
        flash("Invalid reset link", "error")
        return redirect(url_for("views.auth.forgot_password"))

    if len(password) < 8:
        flash("Password must be at least 8 characters", "error")
        return redirect(url_for("views.auth.reset_password", token=token))

    if password != confirm:
        flash("Passwords do not match", "error")
        return redirect(url_for("views.auth.reset_password", token=token))

    authn = get_authn()
    token_hash = hash_token(token)

    token_data = authn.consume_token(token_hash, "password_reset")
    if not token_data:
        flash("Invalid or expired reset link", "error")
        return redirect(url_for("views.auth.forgot_password"))

    # Update password and revoke all sessions
    with get_db().transaction():
        authn.update_password(token_data["user_id"], hash_password(password))
        authn.revoke_all_sessions(token_data["user_id"])

    log.info(f"Password reset completed: user_id={token_data['user_id'][:8]}...")
    flash("Password updated. Please log in.", "success")
    return redirect(url_for("views.auth.login"))


# --- Google SSO for browser ---


@bp.get("/auth/google")
def google_login():
    if not Config.GOOGLE_CLIENT_ID:
        flash("Google login is not configured", "error")
        return redirect(url_for("views.auth.login"))

    # Generate and store state for CSRF protection
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    redirect_uri = Config.GOOGLE_REDIRECT_URI_VIEW

    params = urlencode(
        {
            "client_id": Config.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "email profile",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return redirect(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@bp.get("/auth/google/callback")
def google_callback():
    if not Config.GOOGLE_CLIENT_ID or not Config.GOOGLE_CLIENT_SECRET:
        flash("Google login is not configured", "error")
        return redirect(url_for("views.auth.login"))

    # Verify state
    state = request.args.get("state")
    expected_state = session.pop("oauth_state", None)
    if not state or state != expected_state:
        log.warning("OAuth state mismatch")
        flash("Authentication failed. Please try again.", "error")
        return redirect(url_for("views.auth.login"))

    error = request.args.get("error")
    if error:
        log.warning(f"Google OAuth error: {error}")
        flash("Google login failed", "error")
        return redirect(url_for("views.auth.login"))

    code = request.args.get("code")
    if not code:
        flash("Authentication failed", "error")
        return redirect(url_for("views.auth.login"))

    redirect_uri = Config.GOOGLE_REDIRECT_URI_VIEW

    # Exchange code for tokens
    try:
        token_resp = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": Config.GOOGLE_CLIENT_ID,
                "client_secret": Config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
            timeout=10,
        ).json()
    except http_requests.RequestException:
        log.exception("Google token exchange failed")
        flash("Authentication failed", "error")
        return redirect(url_for("views.auth.login"))

    if "access_token" not in token_resp:
        log.error(f"No access token: {token_resp.get('error')}")
        flash("Authentication failed", "error")
        return redirect(url_for("views.auth.login"))

    # Get user info
    try:
        user_info = http_requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_resp['access_token']}"},
            timeout=10,
        ).json()
    except http_requests.RequestException:
        log.exception("Google userinfo failed")
        flash("Authentication failed", "error")
        return redirect(url_for("views.auth.login"))

    email = user_info.get("email")
    if not email:
        flash("Could not get email from Google", "error")
        return redirect(url_for("views.auth.login"))

    authn = get_authn()

    # Find or create user
    with get_db().transaction():
        user = authn.get_user_by_email(email)
        if not user:
            user_id = authn.create_user(email, password_hash=None)
            log.info(f"SSO user created: user_id={user_id[:8]}...")
        else:
            user_id = user["user_id"]
            if user.get("disabled_at"):
                flash("Your account has been disabled", "error")
                return redirect(url_for("views.auth.login"))

        # Create database session
        raw_token, token_hash = create_token()
        authn.create_session(
            user_id=user_id,
            token_hash=token_hash,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", "")[:1024],
        )

    # Store in Flask session
    login_user(user_id)
    session["token_hash"] = token_hash

    log.info(f"SSO login via browser: user_id={user_id[:8]}...")
    return redirect(url_for("views.dashboard.index"))
