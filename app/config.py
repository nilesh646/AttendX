import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:

    # =====================================================
    # BASIC FLASK CONFIGURATION
    # =====================================================

    SECRET_KEY = os.getenv(
        "SECRET_KEY",
        "change-this-secret-key"
    )

    DEBUG = False

    TESTING = False

    ENV = os.getenv(
        "FLASK_ENV",
        "production"
    )

    # =====================================================
    # PROJECT PATHS
    # =====================================================

    BASE_DIR = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            ".."
        )
    )

    DATA_ROOT = os.getenv(
        "DATA_ROOT",
        os.path.join(BASE_DIR, "runtime_data")
    )

    MEDIA_ROOT = os.path.join(
        DATA_ROOT,
        "media"
    )

    MODEL_ROOT = os.path.join(
        DATA_ROOT,
        "models"
    )

    LOG_ROOT = os.path.join(
        DATA_ROOT,
        "logs"
    )

    # =====================================================
    # DATABASE
    # =====================================================

    DATABASE_PATH = os.getenv(
        "DATABASE_PATH",
        os.path.join(
            DATA_ROOT,
            "attendance.db"
        )
    )

    DATABASE_URI = f"sqlite:///{DATABASE_PATH}"

    # DATABASE_URL = os.getenv("DATABASE_URL")

    # if DATABASE_URL:
    #     SQLALCHEMY_DATABASE_URI = DATABASE_URL
    # else:
    #     SQLALCHEMY_DATABASE_URI = (
    #         f"sqlite:///{DATABASE_PATH}"
    #     )

    # SQLALCHEMY_TRACK_MODIFICATIONS = False

    # =====================================================
    # MEDIA
    # =====================================================

    MASTER_PHOTO_FOLDER = os.path.join(
        MEDIA_ROOT,
        "master"
    )

    SELFIE_FOLDER = os.path.join(
        MEDIA_ROOT,
        "selfies"
    )

    EMBEDDING_FOLDER = os.path.join(
        MEDIA_ROOT,
        "embeddings"
    )

    UPLOAD_FOLDER = SELFIE_FOLDER

    PHOTO_FOLDER = MASTER_PHOTO_FOLDER

    MAX_CONTENT_LENGTH = 5 * 1024 * 1024

    UPLOAD_EXTENSIONS = [
        ".jpg",
        ".jpeg",
        ".png"
    ]

    # =====================================================
    # EMAIL
    # =====================================================

    MAIL_SERVER = os.getenv(
        "MAIL_SERVER",
        "smtp.gmail.com"
    )

    MAIL_PORT = int(
        os.getenv(
            "MAIL_PORT",
            587
        )
    )

    MAIL_USE_TLS = True

    MAIL_USERNAME = os.getenv("MAIL_USERNAME")

    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    MAIL_DEFAULT_SENDER = os.getenv(
        "MAIL_DEFAULT_SENDER"
    )

    # =====================================================
    # OTP
    # =====================================================

    OTP_EXPIRY_SECONDS = int(
        os.getenv(
            "OTP_EXPIRY_SECONDS",
            300
        )
    )

    # =====================================================
    # SESSION
    # =====================================================

    SESSION_TIMEOUT_HOURS = int(
        os.getenv(
            "SESSION_TIMEOUT_HOURS",
            8
        )
    )

    PERMANENT_SESSION_LIFETIME = timedelta(
        hours=SESSION_TIMEOUT_HOURS
    )

    SESSION_COOKIE_HTTPONLY = True

    SESSION_COOKIE_SAMESITE = "Lax"

    SESSION_COOKIE_SECURE = True

    REMEMBER_COOKIE_SECURE = True

    REMEMBER_COOKIE_HTTPONLY = True

    SESSION_COOKIE_NAME = "attendx"

    # =====================================================
    # FACE RECOGNITION
    # =====================================================

    FACE_MATCH_THRESHOLD = float(
        os.getenv(
            "FACE_MATCH_THRESHOLD",
            0.55
        )
    )

    INSIGHTFACE_MODEL_ROOT = MODEL_ROOT

    INSIGHTFACE_MODEL_NAME = os.getenv(
        "INSIGHTFACE_MODEL_NAME",
        "buffalo_l"
    )

    LIVENESS_MODEL_DIR = os.path.join(
        BASE_DIR,
        "resources",
        "anti_spoof_models"
    )

    # =====================================================
    # SOCKET.IO
    # =====================================================

    SOCKETIO_ASYNC_MODE = "threading"

    # =====================================================
    # GEOLOCATION
    # =====================================================

    GEO_ENABLED = os.getenv(
        "GEO_ENABLED",
        "False"
    ).lower() == "true"

    GEO_CAMPUS_LAT = float(
        os.getenv(
            "GEO_CAMPUS_LAT",
            0
        )
    )

    GEO_CAMPUS_LNG = float(
        os.getenv(
            "GEO_CAMPUS_LNG",
            0
        )
    )

    GEO_RADIUS_METERS = int(
        os.getenv(
            "GEO_RADIUS_METERS",
            500
        )
    )

    # =====================================================
    # ADMIN
    # =====================================================

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

    # =====================================================
    # LOGGING
    # =====================================================

    LOG_LEVEL = os.getenv(
        "LOG_LEVEL",
        "INFO"
    )

    JSON_SORT_KEYS = False

    SEND_FILE_MAX_AGE_DEFAULT = 0

    TEMPLATES_AUTO_RELOAD = False

    PREFERRED_URL_SCHEME = "https"