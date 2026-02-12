"""Flask application factory for Safe Family project."""

from datetime import timedelta

from flask import Flask, jsonify

from config.logging import setup_logging
from config.settings import settings
from src.safe_family.api.routes import api_bp
from src.safe_family.auto_git.auto_git import auto_git_bp
from src.safe_family.core.auth import auth_bp
from src.safe_family.core.extensions import db, jwt, mail
from src.safe_family.core.models import User
from src.safe_family.rules.scheduler import schedule_rules_bp
from src.safe_family.todo.goals import goals_bp
from src.safe_family.todo.todo import todo_bp
from src.safe_family.urls.analyzer import analyze_bp
from src.safe_family.urls.blocker import rules_toggle_bp
from src.safe_family.urls.miscellaneous import root_bp
from src.safe_family.urls.notes import notes_bp
from src.safe_family.urls.receiver import receiver_bp
from src.safe_family.urls.suspicious import suspicious_bp
from src.safe_family.users.users import user_bp


def create_app():
    """Create and configure the Flask application."""
    app = Flask(__name__)
    setup_logging()  # Initialize logging configuration
    app.config["FLASK_DEBUG"] = settings.FLASK_DEBUG
    app.config["SQLALCHEMY_DATABASE_URI"] = settings.SQLALCHEMY_DATABASE_URI
    app.config["SQLALCHEMY_ECHO"] = settings.SQLALCHEMY_ECHO
    app.config["SECRET_KEY"] = settings.APP_SECRET_KEY
    app.config["JWT_SECRET_KEY"] = settings.JWT_SECRET_KEY
    app.config["JWT_ACCESS_TOKEN_EXPIRES"] = timedelta(
        hours=settings.JWT_ACCESS_TOKEN_EXPIRES,
    )
    app.config["MAX_CONTENT_LENGTH"] = settings.NOTESYNC_MAX_REQUEST_BYTES

    app.config["MAIL_SERVER"] = settings.MAIL_SERVER
    app.config["MAIL_PORT"] = settings.MAIL_PORT
    app.config["MAIL_USE_TLS"] = settings.MAIL_USE_TLS
    app.config["MAIL_USERNAME"] = settings.MAIL_ACCOUNT
    app.config["MAIL_PASSWORD"] = settings.MAIL_PASSWORD
    app.config["MAIL_DEFAULT_SENDER"] = ("Todo System", settings.MAIL_ACCOUNT)

    db.init_app(app)
    jwt.init_app(app)
    mail.init_app(app)

    @app.context_processor
    def inject_motto():
        """Inject the app motto into all templates."""
        return {"motto": settings.APP_MOTTO}

    app.register_blueprint(root_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(receiver_bp)
    app.register_blueprint(analyze_bp)
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(auto_git_bp)
    # The issue was added to the bug tracker: rules_toggle rename to url_blocker
    app.register_blueprint(rules_toggle_bp)
    app.register_blueprint(schedule_rules_bp)
    app.register_blueprint(suspicious_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(user_bp, url_prefix="/users")
    app.register_blueprint(todo_bp)
    app.register_blueprint(goals_bp)

    # For debug
    # from flask import current_app

    # @app.after_request
    # def log_response_info(response):
    #     # Check if the response is JSON
    #     if response.content_type == "application/json":
    #         # Access the raw data and decode it to log the content
    #         current_app.logger.info(
    #             f"Response Body: {response.get_data(as_text=True)}",
    #         )
    #     return response

    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        return User.query.filter_by(id=identity).one_or_none()

    @jwt.additional_claims_loader
    def add_claims_to_access_token(identity):
        if identity == settings.ADMIN_IDENTITY:
            return {"is_admin": "admin"}
        return {"is_admin": "user"}

    @jwt.expired_token_loader
    def my_expired_token_callback(jwt_header, jwt_payload):
        return jsonify({"msg": "Token has expired", "error": "token_expired"}), 401

    @jwt.invalid_token_loader
    def my_invalid_token_callback(error):
        return jsonify({"msg": "Invalid token", "error": "invalid_token"}), 401

    @jwt.unauthorized_loader
    def my_unauthorized_callback(error):
        return jsonify({"msg": "Missing token", "error": "authorization_required"}), 401

    # The issue was added to the bug tracker: token_in_blocklist_loader or whitelist
    # def check_if_token_revoked(jwt_header, jwt_payload):
    #     pass
    return app
