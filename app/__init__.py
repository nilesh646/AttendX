"""
AttendX Application Factory
Production Ready
"""

import logging
import os

from flask import Flask, jsonify, redirect, request, url_for
from flask_socketio import SocketIO

from app.config import Config
from app.models import init_db, seed_admin

# ---------------------------------------------------------
# Socket.IO
# ---------------------------------------------------------

socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False
)

# ---------------------------------------------------------
# Logger
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Create App
# ---------------------------------------------------------

def create_app(config_class=Config):

    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates"
    )

    app.config.from_object(config_class)

    create_runtime_directories(app)

    init_database(app)

    register_routes(app)

    initialize_socketio(app)

    # preload_ai_models()

    register_context_processors(app)

    register_error_handlers(app)

    start_background_tasks(app)

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    return app


# ---------------------------------------------------------
# Runtime Directories
# ---------------------------------------------------------

def create_runtime_directories(app):

    folders = [

        os.path.dirname(app.config["DATABASE_PATH"]),

        app.config["MASTER_PHOTO_FOLDER"],

        app.config["SELFIE_FOLDER"],

        app.config["UPLOAD_FOLDER"],

        app.config["EMBEDDING_FOLDER"],

        app.config["INSIGHTFACE_MODEL_ROOT"]

    ]

    for folder in folders:
        os.makedirs(folder, exist_ok=True)

    logger.info("Runtime directories verified.")


# ---------------------------------------------------------
# Database
# ---------------------------------------------------------

def init_database(app):

    init_db(app)

    seed_admin(app)

    with app.app_context():

        from app.models import get_db
        from app.utils import generate_join_code

        db = get_db()

        batches = db.execute(
            """
            SELECT id
            FROM batches
            WHERE join_code IS NULL
            """
        ).fetchall()

        updated = False

        for batch in batches:

            db.execute(
                """
                UPDATE batches
                SET join_code=?
                WHERE id=?
                """,
                (
                    generate_join_code(),
                    batch["id"]
                )
            )

            updated = True

        if updated:
            db.commit()

    logger.info("Database initialized.")


# ---------------------------------------------------------
# Blueprints
# ---------------------------------------------------------

def register_routes(app):

    from app.routes import register_blueprints

    register_blueprints(app)

    logger.info("Blueprints registered.")


# ---------------------------------------------------------
# SocketIO
# ---------------------------------------------------------

def initialize_socketio(app):

    socketio.init_app(app)

    logger.info("SocketIO initialized.")


# ---------------------------------------------------------
# AI Loader
# ---------------------------------------------------------

# def preload_ai_models():

#     try:

#         if os.environ.get("SKIP_AI_PRELOAD", "false").lower() == "true":

#             logger.info("AI preload skipped.")

#             return

#         from app.services.biometric_engine import BiometricEngine

#         BiometricEngine.get_instance()

#         logger.info("AI models loaded successfully.")

#     except Exception as e:

#         logger.exception("AI preload failed: %s", e)


# ---------------------------------------------------------
# Context Processor
# ---------------------------------------------------------

def register_context_processors(app):

    @app.context_processor
    def inject_globals():

        from datetime import datetime

        from app.models import get_db

        from app.utils import (

            generate_csrf_token,

            get_current_user,

            get_unread_count

        )

        user = get_current_user()

        notifications = 0

        if user:

            try:

                notifications = get_unread_count(
                    get_db(),
                    user["id"]
                )

            except Exception:

                notifications = 0

        return {

            "current_user": user,

            "csrf_token": generate_csrf_token,

            "notification_count": notifications,

            "today_date": datetime.now().strftime("%Y-%m-%d"),

            "now_hour": datetime.now().hour

        }


# ---------------------------------------------------------
# Error Handlers
# ---------------------------------------------------------

def register_error_handlers(app):

    @app.errorhandler(401)
    def unauthorized(error):

        if request.path.startswith("/api/"):

            return jsonify(
                error="Authentication required."
            ), 401

        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def forbidden(error):

        if request.path.startswith("/api/"):

            return jsonify(
                error="Forbidden."
            ), 403

        return "Forbidden", 403

    @app.errorhandler(404)
    def not_found(error):

        if request.path.startswith("/api/"):

            return jsonify(
                error="Not Found."
            ), 404

        return "Not Found", 404

    @app.errorhandler(500)
    def internal(error):

        if request.path.startswith("/api/"):

            return jsonify(
                error="Internal Server Error."
            ), 500

        return "Internal Server Error", 500


# ---------------------------------------------------------
# Background Tasks
# ---------------------------------------------------------

def start_background_tasks(app):

    try:

        from app.routes.api_routes import broadcast_tokens

        socketio.start_background_task(

            target=broadcast_tokens,

            app=app

        )

        logger.info("Background task started.")

    except Exception as e:

        logger.exception("Unable to start background task: %s", e)