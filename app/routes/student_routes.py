"""
Student Routes v2 — dashboard, join batch via code, check-in, timetable,
                    attendance history, CSV export.
"""
import csv
import io
from datetime import date

from flask import (
    render_template, request, redirect, url_for, flash, session,
    Response, current_app,
)
from app.routes import student_bp
from app.models import get_db
from app.utils import (
    login_required_with_role, today_day_name, sanitize,
    log_audit, create_notification,
)


@student_bp.route("/dashboard")
@login_required_with_role("Student")
def dashboard():
    db = get_db()
    student_id = session["user_id"]
    today = today_day_name()
    today_date = date.today().isoformat()
    student = db.execute("SELECT * FROM users WHERE id = ?", (student_id,)).fetchone()

    if not student["batch_id"]:
        return render_template(
            "student/dashboard.html", active_page="dashboard",
            today_classes=[], today_day=today, student=student,
            no_batch=True, attendance_stats={"present": 0, "absent": 0, "total": 0, "percentage": 0},
        )

    today_classes = db.execute("""
        SELECT t.*, s.subject_name, s.subject_code, u.name as faculty_name,
               asess.id as active_session_id, asess.session_phase,
               a.status as my_status, a.entry_time as my_entry, a.exit_time as my_exit,
               a.flagged_for_audit  -- 🚨 NEW: Added this line
        FROM timetables t
        JOIN subjects s ON t.subject_id = s.id
        JOIN users u    ON t.faculty_id = u.id
        LEFT JOIN active_sessions asess ON asess.timetable_id = t.id AND asess.ended_at IS NULL
        LEFT JOIN attendance a ON a.timetable_id = t.id AND a.student_id = ? AND a.date = ?
        WHERE t.batch_id = ? AND t.day_of_week = ?
        ORDER BY t.start_time
    """, (student_id, today_date, student["batch_id"], today)).fetchall()

    stats = db.execute("""
        SELECT COUNT(*) as total,
               COUNT(CASE WHEN a.status IN ('Present','Late') THEN 1 END) as present,
               COUNT(CASE WHEN a.status = 'Absent' THEN 1 END) as absent
        FROM attendance a WHERE a.student_id = ?
    """, (student_id,)).fetchone()

    total = stats["total"] or 0
    present = stats["present"] or 0
    pct = round((present / total) * 100) if total > 0 else 0

    # Get batch info for display
    batch = db.execute("SELECT * FROM batches WHERE id = ?", (student["batch_id"],)).fetchone()

    return render_template(
        "student/dashboard.html", active_page="dashboard",
        today_classes=today_classes, today_day=today, student=student,
        no_batch=False, batch=batch,
        attendance_stats={"present": present, "absent": stats["absent"] or 0, "total": total, "percentage": pct},
    )


# ═══════════════════════════════════════════════════════════════
#  JOIN CLASS (Google Classroom style — enter alphanumeric code)
# ═══════════════════════════════════════════════════════════════
@student_bp.route("/join", methods=["GET", "POST"])
@login_required_with_role("Student")
def join_class():
    db = get_db()
    student = db.execute("SELECT * FROM users WHERE id = ?", (session["user_id"],)).fetchone()

    if request.method == "POST":
        code = sanitize(request.form.get("join_code", "")).upper().strip()

        if not code or len(code) < 4:
            flash("Please enter a valid join code.", "danger")
            return render_template("student/join_class.html", active_page="join", student=student)

        batch = db.execute(
            "SELECT * FROM batches WHERE join_code = ? AND join_enabled = 1", (code,)
        ).fetchone()

        if not batch:
            flash("Invalid or expired join code. Please check with your admin.", "danger")
            return render_template("student/join_class.html", active_page="join", student=student)

        if student["batch_id"] == batch["id"]:
            flash(f"You're already in {batch['batch_name']}.", "info")
            return redirect(url_for("student.dashboard"))

        if student["batch_id"]:
            old_batch = db.execute("SELECT batch_name FROM batches WHERE id = ?", (student["batch_id"],)).fetchone()
            flash(f"You've been moved from {old_batch['batch_name']} to {batch['batch_name']}.", "info")

        db.execute("UPDATE users SET batch_id = ? WHERE id = ?", (batch["id"], session["user_id"]))
        db.commit()

        log_audit(db, "student_joined_batch", "batch", batch["id"],
                  f"Student {session['user_name']} joined via code {code}")

        flash(f"Successfully joined {batch['batch_name']}!", "success")
        return redirect(url_for("student.dashboard"))

    return render_template("student/join_class.html", active_page="join", student=student)


@student_bp.route("/leave-batch", methods=["POST"])
@login_required_with_role("Student")
def leave_batch():
    db = get_db()
    db.execute("UPDATE users SET batch_id = NULL WHERE id = ?", (session["user_id"],))
    db.commit()
    flash("You have left the batch.", "info")
    return redirect(url_for("student.dashboard"))


# ═══════════════════════════════════════════════════════════════
#  CHECK-IN PAGE
# ═══════════════════════════════════════════════════════════════
@student_bp.route("/checkin/<int:session_id>")
@login_required_with_role("Student")
def checkin(session_id):
    db = get_db()
    student_id = session["user_id"]
    
    # Notice we are pulling teacher_lat and teacher_lng from active_sessions!
    active = db.execute("""
        SELECT asess.*, t.*, s.subject_name, s.subject_code,
               b.batch_name, u.name as faculty_name
        FROM active_sessions asess
        JOIN timetables t ON asess.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN batches b  ON t.batch_id = b.id
        JOIN users u    ON t.faculty_id = u.id
        WHERE asess.id = ? AND asess.ended_at IS NULL
    """, (session_id,)).fetchone()

    if not active:
        flash("No active session found.", "warning")
        return redirect(url_for("student.dashboard"))

    student = db.execute("SELECT batch_id FROM users WHERE id = ?", (student_id,)).fetchone()
    if student["batch_id"] != active["batch_id"]:
        flash("You are not enrolled in this class.", "danger")
        return redirect(url_for("student.dashboard"))

    today_date = date.today().isoformat()
    existing = db.execute(
        "SELECT * FROM attendance WHERE timetable_id=? AND student_id=? AND date=?",
        (active["timetable_id"], student_id, today_date),
    ).fetchone()

    geo_enabled = current_app.config.get("GEO_ENABLED", False)
    
    # 🔥 THE FIX: Pull directly from the database row instead of the .env file!
    classroom_lat = active["teacher_lat"] if active["teacher_lat"] else 0
    classroom_lng = active["teacher_lng"] if active["teacher_lng"] else 0

    return render_template(
        "student/checkin.html", active_page="dashboard",
        active_session=active, session_id=session_id,
        existing_record=existing, geo_enabled=geo_enabled,
        classroom_lat=classroom_lat, classroom_lng=classroom_lng,
    )

# ═══════════════════════════════════════════════════════════════
#  MY TIMETABLE
# ═══════════════════════════════════════════════════════════════
@student_bp.route("/timetable")
@login_required_with_role("Student")
def my_timetable():
    db = get_db()
    student = db.execute("SELECT batch_id FROM users WHERE id = ?", (session["user_id"],)).fetchone()
    if not student["batch_id"]:
        timetable = []
    else:
        timetable = db.execute("""
            SELECT t.*, s.subject_name, s.subject_code, u.name as faculty_name
            FROM timetables t
            JOIN subjects s ON t.subject_id = s.id
            JOIN users u    ON t.faculty_id = u.id
            WHERE t.batch_id = ?
            ORDER BY CASE t.day_of_week
                WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2
                WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4
                WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 ELSE 7 END,
                t.start_time
        """, (student["batch_id"],)).fetchall()

    return render_template("student/timetable.html", active_page="timetable",
                           timetable=timetable, today_day=today_day_name())


# ═══════════════════════════════════════════════════════════════
#  ATTENDANCE HISTORY + CSV EXPORT
# ═══════════════════════════════════════════════════════════════
@student_bp.route("/attendance")
@login_required_with_role("Student")
def attendance_history():
    db = get_db()
    records = db.execute("""
        SELECT a.*, s.subject_name, s.subject_code, u.name as faculty_name,
               t.day_of_week, t.start_time, t.end_time
        FROM attendance a
        JOIN timetables t ON a.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN users u ON t.faculty_id = u.id
        WHERE a.student_id = ?
        ORDER BY a.date DESC LIMIT 200
    """, (session["user_id"],)).fetchall()

    return render_template("student/attendance.html", active_page="attendance", records=records)


@student_bp.route("/attendance/export")
@login_required_with_role("Student")
def export_my_attendance():
    db = get_db()
    records = db.execute("""
        SELECT a.date, s.subject_name, s.subject_code, u.name as faculty_name,
               a.status, a.entry_time, a.exit_time, a.verification_method
        FROM attendance a
        JOIN timetables t ON a.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN users u ON t.faculty_id = u.id
        WHERE a.student_id = ?
        ORDER BY a.date DESC
    """, (session["user_id"],)).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Subject", "Code", "Faculty", "Status", "Entry", "Exit", "Method"])
    for r in records:
        writer.writerow([r["date"], r["subject_name"], r["subject_code"],
                         r["faculty_name"], r["status"],
                         r["entry_time"] or "", r["exit_time"] or "",
                         r["verification_method"]])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment;filename=my_attendance_{date.today()}.csv"},
    )
