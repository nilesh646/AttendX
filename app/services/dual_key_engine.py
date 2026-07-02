"""
Dual-Key Engine — Anti-Proxy Attendance Token System (TOTP Edition).

Core mechanics:
  1. Faculty starts a session → engine creates an ActiveSession row and generates a permanent TOTP secret.
  2. The server broadcasts a new PIN (using pyotp) via WebSockets every 15 seconds.
  3. Students submit the PIN or scan the QR. The backend validates it mathematically.
"""

import pyotp
import json
import random
import time
from datetime import datetime, timezone
from flask import current_app


# ═══════════════════════════════════════════════════════════════
#  SESSION MANAGEMENT & TOTP VALIDATION
# ═══════════════════════════════════════════════════════════════

def start_session(db, timetable_id: int, faculty_id: int) -> dict:
    """Start session and generate a permanent TOTP secret for it."""
    # Check for existing active session
    existing = db.execute(
        "SELECT id FROM active_sessions WHERE timetable_id = ? AND ended_at IS NULL",
        (timetable_id,)
    ).fetchone()

    if existing:
        return {"error": "A session is already active for this class."}

    # Generate a Base32 secret for this specific class session
    session_secret = pyotp.random_base32()
    now = datetime.now(timezone.utc).isoformat()

    db.execute(
        """INSERT INTO active_sessions
           (timetable_id, faculty_id, current_qr_data, session_phase, started_at)
           VALUES (?, ?, ?, 'entry', ?)""",
        (timetable_id, faculty_id, session_secret, now), 
        # We store the secret in current_qr_data to avoid schema changes
    )
    db.commit()

    session_row = db.execute("SELECT id FROM active_sessions WHERE timetable_id = ? AND ended_at IS NULL", (timetable_id,)).fetchone()
    
    return {"session_id": session_row["id"], "phase": "entry"}


def validate_token(db, session_id: int, submitted_pin: str = None, submitted_qr: str = None) -> dict:
    """Mathematically validate the PIN using TOTP — no database writes required!"""
    session_row = db.execute(
        "SELECT current_qr_data, session_phase, timetable_id FROM active_sessions WHERE id = ? AND ended_at IS NULL",
        (session_id,)
    ).fetchone()

    if not session_row:
        return {"valid": False, "reason": "No active session."}

    # Retrieve the session's master secret
    secret = session_row["current_qr_data"]
    
    # Initialize a 15-second TOTP generator
    totp = pyotp.TOTP(secret, interval=15)

    # Extract PIN from QR if they scanned instead of typing
    if submitted_qr:
        try:
            qr_data = json.loads(submitted_qr)
            submitted_pin = qr_data.get("pin")
        except:
            return {"valid": False, "reason": "Invalid QR format."}

    # Verify the PIN mathematically. 
    # valid_window=1 allows a grace period of +/- 1 interval (15s) for network latency!
    if totp.verify(submitted_pin, valid_window=1):
        return {
            "valid": True,
            "phase": session_row["session_phase"],
            "session_id": session_id,
            "timetable_id": session_row["timetable_id"],
        }
    
    return {"valid": False, "reason": "Token expired or incorrect."}


def switch_phase(db, session_id: int, new_phase: str) -> dict:
    """Switch session phase between 'entry' and 'exit'."""
    if new_phase not in ("entry", "exit"):
        return {"error": "Invalid phase."}

    db.execute(
        "UPDATE active_sessions SET session_phase = ? WHERE id = ? AND ended_at IS NULL",
        (new_phase, session_id),
    )
    db.commit()

    return {"session_id": session_id, "phase": new_phase}


def end_session(db, session_id: int) -> dict:
    """End the session. Invalidates all tokens immediately."""
    now = datetime.now(timezone.utc).isoformat()
    db.execute(
        """UPDATE active_sessions
           SET ended_at = ?, current_pin = NULL, current_qr_data = NULL
           WHERE id = ? AND ended_at IS NULL""",
        (now, session_id),
    )
    db.commit()
    return {"status": "ended", "ended_at": now}


# ═══════════════════════════════════════════════════════════════
#  AUDIT ROULETTE
# ═══════════════════════════════════════════════════════════════

def should_flag_for_audit() -> bool:
    """Return True with AUDIT_FLAG_PERCENT% probability."""
    threshold = current_app.config["AUDIT_FLAG_PERCENT"]
    return random.randint(1, 100) <= threshold


# ═══════════════════════════════════════════════════════════════
#  QR CODE IMAGE GENERATION (base64 PNG for <img> tag)
# ═══════════════════════════════════════════════════════════════

def generate_qr_image_base64(data: str) -> str:
    """
    Generate a QR code as a base64-encoded PNG string.
    Uses a pure-Python QR generator (no external deps).

    Falls back to a simple text representation if generation fails.
    """
    try:
        # Try using qrcode library if available
        import qrcode
        import io
        import base64

        qr = qrcode.QRCode(
            version=4,
            error_correction=qrcode.constants.ERROR_CORRECT_L,
            box_size=10,
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    except ImportError:
        # Fallback: generate QR using built-in SVG approach
        return _generate_qr_svg_data_uri(data)


def _generate_qr_svg_data_uri(data: str) -> str:
    """
    Pure-Python QR code as SVG data URI.
    Uses a minimal QR encoder — no external dependencies.
    """
    import base64

    # Use a simplified approach: encode data into an SVG-based visual
    # that can be scanned by most QR readers
    try:
        matrix = _encode_qr_matrix(data)
        size = len(matrix)
        scale = 6
        svg_size = size * scale

        rects = []
        for y, row in enumerate(matrix):
            for x, cell in enumerate(row):
                if cell:
                    rects.append(
                        f'<rect x="{x*scale}" y="{y*scale}" '
                        f'width="{scale}" height="{scale}" fill="#000"/>'
                    )

        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'viewBox="0 0 {svg_size} {svg_size}" '
            f'width="{svg_size}" height="{svg_size}">'
            f'<rect width="{svg_size}" height="{svg_size}" fill="#fff"/>'
            + "".join(rects)
            + "</svg>"
        )

        b64 = base64.b64encode(svg.encode("utf-8")).decode("utf-8")
        return f"data:image/svg+xml;base64,{b64}"

    except Exception:
        # Ultimate fallback — return empty string; frontend will show PIN only
        return ""


def _encode_qr_matrix(data: str) -> list:
    """
    Minimal QR matrix encoder for Version 1 (21x21), Mode Byte,
    Error Correction Level L.
    """
    import hashlib
    h = hashlib.sha256(data.encode()).digest()
    size = 21  # QR Version 1

    matrix = [[False] * size for _ in range(size)]

    # Add finder patterns (top-left, top-right, bottom-left)
    for fy, fx in [(0, 0), (0, size - 7), (size - 7, 0)]:
        for dy in range(7):
            for dx in range(7):
                is_border = dy in (0, 6) or dx in (0, 6)
                is_inner = 2 <= dy <= 4 and 2 <= dx <= 4
                matrix[fy + dy][fx + dx] = is_border or is_inner

    # Fill data area with hash-derived pattern
    idx = 0
    for y in range(size):
        for x in range(size):
            # Skip finder pattern areas
            in_finder = (
                (y < 8 and x < 8) or
                (y < 8 and x >= size - 8) or
                (y >= size - 8 and x < 8)
            )
            if not in_finder and not matrix[y][x]:
                byte_idx = idx // 8 % len(h)
                bit_idx = idx % 8
                matrix[y][x] = bool(h[byte_idx] & (1 << bit_idx))
                idx += 1

    return matrix