"""Authentication views - login, signup, password reset."""

import logging
import os
import secrets
from urllib.parse import urlencode

import requests as http_requests
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from postkit.base import UniqueViolationError

from ...auth import (
    DUMMY_HASH,
    create_token,
    get_session_user,
    get_user_orgs,
    hash_password,
    hash_token,
    login_user,
    logout_user,
    verify_password,
)
from ...config import Config
from ...db import get_authn, get_db
from ...schemas import (
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    SignupRequest,
    validate_form,
)
from .notes import convert_pending_shares

bp = Blueprint("auth", __name__)
log = logging.getLogger(__name__)

DEBUG = os.environ.get("DEBUG", "").lower() in ("1", "true")


def _post_auth_redirect(user_id: str):
    """Determine where to redirect after successful authentication.

    - No orgs: redirect to create org
    - 1 org: auto-select and go to dashboard
    - Multiple orgs: go to org selection
    """
    orgs = get_user_orgs(user_id)

    if not orgs:
        # New user needs to create an org
        return redirect(url_for("views.orgs.new"))

    if len(orgs) == 1:
        # Auto-select the single org
        session["current_org_id"] = orgs[0]["org_id"]
        return redirect(url_for("views.dashboard.index"))

    # Multiple orgs - let user choose
    return redirect(url_for("views.orgs.select"))


@bp.get("/")
def index():
    """Redirect based on auth state and org membership."""
    user_id = get_session_user()
    if user_id:
        return _post_auth_redirect(user_id)
    return redirect(url_for("views.auth.login"))


@bp.get("/login")
def login():
    user_id = get_session_user()
    if user_id:
        return _post_auth_redirect(user_id)
    return render_template(
        "auth/login.html", google_enabled=bool(Config.GOOGLE_CLIENT_ID)
    )


@bp.post("/login")
def login_post():
    data, err = validate_form(LoginRequest)
    if err:
        flash(err, "error")
        return redirect(url_for("views.auth.login"))

    authn = get_authn()

    if authn.is_locked_out(data.email):
        flash("Too many attempts. Please try again later.", "error")
        return redirect(url_for("views.auth.login"))

    creds = authn.get_credentials(data.email)

    # Constant-time verification
    password_hash = (
        creds["password_hash"] if creds and creds.get("password_hash") else DUMMY_HASH
    )
    password_valid = verify_password(data.password, password_hash)

    if (
        not creds
        or not creds.get("password_hash")
        or creds.get("disabled_at")
        or not password_valid
    ):
        authn.record_login_attempt(
            data.email, success=False, ip_address=request.remote_addr
        )
        flash("Invalid email or password", "error")
        return redirect(url_for("views.auth.login"))

    authn.record_login_attempt(data.email, success=True, ip_address=request.remote_addr)

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
    return _post_auth_redirect(creds["user_id"])


@bp.get("/signup")
def signup():
    user_id = get_session_user()
    if user_id:
        return _post_auth_redirect(user_id)
    return render_template(
        "auth/signup.html",
        min_password_length=Config.MIN_PASSWORD_LENGTH,
        next_url=request.args.get("next"),
    )


@bp.post("/signup")
def signup_post():
    data, err = validate_form(SignupRequest)
    if err:
        flash(err, "error")
        return redirect(url_for("views.auth.signup"))

    confirm = request.form.get("confirm", "")
    if data.password != confirm:
        flash("Passwords do not match", "error")
        return redirect(url_for("views.auth.signup"))

    authn = get_authn()

    try:
        user_id = authn.create_user(data.email, hash_password(data.password))
        log.info(f"User created via form: user_id={user_id[:8]}...")

        # Convert pending shares for this email
        # SECURITY NOTE: In production, this should happen AFTER email verification,
        # not on signup. Otherwise an attacker could register someone else's email
        # and gain access to their pending shares. This demo app doesn't have email
        # verification, so we convert on signup for demonstration purposes.
        converted = convert_pending_shares(user_id, data.email)
        if converted > 0:
            log.info(f"Converted {converted} pending shares for user {user_id[:8]}...")

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

        # Check for redirect URL (e.g., from invite flow)
        next_url = request.form.get("next")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)

        # New users go to create their first org
        return redirect(url_for("views.orgs.new"))
    except UniqueViolationError:
        flash("Email already registered", "error")
        return redirect(url_for("views.auth.signup"))
    except Exception:
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
    data, err = validate_form(PasswordResetRequest)
    if err:
        flash(err, "error")
        return redirect(url_for("views.auth.forgot_password"))

    authn = get_authn()
    user = authn.get_user_by_email(data.email)

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
    return render_template(
        "auth/reset.html", token=token, min_password_length=Config.MIN_PASSWORD_LENGTH
    )


@bp.post("/reset-password")
def reset_password_post():
    data, err = validate_form(PasswordResetConfirm)
    if err:
        token = request.form.get("token", "")
        flash(err, "error")
        if token:
            return redirect(url_for("views.auth.reset_password", token=token))
        return redirect(url_for("views.auth.forgot_password"))

    confirm = request.form.get("confirm", "")
    if data.password != confirm:
        flash("Passwords do not match", "error")
        return redirect(url_for("views.auth.reset_password", token=data.token))

    authn = get_authn()
    token_hash = hash_token(data.token)

    token_data = authn.consume_token(token_hash, "password_reset")
    if not token_data:
        flash("Invalid or expired reset link", "error")
        return redirect(url_for("views.auth.forgot_password"))

    # Update password and revoke all sessions
    with get_db().transaction():
        authn.update_password(token_data["user_id"], hash_password(data.password))
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
    is_new_user = False
    with get_db().transaction():
        user = authn.get_user_by_email(email)
        if not user:
            user_id = authn.create_user(email, password_hash=None)
            log.info(f"SSO user created: user_id={user_id[:8]}...")
            is_new_user = True
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

    # Convert pending shares for new SSO users
    # SECURITY NOTE: Google SSO verifies email ownership, so this is safe.
    if is_new_user:
        converted = convert_pending_shares(user_id, email)
        if converted > 0:
            log.info(
                f"Converted {converted} pending shares for SSO user {user_id[:8]}..."
            )

    # Store in Flask session
    login_user(user_id)
    session["token_hash"] = token_hash

    log.info(f"SSO login via browser: user_id={user_id[:8]}...")
    return _post_auth_redirect(user_id)
