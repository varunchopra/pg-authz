import logging

from flask import Blueprint, jsonify, request
from pydantic import ValidationError

from ...auth import create_token, get_current_user, require_auth
from ...db import get_authn
from ...schemas import ApiKeyRequest

bp = Blueprint("api_api_keys", __name__, url_prefix="/api-keys")
log = logging.getLogger(__name__)


@bp.post("")
@require_auth
def create():
    try:
        data = ApiKeyRequest.model_validate(request.json or {})
    except ValidationError as e:
        return jsonify(
            {"error": "validation failed", "details": e.errors(include_context=False)}
        ), 400

    raw_key, key_hash = create_token()
    key_id = get_authn().create_api_key(
        user_id=get_current_user(),
        key_hash=key_hash,
        name=data.name.strip(),
    )

    log.info(f"API key created: key_id={key_id}")
    return jsonify({"key": raw_key, "key_id": key_id}), 201


@bp.get("")
@require_auth
def list_keys():
    keys = get_authn().list_api_keys(get_current_user())
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
                }
                for k in keys
            ]
        }
    )


@bp.delete("/<key_id>")
@require_auth
def revoke(key_id: str):
    user_id = get_current_user()
    authn = get_authn()

    # Verify ownership before revoking
    keys = authn.list_api_keys(user_id)
    if not any(k["key_id"] == key_id for k in keys):
        return jsonify({"error": "not found"}), 404

    authn.revoke_api_key(key_id)
    log.info(f"API key revoked: key_id={key_id}")
    return jsonify({"ok": True})
