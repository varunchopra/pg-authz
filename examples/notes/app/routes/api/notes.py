"""Notes API - demonstrates scoped API key access with multi-tenant support."""

import logging

from flask import Blueprint, jsonify, request
from psycopg.rows import dict_row

from ...auth import OrgContext, authenticated, check_permission
from ...db import get_authz, get_db

bp = Blueprint("api_notes", __name__, url_prefix="/notes")
log = logging.getLogger(__name__)


def get_note_by_id(note_id: str, org_id: str) -> dict | None:
    """Get a note by ID within the specified organization."""
    with get_db().cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT note_id, title, body, owner_id, org_id, created_at, updated_at
            FROM notes WHERE note_id = %s AND org_id = %s
            """,
            (note_id, org_id),
        )
        return cur.fetchone()


@bp.get("")
@authenticated(org=True)
def list_notes(ctx: OrgContext):
    """List all notes the user can access in the current org (respecting API key scopes)."""
    authz = get_authz(ctx.org_id)

    # Get all notes this user can view (in current org's authz namespace)
    viewable_ids = authz.list_resources(("user", ctx.user_id), "note", "view")

    # Filter by API key scope if using API key auth
    if ctx.api_key_id:
        # Check if API key has wildcard access
        has_wildcard = authz.check(("api_key", ctx.api_key_id), "view", ("note", "*"))

        if not has_wildcard:
            # Filter to only notes the API key has specific access to
            viewable_ids = [
                nid
                for nid in viewable_ids
                if authz.check(("api_key", ctx.api_key_id), "view", ("note", nid))
            ]

    # Fetch note details (filtered by org)
    notes = []
    if viewable_ids:
        with get_db().cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT note_id, title, owner_id, created_at, updated_at
                FROM notes WHERE note_id = ANY(%s) AND org_id = %s
                ORDER BY updated_at DESC
                """,
                (viewable_ids, ctx.org_id),
            )
            notes = cur.fetchall()

    return jsonify(
        {
            "notes": [
                {
                    "id": n["note_id"],
                    "title": n["title"],
                    "owner_id": n["owner_id"],
                    "created_at": n["created_at"].isoformat()
                    if n["created_at"]
                    else None,
                    "updated_at": n["updated_at"].isoformat()
                    if n["updated_at"]
                    else None,
                }
                for n in notes
            ]
        }
    )


@bp.get("/<note_id>")
@authenticated(org=True)
def get_note(ctx: OrgContext, note_id: str):
    """Get a specific note (respecting API key scopes)."""
    # Check permission using layered authorization
    if not check_permission("view", ("note", note_id)):
        return jsonify({"error": "no access to this note"}), 403

    note = get_note_by_id(note_id, ctx.org_id)
    if not note:
        return jsonify({"error": "not found"}), 404

    return jsonify(
        {
            "note": {
                "id": note["note_id"],
                "title": note["title"],
                "body": note["body"],
                "owner_id": note["owner_id"],
                "created_at": note["created_at"].isoformat()
                if note["created_at"]
                else None,
                "updated_at": note["updated_at"].isoformat()
                if note["updated_at"]
                else None,
            }
        }
    )


@bp.post("/<note_id>")
@authenticated(org=True)
def update_note(ctx: OrgContext, note_id: str):
    """Update a note (requires edit permission and API key scope)."""
    # Check permission using layered authorization
    if not check_permission("edit", ("note", note_id)):
        return jsonify({"error": "no edit access to this note"}), 403

    note = get_note_by_id(note_id, ctx.org_id)
    if not note:
        return jsonify({"error": "not found"}), 404

    data = request.json or {}
    title = data.get("title", note["title"])
    body = data.get("body", note["body"])

    with get_db().cursor() as cur:
        cur.execute(
            """
            UPDATE notes SET title = %s, body = %s, updated_at = now()
            WHERE note_id = %s AND org_id = %s
            """,
            (title, body, note_id, ctx.org_id),
        )

    log.info(
        f"Note updated via API: note_id={note_id[:8]}... org_id={ctx.org_id[:8]}..."
    )
    return jsonify({"ok": True})


@bp.delete("/<note_id>")
@authenticated(org=True)
def delete_note(ctx: OrgContext, note_id: str):
    """Delete a note (requires owner permission and API key admin scope)."""
    authz = get_authz(ctx.org_id)

    # Check permission using layered authorization (delete requires admin scope)
    if not check_permission("delete", ("note", note_id)):
        return jsonify({"error": "no delete access to this note"}), 403

    # Also need owner permission on the user side
    if not authz.check(("user", ctx.user_id), "owner", ("note", note_id)):
        return jsonify({"error": "only owner can delete"}), 403

    note = get_note_by_id(note_id, ctx.org_id)
    if not note:
        return jsonify({"error": "not found"}), 404

    # Revoke all permissions
    for permission in ["owner", "edit", "view"]:
        users = [
            s[1]
            for s in authz.list_subjects(permission, ("note", note_id))
            if s[0] == "user"
        ]
        for uid in users:
            authz.revoke(permission, resource=("note", note_id), subject=("user", uid))

    with get_db().cursor() as cur:
        cur.execute(
            "DELETE FROM notes WHERE note_id = %s AND org_id = %s",
            (note_id, ctx.org_id),
        )

    log.info(
        f"Note deleted via API: note_id={note_id[:8]}... org_id={ctx.org_id[:8]}..."
    )
    return jsonify({"ok": True})
