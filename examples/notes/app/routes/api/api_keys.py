import logging
from datetime import timedelta

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from ...auth import (
    get_api_key_scopes,
    grant_api_key_scopes,
    revoke_all_api_key_grants,
)
from ...db import get_authn
from ...schemas import ApiKeyRequest
from ...security import OrgContext, authenticated, create_token

bp = Blueprint("api_api_keys", __name__, url_prefix="/api-keys")
log = logging.getLogger(__name__)


@bp.post("")
@authenticated(org=True)
def create(ctx: OrgContext):
    try:
        data = ApiKeyRequest.model_validate(request.json or {})
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 400

    raw_key, key_hash = create_token()
    key_id = get_authn().create_api_key(
        user_id=ctx.user_id,
        key_hash=key_hash,
        name=data.name.strip(),
        expires_in=timedelta(days=data.expires_in_days),
    )

    # Grant authz permissions for scopes
    grant_api_key_scopes(
        key_id,
        org_id=ctx.org_id,
        notes_access=data.scopes.notes.access,
        notes_level=data.scopes.notes.level,
        selected_note_ids=data.scopes.notes.selected_ids,
    )

    log.info(
        f"API key created: key_id={key_id[:8]}... scopes={data.scopes.model_dump()}"
    )
    return jsonify({"key": raw_key, "key_id": key_id}), 201


@bp.get("")
@authenticated(org=True)
def list_keys(ctx: OrgContext):
    keys = get_authn().list_api_keys(ctx.user_id)
    return jsonify(
        {
            "keys": [
                {
                    "id": k["key_id"],
                    "name": k.get("name"),
                    "created_at": k["created_at"].isoformat(),
                    "expires_at": k["expires_at"].isoformat()
                    if k.get("expires_at")
                    else None,
                    "last_used_at": k["last_used_at"].isoformat()
                    if k.get("last_used_at")
                    else None,
                    "scopes": get_api_key_scopes(k["key_id"], ctx.org_id),
                }
                for k in keys
            ]
        }
    )


@bp.delete("/<key_id>")
@authenticated(org=True)
def revoke(ctx: OrgContext, key_id: str):
    authn = get_authn()

    # Verify ownership before revoking
    keys = authn.list_api_keys(ctx.user_id)
    if not any(k["key_id"] == key_id for k in keys):
        return jsonify({"error": "not found"}), 404

    # Revoke all authz grants first
    revoke_all_api_key_grants(key_id, ctx.org_id)

    # Then revoke the key itself
    authn.revoke_api_key(key_id)
    log.info(f"API key revoked: key_id={key_id[:8]}...")
    return jsonify({"ok": True})
