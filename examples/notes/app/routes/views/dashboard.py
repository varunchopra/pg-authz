"""Dashboard views - user profile, sessions, API keys."""

import logging
from datetime import timedelta

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from psycopg.rows import dict_row

from ...auth import (
    API_KEY_PREFIX,
    OrgContext,
    UserContext,
    authenticated,
    create_token,
    get_api_key_scope_display,
    grant_api_key_scopes,
    revoke_all_api_key_grants,
)
from ...db import get_authn, get_authz, get_db

bp = Blueprint("dashboard", __name__)
log = logging.getLogger(__name__)


@bp.get("/dashboard")
@authenticated(org=True)
def index(ctx: OrgContext):
    authn = get_authn()

    user = authn.get_user(ctx.user_id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for("views.auth.logout"))

    sessions = authn.list_sessions(ctx.user_id)
    api_keys = authn.list_api_keys(ctx.user_id)

    # Count notes in current org
    with get_db().cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM notes WHERE org_id = %s AND owner_id = %s",
            (ctx.org_id, ctx.user_id),
        )
        note_count = cur.fetchone()[0]

    return render_template(
        "dashboard/index.html",
        user=user,
        session_count=len(sessions),
        api_key_count=len(api_keys),
        note_count=note_count,
    )


@bp.get("/sessions")
@authenticated
def sessions(ctx: UserContext):
    """Sessions are global (not org-scoped)."""
    authn = get_authn()

    sessions_list = authn.list_sessions(ctx.user_id)

    # Mark current session
    for s in sessions_list:
        s["is_current"] = s["session_id"] == ctx.session_id

    return render_template("dashboard/sessions.html", sessions=sessions_list)


@bp.post("/sessions/<session_id>/revoke")
@authenticated
def revoke_session(ctx: UserContext, session_id: str):
    authn = get_authn()

    revoked = authn.revoke_session_by_id(session_id, ctx.user_id)

    if revoked:
        flash("Session revoked", "success")
        log.info(f"Session revoked: session_id={session_id[:8]}...")
    else:
        flash("Session not found", "error")

    return redirect(url_for("views.dashboard.sessions"))


@bp.post("/sessions/revoke-others")
@authenticated
def revoke_other_sessions(ctx: UserContext):
    if not ctx.session_id:
        flash("Could not identify current session", "error")
        return redirect(url_for("views.dashboard.sessions"))

    count = get_authn().revoke_other_sessions(ctx.user_id, ctx.session_id)

    if count > 0:
        flash(f"Signed out of {count} other device(s)", "success")
        log.info(f"Revoked {count} other sessions for user_id={ctx.user_id[:8]}...")
    else:
        flash("No other sessions to revoke", "info")

    return redirect(url_for("views.dashboard.sessions"))


@bp.get("/api-keys")
@authenticated(org=True)
def api_keys(ctx: OrgContext):
    """API keys with org-scoped permissions."""
    authn = get_authn()

    keys = authn.list_api_keys(ctx.user_id)

    # Add scope summary for current org to each key
    for key in keys:
        key["scopes"] = get_api_key_scope_display(key["key_id"], ctx.org_id)

    # Check for newly created key to display
    new_key = session.pop("new_api_key", None)

    return render_template("dashboard/api_keys.html", keys=keys, new_key=new_key)


@bp.get("/api-keys/new")
@authenticated(org=True)
def new_api_key(ctx: OrgContext):
    """Show API key creation form with scope selection for current org."""
    authz = get_authz(ctx.org_id)

    # Get user's notes in current org for specific resource selection
    note_ids = authz.list_resources(ctx.user_id, "note", "view")

    # Fetch note details (filtered by org)
    notes = []
    if note_ids:
        with get_db().cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT note_id, title FROM notes
                WHERE note_id = ANY(%s) AND org_id = %s
                ORDER BY title
                """,
                (note_ids, ctx.org_id),
            )
            notes = cur.fetchall()

    return render_template("dashboard/api_keys_new.html", notes=notes)


@bp.post("/api-keys")
@authenticated(org=True)
def create_api_key(ctx: OrgContext):
    """Create an API key with org-scoped permissions."""
    name = request.form.get("name", "").strip() or "Unnamed Key"
    expires_in_days = int(request.form.get("expires_in_days", 30))

    # Parse scope configuration
    notes_access = request.form.get("notes_access", "none")
    notes_level = request.form.get("notes_level", "read")
    selected_note_ids = request.form.getlist("selected_notes")

    raw_key, key_hash = create_token(API_KEY_PREFIX)
    key_id = get_authn().create_api_key(
        user_id=ctx.user_id,
        key_hash=key_hash,
        name=name[:64],
        expires_in=timedelta(days=expires_in_days),
    )

    # Grant scopes in current org's authz namespace
    grant_api_key_scopes(
        key_id,
        org_id=ctx.org_id,
        notes_access=notes_access,
        notes_level=notes_level,
        selected_note_ids=selected_note_ids,
    )

    # Store the raw key temporarily to show once
    session["new_api_key"] = raw_key

    log.info(
        f"API key created: key_id={key_id[:8]}... org_id={ctx.org_id[:8]}... notes_access={notes_access}"
    )
    flash("API key created. Copy it now - you won't see it again!", "success")
    return redirect(url_for("views.dashboard.api_keys"))


@bp.post("/api-keys/<key_id>/revoke")
@authenticated(org=True)
def revoke_api_key(ctx: OrgContext, key_id: str):
    """Revoke an API key and its org-scoped permissions."""
    authn = get_authn()

    # Verify ownership
    keys = authn.list_api_keys(ctx.user_id)
    if not any(k["key_id"] == key_id for k in keys):
        flash("API key not found", "error")
        return redirect(url_for("views.dashboard.api_keys"))

    # Revoke authz grants in current org
    revoke_all_api_key_grants(key_id, ctx.org_id)

    # Then revoke the key (global - removes from authn)
    authn.revoke_api_key(key_id)
    log.info(f"API key revoked: key_id={key_id[:8]}...")
    flash("API key revoked", "success")
    return redirect(url_for("views.dashboard.api_keys"))
