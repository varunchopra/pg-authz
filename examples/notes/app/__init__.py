import logging
import uuid

from flask import Flask, g, jsonify, request

from . import db
from .config import Config
from .routes import api_bp, views_bp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger(__name__)

# Track whether plans have been seeded this process
_plans_seeded = False


def seed_plans():
    """Seed default plans if they don't exist (idempotent)."""
    global _plans_seeded
    if _plans_seeded:
        return

    try:
        config = db.get_system_config()

        # Only seed if free plan doesn't exist
        if not config.exists("plans/free"):
            config.set(
                "plans/free",
                {
                    "name": "Free",
                    "seats": 3,
                    "seat_price": 0,
                    "storage_rate": 0.00001,  # $0.01 per 1000 chars
                },
            )
            config.set(
                "plans/pro",
                {
                    "name": "Pro",
                    "seats": 25,
                    "seat_price": 10,  # $10/seat/month
                    "storage_rate": 0.000005,  # $0.005 per 1000 chars
                },
            )
            config.set(
                "plans/enterprise",
                {
                    "name": "Enterprise",
                    "seats": -1,  # Unlimited
                    "seat_price": None,  # Custom pricing
                    "storage_rate": None,  # Custom pricing
                },
            )
            log.info("Default plans seeded")

        _plans_seeded = True
    except Exception as e:
        # Don't fail startup if seeding fails (e.g., DB not ready yet)
        log.warning(f"Could not seed plans: {e}")


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
        # Seed plans on first request (idempotent)
        seed_plans()

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
