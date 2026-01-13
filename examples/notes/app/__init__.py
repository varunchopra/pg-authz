import logging
import uuid

from flask import Flask, g, jsonify, request

from . import db
from .config import Config
from .routes import api_bp, views_bp
from .seed import seed_all

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)


def create_app():
    app = Flask(__name__)
    app.secret_key = Config.SECRET_KEY

    # Database lifecycle
    db.init_app(app)

    # Request context middleware (clear + bind pattern)
    @app.before_request
    def set_request_context():
        g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        authn = db.get_authn()
        authn.clear_actor()
        authn.set_actor(
            request_id=g.request_id,
            ip_address=request.remote_addr,
            user_agent=request.headers.get("User-Agent", "")[:1024],
        )
        # Seed schemas and default data on first request (idempotent)
        try:
            seed_all(db.get_system_config())
        except Exception as e:
            log.warning(f"Could not seed: {e}")

    @app.after_request
    def add_request_id_header(response):
        response.headers["X-Request-ID"] = g.get("request_id", "")
        return response

    # Blueprints
    app.register_blueprint(api_bp)  # /api/*
    app.register_blueprint(views_bp)  # /*

    # Template context processor for admin status and current org
    @app.context_processor
    def inject_context():
        from flask import session

        from .auth import get_org, get_session_user, get_user_orgs, is_org_admin

        user_id = get_session_user()
        org_id = session.get("current_org_id")

        current_org = None
        is_admin = False
        user_org_count = 0

        if user_id:
            user_org_count = len(get_user_orgs(user_id))

        if org_id:
            current_org = get_org(org_id)
            if user_id:
                is_admin = is_org_admin(user_id, org_id)

        return {
            "app_name": Config.APP_NAME,
            "is_admin": is_admin,
            "current_org": current_org,
            "user_org_count": user_org_count,
        }

    # Error handlers (for API - views will render templates)
    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "bad request"}), 400
        return "Bad Request", 400

    @app.errorhandler(401)
    def unauthorized(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "unauthorized"}), 401
        return "Unauthorized", 401

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "forbidden"}), 403
        return "Forbidden", 403

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "not found"}), 404
        return "Not Found", 404

    @app.errorhandler(422)
    def unprocessable(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "unprocessable entity"}), 422
        return "Unprocessable Entity", 422

    @app.errorhandler(429)
    def too_many_requests(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "too many requests"}), 429
        return "Too Many Requests", 429

    @app.errorhandler(500)
    def internal_error(e):
        log.exception("Internal server error")
        if request.path.startswith("/api/"):
            return jsonify({"error": "internal server error"}), 500
        return "Internal Server Error", 500

    @app.errorhandler(502)
    def bad_gateway(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": "bad gateway"}), 502
        return "Bad Gateway", 502

    return app
