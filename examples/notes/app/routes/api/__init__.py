"""API routes - all prefixed with /api."""

from flask import Blueprint

from . import api_keys, health, notes, sso, users

api_bp = Blueprint("api", __name__, url_prefix="/api")
api_bp.register_blueprint(health.bp)
api_bp.register_blueprint(users.bp)
api_bp.register_blueprint(sso.bp)
api_bp.register_blueprint(api_keys.bp)
api_bp.register_blueprint(notes.bp)

__all__ = ["api_bp"]
