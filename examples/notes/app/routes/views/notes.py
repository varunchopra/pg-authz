"""Notes views - create, view, edit, share notes with authz."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from psycopg.rows import dict_row

from ...auth import OrgContext, authenticated
from ...db import get_authn, get_authz, get_db

bp = Blueprint("notes", __name__, url_prefix="/notes")
log = logging.getLogger(__name__)


# --- Database helpers ---


def create_note(title: str, body: str, owner_id: str, org_id: str) -> str:
    """Create a note and return its ID."""
    note_id = str(uuid.uuid4())
    with get_db().cursor() as cur:
        cur.execute(
            """
            INSERT INTO notes (note_id, title, body, owner_id, org_id)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (note_id, title, body, owner_id, org_id),
        )
    return note_id


def get_note(note_id: str, org_id: str) -> dict | None:
    """Get a note by ID (within current org)."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT note_id, title, body, owner_id, org_id, created_at, updated_at
            FROM notes WHERE note_id = %s AND org_id = %s
            """,
            (note_id, org_id),
        )
        return cur.fetchone()


def update_note(note_id: str, title: str, body: str, org_id: str) -> None:
    """Update a note."""
    with get_db().cursor() as cur:
        cur.execute(
            """
            UPDATE notes SET title = %s, body = %s, updated_at = now()
            WHERE note_id = %s AND org_id = %s
            """,
            (title, body, note_id, org_id),
        )


def delete_note(note_id: str, org_id: str) -> None:
    """Delete a note."""
    with get_db().cursor() as cur:
        cur.execute(
            "DELETE FROM notes WHERE note_id = %s AND org_id = %s", (note_id, org_id)
        )


def get_notes_by_ids(note_ids: list[str], org_id: str) -> list[dict]:
    """Get multiple notes by IDs (within current org)."""
    if not note_ids:
        return []
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT note_id, title, body, owner_id, org_id, created_at, updated_at
            FROM notes WHERE note_id = ANY(%s) AND org_id = %s
            ORDER BY updated_at DESC
            """,
            (note_ids, org_id),
        )
        return cur.fetchall()


# --- Routes ---


@bp.get("")
@authenticated(org=True)
def index(ctx: OrgContext):
    """List all notes the user can access in current org."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)
    authn = get_authn()

    # Get all notes this user can view (in current org's authz namespace)
    viewable_ids = authz.list_resources(user_id, "note", "view")
    editable_ids = authz.list_resources(user_id, "note", "edit")
    owned_ids = authz.list_resources(user_id, "note", "owner")

    # Fetch note details (filtered by org)
    notes = get_notes_by_ids(viewable_ids, org_id)

    # Annotate with permission level and owner info
    for note in notes:
        if note["note_id"] in owned_ids:
            note["my_permission"] = "owner"
        elif note["note_id"] in editable_ids:
            note["my_permission"] = "edit"
        else:
            note["my_permission"] = "view"

        # Get owner email
        owner = authn.get_user(note["owner_id"])
        note["owner_email"] = owner["email"] if owner else note["owner_id"]

    return render_template(
        "notes/index.html",
        notes=notes,
        owned_count=len(owned_ids),
        shared_count=len(viewable_ids) - len(owned_ids),
    )


@bp.get("/new")
@authenticated(org=True)
def new(ctx: OrgContext):
    """Show create note form."""
    return render_template("notes/edit.html", note=None)


@bp.post("")
@authenticated(org=True)
def create(ctx: OrgContext):
    """Create a new note in current org."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)

    title = request.form.get("title", "").strip() or "Untitled"
    body = request.form.get("body", "").strip()

    # Create the note with org_id
    note_id = create_note(title, body, user_id, org_id)

    # Grant owner permission in org's authz namespace
    authz.grant("owner", resource=("note", note_id), subject=("user", user_id))

    log.info(
        f"Note created: note_id={note_id[:8]}... org_id={org_id[:8]}... by user_id={user_id[:8]}..."
    )
    flash("Note created", "success")
    return redirect(url_for(".view", note_id=note_id))


@bp.get("/<note_id>")
@authenticated(org=True)
def view(ctx: OrgContext, note_id: str):
    """View a note."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)
    authn = get_authn()

    # Check access in org's authz namespace
    if not authz.check(user_id, "view", ("note", note_id)):
        flash("You don't have access to this note", "error")
        return redirect(url_for(".index"))

    note = get_note(note_id, org_id)
    if not note:
        flash("Note not found", "error")
        return redirect(url_for(".index"))

    # Check permissions for UI
    can_edit = authz.check(user_id, "edit", ("note", note_id))
    can_share = authz.check(user_id, "owner", ("note", note_id))

    # Get owner info
    owner = authn.get_user(note["owner_id"])
    note["owner_email"] = owner["email"] if owner else note["owner_id"]

    return render_template(
        "notes/view.html",
        note=note,
        can_edit=can_edit,
        can_share=can_share,
    )


@bp.get("/<note_id>/edit")
@authenticated(org=True)
def edit(ctx: OrgContext, note_id: str):
    """Show edit note form."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)

    # Check edit permission
    if not authz.check(user_id, "edit", ("note", note_id)):
        flash("You don't have permission to edit this note", "error")
        return redirect(url_for(".view", note_id=note_id))

    note = get_note(note_id, org_id)
    if not note:
        flash("Note not found", "error")
        return redirect(url_for(".index"))

    return render_template("notes/edit.html", note=note)


@bp.post("/<note_id>")
@authenticated(org=True)
def update(ctx: OrgContext, note_id: str):
    """Update a note."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)

    # Check edit permission
    if not authz.check(user_id, "edit", ("note", note_id)):
        flash("You don't have permission to edit this note", "error")
        return redirect(url_for(".view", note_id=note_id))

    title = request.form.get("title", "").strip() or "Untitled"
    body = request.form.get("body", "").strip()

    update_note(note_id, title, body, org_id)

    log.info(f"Note updated: note_id={note_id[:8]}... by user_id={user_id[:8]}...")
    flash("Note updated", "success")
    return redirect(url_for(".view", note_id=note_id))


@bp.post("/<note_id>/delete")
@authenticated(org=True)
def delete(ctx: OrgContext, note_id: str):
    """Delete a note."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)

    # Check owner permission
    if not authz.check(user_id, "owner", ("note", note_id)):
        flash("You don't have permission to delete this note", "error")
        return redirect(url_for(".view", note_id=note_id))

    # Revoke all permissions first
    for permission in ["owner", "edit", "view"]:
        users = authz.list_users(permission, ("note", note_id))
        for uid in users:
            authz.revoke(permission, resource=("note", note_id), subject=("user", uid))

    delete_note(note_id, org_id)

    log.info(f"Note deleted: note_id={note_id[:8]}... by user_id={user_id[:8]}...")
    flash("Note deleted", "success")
    return redirect(url_for(".index"))


# --- Sharing ---


@bp.get("/<note_id>/share")
@authenticated(org=True)
def share(ctx: OrgContext, note_id: str):
    """Show share dialog."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)

    # Check owner permission
    if not authz.check(user_id, "owner", ("note", note_id)):
        flash("You don't have permission to share this note", "error")
        return redirect(url_for(".view", note_id=note_id))

    note = get_note(note_id, org_id)
    if not note:
        flash("Note not found", "error")
        return redirect(url_for(".index"))

    # Get list of teams user owns or is admin of (in current org)
    teams = get_user_teams(user_id, org_id)

    return render_template("notes/share.html", note=note, teams=teams)


@bp.post("/<note_id>/share")
@authenticated(org=True)
def grant_access(ctx: OrgContext, note_id: str):
    """Grant access to a note."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)
    authn = get_authn()

    # Check owner permission
    if not authz.check(user_id, "owner", ("note", note_id)):
        flash("You don't have permission to share this note", "error")
        return redirect(url_for(".view", note_id=note_id))

    share_type = request.form.get("share_type", "user")
    permission = request.form.get("permission", "view")
    expires_days = request.form.get("expires_days")

    # Calculate expiration
    expires_at = None
    if expires_days and expires_days != "never":
        expires_at = datetime.now(timezone.utc) + timedelta(days=int(expires_days))

    if share_type == "user":
        email = request.form.get("email", "").strip()
        if not email:
            flash("Please enter an email address", "error")
            return redirect(url_for(".share", note_id=note_id))

        # Look up user by email
        target_user = authn.get_user_by_email(email)
        if not target_user:
            flash(f"User not found: {email}", "error")
            return redirect(url_for(".share", note_id=note_id))

        authz.grant(
            permission,
            resource=("note", note_id),
            subject=("user", target_user["user_id"]),
            expires_at=expires_at,
        )
        log.info(f"Note shared: note_id={note_id[:8]}... with user {email}")
        flash(f"Shared with {email}", "success")

    elif share_type == "team":
        team_id = request.form.get("team_id", "").strip()
        if not team_id:
            flash("Please select a team", "error")
            return redirect(url_for(".share", note_id=note_id))

        authz.grant(
            permission,
            resource=("note", note_id),
            subject=("team", team_id),
            expires_at=expires_at,
        )
        log.info(f"Note shared: note_id={note_id[:8]}... with team {team_id[:8]}...")
        flash("Shared with team", "success")

    return redirect(url_for(".access", note_id=note_id))


@bp.post("/<note_id>/unshare")
@authenticated(org=True)
def revoke_access(ctx: OrgContext, note_id: str):
    """Revoke access to a note."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)

    # Check owner permission
    if not authz.check(user_id, "owner", ("note", note_id)):
        flash("You don't have permission to manage sharing", "error")
        return redirect(url_for(".view", note_id=note_id))

    subject_type = request.form.get("subject_type")
    subject_id = request.form.get("subject_id")
    permission = request.form.get("permission")

    if subject_type and subject_id and permission:
        authz.revoke(
            permission,
            resource=("note", note_id),
            subject=(subject_type, subject_id),
        )
        log.info(
            f"Note unshared: note_id={note_id[:8]}... revoked {permission} from {subject_type}:{subject_id[:8]}..."
        )
        flash("Access revoked", "success")

    return redirect(url_for(".access", note_id=note_id))


@bp.get("/<note_id>/access")
@authenticated(org=True)
def access(ctx: OrgContext, note_id: str):
    """Show who has access to a note."""
    user_id = ctx.user_id
    org_id = ctx.org_id
    authz = get_authz(org_id)
    authn = get_authn()

    # Check owner permission
    if not authz.check(user_id, "owner", ("note", note_id)):
        flash("You don't have permission to view access details", "error")
        return redirect(url_for(".view", note_id=note_id))

    note = get_note(note_id, org_id)
    if not note:
        flash("Note not found", "error")
        return redirect(url_for(".index"))

    # Get all users with each permission level
    owners = authz.list_users("owner", ("note", note_id))
    editors = authz.list_users("edit", ("note", note_id))
    viewers = authz.list_users("view", ("note", note_id))

    # Build access list with explanations
    access_list = []
    seen_users = set()

    for uid in owners:
        if uid in seen_users:
            continue
        seen_users.add(uid)
        user_info = authn.get_user(uid)
        explanations = authz.explain(uid, "owner", ("note", note_id))
        access_list.append(
            {
                "subject_type": "user",
                "subject_id": uid,
                "display_name": user_info["email"] if user_info else uid,
                "permission": "owner",
                "explanations": explanations,
                "is_current_user": uid == user_id,
            }
        )

    for uid in editors:
        if uid in seen_users:
            continue
        seen_users.add(uid)
        user_info = authn.get_user(uid)
        explanations = authz.explain(uid, "edit", ("note", note_id))
        access_list.append(
            {
                "subject_type": "user",
                "subject_id": uid,
                "display_name": user_info["email"] if user_info else uid,
                "permission": "edit",
                "explanations": explanations,
                "is_current_user": uid == user_id,
            }
        )

    for uid in viewers:
        if uid in seen_users:
            continue
        seen_users.add(uid)
        user_info = authn.get_user(uid)
        explanations = authz.explain(uid, "view", ("note", note_id))
        access_list.append(
            {
                "subject_type": "user",
                "subject_id": uid,
                "display_name": user_info["email"] if user_info else uid,
                "permission": "view",
                "explanations": explanations,
                "is_current_user": uid == user_id,
            }
        )

    return render_template(
        "notes/access.html",
        note=note,
        access_list=access_list,
    )


# --- Helper functions ---


def get_user_teams(user_id: str, org_id: str) -> list[dict]:
    """Get teams that the user owns or is admin of (in current org)."""
    authz = get_authz(org_id)

    # Get teams where user has admin permission
    team_ids = authz.list_resources(user_id, "team", "admin")

    if not team_ids:
        return []

    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT team_id, name, owner_id, created_at
            FROM teams WHERE team_id = ANY(%s) AND org_id = %s
            ORDER BY name
            """,
            (team_ids, org_id),
        )
        return cur.fetchall()
