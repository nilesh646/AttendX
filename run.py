"""
Entry point for the Attendance Portal.

Usage (from project root, inside venv):
    python run.py

Access:
    Local:   http://127.0.0.1:5000
    Network: http://<your-ip>:5000  (any device on same WiFi)
"""

import socket
import sys
import traceback

from app import create_app
from flask_cors import CORS
from app import socketio


# --------------------------------------------------
# Global exception handler (prevents silent exits)
# --------------------------------------------------

def handle_exception(exc_type, exc_value, exc_traceback):
    print("\nUNCAUGHT EXCEPTION:")
    traceback.print_exception(exc_type, exc_value, exc_traceback)


sys.excepthook = handle_exception


# --------------------------------------------------
# Create app
# --------------------------------------------------

app = create_app()


# --------------------------------------------------
# FORCE disable debug and reloader everywhere
# --------------------------------------------------

app.debug = False
app.config["DEBUG"] = False
app.config["ENV"] = "production"
app.config["USE_RELOADER"] = False


# --------------------------------------------------
# Enable CORS
# --------------------------------------------------

CORS(
    app,
    supports_credentials=True,
    origins=[
        "http://127.0.0.1:5000",
        "http://localhost:5000"
    ]
)


# --------------------------------------------------
# Start server
# --------------------------------------------------

if __name__ == "__main__":

    # Detect local IP for LAN access
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        local_ip = s.getsockname()[0]
        s.close()

    except Exception:
        local_ip = "127.0.0.1"

    print("\n" + "=" * 50)
    print("  AttendX Server Running!")
    print("  Local:   http://127.0.0.1:5000")
    print(f"  Network: http://{local_ip}:5000")
    print("  (Share the Network URL with devices on same WiFi)")
    print("=" * 50 + "\n")

    print("DEBUG STATUS:", app.debug)

    try:

        socketio.run(
            app,
            host="0.0.0.0",
            port=5000,
            debug=False,
            use_reloader=False,
            allow_unsafe_werkzeug=True,
            log_output=True
        )

    except Exception as e:

        print("\nServer failed to start:", e)

        traceback.print_exc()