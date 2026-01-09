"""Teams views - create teams, manage members for group-based sharing."""

import logging
import uuid

from flask import Blueprint, flash, redirect, render_template, request, url_for
from psycopg.rows import dict_row

from ...auth import OrgContext, authenticated
from ...db import get_authn, get_authz, get_db

bp = Blueprint("teams", __name__, url_prefix="/teams")
log = logging.getLogger(__name__)


# --- Database helpers ---


def create_team_record(team_id: str, name: str, owner_id: str, org_id: str) -> None:
    """Create a team record in the database."""
    with get_db().cursor() as cur:
        cur.execute(
            """
            INSERT INTO teams (team_id, name, owner_id, org_id)
            VALUES (%s, %s, %s, %s)
            """,
            (team_id, name, owner_id, org_id),
        )


def get_team(team_id: str, org_id: str) -> dict | None:
    """Get a team by ID (within current org)."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT team_id, name, owner_id, org_id, created_at
            FROM teams WHERE team_id = %s AND org_id = %s
            """,
            (team_id, org_id),
        )
        return cur.fetchone()


def delete_team_record(team_id: str, org_id: str) -> None:
    """Delete a team record."""
    with get_db().cursor() as cur:
        cur.execute(
            "DELETE FROM teams WHERE team_id = %s AND org_id = %s", (team_id, org_id)
        )


def get_teams_by_ids(team_ids: list[str], org_id: str) -> list[dict]:
    """Get multiple teams by IDs (within current org)."""
    if not team_ids:
        return []
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT team_id, name, owner_id, org_id, created_at
            FROM teams WHERE team_id = ANY(%s) AND org_id = %s
            ORDER BY name
            """,
            (team_ids, org_id),
        )
        return cur.fetchall()


# --- Routes ---


@bp.get("")
@authenticated(org=True)
def index(ctx: OrgContext):
    """List all teams the user belongs to in current org."""
    authz = get_authz(ctx.org_id)

    # Get all teams where user has at least member permission
    member_team_ids = authz.list_resources(("user", ctx.user_id), "team", "member")
    admin_team_ids = authz.list_resources(("user", ctx.user_id), "team", "admin")
    owner_team_ids = authz.list_resources(("user", ctx.user_id), "team", "owner")

    # Fetch team details (filtered by org)
    teams = get_teams_by_ids(member_team_ids, ctx.org_id)

    # Annotate with permission level and member count
    for team in teams:
        if team["team_id"] in owner_team_ids:
            team["my_role"] = "owner"
        elif team["team_id"] in admin_team_ids:
            team["my_role"] = "admin"
        else:
            team["my_role"] = "member"

        # Count members (filter for users only)
        members = [
            s
            for s in authz.list_subjects("member", ("team", team["team_id"]))
            if s[0] == "user"
        ]
        team["member_count"] = len(members)

    return render_template(
        "teams/index.html",
        teams=teams,
        owned_count=len(owner_team_ids),
    )


@bp.get("/new")
@authenticated(org=True)
def new(ctx: OrgContext):
    """Show create team form."""
    return render_template("teams/new.html")


@bp.post("")
@authenticated(org=True)
def create(ctx: OrgContext):
    """Create a new team in current org."""
    authz = get_authz(ctx.org_id)

    name = request.form.get("name", "").strip()
    if not name:
        flash("Team name is required", "error")
        return redirect(url_for(".new"))

    team_id = str(uuid.uuid4())

    # Create team record with org_id
    create_team_record(team_id, name, ctx.user_id, ctx.org_id)

    # Grant owner permission to creator (owner implies admin implies member)
    authz.grant("owner", resource=("team", team_id), subject=("user", ctx.user_id))

    log.info(
        f"Team created: team_id={team_id[:8]}... org_id={ctx.org_id[:8]}... by user_id={ctx.user_id[:8]}..."
    )
    flash(f"Team '{name}' created", "success")
    return redirect(url_for(".view", team_id=team_id))


@bp.get("/<team_id>")
@authenticated(org=True)
def view(ctx: OrgContext, team_id: str):
    """View a team and its members."""
    authz = get_authz(ctx.org_id)
    authn = get_authn()

    # Check access
    if not authz.check(("user", ctx.user_id), "member", ("team", team_id)):
        flash("You don't have access to this team", "error")
        return redirect(url_for(".index"))

    team = get_team(team_id, ctx.org_id)
    if not team:
        flash("Team not found", "error")
        return redirect(url_for(".index"))

    # Check permissions
    is_admin = authz.check(("user", ctx.user_id), "admin", ("team", team_id))
    is_owner = authz.check(("user", ctx.user_id), "owner", ("team", team_id))

    # Get members with their roles (extract user IDs from tuples)
    owners = [
        s[1] for s in authz.list_subjects("owner", ("team", team_id)) if s[0] == "user"
    ]
    admins = [
        s[1] for s in authz.list_subjects("admin", ("team", team_id)) if s[0] == "user"
    ]
    members = [
        s[1] for s in authz.list_subjects("member", ("team", team_id)) if s[0] == "user"
    ]

    # Build member list
    member_list = []
    seen = set()

    for uid in owners:
        if uid in seen:
            continue
        seen.add(uid)
        user_info = authn.get_user(uid)
        member_list.append(
            {
                "user_id": uid,
                "email": user_info["email"] if user_info else uid,
                "role": "owner",
                "is_current_user": uid == ctx.user_id,
            }
        )

    for uid in admins:
        if uid in seen:
            continue
        seen.add(uid)
        user_info = authn.get_user(uid)
        member_list.append(
            {
                "user_id": uid,
                "email": user_info["email"] if user_info else uid,
                "role": "admin",
                "is_current_user": uid == ctx.user_id,
            }
        )

    for uid in members:
        if uid in seen:
            continue
        seen.add(uid)
        user_info = authn.get_user(uid)
        member_list.append(
            {
                "user_id": uid,
                "email": user_info["email"] if user_info else uid,
                "role": "member",
                "is_current_user": uid == ctx.user_id,
            }
        )

    return render_template(
        "teams/view.html",
        team=team,
        members=member_list,
        is_admin=is_admin,
        is_owner=is_owner,
    )


@bp.post("/<team_id>/members")
@authenticated(org=True)
def add_member(ctx: OrgContext, team_id: str):
    """Add a member to a team."""
    authz = get_authz(ctx.org_id)
    authn = get_authn()

    # Check admin permission
    if not authz.check(("user", ctx.user_id), "admin", ("team", team_id)):
        flash("You don't have permission to add members", "error")
        return redirect(url_for(".view", team_id=team_id))

    email = request.form.get("email", "").strip()
    role = request.form.get("role", "member")

    if not email:
        flash("Email is required", "error")
        return redirect(url_for(".view", team_id=team_id))

    # Look up user
    target_user = authn.get_user_by_email(email)
    if not target_user:
        flash(f"User not found: {email}", "error")
        return redirect(url_for(".view", team_id=team_id))

    # Grant the appropriate permission
    if role == "admin":
        authz.grant(
            "admin",
            resource=("team", team_id),
            subject=("user", target_user["user_id"]),
        )
    else:
        authz.grant(
            "member",
            resource=("team", team_id),
            subject=("user", target_user["user_id"]),
        )

    log.info(f"Team member added: team_id={team_id[:8]}... user={email} role={role}")
    flash(f"Added {email} to team", "success")
    return redirect(url_for(".view", team_id=team_id))


@bp.post("/<team_id>/members/<member_id>/remove")
@authenticated(org=True)
def remove_member(ctx: OrgContext, team_id: str, member_id: str):
    """Remove a member from a team."""
    authz = get_authz(ctx.org_id)

    # Check admin permission
    if not authz.check(("user", ctx.user_id), "admin", ("team", team_id)):
        flash("You don't have permission to remove members", "error")
        return redirect(url_for(".view", team_id=team_id))

    # Can't remove the owner
    if authz.check(("user", member_id), "owner", ("team", team_id)):
        flash("Cannot remove the team owner", "error")
        return redirect(url_for(".view", team_id=team_id))

    # Can't remove yourself if you're the last admin
    if member_id == ctx.user_id:
        admins = [
            s[1]
            for s in authz.list_subjects("admin", ("team", team_id))
            if s[0] == "user"
        ]
        if len(admins) <= 1:
            flash("You are the last admin - cannot remove yourself", "error")
            return redirect(url_for(".view", team_id=team_id))

    # Revoke all permissions
    for permission in ["admin", "member"]:
        authz.revoke(
            permission, resource=("team", team_id), subject=("user", member_id)
        )

    log.info(
        f"Team member removed: team_id={team_id[:8]}... member_id={member_id[:8]}..."
    )
    flash("Member removed", "success")
    return redirect(url_for(".view", team_id=team_id))


@bp.post("/<team_id>/members/<member_id>/promote")
@authenticated(org=True)
def promote_member(ctx: OrgContext, team_id: str, member_id: str):
    """Promote a member to admin."""
    authz = get_authz(ctx.org_id)

    # Check owner permission (only owners can promote to admin)
    if not authz.check(("user", ctx.user_id), "owner", ("team", team_id)):
        flash("Only team owners can promote members", "error")
        return redirect(url_for(".view", team_id=team_id))

    authz.grant("admin", resource=("team", team_id), subject=("user", member_id))

    log.info(
        f"Team member promoted: team_id={team_id[:8]}... member_id={member_id[:8]}..."
    )
    flash("Member promoted to admin", "success")
    return redirect(url_for(".view", team_id=team_id))


@bp.post("/<team_id>/members/<member_id>/demote")
@authenticated(org=True)
def demote_member(ctx: OrgContext, team_id: str, member_id: str):
    """Demote an admin to regular member."""
    authz = get_authz(ctx.org_id)

    # Check owner permission
    if not authz.check(("user", ctx.user_id), "owner", ("team", team_id)):
        flash("Only team owners can demote admins", "error")
        return redirect(url_for(".view", team_id=team_id))

    # Can't demote yourself
    if member_id == ctx.user_id:
        flash("You cannot demote yourself", "error")
        return redirect(url_for(".view", team_id=team_id))

    authz.revoke("admin", resource=("team", team_id), subject=("user", member_id))

    log.info(
        f"Team member demoted: team_id={team_id[:8]}... member_id={member_id[:8]}..."
    )
    flash("Admin demoted to member", "success")
    return redirect(url_for(".view", team_id=team_id))


@bp.post("/<team_id>/delete")
@authenticated(org=True)
def delete(ctx: OrgContext, team_id: str):
    """Delete a team."""
    authz = get_authz(ctx.org_id)

    # Check owner permission
    if not authz.check(("user", ctx.user_id), "owner", ("team", team_id)):
        flash("Only team owners can delete teams", "error")
        return redirect(url_for(".view", team_id=team_id))

    team = get_team(team_id, ctx.org_id)
    if not team:
        flash("Team not found", "error")
        return redirect(url_for(".index"))

    # Revoke all team permissions
    for permission in ["owner", "admin", "member"]:
        users = [
            s[1]
            for s in authz.list_subjects(permission, ("team", team_id))
            if s[0] == "user"
        ]
        for uid in users:
            authz.revoke(permission, resource=("team", team_id), subject=("user", uid))

    # Delete team record
    delete_team_record(team_id, ctx.org_id)

    log.info(f"Team deleted: team_id={team_id[:8]}... by user_id={ctx.user_id[:8]}...")
    flash(f"Team '{team['name']}' deleted", "success")
    return redirect(url_for(".index"))
