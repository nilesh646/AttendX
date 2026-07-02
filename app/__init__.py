"""
AttendX v2 — Application Factory
All features: CSRF, session timeout, notifications, audit log,
              join codes, rate limiting, geolocation, exports.
"""

import os
from flask import Flask, redirect, url_for

# --- NEW: Import SocketIO ---
from flask_socketio import SocketIO

from app.config import Config
from app.models import init_db, seed_admin

# --- NEW: Initialize globally so routes can access it ---
socketio = SocketIO(
    cors_allowed_origins="*",
    async_mode="threading",
    logger=False,
    engineio_logger=False
)

def create_app(config_class=Config):
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.config.from_object(config_class)

    # ── Ensure media directories ──
    os.makedirs(app.config["MASTER_PHOTO_FOLDER"], exist_ok=True)
    os.makedirs(app.config["SELFIE_FOLDER"], exist_ok=True)

    # ── Init DB ──
    init_db(app)
    seed_admin(app)

    # ── Generate join codes for batches that don't have one ──
    with app.app_context():
        from app.models import get_db
        from app.utils import generate_join_code
        db = get_db()
        batches = db.execute("SELECT id FROM batches WHERE join_code IS NULL").fetchall()
        for b in batches:
            code = generate_join_code()
            db.execute("UPDATE batches SET join_code=? WHERE id=?", (code, b["id"]))
        if batches:
            db.commit()

    # --- NEW: Initialize SocketIO with the app ---
    socketio.init_app(app)

    # ── Register blueprints ──
    from app.routes import register_blueprints
    register_blueprints(app)

    # ── Pre-Load AI Engine (NEW V3 FIX) ──
    with app.app_context():
        try:
            print("\n>>> ATTEMPTING TO LOAD AI MODELS IN V2...")
            from app.services.biometric_engine import BiometricEngine
            BiometricEngine.get_instance()
            print(">>> AI MODELS SUCCESSFULLY LOADED IN V2!\n")
        except Exception as e:
            print(f"\n>>> 🚨 FATAL AI LOAD ERROR: {e}\n")
            import traceback
            traceback.print_exc() # This will print the exact line causing the crash
    

    # ── Root redirect ──
    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    # ── Global template context ──
    @app.context_processor
    def inject_globals():
        from datetime import datetime
        from app.utils import get_current_user, generate_csrf_token, get_unread_count
        user = get_current_user()
        notif_count = 0
        if user:
            try:
                from app.models import get_db
                notif_count = get_unread_count(get_db(), user["id"])
            except Exception:
                pass
        return dict(
            current_user=user,
            now_hour=datetime.now().hour,
            today_date=datetime.now().strftime("%Y-%m-%d"),
            csrf_token=generate_csrf_token,
            notification_count=notif_count,
        )

    # ── JSON error handlers for /api/ routes ──
    from flask import jsonify, request as flask_request

    @app.errorhandler(401)
    def handle_401(e):
        if flask_request.path.startswith("/api/"):
            return jsonify({"error": "Not authenticated. Please log in."}), 401
        return redirect(url_for("auth.login"))

    @app.errorhandler(403)
    def handle_403(e):
        if flask_request.path.startswith("/api/"):
            return jsonify({"error": "Forbidden."}), 403
        return "Forbidden", 403

    @app.errorhandler(404)
    def handle_404(e):
        if flask_request.path.startswith("/api/"):
            return jsonify({"error": "Not found."}), 404
        return "Not found", 404

    @app.errorhandler(500)
    def handle_500(e):
        if flask_request.path.startswith("/api/"):
            return jsonify({"error": "Internal server error."}), 500
        return "Internal server error", 500

    from app.routes.api_routes import broadcast_tokens
    socketio.start_background_task(
    target=broadcast_tokens,
    app=app
)

    return app