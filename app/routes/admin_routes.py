"""
Admin Routes v2 — Full CRUD + join codes + audit log + CSV export + notifications.
"""
import csv
import io
from datetime import datetime, date, timezone

from flask import (
    render_template, request, redirect, url_for, flash, session, Response,
)
from app.routes import admin_bp
from app.models import get_db
from app.utils import (
    login_required_with_role, hash_password, sanitize,
    generate_join_code, log_audit, create_notification,
)


def _pending_count():
    db = get_db()
    return db.execute("SELECT COUNT(*) as c FROM schedule_requests WHERE admin_status = 'Pending'").fetchone()["c"]


# ═══════════════════════════════════════════════════════════════
#  DASHBOARD
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/dashboard")
@login_required_with_role("Admin")
def dashboard():
    db = get_db()
    stats = {
        "admins": db.execute("SELECT COUNT(*) as c FROM users WHERE role='Admin'").fetchone()["c"],
        "faculty": db.execute("SELECT COUNT(*) as c FROM users WHERE role='Faculty'").fetchone()["c"],
        "students": db.execute("SELECT COUNT(*) as c FROM users WHERE role='Student'").fetchone()["c"],
        "batches": db.execute("SELECT COUNT(*) as c FROM batches").fetchone()["c"],
        "subjects": db.execute("SELECT COUNT(*) as c FROM subjects").fetchone()["c"],
        "pending_requests": _pending_count(),
    }
    recent_users = db.execute("SELECT * FROM users ORDER BY created_at DESC LIMIT 10").fetchall()
    pending_requests = db.execute("""
        SELECT sr.*, u.name as faculty_name, s.subject_name
        FROM schedule_requests sr
        JOIN users u ON sr.requested_by_faculty_id = u.id
        JOIN timetables t ON sr.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        WHERE sr.admin_status = 'Pending' ORDER BY sr.created_at DESC
    """).fetchall()
    return render_template("admin/dashboard.html", active_page="dashboard",
                           stats=stats, recent_users=recent_users,
                           pending_requests=pending_requests, pending_count=stats["pending_requests"])


# ═══════════════════════════════════════════════════════════════
#  ADMIN MANAGEMENT
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/admins")
@login_required_with_role("Admin")
def manage_admins():
    db = get_db()
    admin_list = db.execute("SELECT * FROM users WHERE role='Admin' ORDER BY name").fetchall()
    return render_template("admin/manage_admins.html", active_page="admins",
                           admin_list=admin_list, current_admin_id=session["user_id"],
                           pending_count=_pending_count())

@admin_bp.route("/admins/add", methods=["POST"])
@login_required_with_role("Admin")
def add_admin():
    name = sanitize(request.form.get("name", ""))
    email = sanitize(request.form.get("email", "")).lower()
    password = request.form.get("password", "").strip()
    if not name or not email or not password:
        flash("All fields are required.", "danger")
        return redirect(url_for("admin.manage_admins"))
    db = get_db()
    if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
        flash("A user with this email already exists.", "danger")
        return redirect(url_for("admin.manage_admins"))
    db.execute("INSERT INTO users (role, name, email, password_hash, is_verified) VALUES ('Admin', ?, ?, ?, 1)",
               (name, email, hash_password(password)))
    db.commit()
    log_audit(db, "admin_created", "user", None, f"Created admin: {email}")
    flash(f"Admin '{name}' added successfully.", "success")
    return redirect(url_for("admin.manage_admins"))

@admin_bp.route("/admins/edit", methods=["POST"])
@login_required_with_role("Admin")
def edit_admin():
    user_id = request.form.get("user_id")
    name = sanitize(request.form.get("name", ""))
    email = sanitize(request.form.get("email", "")).lower()
    password = request.form.get("password", "").strip()
    db = get_db()
    if password:
        db.execute("UPDATE users SET name=?, email=?, password_hash=? WHERE id=? AND role='Admin'",
                   (name, email, hash_password(password), user_id))
    else:
        db.execute("UPDATE users SET name=?, email=? WHERE id=? AND role='Admin'", (name, email, user_id))
    db.commit()
    log_audit(db, "admin_edited", "user", int(user_id))
    flash("Admin updated.", "success")
    return redirect(url_for("admin.manage_admins"))

@admin_bp.route("/admins/delete/<int:user_id>", methods=["POST"])
@login_required_with_role("Admin")
def delete_admin(user_id):
    if user_id == session["user_id"]:
        flash("You cannot delete your own account.", "danger")
        return redirect(url_for("admin.manage_admins"))
    db = get_db()
    if db.execute("SELECT COUNT(*) as c FROM users WHERE role='Admin'").fetchone()["c"] <= 1:
        flash("Cannot delete the last admin account.", "danger")
        return redirect(url_for("admin.manage_admins"))
    db.execute("DELETE FROM otp_tokens WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM schedule_requests WHERE reviewed_by_admin_id=?", (user_id,))
    db.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=? AND role='Admin'", (user_id,))
    db.commit()
    log_audit(db, "admin_deleted", "user", user_id)
    flash("Admin deleted.", "info")
    return redirect(url_for("admin.manage_admins"))


# ═══════════════════════════════════════════════════════════════
#  FACULTY MANAGEMENT
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/faculty")
@login_required_with_role("Admin")
def manage_faculty():
    db = get_db()
    faculty_list = db.execute("SELECT * FROM users WHERE role='Faculty' ORDER BY name").fetchall()
    return render_template("admin/manage_faculty.html", active_page="faculty",
                           faculty_list=faculty_list, pending_count=_pending_count())

@admin_bp.route("/faculty/add", methods=["POST"])
@login_required_with_role("Admin")
def add_faculty():
    name = sanitize(request.form.get("name", ""))
    email = sanitize(request.form.get("email", "")).lower()
    password = request.form.get("password", "").strip()
    if not name or not email or not password:
        flash("All fields are required.", "danger")
        return redirect(url_for("admin.manage_faculty"))
    db = get_db()
    if db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
        flash("A user with this email already exists.", "danger")
        return redirect(url_for("admin.manage_faculty"))
    db.execute("INSERT INTO users (role, name, email, password_hash, is_verified) VALUES ('Faculty', ?, ?, ?, 1)",
               (name, email, hash_password(password)))
    db.commit()
    log_audit(db, "faculty_created", "user", None, f"Created faculty: {email}")
    flash(f"Faculty '{name}' added successfully.", "success")
    return redirect(url_for("admin.manage_faculty"))

@admin_bp.route("/faculty/edit", methods=["POST"])
@login_required_with_role("Admin")
def edit_faculty():
    user_id = request.form.get("user_id")
    name = sanitize(request.form.get("name", ""))
    email = sanitize(request.form.get("email", "")).lower()
    password = request.form.get("password", "").strip()
    db = get_db()
    if password:
        db.execute("UPDATE users SET name=?, email=?, password_hash=? WHERE id=? AND role='Faculty'",
                   (name, email, hash_password(password), user_id))
    else:
        db.execute("UPDATE users SET name=?, email=? WHERE id=? AND role='Faculty'", (name, email, user_id))
    db.commit()
    flash("Faculty updated.", "success")
    return redirect(url_for("admin.manage_faculty"))

@admin_bp.route("/faculty/delete/<int:user_id>", methods=["POST"])
@login_required_with_role("Admin")
def delete_faculty(user_id):
    db = get_db()
    db.execute("DELETE FROM otp_tokens WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM schedule_requests WHERE requested_by_faculty_id=?", (user_id,))
    db.execute("DELETE FROM active_sessions WHERE faculty_id=?", (user_id,))
    db.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM timetables WHERE faculty_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=? AND role='Faculty'", (user_id,))
    db.commit()
    log_audit(db, "faculty_deleted", "user", user_id)
    flash("Faculty deleted.", "info")
    return redirect(url_for("admin.manage_faculty"))


# ═══════════════════════════════════════════════════════════════
#  STUDENT MANAGEMENT
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/students")
@login_required_with_role("Admin")
def manage_students():
    db = get_db()
    students = db.execute("""
        SELECT u.*, b.batch_name FROM users u
        LEFT JOIN batches b ON u.batch_id = b.id
        WHERE u.role = 'Student' ORDER BY u.name
    """).fetchall()
    batches = db.execute("SELECT * FROM batches ORDER BY batch_name").fetchall()
    return render_template("admin/manage_students.html", active_page="students",
                           students=students, batches=batches, pending_count=_pending_count())

@admin_bp.route("/students/assign-batch", methods=["POST"])
@login_required_with_role("Admin")
def assign_student_batch():
    student_id = request.form.get("student_id")
    batch_id = request.form.get("batch_id") or None
    db = get_db()
    db.execute("UPDATE users SET batch_id=? WHERE id=? AND role='Student'", (batch_id, student_id))
    db.commit()
    flash("Student batch assignment updated.", "success")
    return redirect(url_for("admin.manage_students"))

@admin_bp.route("/students/delete/<int:user_id>", methods=["POST"])
@login_required_with_role("Admin")
def delete_student(user_id):
    db = get_db()
    db.execute("DELETE FROM otp_tokens WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM attendance WHERE student_id=?", (user_id,))
    db.execute("DELETE FROM notifications WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM rate_limits WHERE user_id=?", (user_id,))
    db.execute("DELETE FROM users WHERE id=? AND role='Student'", (user_id,))
    db.commit()
    log_audit(db, "student_deleted", "user", user_id)
    flash("Student deleted.", "info")
    return redirect(url_for("admin.manage_students"))


# ═══════════════════════════════════════════════════════════════
#  BATCH MANAGEMENT (with join codes)
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/batches")
@login_required_with_role("Admin")
def manage_batches():
    db = get_db()
    batches = db.execute("""
        SELECT b.*,
               (SELECT COUNT(*) FROM users WHERE batch_id = b.id) as student_count,
               (SELECT COUNT(*) FROM timetables WHERE batch_id = b.id) as timetable_count
        FROM batches b ORDER BY b.batch_name
    """).fetchall()
    return render_template("admin/manage_batches.html", active_page="batches",
                           batches=batches, pending_count=_pending_count())

@admin_bp.route("/batches/add", methods=["POST"])
@login_required_with_role("Admin")
def add_batch():
    name = sanitize(request.form.get("batch_name", ""))
    if not name:
        flash("Batch name is required.", "danger")
        return redirect(url_for("admin.manage_batches"))
    db = get_db()
    if db.execute("SELECT id FROM batches WHERE batch_name = ?", (name,)).fetchone():
        flash("A batch with this name already exists.", "danger")
        return redirect(url_for("admin.manage_batches"))
    code = generate_join_code()
    # Ensure unique
    while db.execute("SELECT id FROM batches WHERE join_code = ?", (code,)).fetchone():
        code = generate_join_code()
    db.execute("INSERT INTO batches (batch_name, join_code) VALUES (?, ?)", (name, code))
    db.commit()
    log_audit(db, "batch_created", "batch", None, f"{name} (code: {code})")
    flash(f"Batch '{name}' created. Join code: {code}", "success")
    return redirect(url_for("admin.manage_batches"))

@admin_bp.route("/batches/edit", methods=["POST"])
@login_required_with_role("Admin")
def edit_batch():
    batch_id = request.form.get("batch_id")
    name = sanitize(request.form.get("batch_name", ""))
    db = get_db()
    db.execute("UPDATE batches SET batch_name=? WHERE id=?", (name, batch_id))
    db.commit()
    flash("Batch updated.", "success")
    return redirect(url_for("admin.manage_batches"))

@admin_bp.route("/batches/regenerate-code/<int:batch_id>", methods=["POST"])
@login_required_with_role("Admin")
def regenerate_join_code(batch_id):
    db = get_db()
    code = generate_join_code()
    while db.execute("SELECT id FROM batches WHERE join_code = ?", (code,)).fetchone():
        code = generate_join_code()
    db.execute("UPDATE batches SET join_code = ? WHERE id = ?", (code, batch_id))
    db.commit()
    flash(f"New join code generated: {code}", "success")
    return redirect(url_for("admin.manage_batches"))

@admin_bp.route("/batches/toggle-join/<int:batch_id>", methods=["POST"])
@login_required_with_role("Admin")
def toggle_join(batch_id):
    db = get_db()
    batch = db.execute("SELECT join_enabled FROM batches WHERE id = ?", (batch_id,)).fetchone()
    new_val = 0 if batch["join_enabled"] else 1
    db.execute("UPDATE batches SET join_enabled = ? WHERE id = ?", (new_val, batch_id))
    db.commit()
    status = "enabled" if new_val else "disabled"
    flash(f"Join code {status}.", "info")
    return redirect(url_for("admin.manage_batches"))

@admin_bp.route("/batches/delete/<int:batch_id>", methods=["POST"])
@login_required_with_role("Admin")
def delete_batch(batch_id):
    db = get_db()
    tt_ids = [r["id"] for r in db.execute("SELECT id FROM timetables WHERE batch_id = ?", (batch_id,)).fetchall()]
    for tt_id in tt_ids:
        db.execute("DELETE FROM attendance WHERE timetable_id=?", (tt_id,))
        db.execute("DELETE FROM schedule_requests WHERE timetable_id=?", (tt_id,))
        db.execute("DELETE FROM active_sessions WHERE timetable_id=?", (tt_id,))
    db.execute("DELETE FROM timetables WHERE batch_id = ?", (batch_id,))
    db.execute("UPDATE users SET batch_id = NULL WHERE batch_id = ?", (batch_id,))
    db.execute("DELETE FROM batches WHERE id = ?", (batch_id,))
    db.commit()
    log_audit(db, "batch_deleted", "batch", batch_id)
    flash("Batch deleted. Students have been unassigned.", "info")
    return redirect(url_for("admin.manage_batches"))


# ═══════════════════════════════════════════════════════════════
#  SUBJECT MANAGEMENT
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/subjects")
@login_required_with_role("Admin")
def manage_subjects():
    db = get_db()
    subjects = db.execute("""
        SELECT s.*, (SELECT COUNT(*) FROM timetables WHERE subject_id = s.id) as timetable_count
        FROM subjects s ORDER BY s.subject_code
    """).fetchall()
    return render_template("admin/manage_subjects.html", active_page="subjects",
                           subjects=subjects, pending_count=_pending_count())

@admin_bp.route("/subjects/add", methods=["POST"])
@login_required_with_role("Admin")
def add_subject():
    code = sanitize(request.form.get("subject_code", "")).upper()
    name = sanitize(request.form.get("subject_name", ""))
    if not code or not name:
        flash("Both code and name are required.", "danger")
        return redirect(url_for("admin.manage_subjects"))
    db = get_db()
    if db.execute("SELECT id FROM subjects WHERE subject_code = ?", (code,)).fetchone():
        flash("A subject with this code already exists.", "danger")
        return redirect(url_for("admin.manage_subjects"))
    db.execute("INSERT INTO subjects (subject_code, subject_name) VALUES (?, ?)", (code, name))
    db.commit()
    flash(f"Subject '{code}' created.", "success")
    return redirect(url_for("admin.manage_subjects"))

@admin_bp.route("/subjects/edit", methods=["POST"])
@login_required_with_role("Admin")
def edit_subject():
    subject_id = request.form.get("subject_id")
    code = sanitize(request.form.get("subject_code", "")).upper()
    name = sanitize(request.form.get("subject_name", ""))
    db = get_db()
    db.execute("UPDATE subjects SET subject_code=?, subject_name=? WHERE id=?", (code, name, subject_id))
    db.commit()
    flash("Subject updated.", "success")
    return redirect(url_for("admin.manage_subjects"))

@admin_bp.route("/subjects/delete/<int:subject_id>", methods=["POST"])
@login_required_with_role("Admin")
def delete_subject(subject_id):
    db = get_db()
    tt_ids = [r["id"] for r in db.execute("SELECT id FROM timetables WHERE subject_id = ?", (subject_id,)).fetchall()]
    for tt_id in tt_ids:
        db.execute("DELETE FROM attendance WHERE timetable_id=?", (tt_id,))
        db.execute("DELETE FROM schedule_requests WHERE timetable_id=?", (tt_id,))
        db.execute("DELETE FROM active_sessions WHERE timetable_id=?", (tt_id,))
    db.execute("DELETE FROM timetables WHERE subject_id = ?", (subject_id,))
    db.execute("DELETE FROM subjects WHERE id = ?", (subject_id,))
    db.commit()
    flash("Subject deleted.", "info")
    return redirect(url_for("admin.manage_subjects"))


# ═══════════════════════════════════════════════════════════════
#  TIMETABLE MANAGEMENT
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/timetable")
@login_required_with_role("Admin")
def manage_timetable():
    db = get_db()
    timetable = db.execute("""
        SELECT t.*, s.subject_name, s.subject_code, b.batch_name, u.name as faculty_name
        FROM timetables t JOIN subjects s ON t.subject_id = s.id
        JOIN batches b ON t.batch_id = b.id JOIN users u ON t.faculty_id = u.id
        ORDER BY CASE t.day_of_week WHEN 'Monday' THEN 1 WHEN 'Tuesday' THEN 2
            WHEN 'Wednesday' THEN 3 WHEN 'Thursday' THEN 4
            WHEN 'Friday' THEN 5 WHEN 'Saturday' THEN 6 ELSE 7 END, t.start_time
    """).fetchall()
    subjects = db.execute("SELECT * FROM subjects ORDER BY subject_code").fetchall()
    batches = db.execute("SELECT * FROM batches ORDER BY batch_name").fetchall()
    faculty_list = db.execute("SELECT * FROM users WHERE role='Faculty' ORDER BY name").fetchall()
    return render_template("admin/manage_timetable.html", active_page="timetable",
                           timetable=timetable, subjects=subjects, batches=batches,
                           faculty_list=faculty_list, pending_count=_pending_count())

@admin_bp.route("/timetable/add", methods=["POST"])
@login_required_with_role("Admin")
def add_timetable():
    subject_id = request.form.get("subject_id")
    batch_id = request.form.get("batch_id")
    faculty_id = request.form.get("faculty_id")
    day = request.form.get("day_of_week")
    start = request.form.get("start_time")
    end = request.form.get("end_time")
    if not all([subject_id, batch_id, faculty_id, day, start, end]):
        flash("All fields are required.", "danger")
        return redirect(url_for("admin.manage_timetable"))
    if start >= end:
        flash("Start time must be before end time.", "danger")
        return redirect(url_for("admin.manage_timetable"))
    db = get_db()
    if db.execute("SELECT id FROM timetables WHERE batch_id=? AND day_of_week=? AND NOT (end_time<=? OR start_time>=?)",
                  (batch_id, day, start, end)).fetchone():
        flash("Time conflict: this batch already has a class during this slot.", "danger")
        return redirect(url_for("admin.manage_timetable"))
    if db.execute("SELECT id FROM timetables WHERE faculty_id=? AND day_of_week=? AND NOT (end_time<=? OR start_time>=?)",
                  (faculty_id, day, start, end)).fetchone():
        flash("Time conflict: this faculty member is already assigned during this slot.", "danger")
        return redirect(url_for("admin.manage_timetable"))
    db.execute("INSERT INTO timetables (subject_id, batch_id, faculty_id, day_of_week, start_time, end_time) VALUES (?,?,?,?,?,?)",
               (subject_id, batch_id, faculty_id, day, start, end))
    db.commit()
    flash("Timetable slot added.", "success")
    return redirect(url_for("admin.manage_timetable"))

@admin_bp.route("/timetable/edit", methods=["POST"])
@login_required_with_role("Admin")
def edit_timetable():
    slot_id = request.form.get("slot_id")
    subject_id = request.form.get("subject_id")
    batch_id = request.form.get("batch_id")
    faculty_id = request.form.get("faculty_id")
    day = request.form.get("day_of_week")
    start = request.form.get("start_time")
    end = request.form.get("end_time")
    if start >= end:
        flash("Start time must be before end time.", "danger")
        return redirect(url_for("admin.manage_timetable"))
    db = get_db()
    if db.execute("SELECT id FROM timetables WHERE batch_id=? AND day_of_week=? AND id!=? AND NOT (end_time<=? OR start_time>=?)",
                  (batch_id, day, slot_id, start, end)).fetchone():
        flash("Time conflict with another class for this batch.", "danger")
        return redirect(url_for("admin.manage_timetable"))
    if db.execute("SELECT id FROM timetables WHERE faculty_id=? AND day_of_week=? AND id!=? AND NOT (end_time<=? OR start_time>=?)",
                  (faculty_id, day, slot_id, start, end)).fetchone():
        flash("Time conflict for this faculty member.", "danger")
        return redirect(url_for("admin.manage_timetable"))
    db.execute("UPDATE timetables SET subject_id=?, batch_id=?, faculty_id=?, day_of_week=?, start_time=?, end_time=? WHERE id=?",
               (subject_id, batch_id, faculty_id, day, start, end, slot_id))
    db.commit()
    flash("Timetable slot updated.", "success")
    return redirect(url_for("admin.manage_timetable"))

@admin_bp.route("/timetable/delete/<int:slot_id>", methods=["POST"])
@login_required_with_role("Admin")
def delete_timetable(slot_id):
    db = get_db()
    db.execute("DELETE FROM attendance WHERE timetable_id=?", (slot_id,))
    db.execute("DELETE FROM schedule_requests WHERE timetable_id=?", (slot_id,))
    db.execute("DELETE FROM active_sessions WHERE timetable_id=?", (slot_id,))
    db.execute("DELETE FROM timetables WHERE id = ?", (slot_id,))
    db.commit()
    flash("Timetable slot deleted.", "info")
    return redirect(url_for("admin.manage_timetable"))


# ═══════════════════════════════════════════════════════════════
#  SCHEDULE REQUESTS + NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/requests")
@login_required_with_role("Admin")
def schedule_requests():
    db = get_db()
    requests_list = db.execute("""
        SELECT sr.*, u.name as faculty_name, s.subject_name, t.day_of_week, t.start_time, t.end_time
        FROM schedule_requests sr
        JOIN users u ON sr.requested_by_faculty_id = u.id
        JOIN timetables t ON sr.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        ORDER BY CASE sr.admin_status WHEN 'Pending' THEN 0 ELSE 1 END, sr.created_at DESC
    """).fetchall()
    return render_template("admin/schedule_requests.html", active_page="requests",
                           requests=requests_list, pending_count=_pending_count())

@admin_bp.route("/requests/<int:req_id>/handle", methods=["POST"])
@admin_bp.route("/requests/<int:req_id>/handle", methods=["POST"])
@login_required_with_role("Admin")
def handle_request(req_id):
    action = request.form.get("action")
    db = get_db()

    req = db.execute(
        "SELECT * FROM schedule_requests WHERE id = ?",
        (req_id,)
    ).fetchone()

    if not req or req["admin_status"] != "Pending":
        flash("Request not found or already processed.", "warning")
        return redirect(url_for("admin.schedule_requests"))

    now = datetime.now(timezone.utc).isoformat()
    admin_id = session["user_id"]
    status = "Approved" if action == "approve" else "Rejected"

    # Update request status
    db.execute("""
        UPDATE schedule_requests
        SET admin_status=?,
            reviewed_by_admin_id=?,
            reviewed_at=?
        WHERE id=?
    """,
    (
        status,
        admin_id,
        now,
        req_id
    ))

    # ==================================================
    # APPLY APPROVED RESCHEDULE TO TIMETABLE
    # ==================================================
    if action == "approve" and req["request_type"] == "Reschedule":

        try:
            request_date = datetime.strptime(
                req["new_date"],
                "%Y-%m-%d"
            )

            new_day = request_date.strftime("%A")

            old_tt = db.execute("""
                SELECT *
                FROM timetables
                WHERE id = ?
            """, (req["timetable_id"],)).fetchone()

            print("\n===== CREATING NEW TIMETABLE =====")
            print("Old Timetable ID:", old_tt["id"])
            print("New Day:", new_day)
            print("New Start:", req["new_start_time"])
            print("New End:", req["new_end_time"])

            db.execute("""
                INSERT INTO timetables (
                    subject_id,
                    batch_id,
                    faculty_id,
                    day_of_week,
                    start_time,
                    end_time
                )
                VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                old_tt["subject_id"],
                old_tt["batch_id"],
                old_tt["faculty_id"],
                new_day,
                req["new_start_time"],
                req["new_end_time"]
            ))

            print("===== NEW TIMETABLE CREATED =====\n")

        except Exception as e:
            print("RESCHEDULE UPDATE ERROR:", str(e))

    db.commit()

    # Notify faculty
    create_notification(
        db,
        req["requested_by_faculty_id"],
        f"Schedule Request {status}",
        f"Your {req['request_type'].lower()} request has been {status.lower()} by admin.",
        url_for("faculty.my_requests")
    )

    # Notify affected students
    tt = db.execute(
        "SELECT batch_id FROM timetables WHERE id = ?",
        (req["timetable_id"],)
    ).fetchone()

    if tt:
        students = db.execute(
            "SELECT id FROM users WHERE batch_id = ? AND role = 'Student'",
            (tt["batch_id"],)
        ).fetchall()

        for s in students:
            create_notification(
                db,
                s["id"],
                f"Class {req['request_type']}",
                f"A class has been {req['request_type'].lower()}d. Check your timetable.",
                url_for("student.my_timetable")
            )

    log_audit(
        db,
        f"request_{status.lower()}",
        "schedule_request",
        req_id
    )

    flash(
        f"Request {status.lower()}.",
        "success" if action == "approve" else "info"
    )

    return redirect(url_for("admin.schedule_requests"))


# ═══════════════════════════════════════════════════════════════
#  AUDIT LOG
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/audit-log")
@login_required_with_role("Admin")
def audit_log():
    db = get_db()
    logs = db.execute("""
        SELECT al.*, u.name as user_name
        FROM audit_log al LEFT JOIN users u ON al.user_id = u.id
        ORDER BY al.created_at DESC LIMIT 200
    """).fetchall()
    return render_template("admin/audit_log.html", active_page="audit", logs=logs, pending_count=_pending_count())


# ═══════════════════════════════════════════════════════════════
#  ATTENDANCE REPORTS + CSV EXPORT
# ═══════════════════════════════════════════════════════════════
@admin_bp.route("/reports")
@login_required_with_role("Admin")
def reports():
    db = get_db()
    batches = db.execute("SELECT * FROM batches ORDER BY batch_name").fetchall()
    subjects = db.execute("SELECT * FROM subjects ORDER BY subject_code").fetchall()

    # Filters
    batch_id = request.args.get("batch_id", "")
    subject_id = request.args.get("subject_id", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = """
        SELECT a.*, u.name as student_name, u.email as student_email,
               s.subject_name, s.subject_code, b.batch_name,
               t.day_of_week, t.start_time, t.end_time
        FROM attendance a
        JOIN users u ON a.student_id = u.id
        JOIN timetables t ON a.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN batches b ON t.batch_id = b.id
        WHERE 1=1
    """
    params = []
    if batch_id:
        query += " AND t.batch_id = ?"
        params.append(batch_id)
    if subject_id:
        query += " AND t.subject_id = ?"
        params.append(subject_id)
    if date_from:
        query += " AND a.date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND a.date <= ?"
        params.append(date_to)
    query += " ORDER BY a.date DESC, u.name LIMIT 500"

    records = db.execute(query, params).fetchall()

    # Summary stats
    total = len(records)
    present = sum(1 for r in records if r["status"] in ("Present", "Late"))
    absent = sum(1 for r in records if r["status"] == "Absent")

    return render_template("admin/reports.html", active_page="reports",
                           records=records, batches=batches, subjects=subjects,
                           filters={"batch_id": batch_id, "subject_id": subject_id,
                                    "date_from": date_from, "date_to": date_to},
                           summary={"total": total, "present": present, "absent": absent},
                           pending_count=_pending_count())


@admin_bp.route("/reports/export")
@login_required_with_role("Admin")
def export_report():
    db = get_db()
    batch_id = request.args.get("batch_id", "")
    subject_id = request.args.get("subject_id", "")
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")

    query = """
        SELECT a.date, u.name, u.email, s.subject_name, s.subject_code,
               b.batch_name, a.status, a.entry_time, a.exit_time, a.verification_method
        FROM attendance a JOIN users u ON a.student_id = u.id
        JOIN timetables t ON a.timetable_id = t.id
        JOIN subjects s ON t.subject_id = s.id
        JOIN batches b ON t.batch_id = b.id WHERE 1=1
    """
    params = []
    if batch_id:
        query += " AND t.batch_id = ?"
        params.append(batch_id)
    if subject_id:
        query += " AND t.subject_id = ?"
        params.append(subject_id)
    if date_from:
        query += " AND a.date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND a.date <= ?"
        params.append(date_to)
    query += " ORDER BY a.date DESC, u.name"
    records = db.execute(query, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Date", "Student", "Email", "Subject", "Code", "Batch", "Status", "Entry", "Exit", "Method"])
    for r in records:
        writer.writerow([r["date"], r["name"], r["email"], r["subject_name"], r["subject_code"],
                         r["batch_name"], r["status"], r["entry_time"] or "", r["exit_time"] or "",
                         r["verification_method"]])
    return Response(output.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment;filename=attendance_report_{date.today()}.csv"})
