import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Production-ready configuration for AttendX"""

    # ==================================================
    # Flask
    # ==================================================
    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "fallback-dev-key-change-me"
    )

    FLASK_ENV = os.getenv(
        "FLASK_ENV",
        "production"
    )

    DEBUG = False

    # ==================================================
    # Environment Detection
    # ==================================================
    RENDER = os.getenv("RENDER", "false").lower() == "true"

    BASE_DIR = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            ".."
        )
    )

    DATA_ROOT = (
        "/var/data"
        if RENDER
        else BASE_DIR
    )

    MEDIA_ROOT = os.getenv(
        "MEDIA_ROOT",
        os.path.join(DATA_ROOT, "media")
    )

    # ==================================================
    # Database
    # ==================================================
    DATABASE_PATH = os.getenv(
        "DATABASE_PATH",
        os.path.join(DATA_ROOT, "attendance.db")
    )

    # ==================================================
    # Email
    # ==================================================
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", 587))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "True").lower() == "true"
    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER")

    # ==================================================
    # OTP
    # ==================================================
    OTP_EXPIRY_SECONDS = int(
        os.getenv("OTP_EXPIRY_SECONDS", 300)
    )

    # ==================================================
    # Dual Key Engine
    # ==================================================
    TOKEN_REFRESH_SECONDS = int(
        os.getenv("TOKEN_REFRESH_SECONDS", 15)
    )

    # ==================================================
    # Audit
    # ==================================================
    AUDIT_FLAG_PERCENT = int(
        os.getenv("AUDIT_FLAG_PERCENT", 5)
    )

    # ==================================================
    # Session
    # ==================================================
    SESSION_TIMEOUT_HOURS = int(
        os.getenv("SESSION_TIMEOUT_HOURS", 8)
    )

    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=SESSION_TIMEOUT_HOURS
    )

    RATE_LIMIT_PIN_ATTEMPTS = int(
        os.getenv("RATE_LIMIT_PIN_ATTEMPTS", 5)
    )

    RATE_LIMIT_WINDOW_SECONDS = int(
        os.getenv("RATE_LIMIT_WINDOW_SECONDS", 60)
    )

    LATE_THRESHOLD_MINUTES = int(
        os.getenv("LATE_THRESHOLD_MINUTES", 10)
    )

    # ==================================================
    # Seed Admin
    # ==================================================
    ADMIN_NAME = os.getenv(
        "ADMIN_NAME",
        "System Admin"
    )

    ADMIN_EMAIL = os.getenv(
        "ADMIN_EMAIL",
        "admin@attendance.local"
    )

    ADMIN_PASSWORD = os.getenv(
        "ADMIN_PASSWORD",
        "admin123"
    )

    # ==================================================
    # Daily Digest
    # ==================================================
    DIGEST_HOUR = int(
        os.getenv("DIGEST_HOUR", 8)
    )

    DIGEST_MINUTE = int(
        os.getenv("DIGEST_MINUTE", 0)
    )

    # ==================================================
    # Geolocation
    # ==================================================
    GEO_ENABLED = os.getenv(
        "GEO_ENABLED",
        "False"
    ).lower() == "true"

    GEO_CAMPUS_LAT = float(
        os.getenv("GEO_CAMPUS_LAT", 0.0)
    )

    GEO_CAMPUS_LNG = float(
        os.getenv("GEO_CAMPUS_LNG", 0.0)
    )

    GEO_RADIUS_METERS = int(
        os.getenv("GEO_RADIUS_METERS", 500)
    )

    # ==================================================
    # Media Storage
    # ==================================================
    MEDIA_FOLDER = MEDIA_ROOT

    MASTER_PHOTO_FOLDER = os.path.join(
        MEDIA_FOLDER,
        "master"
    )

    SELFIE_FOLDER = os.path.join(
        MEDIA_FOLDER,
        "selfies"
    )

    EMBEDDING_FOLDER = os.path.join(
        MEDIA_FOLDER,
        "embeddings"
    )

    UPLOAD_FOLDER = SELFIE_FOLDER

    PHOTO_FOLDER = MASTER_PHOTO_FOLDER

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    # ==================================================
    # Face Recognition
    # ==================================================
    FACE_MATCH_THRESHOLD = float(
        os.getenv("FACE_MATCH_THRESHOLD", 0.55)
    )

    INSIGHTFACE_MODEL_ROOT = os.getenv(
        "INSIGHTFACE_MODEL_ROOT",
        os.path.join(DATA_ROOT, "models")
    )

    INSIGHTFACE_MODEL_NAME = os.getenv(
        "INSIGHTFACE_MODEL_NAME",
        "buffalo_l"
    )

    LIVENESS_MODEL_DIR = os.getenv(
        "LIVENESS_MODEL_DIR",
        os.path.join(DATA_ROOT, "anti_spoof_models")
    )

    # ==================================================
    # Socket.IO
    # ==================================================
    SOCKETIO_ASYNC_MODE = os.getenv(
        "SOCKETIO_ASYNC_MODE",
        "eventlet"
    )

    # ==================================================
    # Logging
    # ==================================================
    LOG_LEVEL = os.getenv(
        "LOG_LEVEL",
        "INFO"
    )

    # ==================================================
    # Production Flags
    # ==================================================
    PREFERRED_URL_SCHEME = "https"

    SESSION_COOKIE_SECURE = RENDER

    REMEMBER_COOKIE_SECURE = RENDER

    SESSION_COOKIE_HTTPONLY = True

    SESSION_COOKIE_SAMESITE = "Lax"