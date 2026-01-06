import logging
import secrets
from urllib.parse import urlencode

import requests as http_requests
from flask import Blueprint, jsonify, request, session

from ...auth import create_token
from ...config import Config
from ...db import get_authn, get_db

bp = Blueprint("api_sso", __name__, url_prefix="/auth")
log = logging.getLogger(__name__)


@bp.get("/google")
def google_auth_url():
    if not Config.GOOGLE_CLIENT_ID:
        return jsonify({"error": "google sso not configured"}), 501

    # Generate and store state for CSRF protection
    state = secrets.token_urlsafe(32)
    session["oauth_state"] = state

    params = urlencode(
        {
            "client_id": Config.GOOGLE_CLIENT_ID,
            "redirect_uri": Config.GOOGLE_REDIRECT_URI_API,
            "response_type": "code",
            "scope": "email profile",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
        }
    )
    return jsonify({"url": f"https://accounts.google.com/o/oauth2/v2/auth?{params}"})


@bp.get("/google/callback")
def google_callback():
    if not Config.GOOGLE_CLIENT_ID or not Config.GOOGLE_CLIENT_SECRET:
        return jsonify({"error": "google sso not configured"}), 501

    # Verify state to prevent CSRF
    state = request.args.get("state")
    expected_state = session.pop("oauth_state", None)
    if not state or state != expected_state:
        log.warning("OAuth state mismatch - possible CSRF attempt")
        return jsonify({"error": "invalid state"}), 400

    code = request.args.get("code")
    error = request.args.get("error")

    if error:
        log.warning(f"Google OAuth error: {error}")
        return jsonify({"error": error}), 400

    if not code:
        return jsonify({"error": "missing code"}), 400

    # Exchange code for tokens
    try:
        token_resp = http_requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": Config.GOOGLE_CLIENT_ID,
                "client_secret": Config.GOOGLE_CLIENT_SECRET,
                "redirect_uri": Config.GOOGLE_REDIRECT_URI_API,
                "grant_type": "authorization_code",
            },
            timeout=10,
        ).json()
    except http_requests.RequestException:
        log.exception("Google token exchange failed")
        return jsonify({"error": "authentication failed"}), 502

    if "access_token" not in token_resp:
        log.error(f"No access token in response: {token_resp.get('error')}")
        return jsonify({"error": "authentication failed"}), 400

    # Get user info
    try:
        user_info = http_requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {token_resp['access_token']}"},
            timeout=10,
        ).json()
    except http_requests.RequestException:
        log.exception("Google userinfo request failed")
        return jsonify({"error": "authentication failed"}), 502

    email = user_info.get("email")
    if not email:
        return jsonify({"error": "no email from google"}), 400

    authn = get_authn()

    # Find or create user within a transaction
    with get_db().transaction():
        user = authn.get_user_by_email(email)
        if not user:
            user_id = authn.create_user(email, password_hash=None)
            log.info(f"SSO user created: user_id={user_id[:8]}...")
        else:
            user_id = user["user_id"]

            # Check if user is disabled
            if user.get("disabled_at"):
                log.warning(f"Disabled user SSO attempt: user_id={user_id[:8]}...")
                return jsonify({"error": "account disabled"}), 403

        raw_token, token_hash = create_token()
        authn.create_session(
            user_id=user_id,
            token_hash=token_hash,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", "")[:1024],
        )

    log.info(f"SSO login: user_id={user_id[:8]}...")
    return jsonify({"token": raw_token})
