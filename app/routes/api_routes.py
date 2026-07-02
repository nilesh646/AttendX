"""
API Routes v2 — JSON endpoints with rate limiting, late marking,
                geolocation check, device fingerprinting.
"""
import json
import base64
import os
from unittest import result
import cv2
import concurrent.futures
from datetime import datetime, date, time, timezone
from app.services.dual_key_engine import generate_qr_image_base64
import pyotp
import json
import time

# --- NEW: Create a dedicated background worker for heavy AI tasks ---
# This prevents the AI from freezing your WebSockets!
ai_executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

from flask import Blueprint, request, jsonify, session, current_app

from app.models import get_db
from app.services.dual_key_engine import (
    start_session, end_session, switch_phase, 
    validate_token, should_flag_for_audit
)
from app.utils import (
    check_rate_limit, record_rate_limit, log_audit, create_notification,
)

api_bp = Blueprint("api", __name__, url_prefix="/api")


def _require_auth(*roles):
    if "user_id" not in session:
        return {"error": "Not authenticated."}, 401
    if roles and session.get("user_role") not in roles:
        return {"error": "Forbidden."}, 403
    return None


def _check_late(timetable_id, db):
    """Check if current time is past start_time + LATE_THRESHOLD_MINUTES."""
    slot = db.execute("SELECT start_time FROM timetables WHERE id = ?", (timetable_id,)).fetchone()
    if not slot:
        return False
    try:
        start = datetime.strptime(slot["start_time"], "%H:%M").time()
        threshold = current_app.config.get("LATE_THRESHOLD_MINUTES", 10)
        now_time = datetime.now().time()
        start_dt = datetime.combine(date.today(), start)
        late_dt = start_dt + __import__("datetime").timedelta(minutes=threshold)
        return now_time > late_dt.time()
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════
#  SESSION MANAGEMENT
# ═══════════════════════════════════════════════════════════════
@api_bp.route("/session/start", methods=["POST"])
def api_start_session():
    err = _require_auth("Faculty")
    if err:
        return jsonify(err[0]), err[1]

    data = request.get_json(silent=True) or {}
    timetable_id = data.get("timetable_id")
    teacher_lat = data.get("teacher_lat") # NEW: Catch latitude
    teacher_lng = data.get("teacher_lng") # NEW: Catch longitude

    # 🔥 NEW: Terminal output for debugging so you can see it working!
    print("\n" + "="*40)
    print("📍 SESSION START INITIATED")
    if teacher_lat and teacher_lng:
        print(f"Teacher Latitude:  {teacher_lat}")
        print(f"Teacher Longitude: {teacher_lng}")
    else:
        print("⚠️ WARNING: No teacher location received!")
    print("="*40 + "\n")

    if not timetable_id:
        return jsonify({"error": "timetable_id is required."}), 400

    db = get_db()

    slot = db.execute(
        "SELECT * FROM timetables WHERE id = ? AND faculty_id = ?",
        (timetable_id, session["user_id"])
    ).fetchone()

    if not slot:
        return jsonify({"error": "Timetable slot not found or not yours."}), 404

    # Start session
    result = start_session(db, timetable_id, session["user_id"])

    if "error" in result:
        return jsonify(result), 409

    session_id = result["session_id"]

    # 🔥 NEW: Save the teacher's live coordinates to the newly created session
    if teacher_lat and teacher_lng:
        db.execute(
            "UPDATE active_sessions SET teacher_lat=?, teacher_lng=? WHERE id=?", 
            (teacher_lat, teacher_lng, session_id)
        )
        db.commit()

    # Fetch session data
    sess = db.execute(
        "SELECT current_qr_data, session_phase FROM active_sessions WHERE id = ?",
        (session_id,)
    ).fetchone()

    if not sess:
        return jsonify({"error": "Session creation failed."}), 500

    secret = sess["current_qr_data"]

    import pyotp
    import json
    import time
    from app.services.dual_key_engine import generate_qr_image_base64

    # Generate FIRST QR immediately
    totp = pyotp.TOTP(secret, interval=15)
    current_pin = totp.now()

    qr_payload = json.dumps({
        "sid": session_id,
        "pin": current_pin,
        "ts": time.time()
    })

    qr_img_base64 = generate_qr_image_base64(qr_payload)

    log_audit(db, "session_started", "timetable", timetable_id)

    return jsonify({
        "session_id": session_id,
        "phase": sess["session_phase"],
        "qr_image": qr_img_base64
    }), 201


@api_bp.route("/session/<int:session_id>/location", methods=["POST"])
def api_update_session_location(session_id):
    err = _require_auth("Faculty")
    if err:
        return jsonify(err[0]), err[1]

    data = request.get_json(silent=True) or {}
    teacher_lat = data.get("teacher_lat")
    teacher_lng = data.get("teacher_lng")

    if teacher_lat and teacher_lng:
        db = get_db()
        db.execute(
            "UPDATE active_sessions SET teacher_lat=?, teacher_lng=? WHERE id=? AND faculty_id=?",
            (teacher_lat, teacher_lng, session_id, session["user_id"])
        )

        db.execute("UPDATE active_sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?", (session_id,))
    
        # 👇 PASTE THIS LINE HERE 👇
        db.execute("DELETE FROM device_locks WHERE session_id = ?", (session_id,))
        db.commit()

        # 🔥 Terminal output on REFRESH
        print("\n" + "="*40)
        print("📍 SESSION LOCATION UPDATED (REFRESH)")
        print(f"Session ID:        {session_id}")
        print(f"Teacher Latitude:  {teacher_lat}")
        print(f"Teacher Longitude: {teacher_lng}")
        print("="*40 + "\n")

        return jsonify({"status": "ok"}), 200

    return jsonify({"error": "No coordinates provided."}), 400

@api_bp.route("/session/end", methods=["POST"])
def api_end_session():
    print("\n" + "🔴"*20)
    print(">>> API: END SESSION TRIGGERED <<<")
    err = _require_auth("Faculty")
    if err: return jsonify(err[0]), err[1]
    
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    print(f"Ending Session ID: {session_id}")
    
    if not session_id:
        return jsonify({"error": "session_id is required."}), 400
        
    db = get_db()
    sess = db.execute("SELECT id FROM active_sessions WHERE id = ? AND faculty_id = ?",
                      (session_id, session["user_id"])).fetchone()
    if not sess:
        print("ERROR: Session not found!")
        return jsonify({"error": "Session not found."}), 404
        
    db.execute("""
        UPDATE active_sessions 
        SET ended_at = CURRENT_TIMESTAMP 
        WHERE id = ?
    """, (session_id,))
    
    db.execute("DELETE FROM device_locks WHERE session_id = ?", (session_id,))
    db.commit()
    
    print(f"✅ SUCCESS: Session {session_id} ended. DB updated.")
    print("🔴"*20 + "\n")
    return jsonify({"success": True, "message": "Session ended and phones unlocked."}), 200


@api_bp.route("/session/switch-phase", methods=["POST"])
def api_switch_phase():
    err = _require_auth("Faculty")
    if err: return jsonify(err[0]), err[1]
    data = request.get_json(silent=True) or {}
    session_id = data.get("session_id")
    new_phase = data.get("phase")
    if not session_id or not new_phase:
        return jsonify({"error": "session_id and phase are required."}), 400
    db = get_db()
    sess = db.execute("SELECT * FROM active_sessions WHERE id = ? AND faculty_id = ?",
                      (session_id, session["user_id"])).fetchone()
    if not sess:
        return jsonify({"error": "Session not found."}), 404
        
    result = switch_phase(db, session_id, new_phase)
    if "error" in result:
        return jsonify(result), 400
        
    # NOTE: QR generation removed here as well!
    return jsonify(result), 200


from app import socketio
import pyotp
import json
import time

# Client joins their specific classroom's WebSocket room
@socketio.on('join_session')
def handle_join_session(data):
    from flask_socketio import join_room
    session_id = data.get('session_id')
    join_room(f"session_{session_id}")

# Background task to push synchronized tokens every 15 seconds
def broadcast_tokens(app):
    while True:
        socketio.sleep(6)
        with app.app_context():
            db = get_db()
            active_sessions = db.execute(
                "SELECT id, current_qr_data, session_phase FROM active_sessions WHERE ended_at IS NULL"
            ).fetchall()
            
            for sess in active_sessions:
                try:
                    secret = sess["current_qr_data"]
                    from app.services.dual_key_engine import generate_qr_image_base64
                    
                    totp = pyotp.TOTP(secret, interval=15)
                    current_pin = totp.now()
                    
                    # Replacement: ts is now time.time() float
                    qr_payload = json.dumps({
                        "sid": sess["id"], 
                        "pin": current_pin, 
                        "ts": time.time() 
                    })
                    
                    qr_img_base64 = generate_qr_image_base64(qr_payload)
                    
                    socketio.emit('token_update', {
                        "pin": current_pin,
                        "qr_image": qr_img_base64,
                        "phase": sess["session_phase"]
                    }, to=f"session_{sess['id']}")
                    
                except Exception as e:
                    print(f"Broadcast error: {e}")
                    continue


# ═══════════════════════════════════════════════════════════════
#  TOKEN VALIDATION (with rate limiting + late marking + geo)
# ═══════════════════════════════════════════════════════════════
@api_bp.route("/session/<int:session_id>/validate", methods=["POST"])
def api_validate_token(session_id):
    err = _require_auth("Student")
    if err: return jsonify(err[0]), err[1]

    student_id = session["user_id"]
    db = get_db()

    data = request.get_json(silent=True) or {}


    device_info = data.get("device_info")


    print("\n" + "="*45)
    print(f"📡 INCOMING CHECK-IN REQUEST")
    print(f"Student ID: {student_id}")
    print(f"Device ID:  {device_info}")
    print("="*45 + "\n")

    # ── Rate limiting ──
    if not check_rate_limit(db, student_id, "pin_validate"):
        return jsonify({"valid": False, "reason": "Too many attempts. Please wait 60 seconds."}), 429
    
    is_blocked, lock_reason = check_device_lock(db, student_id, device_info, session_id)
    if is_blocked:
        print(f"❌ BLOCKED: {lock_reason}")
        return jsonify({"valid": False, "reason": lock_reason}), 403

    data = request.get_json(silent=True) or {}
    submitted_pin = data.get("pin")
    submitted_qr = data.get("qr_data")
    geo_lat = data.get("geo_lat")
    geo_lng = data.get("geo_lng")
    geo_accuracy = data.get("geo_accuracy")
    geo_distance = data.get("geo_distance")
    geo_trust_score = data.get("geo_trust_score")
    geo_trust_level = data.get("geo_trust_level")
    device_info = data.get("device_info")

    if not submitted_pin and not submitted_qr:
        return jsonify({"error": "Submit a PIN or QR code."}), 400

    record_rate_limit(db, student_id, "pin_validate")

    if submitted_qr:
        try:
            qr_obj = json.loads(submitted_qr)
            qr_ts = qr_obj.get("ts", 0)

            latency = time.time() - float(qr_ts)

            if latency > 5:
                return jsonify({
                    "valid": False,
                    "reason": "QR Expired. Scan the live screen."
                }), 403

            if latency < 0.7:
                return jsonify({
                    "valid": False,
                    "reason": "Invalid scan timing."
                }), 403

        except (json.JSONDecodeError, TypeError, ValueError):
            pass

    result = validate_token(db, session_id, submitted_pin, submitted_qr)

    if not result.get("valid"):
        return jsonify(result), 400

    # ── Token valid — record attendance ──
    timetable_id = result["timetable_id"]
    phase = result["phase"]
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()

    # Batch check
    slot = db.execute("SELECT batch_id FROM timetables WHERE id = ?", (timetable_id,)).fetchone()
    student = db.execute("SELECT batch_id FROM users WHERE id = ?", (student_id,)).fetchone()
    if slot and student and slot["batch_id"] != student["batch_id"]:
        return jsonify({"valid": False, "reason": "You are not enrolled in this class."}), 403

    # ── Classroom-level geolocation trust scoring (DYNAMIC) ──
    geo_verdict = "no_data"  
    flagged = should_flag_for_audit()
    geo_config = current_app.config

    if geo_config.get("GEO_ENABLED"):
        # 🔥 NEW: Pull the Teacher's live coordinates for this specific session
        session_loc = db.execute("""
            SELECT teacher_lat, teacher_lng, allowed_radius 
            FROM active_sessions 
            WHERE id = ?
        """, (session_id,)).fetchone()

        if session_loc and session_loc["teacher_lat"] and session_loc["teacher_lng"]:
            lat1 = float(session_loc["teacher_lat"])
            lng1 = float(session_loc["teacher_lng"])
            allowed_radius = int(session_loc["allowed_radius"] or 50)
            
            if geo_lat and geo_lng:
                import math
                lat2, lng2 = float(geo_lat), float(geo_lng)
                R = 6371000
                dlat = math.radians(lat2 - lat1)
                dlng = math.radians(lng2 - lng1)
                a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
                distance = R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
                geo_distance = int(distance)

                acc = float(geo_accuracy or 50)

                ip_addr = request.environ.get('HTTP_X_FORWARDED_FOR', request.remote_addr)
                if ip_addr and ',' in ip_addr: ip_addr = ip_addr.split(',')[0].strip() # Handle Ngrok/Proxy
                
                try:
                    ip_res = requests.get(f"http://ip-api.com/json/{ip_addr}?fields=status,lat,lon", timeout=1.5).json()
                    if ip_res.get('status') == 'success':
                        # Calculate distance between IP location and claimed GPS location
                        # IP geolocation is accurate to city level (~20-50km)
                        dlat_ip = math.radians(ip_res['lat'] - lat2)
                        dlng_ip = math.radians(ip_res['lon'] - lng2)
                        a_ip = math.sin(dlat_ip/2)**2 + math.cos(math.radians(lat2)) * math.cos(math.radians(ip_res['lat'])) * math.sin(dlng_ip/2)**2
                        dist_ip_gps = (R/1000) * 2 * math.atan2(math.sqrt(a_ip), math.sqrt(1 - a_ip)) # in KM
                        
                        if dist_ip_gps > 60: # If IP city is > 60km away from GPS room
                            print(f"🚨 ALERT: IP Location mismatch! IP City is {int(dist_ip_gps)}km away from GPS.")
                            flagged = True # Send to faculty review automatically
                except: pass

                # 🔥 NEW: Terminal output for Student Check-in
                print("\n" + "="*45)
                print("🧑‍🎓 STUDENT CHECK-IN ATTEMPT")
                print(f"Teacher Location: {lat1:.6f}, {lng1:.6f}")
                print(f"Student Location: {lat2:.6f}, {lng2:.6f}")
                print(f"Calculated Dist:  {geo_distance} meters")
                print(f"Allowed Radius:   {allowed_radius} meters")
                print(f"GPS Accuracy:     {acc} meters")
                
                # Verify against dynamic radius
                if distance <= allowed_radius:
                    geo_trust_score = 100 if distance <= 15 else (70 if distance <= 25 else 40)
                    geo_verdict = "strong" if distance <= 15 else ("moderate" if distance <= 25 else "weak")
                    print(f"Verdict:          ✅ PASS ({geo_verdict.upper()})")
                else:
                    print(f"Verdict:          ❌ BLOCKED (Out of bounds)")
                    print("="*45 + "\n")
                    return jsonify({
                        "valid": False,
                        "reason": f"Server Lock: You are {geo_distance}m away. You must be within {allowed_radius}m of the teacher.",
                        "geo_verdict": "reject",
                    }), 403

                # Accuracy penalty
                if acc > 30:
                    penalty = min((acc - 30) * 0.5, 40)
                    geo_trust_score = max(int(geo_trust_score - penalty), 5)
                    print(f"Note: Applied penalty for low GPS accuracy.")
                
                print("="*45 + "\n")
            else:
                geo_verdict = "denied"
                geo_trust_score = 0
        else:
            # Fallback if no teacher location is set
            geo_verdict = "no_data"
            geo_trust_score = 0

    if phase == "entry":
        existing = db.execute(
            "SELECT id, entry_time FROM attendance WHERE timetable_id=? AND student_id=? AND date=?",
            (timetable_id, student_id, today)).fetchone()

        if existing and existing["entry_time"]:
            return jsonify({"valid": True, "already_marked": True, "message": "Entry already recorded."}), 200

        is_late = _check_late(timetable_id, db)
        status = "Late" if is_late else "Present"
        flagged = should_flag_for_audit()

        if geo_verdict in ("denied", "weak"):
            flagged = True

        # 🔥 THE ANTI-FARMING TRAP
        farming_check = db.execute(
            "SELECT id FROM attendance WHERE timetable_id=? AND device_info=? AND student_id!=? AND date=?",
            (timetable_id, device_info, student_id, today)
        ).fetchone()

        if farming_check:
            flagged = True  # Silently force them into the Faculty Review queue

        # Store the validated data in the secure session
        session[f"pending_entry_{timetable_id}"] = {
            "entry_time": now,
            "status": status,
            "flagged": int(flagged),
            "device_info": device_info,
            "geo_lat": geo_lat,
            "geo_lng": geo_lng,
            "geo_accuracy": geo_accuracy,
            "geo_distance": geo_distance,
            "geo_trust_score": geo_trust_score,
            "geo_verdict": geo_verdict
        }

        enforce_device_lock(db, student_id, device_info, session_id)
        print("🔒 HARDWARE LOCKED: Student and Device are now permanently tied for this session.")

        resp = {
            "valid": True, "phase": "entry",
            "message": f"{'Late entry' if is_late else 'Entry'} recorded. Selfie required.",
            "needs_selfie": True, "flagged_for_audit": flagged, "status": status,
        }
        if geo_verdict != "no_data":
            resp["geo_verdict"] = geo_verdict
            resp["geo_trust_score"] = geo_trust_score
        return jsonify(resp), 200

    elif phase == "exit":
        existing = db.execute(
            "SELECT id FROM attendance WHERE timetable_id=? AND student_id=? AND date=?",
            (timetable_id, student_id, today)).fetchone()
        if not existing:
            return jsonify({"valid": False, "reason": "No entry record found. Mark entry first."}), 400
        db.execute("UPDATE attendance SET exit_time = ? WHERE id = ?", (now, existing["id"]))
        db.commit()
        return jsonify({"valid": True, "phase": "exit", "message": "Exit recorded. You may leave.", "needs_selfie": False}), 200

    return jsonify({"valid": False, "reason": "Unknown phase."}), 400


# ═══════════════════════════════════════════════════════════════
#  SELFIE UPLOAD (with face match scoring + username-based storage)
# ═══════════════════════════════════════════════════════════════

def process_face_async(master_path, selfie_path):
    """Heavy AI logic moved to a background thread to prevent server freeze."""
    from app.services.biometric_engine import BiometricEngine
    engine = BiometricEngine.get_instance()
    
    img_master = cv2.imread(master_path)
    img_selfie = cv2.imread(selfie_path)
    
    # Gate 1: Liveness Check
    liveness = engine.check_liveness(img_selfie)
    if not liveness.get("is_real", False):
        return {"face_found": True, "match": False, "trust_score": 0, "details": liveness.get("reason", "Spoof detected.")}
    
    # Gate 2: Identity Extraction
    emb_master = engine.get_embedding(img_master)
    emb_selfie = engine.get_embedding(img_selfie)
    
    if emb_master is None or emb_selfie is None:
        return {"face_found": False, "match": False, "trust_score": 0, "details": "Could not extract face features."}
        
    # Gate 3: Similarity Scoring
    sim = engine.compare_embeddings(emb_master, emb_selfie)
    trust_score = int(max(0, sim) * 100)
    match = True if trust_score > 45 else False
    
    return {
        "face_found": True,
        "match": match,
        "trust_score": trust_score,
        "details": "Identity verified." if match else "Identity mismatch."
    }


@api_bp.route("/session/<int:session_id>/selfie", methods=["POST"])
def api_upload_selfie(session_id):
    err = _require_auth("Student")
    if err: return jsonify(err[0]), err[1]
    student_id = session["user_id"]
    today = date.today().isoformat()
    db = get_db()

    sess = db.execute("SELECT timetable_id, faculty_id FROM active_sessions WHERE id = ?", (session_id,)).fetchone()
    if not sess:
        return jsonify({"error": "Session not found."}), 404

    timetable_id = sess["timetable_id"]
    
    # Retrieve the pending ticket
    pending = session.get(f"pending_entry_{timetable_id}")
    if not pending:
        return jsonify({"error": "Validation expired or missing. Please scan the QR code again."}), 400

    data = request.get_json(silent=True) or {}
    selfie_b64 = data.get("selfie_data")
    if not selfie_b64:
        return jsonify({"error": "No selfie data received."}), 400

    student = db.execute("SELECT name, email, profile_photo FROM users WHERE id = ?", (student_id,)).fetchone()
    if not student:
        return jsonify({"error": "Student record not found."}), 404

    import base64, os
    from app.services.biometric_engine import get_safe_username, get_selfie_path

    safe_name = get_safe_username(student["email"], student["name"])
    selfie_path = get_selfie_path(safe_name, today, session_id)
    
    if "," in selfie_b64:
        selfie_b64 = selfie_b64.split(",", 1)[1]
        
    # 🔥 FIX: Ensure the string is mathematically padded before decoding.
    # Missing padding will corrupt the jpeg file and cause the AI to fail.
    selfie_b64 += "=" * ((4 - len(selfie_b64) % 4) % 4)
    
    with open(selfie_path, "wb") as f:
        f.write(base64.b64decode(selfie_b64))

    rel_path = os.path.relpath(selfie_path, os.path.join(current_app.root_path, "static")).replace("\\", "/")

    # ── Offloaded ML Face Comparison ──
    face_result = {"face_found": False, "match": False, "trust_score": 0, "details": "No master photo available."}
    
    if student["profile_photo"]:
        master_path = os.path.join(current_app.root_path, "static", student["profile_photo"])
        if os.path.exists(master_path) and os.path.exists(selfie_path):
            # --- NEW: Send the heavy work to the background thread! ---
            future = ai_executor.submit(process_face_async, master_path, selfie_path)
            face_result = future.result()

    if not face_result.get("face_found"):
        if os.path.exists(selfie_path): os.remove(selfie_path)
        return jsonify({"error": face_result.get("details", "No face detected. Start over.")}), 400

    trust_score = face_result.get("trust_score", 0)

    # 🚨 3-TIER LOGIC & DB WRITE
    if trust_score < 55:
        # Hard Reject: Do not write to DB at all. Let them try again or be absent.
        if os.path.exists(selfie_path): os.remove(selfie_path)
        return jsonify({
            "status": "ok", "status_code": "rejected", 
            "message": "Face match failed. Attendance rejected.",
            "face_trust_score": trust_score
        }), 200

    # Pass or Review: Now we write to the database
    final_status = pending["status"]
    final_flag = 1 if (55 <= trust_score <= 80) else pending["flagged"]
    status_code = "review" if (55 <= trust_score <= 80) else "success"
    final_msg = "Partial match. Sent for review." if status_code == "review" else "Selfie verified successfully."

    # Insert the official record
    db.execute(
        """INSERT INTO attendance (timetable_id, student_id, date, entry_time, status, verification_method, 
           flagged_for_audit, selfie_filepath, device_info, geo_lat, geo_lng, geo_accuracy, geo_distance, geo_trust_score, geo_verdict)
           VALUES (?, ?, ?, ?, ?, 'Dual-Key', ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (timetable_id, student_id, today, pending["entry_time"], final_status, final_flag, rel_path, 
         pending["device_info"], pending["geo_lat"], pending["geo_lng"], pending["geo_accuracy"], 
         pending["geo_distance"], pending["geo_trust_score"], pending["geo_verdict"])
    )
    db.commit()

    # Destroy the ticket so they can't submit twice
    session.pop(f"pending_entry_{timetable_id}", None)

    # Notify Faculty
    student_name = session.get("user_name", "A student")
    create_notification(db, sess["faculty_id"], "Student Checked In", f"{student_name} marked {final_status.lower()} entry.", None)

    return jsonify({
        "status": "ok",
        "message": final_msg,
        "status_code": status_code,
        "face_match": True,
        "face_trust_score": trust_score,
        "face_details": face_result.get("details", ""),
    }), 200


# ═══════════════════════════════════════════════════════════════
#  LIVE ROSTER
# ═══════════════════════════════════════════════════════════════
@api_bp.route("/session/<int:session_id>/roster", methods=["GET"])
def api_get_roster(session_id):
    err = _require_auth("Faculty")
    if err: return jsonify(err[0]), err[1]
    db = get_db()
    sess = db.execute("SELECT * FROM active_sessions WHERE id = ?", (session_id,)).fetchone()
    if not sess:
        return jsonify({"error": "Session not found."}), 404
    today = date.today().isoformat()
    timetable_id = sess["timetable_id"]
    roster = db.execute("""
        SELECT u.id, u.name, u.email, u.profile_photo,
               a.entry_time, a.exit_time, a.status, a.selfie_filepath,
               a.verification_method, a.flagged_for_audit
        FROM users u JOIN timetables t ON u.batch_id = t.batch_id
        LEFT JOIN attendance a ON a.student_id = u.id AND a.timetable_id = ? AND a.date = ?
        WHERE t.id = ? AND u.role = 'Student' ORDER BY u.name
    """, (timetable_id, today, timetable_id)).fetchall()
    students = []
    present_count = 0
    for r in roster:
        # 🚨 FIX: Only count actual presents, lates, and pending reviews
        if r["status"] in ("Present", "Late") or r["flagged_for_audit"]:
            present_count += 1
            
        students.append({
            "id": r["id"], "name": r["name"], "email": r["email"],
            "photo": r["profile_photo"],
            "entry_time": r["entry_time"], "exit_time": r["exit_time"],
            "status": r["status"] or "Absent",
            "selfie": r["selfie_filepath"],
            "method": r["verification_method"] or "-",
            "flagged": bool(r["flagged_for_audit"]),
        })
    return jsonify({"phase": sess["session_phase"], "total": len(students),
                    "present": present_count, "students": students}), 200


# ═══════════════════════════════════════════════════════════════
#  MANUAL OVERRIDE
# ═══════════════════════════════════════════════════════════════
@api_bp.route("/session/<int:session_id>/override", methods=["POST"])
def api_manual_override(session_id):
    err = _require_auth("Faculty")
    if err: return jsonify(err[0]), err[1]
    data = request.get_json(silent=True) or {}
    student_id = data.get("student_id")
    if not student_id:
        return jsonify({"error": "student_id is required."}), 400
    db = get_db()
    sess = db.execute("SELECT * FROM active_sessions WHERE id = ? AND faculty_id = ?",
                      (session_id, session["user_id"])).fetchone()
    if not sess:
        return jsonify({"error": "Session not found or not yours."}), 404
    today = date.today().isoformat()
    now = datetime.now(timezone.utc).isoformat()
    timetable_id = sess["timetable_id"]
    existing = db.execute(
        "SELECT id FROM attendance WHERE timetable_id=? AND student_id=? AND date=?",
        (timetable_id, student_id, today)).fetchone()
    if existing:
        db.execute("UPDATE attendance SET entry_time=?, status='Present', verification_method='Faculty_Override' WHERE id=?",
                   (now, existing["id"]))
    else:
        db.execute(
            """INSERT INTO attendance (timetable_id, student_id, date, entry_time, status, verification_method, flagged_for_audit)
               VALUES (?, ?, ?, ?, 'Present', 'Faculty_Override', 0)""",
            (timetable_id, student_id, today, now))
    db.commit()
    student = db.execute("SELECT name FROM users WHERE id=?", (student_id,)).fetchone()
    name = student["name"] if student else f"Student #{student_id}"
    log_audit(db, "manual_override", "attendance", None, f"{name} marked present by faculty")
    return jsonify({"status": "ok", "message": f"{name} marked present via override."}), 200


# ═══════════════════════════════════════════════════════════════
#  NOTIFICATIONS API
# ═══════════════════════════════════════════════════════════════
@api_bp.route("/notifications/count", methods=["GET"])
def api_notification_count():
    if "user_id" not in session:
        return jsonify({"count": 0}), 200
    db = get_db()
    from app.utils import get_unread_count
    return jsonify({"count": get_unread_count(db, session["user_id"])}), 200


def check_device_lock(db, student_id, device_info, session_id):
    """Checks if a device is being shared or if a student is swapping phones."""
    
    # 1. Did another student already use this exact phone for this class?
    device_used_by_other = db.execute(
        "SELECT student_id FROM device_locks WHERE session_id = ? AND device_info = ?",
        (session_id, device_info)
    ).fetchone()
    
    if device_used_by_other and str(device_used_by_other["student_id"]) != str(student_id):
        return True, "Security Alert: This device has already been used by another student."
        
    # 2. Did THIS student already use a DIFFERENT phone for this class?
    student_used_other_device = db.execute(
        "SELECT device_info FROM device_locks WHERE session_id = ? AND student_id = ?",
        (session_id, student_id)
    ).fetchone()
    
    if student_used_other_device and student_used_other_device["device_info"] != device_info:
        return True, "Security Alert: You cannot switch devices during an active class."
        
    return False, ""

def enforce_device_lock(db, student_id, device_info, session_id):
    """Locks the device to the student after a successful scan."""
    existing = db.execute(
        "SELECT id FROM device_locks WHERE session_id = ? AND student_id = ?", 
        (session_id, student_id)
    ).fetchone()
    
    if not existing:
        db.execute(
            "INSERT INTO device_locks (session_id, student_id, device_info) VALUES (?, ?, ?)",
            (session_id, student_id, device_info)
        )
        # Note: We don't need db.commit() here because the main route commits at the very end