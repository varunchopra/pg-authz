"""View routes - HTML pages for browser UI."""

from flask import Blueprint

from . import auth, dashboard, notes, orgs, teams

views_bp = Blueprint("views", __name__)
views_bp.register_blueprint(auth.bp)
views_bp.register_blueprint(dashboard.bp)
views_bp.register_blueprint(notes.bp)
views_bp.register_blueprint(orgs.bp)
views_bp.register_blueprint(teams.bp)

__all__ = ["views_bp"]
