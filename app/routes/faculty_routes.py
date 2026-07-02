"""
Faculty Routes v2 — dashboard, sessions, attendance + export, schedule requests.
"""
import csv
import io
from datetime import date


from flask import (
    render_template, request, redirect, url_for, flash, session, Response,
)
from app.routes import faculty_bp
from app.models import get_db
from app.utils import login_required_with_role, today_day_name, sanitize, log_audit


@faculty_bp.route("/dashboard")
@login_required_with_role("Faculty")
def dashboard():
    print("\n" + "🟢"*20)
    print(">>> UI: RENDERING DASHBOARD <<<")
    db = get_db()
    faculty_id = session["user_id"]
    today = today_day_name()
    today_date = date.today().isoformat()

    # 🔥 TIMEZONE FIX in Subquery: date(completed.ended_at, 'localtime') = date('now', 'localtime')
    today_classes = db.execute("""
        SELECT t.*, s.subject_name, s.subject_code, b.batch_name,
               (SELECT COUNT(*) FROM users u WHERE u.batch_id = t.batch_id AND u.role='Student') as student_count,
               asess.id as active_session_id, asess.session_phase,
               (SELECT 1 FROM active_sessions completed 
                WHERE completed.timetable_id = t.id 
                AND completed.ended_at IS NOT NULL
                AND date(completed.ended_at, 'localtime') = date('now', 'localtime')
                LIMIT 1) as completed_today
        FROM timetables t JOIN subjects s ON t.subject_id = s.id
        JOIN batches b ON t.batch_id = b.id
        LEFT JOIN active_sessions asess ON asess.timetable_id = t.id AND asess.ended_at IS NULL
        WHERE t.faculty_id = ? AND t.day_of_week = ? ORDER BY t.start_time
    """, (faculty_id, today)).fetchall()

    for cls in today_classes:
        print(f"Class: {cls['subject_name']} | Active ID: {cls['active_session_id']} | Completed Today: {bool(cls['completed_today'])}")
    print("🟢"*20 + "\n")

    today_stats = db.execute("""
        SELECT COUNT(CASE WHEN a.status IN ('Present','Late') THEN 1 END) as present,
               COUNT(CASE WHEN a.status = 'Absent' THEN 1 END) as absent,
               COUNT(CASE WHEN a.flagged_for_audit = 1 THEN 1 END) as flagged
        FROM attendance a JOIN timetables t ON a.timetable_id = t.id
        WHERE t.faculty_id = ? AND a.date = ?
    """, (faculty_id, today_date)).fetchone()

    pending = db.execute(
        "SELECT COUNT(*) as c FROM schedule_requests WHERE requested_by_faculty_id = ? AND admin_status = 'Pending'",
        (faculty_id,),
    ).fetchone()["c"]

    return render_template("faculty/dashboard.html", active_page="dashboard",
                           today_classes=today_classes, today_day=today,
                           today_stats=today_stats, pending_requests=pending)

@faculty_bp.route("/session/<int:timetable_id>")
@login_required_with_role("Faculty")
def class_session(timetable_id):
    print("\n" + "🔵"*20)
    print(f">>> UI: RENDERING CLASS SESSION (Timetable ID: {timetable_id}) <<<")

    db = get_db()
    slot = db.execute("""
        SELECT t.*, s.subject_name, s.subject_code, b.batch_name
        FROM timetables t JOIN subjects s ON t.subject_id = s.id
        JOIN batches b ON t.batch_id = b.id
        WHERE t.id = ? AND t.faculty_id = ?
    """, (timetable_id, session["user_id"])).fetchone()
    
    if not slot:
        flash("Class not found.", "danger")
        return redirect(url_for("faculty.dashboard"))
        
    active = db.execute(
        "SELECT * FROM active_sessions WHERE timetable_id = ? AND ended_at IS NULL", (timetable_id,)
    ).fetchone()
    
    print(f"Active Session Found? {'YES (ID: ' + str(active['id']) + ')' if active else 'NO'}")

    # 🔥 TIMEZONE FIX: Let SQLite check if the UTC ended_at matches TODAY in LOCAL time
    last_session = db.execute("""
        SELECT id, ended_at, 
               (date(ended_at, 'localtime') = date('now', 'localtime')) as is_today 
        FROM active_sessions WHERE timetable_id = ? ORDER BY id DESC LIMIT 1
    """, (timetable_id,)).fetchone()

    completed_today = False
    completed_session_id = None

    if last_session:
        print(f"Last Session DB Record -> ID: {last_session['id']}, ended_at (UTC): {last_session['ended_at']}")
        if last_session["ended_at"] and last_session["is_today"]:
            print("✅ MATCH: Session was completed TODAY (Local Time)!")
            completed_today = True
            completed_session_id = last_session["id"]
        else:
            print("❌ NO MATCH: Session was NOT completed today.")
    else:
        print("No previous sessions found.")

    print(f"Passing to HTML -> completed_today: {completed_today}, completed_session_id: {completed_session_id}")
    print("🔵"*20 + "\n")

    return render_template("faculty/class_session.html", active_page="dashboard",
                           slot=slot, active_session=active, 
                           completed_today=completed_today, 
                           completed_session_id=completed_session_id, 
                           pending_requests=0)


@faculty_bp.route("/timetable")
@login_required_with_role("Faculty")
def my_timetable():
    db = get_db()
    timetable = db.execute("""
        SELECT t.*, s.subject_name, s.subject_code, b.batch_name
        FROM timetables t JOIN subjects s ON t.subject_id = s.id
        JOIN batches b ON t.batch_id = b.id
        WHERE t.faculty_id = ?
        ORDER BY CASE t.day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2
            WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4
            WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 ELSE 7 END, t.start_time
    """, (session["user_id"],)).fetchall()
    return render_template("faculty/timetable.html", active_page="timetable",
                           timetable=timetable, today_day=today_day_name(), pending_requests=0)


@faculty_bp.route("/attendance")
@login_required_with_role("Faculty")
def attendance_history():
    db = get_db()
    faculty_id = session["user_id"]
    records = db.execute("""
        SELECT a.*, u.name as student_name, u.profile_photo, s.subject_name, s.subject_code,
               b.batch_name, t.day_of_week, t.start_time, t.end_time
        FROM attendance a JOIN users u ON a.student_id = u.id
        JOIN timetables t ON a.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id JOIN batches b ON t.batch_id = b.id
        WHERE t.faculty_id = ? ORDER BY a.date DESC, a.entry_time DESC LIMIT 200
    """, (faculty_id,)).fetchall()

    flagged = db.execute("""
        SELECT a.*, u.name as student_name, u.profile_photo, s.subject_name
        FROM attendance a JOIN users u ON a.student_id = u.id
        JOIN timetables t ON a.timetable_id = t.id JOIN subjects s ON t.subject_id = s.id
        WHERE t.faculty_id = ? AND a.flagged_for_audit = 1 AND a.selfie_filepath IS NOT NULL
        ORDER BY a.date DESC LIMIT 20
    """, (faculty_id,)).fetchall()

    return render_template("faculty/attendance.html", active_page="attendance",
                           records=records, flagged=flagged, pending_requests=0)


@faculty_bp.route("/attendance/export")
@login_required_with_role("Faculty")
def export_attendance():
    db = get_db()
    records = db.execute("""
        SELECT a.date, u.name, u.email, s.subject_name, s.subject_code,
               b.batch_name, a.status, a.entry_time, a.exit_time, a.verification_method
        FROM attendance a JOIN users u ON a.student_id = u.id
        JOIN timetables t ON a.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id JOIN batches b ON t.batch_id = b.id
        WHERE t.faculty_id = ? ORDER BY a.date DESC, u.name
    """, (session["user_id"],)).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Student", "Email", "Subject", "Code", "Batch", "Status", "Entry", "Exit", "Method"])
    for r in records:
        writer.writerow([r["date"], r["name"], r["email"], r["subject_name"], r["subject_code"],
                         r["batch_name"], r["status"], r["entry_time"] or "", r["exit_time"] or "",
                         r["verification_method"]])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename=faculty_attendance_{date.today()}.csv"})


@faculty_bp.route("/requests")
@login_required_with_role("Faculty")
def my_requests():
    db = get_db()
    faculty_id = session["user_id"]
    requests_list = db.execute("""
        SELECT sr.*, s.subject_name, t.day_of_week, t.start_time, t.end_time
        FROM schedule_requests sr JOIN timetables t ON sr.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        WHERE sr.requested_by_faculty_id = ? ORDER BY sr.created_at DESC
    """, (faculty_id,)).fetchall()

    slots = db.execute("""
        SELECT t.id, s.subject_name, s.subject_code, b.batch_name, t.day_of_week, t.start_time, t.end_time
        FROM timetables t JOIN subjects s ON t.subject_id = s.id JOIN batches b ON t.batch_id = b.id
        WHERE t.faculty_id = ? ORDER BY t.day_of_week, t.start_time
    """, (faculty_id,)).fetchall()

    pending = db.execute(
        "SELECT COUNT(*) as c FROM schedule_requests WHERE requested_by_faculty_id = ? AND admin_status = 'Pending'",
        (faculty_id,),
    ).fetchone()["c"]

    return render_template("faculty/requests.html", active_page="requests",
                           requests=requests_list, timetable_slots=slots, pending_requests=pending)


@faculty_bp.route("/requests/submit", methods=["POST"])
@login_required_with_role("Faculty")
def submit_request():
    db = get_db()
    timetable_id = request.form.get("timetable_id")
    req_type = request.form.get("request_type")
    reason = sanitize(request.form.get("reason", ""))
    new_date = request.form.get("new_date") or None
    new_start = request.form.get("new_start_time") or None
    new_end = request.form.get("new_end_time") or None
    if not timetable_id or not req_type:
        flash("Please select a class and request type.", "danger")
        return redirect(url_for("faculty.my_requests"))
    db.execute(
        """INSERT INTO schedule_requests (timetable_id, requested_by_faculty_id, request_type, reason, new_date, new_start_time, new_end_time)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (timetable_id, session["user_id"], req_type, reason, new_date, new_start, new_end))
    db.commit()

    # Notify admins
    admins = db.execute("SELECT id FROM users WHERE role='Admin'").fetchall()
    for a in admins:
        from app.utils import create_notification
        create_notification(db, a["id"], "New Schedule Request",
                            f"Faculty {session['user_name']} submitted a {req_type.lower()} request.",
                            url_for("admin.schedule_requests"))

    log_audit(db, "schedule_request_submitted", "schedule_request", None, f"{req_type}: {reason}")
    flash("Schedule request submitted. Awaiting admin approval.", "success")
    return redirect(url_for("faculty.my_requests"))

@faculty_bp.route("/attendance/review/<int:record_id>", methods=["POST"])
@login_required_with_role("Faculty")
def review_attendance(record_id):
    action = request.form.get("action")
    db = get_db()
    
    # Security: Ensure this faculty member owns this class
    record = db.execute("""
        SELECT a.* FROM attendance a 
        JOIN timetables t ON a.timetable_id = t.id 
        WHERE a.id = ? AND t.faculty_id = ?
    """, (record_id, session["user_id"])).fetchone()
    
    if not record:
        flash("Record not found or unauthorized.", "danger")
        return redirect(url_for("faculty.attendance_history"))
        
    if action == "verify":
        # Keep their existing status (Present or Late), just remove the flag
        db.execute("UPDATE attendance SET flagged_for_audit = 0 WHERE id = ?", (record_id,))
        flash("Student identity verified.", "success")
    
    elif action == "reject":
        # Mark them absent and remove the flag
        db.execute("UPDATE attendance SET status = 'Absent', flagged_for_audit = 0 WHERE id = ?", (record_id,))
        flash("Attendance rejected. Marked as Absent.", "info")
        
    db.commit()
    return redirect(url_for("faculty.attendance_history"))




@faculty_bp.route("/session/<int:timetable_id>/end", methods=["POST", "GET"])
@login_required_with_role("Faculty")
def end_session(timetable_id):
    db = get_db()

    # 1. Find the currently active session for this class
    active_session = db.execute(
        "SELECT id FROM active_sessions WHERE timetable_id = ? AND ended_at IS NULL",
        (timetable_id,)
    ).fetchone()

    if active_session:
        session_id = active_session["id"]

        # 2. Mark the session as officially ended (Timestamp it)
        db.execute(
            "UPDATE active_sessions SET ended_at = CURRENT_TIMESTAMP WHERE id = ?",
            (session_id,)
        )

        # 3. 🔥 THE HOUSEKEEPING: Delete hardware locks to free up student phones!
        db.execute("DELETE FROM device_locks WHERE session_id = ?", (session_id,))
        
        db.commit()
        flash("Session ended securely. All student devices are unlocked.", "success")
    else:
        flash("No active session found to end.", "info")

    # 4. Send the teacher back to the class dashboard
    return redirect(url_for("faculty.class_session", timetable_id=timetable_id))