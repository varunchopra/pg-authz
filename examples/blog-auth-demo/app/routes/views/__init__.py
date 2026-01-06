"""View routes - HTML pages for browser UI."""

from flask import Blueprint

from . import auth, dashboard

views_bp = Blueprint("views", __name__)
views_bp.register_blueprint(auth.bp)
views_bp.register_blueprint(dashboard.bp)

__all__ = ["views_bp"]
