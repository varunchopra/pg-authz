"""Notes views - create, view, edit, share notes with authz."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, url_for
from psycopg.rows import dict_row

from ...auth import OrgContext, UserContext, authenticated
from ...db import get_authn, get_authz, get_db, get_meter, get_note_org_id

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

    # Permission-aware resource listing: returns only notes this user can access.
    # Handles direct grants, team membership, and hierarchy (owner→edit→view).
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

    # Get cross-org shared notes
    shared_with_me = get_shared_with_me(user_id, "note")

    return render_template(
        "notes/index.html",
        notes=notes,
        owned_count=len(owned_ids),
        shared_count=len(viewable_ids) - len(owned_ids),
        shared_with_me=shared_with_me,
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

    # Grant owner permission - cascades to edit and view via hierarchy
    authz.grant("owner", resource=("note", note_id), subject=("user", user_id))

    # Track storage usage (charged to note owner)
    content_len = len(title) + len(body)
    if content_len > 0:
        meter = get_meter(org_id)
        meter.consume(user_id, "storage", content_len, "characters")

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


@bp.get("/shared/<note_id>")
@authenticated(org=False)
def view_shared(ctx: UserContext, note_id: str):
    """View a note shared from another organization.

    This route implements context switching for cross-org access:
    1. Look up which org owns the note
    2. Check if user has access in that org's authz namespace
    3. If yes, fetch and display the note
    """
    user_id = ctx.user_id
    authn = get_authn()

    # 1. Find which org this note belongs to (no RLS needed for this lookup)
    note_org_id = get_note_org_id(note_id)
    if not note_org_id:
        flash("Note not found", "error")
        return redirect(url_for("views.dashboard.index"))

    # 2. Check access in the note's org namespace (context switch)
    authz = get_authz(note_org_id)

    if not authz.check(user_id, "view", ("note", note_id)):
        flash("You don't have access to this note", "error")
        return redirect(url_for("views.dashboard.index"))

    # 3. Fetch note (now we know user has access)
    note = get_note(note_id, note_org_id)
    if not note:
        flash("Note not found", "error")
        return redirect(url_for("views.dashboard.index"))

    # Check permissions for UI
    can_edit = authz.check(user_id, "edit", ("note", note_id))
    can_share = False  # External users can't share

    # Get owner info
    owner = authn.get_user(note["owner_id"])
    note["owner_email"] = owner["email"] if owner else note["owner_id"]

    # Get org name for display
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT name FROM orgs WHERE org_id = %s", (note_org_id,))
        org_row = cur.fetchone()
        org_name = org_row["name"] if org_row else note_org_id

    return render_template(
        "notes/view.html",
        note=note,
        can_edit=can_edit,
        can_share=can_share,
        is_external_share=True,
        source_org_name=org_name,
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

    # Get old content for delta calculation
    note = get_note(note_id, org_id)
    if not note:
        flash("Note not found", "error")
        return redirect(url_for(".index"))

    old_len = len(note["title"]) + len(note["body"])

    title = request.form.get("title", "").strip() or "Untitled"
    body = request.form.get("body", "").strip()
    new_len = len(title) + len(body)

    update_note(note_id, title, body, org_id)

    # Record storage change (charged to note owner, not editor)
    delta = new_len - old_len
    if delta != 0:
        meter = get_meter(org_id)
        if delta > 0:
            meter.consume(note["owner_id"], "storage", delta, "characters")
        else:
            meter.adjust(note["owner_id"], "storage", abs(delta), "characters")

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

    # Get note before deletion for storage credit
    note = get_note(note_id, org_id)
    if not note:
        flash("Note not found", "error")
        return redirect(url_for(".index"))

    content_len = len(note["title"]) + len(note["body"])

    # Revoke all permissions first
    for permission in ["owner", "edit", "view"]:
        users = authz.list_users(permission, ("note", note_id))
        for uid in users:
            authz.revoke(permission, resource=("note", note_id), subject=("user", uid))

    delete_note(note_id, org_id)

    # Credit back storage to note owner
    if content_len > 0:
        meter = get_meter(org_id)
        meter.adjust(note["owner_id"], "storage", content_len, "characters")

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

        if target_user:
            # User exists - grant directly
            authz.grant(
                permission,
                resource=("note", note_id),
                subject=("user", target_user["user_id"]),
                expires_at=expires_at,
            )
            log.info(f"Note shared: note_id={note_id[:8]}... with user {email}")
            flash(f"Shared with {email}", "success")
        else:
            # User doesn't exist - create pending share
            # Will be converted to real grant when user signs up and verifies email
            share_id = create_pending_share(
                recipient_email=email,
                org_id=org_id,
                resource_type="note",
                resource_id=note_id,
                permission=permission,
                invited_by=user_id,
                expires_at=expires_at,
            )
            if share_id:
                log.info(f"Pending share created: note_id={note_id[:8]}... for {email}")
                flash(
                    f"Invite sent to {email}. They'll get access when they sign up.",
                    "success",
                )
            else:
                flash(f"Share already pending for {email}", "info")

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
        # Explain why this user has access (direct grant, team membership, or hierarchy)
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


# --- Pending Shares helpers ---


def create_pending_share(
    recipient_email: str,
    org_id: str,
    resource_type: str,
    resource_id: str,
    permission: str,
    invited_by: str,
    expires_at: datetime | None = None,
) -> str | None:
    """Create a pending share for an external user.

    Returns the share ID if created, None if duplicate.
    """
    share_id = str(uuid.uuid4())
    with get_db().cursor() as cur:
        try:
            cur.execute(
                """
                INSERT INTO pending_shares
                (id, recipient_email, org_id, resource_type, resource_id,
                 permission, invited_by, expires_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (recipient_email, org_id, resource_type, resource_id, permission)
                DO NOTHING
                RETURNING id
                """,
                (
                    share_id,
                    recipient_email.lower(),
                    org_id,
                    resource_type,
                    resource_id,
                    permission,
                    invited_by,
                    expires_at,
                ),
            )
            row = cur.fetchone()
            return row[0] if row else None
        except Exception as e:
            log.error(f"Failed to create pending share: {e}")
            return None


def get_pending_shares_for_email(email: str) -> list[dict]:
    """Get all unconverted pending shares for an email."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT ps.*, n.title as resource_title, o.name as org_name
            FROM pending_shares ps
            LEFT JOIN notes n ON ps.resource_type = 'note' AND ps.resource_id = n.note_id
            LEFT JOIN orgs o ON ps.org_id = o.org_id
            WHERE ps.recipient_email = %s
            AND ps.converted_at IS NULL
            AND (ps.expires_at IS NULL OR ps.expires_at > now())
            ORDER BY ps.invited_at DESC
            """,
            (email.lower(),),
        )
        return cur.fetchall()


def convert_pending_shares(user_id: str, email: str) -> int:
    """Convert pending shares to real grants after email verification.

    SECURITY: Must only be called AFTER email is verified!
    Returns count of shares converted.
    """
    pending = get_pending_shares_for_email(email)
    converted = 0

    for share in pending:
        try:
            # Grant in the original org's namespace
            authz = get_authz(share["org_id"])
            authz.grant(
                share["permission"],
                resource=(share["resource_type"], share["resource_id"]),
                subject=("user", user_id),
                expires_at=share["expires_at"],
            )

            # Mark as converted
            with get_db().cursor() as cur:
                cur.execute(
                    """
                    UPDATE pending_shares
                    SET converted_at = now(), converted_to_user_id = %s
                    WHERE id = %s
                    """,
                    (user_id, share["id"]),
                )
            converted += 1
            log.info(
                f"Converted pending share: {share['resource_type']}:{share['resource_id'][:8]}... "
                f"to user {user_id[:8]}..."
            )
        except Exception as e:
            log.error(f"Failed to convert pending share {share['id']}: {e}")

    return converted


def get_shared_with_me(user_id: str, resource_type: str = "note") -> list[dict]:
    """Get resources shared with user from other organizations.

    Uses the cross-namespace recipient_visibility RLS policy.
    """
    # Get user's orgs to exclude from results
    with get_db().cursor() as cur:
        cur.execute("SELECT org_id FROM org_memberships WHERE user_id = %s", (user_id,))
        user_org_ids = [row[0] for row in cur.fetchall()]

    if not user_org_ids:
        return []

    # Query cross-org grants using authz client
    # We need to use any org's authz client and set user context
    authz = get_authz(user_org_ids[0])
    authz.set_user_context(user_id)

    shared_resources = authz.list_resources_shared_with_me(
        user_id, resource_type, "view"
    )

    if not shared_resources:
        return []

    # Fetch note details for each shared resource
    result = []
    authn = get_authn()
    for item in shared_resources:
        # Extract org_id from namespace (format: "org:{org_id}")
        namespace = item["namespace"]
        if not namespace.startswith("org:"):
            continue
        note_org_id = namespace[4:]

        # Get note details
        with get_db().cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT note_id, title, owner_id, created_at FROM notes WHERE note_id = %s",
                (item["resource_id"],),
            )
            note = cur.fetchone()
            if not note:
                continue

            # Get org name
            cur.execute("SELECT name FROM orgs WHERE org_id = %s", (note_org_id,))
            org_row = cur.fetchone()
            org_name = org_row["name"] if org_row else note_org_id

        # Get owner info
        owner = authn.get_user(note["owner_id"])
        owner_email = owner["email"] if owner else note["owner_id"]

        result.append(
            {
                "note_id": note["note_id"],
                "title": note["title"],
                "owner_email": owner_email,
                "org_id": note_org_id,
                "org_name": org_name,
                "my_permission": item["relation"],
                "created_at": note["created_at"],
                "expires_at": item["expires_at"],
            }
        )

    return result
