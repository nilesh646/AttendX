"""
AttendX
Production Entry Point
Compatible with:
- Render
- Gunicorn
- Flask-SocketIO
"""

import logging
import os
import sys
import traceback

from flask_cors import CORS

from app import create_app, socketio

# --------------------------------------------------------
# Logging
# --------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------
# Global Exception Handler
# --------------------------------------------------------

def handle_exception(exc_type, exc_value, exc_traceback):

    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(
            exc_type,
            exc_value,
            exc_traceback
        )
        return

    logger.exception(
        "Uncaught Exception",
        exc_info=(
            exc_type,
            exc_value,
            exc_traceback
        )
    )

sys.excepthook = handle_exception

# --------------------------------------------------------
# Create Flask App
# --------------------------------------------------------

app = create_app()

# --------------------------------------------------------
# Enable CORS
# --------------------------------------------------------

CORS(
    app,
    supports_credentials=True,
    origins="*"
)

# --------------------------------------------------------
# Health Check
# --------------------------------------------------------

@app.route("/health")
def health():

    return {
        "status": "ok",
        "service": "AttendX"
    }, 200

# --------------------------------------------------------
# Startup Information
# --------------------------------------------------------

PORT = int(os.environ.get("PORT", 5000))

logger.info("-------------------------------------")
logger.info("AttendX Starting")
logger.info("Port : %s", PORT)
logger.info("Environment : %s", os.getenv("FLASK_ENV", "production"))
logger.info("-------------------------------------")

# --------------------------------------------------------
# Local Development
# --------------------------------------------------------

if __name__ == "__main__":

    socketio.run(
        app,
        host="0.0.0.0",
        port=PORT,
        debug=False,
        use_reloader=False,
        allow_unsafe_werkzeug=True
    )