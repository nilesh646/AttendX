"""
Entry point for AttendX.
"""

import os
import sys
import traceback

from flask_cors import CORS

from app import create_app, socketio


# ---------------------------------------------------
# Global exception handler
# ---------------------------------------------------

def handle_exception(exc_type, exc_value, exc_traceback):
    print("\nUNCAUGHT EXCEPTION:")
    traceback.print_exception(exc_type, exc_value, exc_traceback)


sys.excepthook = handle_exception


# ---------------------------------------------------
# Create Flask App
# ---------------------------------------------------

app = create_app()


# ---------------------------------------------------
# Production Configuration
# ---------------------------------------------------

app.config["DEBUG"] = False
app.config["ENV"] = "production"


# ---------------------------------------------------
# CORS
# ---------------------------------------------------

CORS(
    app,
    supports_credentials=True,
    origins="*"
)


# ---------------------------------------------------
# Render Entry Point
# ---------------------------------------------------

if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )