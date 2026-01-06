"""Dashboard views - user profile, sessions, API keys."""

import logging

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from ...auth import (
    create_token,
    get_current_session_id,
    get_session_user,
    require_login,
)
from ...db import get_authn

bp = Blueprint("dashboard", __name__)
log = logging.getLogger(__name__)


@bp.get("/dashboard")
@require_login
def index():
    user_id = get_session_user()
    authn = get_authn()

    user = authn.get_user(user_id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("views.auth.logout"))

    sessions = authn.list_sessions(user_id)
    api_keys = authn.list_api_keys(user_id)

    return render_template(
        "dashboard/index.html",
        user=user,
        session_count=len(sessions),
        api_key_count=len(api_keys),
    )


@bp.get("/sessions")
@require_login
def sessions():
    user_id = get_session_user()
    current_session_id = get_current_session_id()
    authn = get_authn()

    sessions_list = authn.list_sessions(user_id)

    # Mark current session
    for s in sessions_list:
        s["is_current"] = s["session_id"] == current_session_id

    return render_template("dashboard/sessions.html", sessions=sessions_list)


@bp.post("/sessions/<session_id>/revoke")
@require_login
def revoke_session(session_id: str):
    user_id = get_session_user()
    authn = get_authn()

    revoked = authn.revoke_session_by_id(session_id, user_id)

    if revoked:
        flash("Session revoked", "success")
        log.info(f"Session revoked: session_id={session_id[:8]}...")
    else:
        flash("Session not found", "error")

    return redirect(url_for("views.dashboard.sessions"))


@bp.get("/api-keys")
@require_login
def api_keys():
    user_id = get_session_user()
    authn = get_authn()

    keys = authn.list_api_keys(user_id)

    # Check for newly created key to display
    new_key = session.pop("new_api_key", None)

    return render_template("dashboard/api_keys.html", keys=keys, new_key=new_key)


@bp.post("/api-keys")
@require_login
def create_api_key():
    user_id = get_session_user()
    name = request.form.get("name", "").strip() or "Unnamed Key"

    raw_key, key_hash = create_token()
    key_id = get_authn().create_api_key(
        user_id=user_id,
        key_hash=key_hash,
        name=name[:64],  # Limit name length
    )

    # Store the raw key temporarily to show once
    session["new_api_key"] = raw_key

    log.info(f"API key created: key_id={key_id}")
    flash("API key created. Copy it now - you won't see it again!", "success")
    return redirect(url_for("views.dashboard.api_keys"))


@bp.post("/api-keys/<key_id>/revoke")
@require_login
def revoke_api_key(key_id: str):
    user_id = get_session_user()
    authn = get_authn()

    # Verify ownership
    keys = authn.list_api_keys(user_id)
    if not any(k["key_id"] == key_id for k in keys):
        flash("API key not found", "error")
        return redirect(url_for("views.dashboard.api_keys"))

    authn.revoke_api_key(key_id)
    log.info(f"API key revoked: key_id={key_id}")
    flash("API key revoked", "success")
    return redirect(url_for("views.dashboard.api_keys"))
