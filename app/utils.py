import random
import string
import re
import html as html_lib
from datetime import datetime, timedelta, timezone
from functools import wraps

from werkzeug.security import generate_password_hash, check_password_hash as _check_pw
from flask import redirect, url_for, flash, abort, session, request, current_app


# ═══════════════════════════════════════════════════════════════
#  PASSWORD HASHING
# ═══════════════════════════════════════════════════════════════
def hash_password(plain: str) -> str:
    return generate_password_hash(plain)

def check_password(plain: str, hashed: str) -> bool:
    return _check_pw(hashed, plain)


# ═══════════════════════════════════════════════════════════════
#  OTP GENERATION
# ═══════════════════════════════════════════════════════════════
def generate_otp(length: int = 6) -> str:
    return "".join(random.choices(string.digits, k=length))

def otp_expiry(seconds: int = 300) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=seconds)


# ═══════════════════════════════════════════════════════════════
#  JOIN CODE GENERATION (alphanumeric, 6 chars, like Google Classroom)
# ═══════════════════════════════════════════════════════════════
def generate_join_code(length: int = 6) -> str:
    chars = string.ascii_uppercase + string.digits
    # Exclude confusing characters: 0/O, 1/I/L
    chars = chars.replace("O", "").replace("0", "").replace("I", "").replace("L", "").replace("1", "")
    return "".join(random.choices(chars, k=length))


# ═══════════════════════════════════════════════════════════════
#  ROLE-BASED ACCESS DECORATORS
# ═══════════════════════════════════════════════════════════════
def login_required_with_role(*allowed_roles):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in first.", "warning")
                return redirect(url_for("auth.login"))
            if session.get("user_role") not in allowed_roles:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return decorator


def get_current_user():
    if "user_id" in session:
        return {
            "id": session["user_id"],
            "role": session["user_role"],
            "name": session["user_name"],
            "email": session["user_email"],
        }
    return None


# ═══════════════════════════════════════════════════════════════
#  CSRF PROTECTION
# ═══════════════════════════════════════════════════════════════
def generate_csrf_token():
    if "_csrf_token" not in session:
        session["_csrf_token"] = "".join(random.choices(string.ascii_letters + string.digits, k=32))
    return session["_csrf_token"]


def validate_csrf():
    """Call at the top of POST handlers. Returns True if valid."""
    token = session.get("_csrf_token")
    submitted = request.form.get("_csrf_token") or request.headers.get("X-CSRF-Token")
    if not token or not submitted or token != submitted:
        return False
    return True


# ═══════════════════════════════════════════════════════════════
#  INPUT SANITIZATION
# ═══════════════════════════════════════════════════════════════
def sanitize(text: str) -> str:
    """Remove HTML tags and escape dangerous characters."""
    if not text:
        return ""
    text = text.strip()
    text = html_lib.escape(text)
    # Remove any remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    return text


# ═══════════════════════════════════════════════════════════════
#  RATE LIMITING
# ═══════════════════════════════════════════════════════════════
def check_rate_limit(db, user_id: int, action: str) -> bool:
    """Returns True if user is within rate limit, False if blocked."""
    max_attempts = current_app.config["RATE_LIMIT_PIN_ATTEMPTS"]
    window_secs = current_app.config["RATE_LIMIT_WINDOW_SECONDS"]
    cutoff = (datetime.now(timezone.utc) - timedelta(seconds=window_secs)).isoformat()

    row = db.execute(
        "SELECT COUNT(*) as c FROM rate_limits WHERE user_id=? AND action=? AND attempted_at > ?",
        (user_id, action, cutoff),
    ).fetchone()

    return row["c"] < max_attempts


def record_rate_limit(db, user_id: int, action: str):
    """Record an attempt for rate limiting."""
    db.execute(
        "INSERT INTO rate_limits (user_id, action, attempted_at) VALUES (?, ?, ?)",
        (user_id, action, datetime.now(timezone.utc).isoformat()),
    )
    db.commit()

    # Cleanup old entries (older than 1 hour)
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    db.execute("DELETE FROM rate_limits WHERE attempted_at < ?", (cutoff,))
    db.commit()


# ═══════════════════════════════════════════════════════════════
#  AUDIT LOGGING
# ═══════════════════════════════════════════════════════════════
def log_audit(db, action: str, target_type: str = None,
              target_id: int = None, details: str = None):
    """Log an action to the audit trail."""
    user_id = session.get("user_id", 0)
    user_role = session.get("user_role", "System")
    ip = request.remote_addr or "unknown"

    db.execute(
        """INSERT INTO audit_log (user_id, user_role, action, target_type, target_id, details, ip_address)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (user_id, user_role, action, target_type, target_id, details, ip),
    )
    db.commit()


# ═══════════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════
def create_notification(db, user_id: int, title: str, message: str, link: str = None):
    db.execute(
        "INSERT INTO notifications (user_id, title, message, link) VALUES (?, ?, ?, ?)",
        (user_id, title, message, link),
    )
    db.commit()


def get_unread_count(db, user_id: int) -> int:
    row = db.execute(
        "SELECT COUNT(*) as c FROM notifications WHERE user_id=? AND is_read=0",
        (user_id,),
    ).fetchone()
    return row["c"]


# ═══════════════════════════════════════════════════════════════
#  MISC HELPERS
# ═══════════════════════════════════════════════════════════════
def allowed_image(filename: str) -> bool:
    allowed = {"png", "jpg", "jpeg", "webp"}
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed

def today_day_name() -> str:
    return datetime.now().strftime("%A")



import base64
import cv2
import numpy as np

def base64_to_cv2(b64_string):
    """Converts a web-captured Base64 image to an OpenCV BGR array."""
    if "," in b64_string:
        b64_string = b64_string.split(",")[1]
    img_data = base64.b64decode(b64_string)
    nparr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img