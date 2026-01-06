import logging

from flask import Blueprint, jsonify

from ...db import get_authn

bp = Blueprint("api_health", __name__)
log = logging.getLogger(__name__)


@bp.get("/health")
def health():
    try:
        stats = get_authn().get_stats()
        return jsonify(
            {
                "status": "healthy",
                "database": "connected",
                "authn_schema": "ok",
                "users": stats.get("user_count", 0),
            }
        )
    except Exception:
        log.exception("Health check failed")
        return jsonify({"status": "unhealthy", "database": "disconnected"}), 503
