"""
Auth Routes v2 — login, signup, OTP, password reset, change password, profile photo.
"""
from datetime import datetime, timezone
import os, base64

from flask import (
    render_template, request, redirect, url_for, flash, session, current_app, jsonify,
)
from app.routes import auth_bp
from app.models import get_db
from app.utils import (
    hash_password, check_password, generate_otp, otp_expiry,
    sanitize, log_audit,
)


def _set_session(user_row):
    session.clear()
    session["user_id"] = user_row["id"]
    session["user_role"] = user_row["role"]
    session["user_name"] = user_row["name"]
    session["user_email"] = user_row["email"]
    session.permanent = True


def _dashboard_for_role(role):
    return {
        "Admin": "admin.dashboard",
        "Faculty": "faculty.dashboard",
        "Student": "student.dashboard",
    }.get(role, "auth.login")


def _send_otp_email(email, otp_code, purpose):
    from app.services.email_service import DEV_MODE, send_otp_email
    if not DEV_MODE:
        send_otp_email(email, otp_code, purpose)
        return
    subject = "Your Verification Code" if purpose == "signup" else "Password Reset Code"
    print(f"\n{'='*50}")
    print(f"  EMAIL -> {email}")
    print(f"  Subject: {subject}")
    print(f"  OTP Code: {otp_code}")
    print(f"{'='*50}\n")


def _create_and_send_otp(user_id, email, purpose):
    db = get_db()
    code = generate_otp()
    expiry_secs = current_app.config["OTP_EXPIRY_SECONDS"]
    expires = otp_expiry(expiry_secs)
    db.execute(
        "UPDATE otp_tokens SET is_used = 1 WHERE user_id = ? AND purpose = ? AND is_used = 0",
        (user_id, purpose),
    )
    db.execute(
        "INSERT INTO otp_tokens (user_id, otp_code, purpose, expires_at) VALUES (?, ?, ?, ?)",
        (user_id, code, purpose, expires.isoformat()),
    )
    db.commit()
    _send_otp_email(email, code, purpose)
    return expiry_secs


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session:
        return redirect(url_for(_dashboard_for_role(session["user_role"])))
    if request.method == "POST":
        email = sanitize(request.form.get("email", "")).lower()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user is None or not check_password(password, user["password_hash"]):
            flash("Invalid email or password.", "danger")
            return render_template("auth/login.html")
        if not user["is_verified"]:
            _create_and_send_otp(user["id"], user["email"], "signup")
            flash("Account not verified. We sent a new code to your email.", "warning")
            return redirect(url_for("auth.verify_otp_page", email=user["email"], purpose="signup"))
        _set_session(user)
        log_audit(db, "login", "user", user["id"])
        flash(f"Welcome back, {user['name']}!", "success")
        return redirect(url_for(_dashboard_for_role(user["role"])))
    return render_template("auth/login.html")


@auth_bp.route("/signup", methods=["GET", "POST"])
def signup():
    if "user_id" in session:
        return redirect(url_for(_dashboard_for_role(session["user_role"])))

    if request.method == "POST":
        # Handle JSON (from camera enrollment flow)
        is_json = request.is_json
        if is_json:
            data = request.get_json()
            name = sanitize(data.get("name", ""))
            email = sanitize(data.get("email", "")).lower()
            password = data.get("password", "")
            confirm = data.get("confirm_password", "")
            master_photo = data.get("master_photo", "")
        else:
            name = sanitize(request.form.get("name", ""))
            email = sanitize(request.form.get("email", "")).lower()
            password = request.form.get("password", "")
            confirm = request.form.get("confirm_password", "")
            master_photo = ""

        errors = []
        if not name or len(name) < 2:
            errors.append("Name must be at least 2 characters.")
        if not email or "@" not in email:
            errors.append("Enter a valid email address.")
        if len(password) < 8:
            errors.append("Password must be at least 8 characters.")
        if password != confirm:
            errors.append("Passwords do not match.")
        if not master_photo:
            errors.append("Face enrollment photo is required.")

        db = get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            errors.append("An account with this email already exists.")

        # --- NEW: ANTI-SPOOFING VERIFICATION GATE ---
        # --- NEW: ANTI-SPOOFING VERIFICATION GATE (V3 Engine) ---
        if not errors and master_photo:
            from app.services.biometric_engine import BiometricEngine, decode_base64_image
            try:
                # Decode directly to memory (no temp file needed!)
                img_array = decode_base64_image(master_photo)
                engine = BiometricEngine.get_instance()
                liveness_result = engine.check_liveness(img_array)
                
                if not liveness_result.get("is_real", False):
                    errors.append(f"Security Alert: {liveness_result.get('reason', 'Spoof detected!')}")
            except Exception as e:
                errors.append(f"Photo processing error: {str(e)}")

        if errors:
            if is_json:
                return jsonify({"success": False, "error": errors[0]}), 400
            for e in errors:
                flash(e, "danger")
            return render_template("auth/signup.html")

        # --- VALIDATED: PROCEED TO PERMANENT SAVE & DB INSERT ---
        from app.services.biometric_engine import save_image_from_base64, get_safe_username, get_master_photo_path
        
        # Save the master photo permanently using v3 utilities
        user_slug = get_safe_username(email, name)
        master_dest = get_master_photo_path(user_slug)
        save_image_from_base64(master_photo, master_dest)

        # Create relative path for DB storage
        photo_rel_path = os.path.relpath(master_dest, os.path.join(current_app.root_path, "static")).replace("\\", "/")

        db.execute(
            "INSERT INTO users (role, name, email, password_hash, is_verified, profile_photo) VALUES ('Student', ?, ?, ?, 0, ?)",
            (name, email, hash_password(password), photo_rel_path),
        )
        db.commit()
        
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        
        # Import local helper to send OTP
        from app.routes.auth_routes import _send_otp_email
        otp_code = generate_otp()
        db.execute(
            "INSERT INTO otp_tokens (user_id, otp_code, purpose, expires_at) VALUES (?, ?, ?, ?)",
            (user["id"], otp_code, "signup", otp_expiry().isoformat())
        )
        db.commit()
        _send_otp_email(email, otp_code, "signup")

        if is_json:
            return jsonify({
                "success": True,
                "redirect": url_for("auth.verify_otp_page", email=email, purpose="signup"),
            })

        flash("Account created! Check your email for the verification code.", "success")
        return redirect(url_for("auth.verify_otp_page", email=email, purpose="signup"))

    return render_template("auth/signup.html")

@auth_bp.route("/verify-otp")
def verify_otp_page():
    email = request.args.get("email", "")
    purpose = request.args.get("purpose", "signup")
    if not email:
        return redirect(url_for("auth.login"))
    return render_template(
        "auth/verify_otp.html", email=email, purpose=purpose,
        expiry_seconds=current_app.config["OTP_EXPIRY_SECONDS"],
    )


@auth_bp.route("/verify-otp", methods=["POST"])
def verify_otp():
    email = sanitize(request.form.get("email", "")).lower()
    purpose = request.form.get("purpose", "signup")
    otp_code = request.form.get("otp_code", "").strip()
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        flash("Account not found.", "danger")
        return redirect(url_for("auth.login"))
    token = db.execute(
        "SELECT * FROM otp_tokens WHERE user_id = ? AND purpose = ? AND is_used = 0 ORDER BY created_at DESC LIMIT 1",
        (user["id"], purpose),
    ).fetchone()
    if not token:
        flash("No active verification code. Please request a new one.", "warning")
        return redirect(url_for("auth.verify_otp_page", email=email, purpose=purpose))
    expires_at = datetime.fromisoformat(token["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        db.execute("UPDATE otp_tokens SET is_used = 1 WHERE id = ?", (token["id"],))
        db.commit()
        flash("Code expired. Please request a new one.", "warning")
        return redirect(url_for("auth.verify_otp_page", email=email, purpose=purpose))
    if token["otp_code"] != otp_code:
        flash("Incorrect code. Please try again.", "danger")
        return redirect(url_for("auth.verify_otp_page", email=email, purpose=purpose))
    db.execute("UPDATE otp_tokens SET is_used = 1 WHERE id = ?", (token["id"],))
    if purpose == "signup":
        db.execute("UPDATE users SET is_verified = 1 WHERE id = ?", (user["id"],))
        db.commit()
        flash("Email verified! You can now log in.", "success")
        return redirect(url_for("auth.login"))
    elif purpose == "password_reset":
        db.commit()
        session["reset_email"] = email
        session["reset_verified"] = True
        return redirect(url_for("auth.reset_password_page"))
    db.commit()
    return redirect(url_for("auth.login"))


@auth_bp.route("/resend-otp")
def resend_otp():
    email = sanitize(request.args.get("email", "")).lower()
    purpose = request.args.get("purpose", "signup")
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        flash("Account not found.", "danger")
        return redirect(url_for("auth.login"))
    _create_and_send_otp(user["id"], email, purpose)
    flash("A new code has been sent to your email.", "info")
    return redirect(url_for("auth.verify_otp_page", email=email, purpose=purpose))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = sanitize(request.form.get("email", "")).lower()
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            _create_and_send_otp(user["id"], email, "password_reset")
        flash("If that email is registered, you'll receive a reset code shortly.", "info")
        return redirect(url_for("auth.verify_otp_page", email=email, purpose="password_reset"))
    return render_template("auth/forgot_password.html")


@auth_bp.route("/reset-password", methods=["GET"])
def reset_password_page():
    if not session.get("reset_verified"):
        flash("Please verify your identity first.", "warning")
        return redirect(url_for("auth.forgot_password"))
    return render_template("auth/reset_password.html", email=session.get("reset_email", ""), token="verified")


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    email = sanitize(request.form.get("email", "")).lower()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")
    if not session.get("reset_verified") or session.get("reset_email") != email:
        flash("Invalid reset session. Please start over.", "danger")
        return redirect(url_for("auth.forgot_password"))
    if len(password) < 8:
        flash("Password must be at least 8 characters.", "danger")
        return redirect(url_for("auth.reset_password_page"))
    if password != confirm:
        flash("Passwords do not match.", "danger")
        return redirect(url_for("auth.reset_password_page"))
    db = get_db()
    db.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hash_password(password), email))
    db.commit()
    session.pop("reset_email", None)
    session.pop("reset_verified", None)
    flash("Password updated! Please log in with your new password.", "success")
    return redirect(url_for("auth.login"))


# ═══════════════════════════════════════════════════════════════
#  CHANGE PASSWORD (from dashboard — all roles)
# ═══════════════════════════════════════════════════════════════
@auth_bp.route("/change-password", methods=["GET", "POST"])
def change_password():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    if request.method == "POST":
        current = request.form.get("current_password", "")
        new_pw = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        db = get_db()
        user = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()
        if not check_password(current, user["password_hash"]):
            flash("Current password is incorrect.", "danger")
            return render_template("auth/change_password.html")
        if len(new_pw) < 8:
            flash("New password must be at least 8 characters.", "danger")
            return render_template("auth/change_password.html")
        if new_pw != confirm:
            flash("New passwords do not match.", "danger")
            return render_template("auth/change_password.html")
        db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hash_password(new_pw), session["user_id"]))
        db.commit()
        log_audit(db, "password_changed", "user", session["user_id"])
        flash("Password changed successfully.", "success")
        return redirect(url_for(_dashboard_for_role(session["user_role"])))
    return render_template("auth/change_password.html")


# ═══════════════════════════════════════════════════════════════
#  PROFILE PHOTO UPLOAD
# ═══════════════════════════════════════════════════════════════
@auth_bp.route("/upload-photo", methods=["POST"])
def upload_photo():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    photo_data = request.form.get("photo_data", "")
    if not photo_data:
        flash("No photo received.", "danger")
        return redirect(url_for(_dashboard_for_role(session["user_role"])))
    photo_dir = current_app.config["PHOTO_FOLDER"]
    os.makedirs(photo_dir, exist_ok=True)
    filename = f"profile_{session['user_id']}.jpg"
    filepath = os.path.join(photo_dir, filename)
    if "," in photo_data:
        photo_data = photo_data.split(",", 1)[1]
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(photo_data))
    db = get_db()
    db.execute("UPDATE users SET profile_photo = ? WHERE id = ?",
               (f"uploads/photos/{filename}", session["user_id"]))
    db.commit()
    flash("Profile photo updated.", "success")
    return redirect(url_for(_dashboard_for_role(session["user_role"])))


# ═══════════════════════════════════════════════════════════════
#  NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════
@auth_bp.route("/notifications")
def notifications():
    if "user_id" not in session:
        return redirect(url_for("auth.login"))
    db = get_db()
    notifs = db.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC LIMIT 50",
        (session["user_id"],),
    ).fetchall()
    # Mark all as read
    db.execute("UPDATE notifications SET is_read = 1 WHERE user_id = ?", (session["user_id"],))
    db.commit()
    return render_template("auth/notifications.html", notifications=notifs)


@auth_bp.route("/logout")
def logout():
    name = session.get("user_name", "")
    session.clear()
    flash(f"Goodbye{', ' + name if name else ''}! You've been logged out.", "info")
    return redirect(url_for("auth.login"))
