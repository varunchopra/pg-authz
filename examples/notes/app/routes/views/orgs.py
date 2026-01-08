"""Organization management views."""

import logging
import re
import secrets
from datetime import datetime, timedelta, timezone

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
    OrgContext,
    UserContext,
    authenticated,
    get_org,
    get_org_by_slug,
    get_session_user,
    get_user_orgs,
    is_org_member,
)
from ...db import get_authn, get_authz, get_authz_for_org, get_db

bp = Blueprint("orgs", __name__, url_prefix="/orgs")
log = logging.getLogger(__name__)


def slugify(name: str) -> str:
    """Convert org name to URL-friendly slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug[:50]


def create_org_record(org_id: str, name: str, slug: str, owner_id: str) -> None:
    """Create organization record in database."""
    with get_db().cursor() as cur:
        cur.execute(
            """
            INSERT INTO orgs (org_id, name, slug, owner_id)
            VALUES (%s, %s, %s, %s)
            """,
            (org_id, name, slug, owner_id),
        )


def create_org_membership(org_id: str, user_id: str, role: str = "member") -> None:
    """Create org membership record."""
    with get_db().cursor() as cur:
        cur.execute(
            """
            INSERT INTO org_memberships (org_id, user_id, role)
            VALUES (%s, %s, %s)
            """,
            (org_id, user_id, role),
        )


def initialize_org_authz(org_id: str, owner_id: str) -> None:
    """Initialize authz namespace for a new organization.

    Sets up permission hierarchies and grants owner permission.
    """
    authz = get_authz_for_org(org_id)

    # Set up permission hierarchies (highest to lowest)
    # Note: owner -> edit -> view
    authz.set_hierarchy("note", "owner", "edit", "view")

    # Team: owner -> admin -> member
    authz.set_hierarchy("team", "owner", "admin", "member")

    # Org: owner -> admin -> member
    authz.set_hierarchy("org", "owner", "admin", "member")

    # Grant owner permission on org
    authz.grant("owner", resource=("org", org_id), subject=("user", owner_id))


def get_org_members(org_id: str) -> list[dict]:
    """Get all members of an organization."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT m.user_id, m.role, m.created_at,
                   u.email
            FROM org_memberships m
            LEFT JOIN authn.users u ON m.user_id = u.id::text
            WHERE m.org_id = %s
            ORDER BY m.role, m.created_at
            """,
            (org_id,),
        )
        return cur.fetchall()


def get_org_invites(org_id: str) -> list[dict]:
    """Get pending invites for an organization."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT * FROM org_invites
            WHERE org_id = %s
            AND used_at IS NULL
            AND expires_at > now()
            ORDER BY created_at DESC
            """,
            (org_id,),
        )
        return cur.fetchall()


# =============================================================================
# ROUTES
# =============================================================================


@bp.get("/select")
@authenticated
def select(ctx: UserContext):
    """Org selection page - shown when user has multiple orgs or none."""
    user_id = ctx.user_id
    orgs = get_user_orgs(user_id)

    if not orgs:
        # No orgs - redirect to create first org
        return redirect(url_for(".new"))

    if len(orgs) == 1:
        # Single org - auto-select and redirect
        session["current_org_id"] = orgs[0]["org_id"]
        return redirect(url_for("views.dashboard.index"))

    return render_template("orgs/select.html", orgs=orgs)


@bp.get("/new")
@authenticated
def new(ctx: UserContext):
    """Show create organization form."""
    return render_template("orgs/new.html")


@bp.post("")
@authenticated
def create(ctx: UserContext):
    """Create a new organization."""
    user_id = ctx.user_id
    name = request.form.get("name", "").strip()

    if not name:
        flash("Organization name is required", "error")
        return redirect(url_for(".new"))

    if len(name) < 2:
        flash("Organization name must be at least 2 characters", "error")
        return redirect(url_for(".new"))

    slug = slugify(name)

    # Check if slug is unique
    if get_org_by_slug(slug):
        flash("An organization with a similar name already exists", "error")
        return redirect(url_for(".new"))

    # Generate org_id
    import uuid

    org_id = str(uuid.uuid4())

    # Create org record
    create_org_record(org_id, name, slug, user_id)

    # Create membership as owner
    create_org_membership(org_id, user_id, role="owner")

    # Initialize authz namespace
    initialize_org_authz(org_id, user_id)

    # Set as current org
    session["current_org_id"] = org_id

    log.info(f"Organization created: org_id={org_id[:8]}... name={name}")
    flash(f"Organization '{name}' created!", "success")
    return redirect(url_for("views.dashboard.index"))


@bp.post("/<org_id>/switch")
@authenticated
def switch(ctx: UserContext, org_id: str):
    """Switch to a different organization."""
    user_id = ctx.user_id

    if not is_org_member(user_id, org_id):
        flash("You don't have access to that organization", "error")
        return redirect(url_for(".select"))

    org = get_org(org_id)
    if not org:
        flash("Organization not found", "error")
        return redirect(url_for(".select"))

    session["current_org_id"] = org_id
    flash(f"Switched to {org['name']}", "success")
    return redirect(url_for("views.dashboard.index"))


def _verify_settings_access(org_id: str):
    """Common verification for settings pages."""
    if session.get("current_org_id") != org_id:
        flash("Please switch to the organization first", "error")
        return None, redirect(url_for(".select"))

    org = get_org(org_id)
    if not org:
        flash("Organization not found", "error")
        return None, redirect(url_for(".select"))

    return org, None


@bp.get("/<org_id>/settings")
@authenticated(org=True, admin=True)
def settings(ctx: OrgContext, org_id: str):
    """Organization settings - General tab."""
    org, error = _verify_settings_access(org_id)
    if error:
        return error

    return render_template(
        "orgs/settings/general.html",
        org=org,
        is_owner=ctx.user_id == org["owner_id"],
        active_tab="general",
    )


@bp.get("/<org_id>/settings/members")
@authenticated(org=True, admin=True)
def settings_members(ctx: OrgContext, org_id: str):
    """Organization settings - Members tab (consolidated)."""
    org, error = _verify_settings_access(org_id)
    if error:
        return error

    authz = get_authz(org_id)

    # Get all members with full user details
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT u.id::text as user_id, u.email, u.created_at,
                   u.email_verified_at, u.disabled_at, m.role as org_role
            FROM authn.users u
            JOIN org_memberships m ON u.id::text = m.user_id
            WHERE m.org_id = %s
            ORDER BY
                CASE m.role WHEN 'owner' THEN 0 WHEN 'admin' THEN 1 ELSE 2 END,
                u.created_at DESC
            """,
            (org_id,),
        )
        members = cur.fetchall()

    # Check admin status and count stats
    admin_count = 0
    disabled_count = 0
    for member in members:
        member["is_admin"] = authz.check(member["user_id"], "admin", ("org", org_id))
        if member["is_admin"] or member["user_id"] == org["owner_id"]:
            admin_count += 1
        if member["disabled_at"]:
            disabled_count += 1

    invites = get_org_invites(org_id)

    return render_template(
        "orgs/settings/members.html",
        org=org,
        members=members,
        invites=invites,
        admin_count=admin_count,
        disabled_count=disabled_count,
        current_user_id=ctx.user_id,
        is_owner=ctx.user_id == org["owner_id"],
        active_tab="members",
    )


@bp.get("/<org_id>/settings/audit")
@authenticated(org=True, admin=True)
def settings_audit(ctx: OrgContext, org_id: str):
    """Organization settings - Audit tab."""
    org, error = _verify_settings_access(org_id)
    if error:
        return error

    authz = get_authz(org_id)

    # Get filter parameters
    event_type = request.args.get("event_type")
    actor_id = request.args.get("actor_id")

    # Fetch audit events from authz (org-scoped)
    events = authz.get_audit_events(
        event_type=event_type if event_type else None,
        actor_id=actor_id if actor_id else None,
        limit=100,
    )

    return render_template(
        "orgs/settings/audit.html",
        org=org,
        events=events,
        filter_event_type=event_type,
        filter_actor_id=actor_id,
        active_tab="audit",
    )


@bp.post("/<org_id>/invite")
@authenticated(org=True, admin=True)
def create_invite(ctx: OrgContext, org_id: str):
    """Create an invite link for the organization."""
    if session.get("current_org_id") != org_id:
        flash("Please switch to the organization first", "error")
        return redirect(url_for(".select"))

    email = request.form.get("email", "").strip().lower() or None
    role = request.form.get("role", "member")
    expires_days = int(request.form.get("expires_days", 7))

    if role not in ("admin", "member"):
        role = "member"

    code = secrets.token_urlsafe(16)
    expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)

    with get_db().cursor() as cur:
        cur.execute(
            """
            INSERT INTO org_invites (org_id, code, email, role, created_by, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (org_id, code, email, role, ctx.user_id, expires_at),
        )

    invite_url = url_for("views.orgs.view_invite", code=code, _external=True)
    log.info(f"Invite created: org_id={org_id[:8]}... code={code[:8]}...")

    flash(f"Invite created! Share this link: {invite_url}", "success")
    return redirect(url_for(".settings", org_id=org_id))


@bp.get("/invite/<code>")
def view_invite(code: str):
    """View invite details (before accepting)."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT i.*, o.name as org_name
            FROM org_invites i
            JOIN orgs o ON i.org_id = o.org_id
            WHERE i.code = %s
            AND i.used_at IS NULL
            AND i.expires_at > now()
            """,
            (code,),
        )
        invite = cur.fetchone()

    if not invite:
        flash("Invalid or expired invite link", "error")
        return redirect(url_for("views.auth.login"))

    # Check if user is logged in
    user_id = get_session_user()

    if user_id:
        # Check if already a member
        if is_org_member(user_id, invite["org_id"]):
            session["current_org_id"] = invite["org_id"]
            flash(f"You're already a member of {invite['org_name']}", "info")
            return redirect(url_for("views.dashboard.index"))

    return render_template(
        "orgs/invite.html",
        invite=invite,
        is_logged_in=user_id is not None,
    )


@bp.post("/invite/<code>/accept")
@authenticated
def accept_invite(ctx: UserContext, code: str):
    """Accept an invitation to join an organization."""
    user_id = ctx.user_id

    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT * FROM org_invites
            WHERE code = %s
            AND used_at IS NULL
            AND expires_at > now()
            """,
            (code,),
        )
        invite = cur.fetchone()

    if not invite:
        flash("Invalid or expired invite link", "error")
        return redirect(url_for(".select"))

    # Check if invite is for specific email
    if invite["email"]:
        # Get user's email
        from ...db import get_authn

        user = get_authn().get_user(user_id)
        if user and user["email"].lower() != invite["email"]:
            flash("This invite is for a different email address", "error")
            return redirect(url_for(".select"))

    # Check if already a member
    if is_org_member(user_id, invite["org_id"]):
        session["current_org_id"] = invite["org_id"]
        flash("You're already a member of this organization", "info")
        return redirect(url_for("views.dashboard.index"))

    # Create membership
    create_org_membership(invite["org_id"], user_id, role=invite["role"])

    # Grant org permission in authz
    authz = get_authz_for_org(invite["org_id"])
    authz.grant(
        invite["role"], resource=("org", invite["org_id"]), subject=("user", user_id)
    )

    # Mark invite as used
    with get_db().cursor() as cur:
        cur.execute(
            """
            UPDATE org_invites
            SET used_at = now(), used_by = %s
            WHERE invite_id = %s
            """,
            (user_id, invite["invite_id"]),
        )

    # Set as current org
    session["current_org_id"] = invite["org_id"]

    org = get_org(invite["org_id"])
    log.info(
        f"User joined org via invite: user_id={user_id[:8]}... org_id={invite['org_id'][:8]}..."
    )
    flash(f"Welcome to {org['name']}!", "success")
    return redirect(url_for("views.dashboard.index"))


@bp.post("/<org_id>/members/<member_id>/remove")
@authenticated(org=True, admin=True)
def remove_member(ctx: OrgContext, org_id: str, member_id: str):
    """Remove a member from the organization."""
    if session.get("current_org_id") != org_id:
        flash("Please switch to the organization first", "error")
        return redirect(url_for(".select"))

    org = get_org(org_id)
    if not org:
        flash("Organization not found", "error")
        return redirect(url_for(".select"))

    # Can't remove the owner
    if member_id == org["owner_id"]:
        flash("Cannot remove the organization owner", "error")
        return redirect(url_for(".settings_members", org_id=org_id))

    # Can't remove yourself
    if member_id == ctx.user_id:
        flash("Cannot remove yourself. Use 'Leave Organization' instead.", "error")
        return redirect(url_for(".settings_members", org_id=org_id))

    # Remove membership
    with get_db().cursor() as cur:
        cur.execute(
            """
            DELETE FROM org_memberships
            WHERE org_id = %s AND user_id = %s
            """,
            (org_id, member_id),
        )

    # Revoke org permission in authz
    authz = get_authz_for_org(org_id)
    for role in ("owner", "admin", "member"):
        authz.revoke(role, resource=("org", org_id), subject=("user", member_id))

    log.info(f"Member removed: user_id={member_id[:8]}... org_id={org_id[:8]}...")
    flash("Member removed", "success")
    return redirect(url_for(".settings_members", org_id=org_id))


@bp.post("/<org_id>/leave")
@authenticated
def leave(ctx: UserContext, org_id: str):
    """Leave an organization."""
    user_id = ctx.user_id

    org = get_org(org_id)
    if not org:
        flash("Organization not found", "error")
        return redirect(url_for(".select"))

    # Can't leave if you're the owner
    if user_id == org["owner_id"]:
        flash("Owners cannot leave. Transfer ownership first.", "error")
        return redirect(url_for(".settings", org_id=org_id))

    if not is_org_member(user_id, org_id):
        flash("You're not a member of this organization", "error")
        return redirect(url_for(".select"))

    # Remove membership
    with get_db().cursor() as cur:
        cur.execute(
            """
            DELETE FROM org_memberships
            WHERE org_id = %s AND user_id = %s
            """,
            (org_id, user_id),
        )

    # Revoke org permission in authz
    authz = get_authz_for_org(org_id)
    for role in ("owner", "admin", "member"):
        authz.revoke(role, resource=("org", org_id), subject=("user", user_id))

    # Clear current org if it was this one
    if session.get("current_org_id") == org_id:
        session.pop("current_org_id", None)

    log.info(f"User left org: user_id={user_id[:8]}... org_id={org_id[:8]}...")
    flash(f"You have left {org['name']}", "success")
    return redirect(url_for(".select"))


# =============================================================================
# USER MANAGEMENT ROUTES (from admin.py)
# =============================================================================


@bp.post("/<org_id>/users/<user_id>/disable")
@authenticated(org=True, admin=True)
def disable_user(ctx: OrgContext, org_id: str, user_id: str):
    """Disable a user account."""
    if user_id == ctx.user_id:
        flash("You cannot disable your own account", "error")
        return redirect(url_for(".settings_members", org_id=org_id))

    authn = get_authn()
    authn.disable_user(user_id)

    log.info(f"User disabled by admin: user_id={user_id[:8]}...")
    flash("User disabled", "success")
    return redirect(url_for(".settings_members", org_id=org_id))


@bp.post("/<org_id>/users/<user_id>/enable")
@authenticated(org=True, admin=True)
def enable_user(ctx: OrgContext, org_id: str, user_id: str):
    """Enable a disabled user account."""
    authn = get_authn()
    authn.enable_user(user_id)

    log.info(f"User enabled by admin: user_id={user_id[:8]}...")
    flash("User enabled", "success")
    return redirect(url_for(".settings_members", org_id=org_id))


@bp.post("/<org_id>/users/<user_id>/grant-admin")
@authenticated(org=True, admin=True)
def grant_admin(ctx: OrgContext, org_id: str, user_id: str):
    """Grant org admin permission to a user."""
    authz = get_authz(org_id)
    authz.grant("admin", resource=("org", org_id), subject=("user", user_id))

    log.info(f"Org admin granted: org_id={org_id[:8]}... user_id={user_id[:8]}...")
    flash("Admin permission granted", "success")
    return redirect(url_for(".settings_members", org_id=org_id))


@bp.post("/<org_id>/users/<user_id>/revoke-admin")
@authenticated(org=True, admin=True)
def revoke_admin(ctx: OrgContext, org_id: str, user_id: str):
    """Revoke org admin permission from a user."""
    if user_id == ctx.user_id:
        flash("You cannot revoke your own admin permission", "error")
        return redirect(url_for(".settings_members", org_id=org_id))

    authz = get_authz(org_id)
    authz.revoke("admin", resource=("org", org_id), subject=("user", user_id))

    log.info(f"Org admin revoked: org_id={org_id[:8]}... user_id={user_id[:8]}...")
    flash("Admin permission revoked", "success")
    return redirect(url_for(".settings_members", org_id=org_id))


@bp.post("/<org_id>/users/<user_id>/transfer-ownership")
@authenticated(org=True, admin=True)
def transfer_ownership(ctx: OrgContext, org_id: str, user_id: str):
    """Transfer organization ownership to another member."""
    org = get_org(org_id)
    if not org:
        flash("Organization not found", "error")
        return redirect(url_for(".select"))

    # Only the current owner can transfer ownership
    if ctx.user_id != org["owner_id"]:
        flash("Only the owner can transfer ownership", "error")
        return redirect(url_for(".settings_members", org_id=org_id))

    # Can't transfer to yourself
    if user_id == ctx.user_id:
        flash("You are already the owner", "error")
        return redirect(url_for(".settings_members", org_id=org_id))

    # Verify target is an org member
    if not is_org_member(user_id, org_id):
        flash("User is not a member of this organization", "error")
        return redirect(url_for(".settings_members", org_id=org_id))

    authz = get_authz(org_id)

    with get_db().transaction():
        # Update org owner_id in database
        with get_db().cursor() as cur:
            cur.execute(
                """
                UPDATE orgs SET owner_id = %s, updated_at = now()
                WHERE org_id = %s
                """,
                (user_id, org_id),
            )

            # Update org_memberships roles
            cur.execute(
                """
                UPDATE org_memberships SET role = 'admin'
                WHERE org_id = %s AND user_id = %s
                """,
                (org_id, ctx.user_id),
            )
            cur.execute(
                """
                UPDATE org_memberships SET role = 'owner'
                WHERE org_id = %s AND user_id = %s
                """,
                (org_id, user_id),
            )

        # Update authz permissions
        # Revoke owner from old owner, grant admin
        authz.revoke("owner", resource=("org", org_id), subject=("user", ctx.user_id))
        authz.grant("admin", resource=("org", org_id), subject=("user", ctx.user_id))

        # Grant owner to new owner (revoke any existing lower permissions first)
        authz.revoke("admin", resource=("org", org_id), subject=("user", user_id))
        authz.revoke("member", resource=("org", org_id), subject=("user", user_id))
        authz.grant("owner", resource=("org", org_id), subject=("user", user_id))

    log.info(
        f"Ownership transferred: org_id={org_id[:8]}... from={ctx.user_id[:8]}... to={user_id[:8]}..."
    )
    flash("Ownership transferred successfully. You are now an admin.", "success")
    return redirect(url_for(".settings_members", org_id=org_id))


@bp.get("/<org_id>/users/<user_id>/sessions")
@authenticated(org=True, admin=True)
def user_sessions(ctx: OrgContext, org_id: str, user_id: str):
    """View sessions for a specific user."""
    org, error = _verify_settings_access(org_id)
    if error:
        return error

    authn = get_authn()

    user = authn.get_user(user_id)
    if not user:
        flash("User not found", "error")
        return redirect(url_for(".settings_members", org_id=org_id))

    sessions = authn.list_sessions(user_id)

    return render_template(
        "orgs/settings/user_sessions.html",
        org=org,
        target_user={"user_id": user_id, "email": user["email"]},
        sessions=sessions,
        active_tab="members",
    )


@bp.post("/<org_id>/users/<user_id>/sessions/<session_id>/revoke")
@authenticated(org=True, admin=True)
def revoke_user_session(ctx: OrgContext, org_id: str, user_id: str, session_id: str):
    """Revoke a specific session for a user."""
    authn = get_authn()
    revoked = authn.revoke_session_by_id(session_id, user_id)

    if revoked:
        log.info(f"Session revoked by admin: session_id={session_id[:8]}...")
        flash("Session revoked", "success")
    else:
        flash("Session not found", "error")

    return redirect(url_for(".user_sessions", org_id=org_id, user_id=user_id))
