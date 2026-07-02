"""
Database layer — raw SQLite3 (v2 with all features).

Tables: users, batches, subjects, timetables, attendance,
        schedule_requests, otp_tokens, active_sessions,
        batch_join_codes, audit_log, rate_limits, notifications,
        device_locks
"""

import sqlite3
from flask import g, current_app


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(
            current_app.config["DATABASE_PATH"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SQL_SCHEMA = """
-- 1. USERS
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    role            TEXT    NOT NULL CHECK(role IN ('Admin','Faculty','Student')),
    name            TEXT    NOT NULL,
    email           TEXT    NOT NULL UNIQUE,
    password_hash   TEXT    NOT NULL,
    is_verified     INTEGER NOT NULL DEFAULT 0,
    batch_id        INTEGER,
    profile_photo   TEXT,
    device_fingerprint TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (batch_id) REFERENCES batches(id)
);

-- 2. BATCHES
CREATE TABLE IF NOT EXISTS batches (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_name      TEXT    NOT NULL UNIQUE,
    join_code       TEXT    UNIQUE,
    join_enabled    INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 3. SUBJECTS
CREATE TABLE IF NOT EXISTS subjects (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_name    TEXT    NOT NULL,
    subject_code    TEXT    NOT NULL UNIQUE,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 4. TIMETABLES
CREATE TABLE IF NOT EXISTS timetables (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id      INTEGER NOT NULL,
    batch_id        INTEGER NOT NULL,
    faculty_id      INTEGER NOT NULL,
    day_of_week     TEXT    NOT NULL CHECK(day_of_week IN
                        ('Monday','Tuesday','Wednesday','Thursday',
                         'Friday','Saturday','Sunday')),
    start_time      TEXT    NOT NULL,
    end_time        TEXT    NOT NULL,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (subject_id) REFERENCES subjects(id),
    FOREIGN KEY (batch_id)   REFERENCES batches(id),
    FOREIGN KEY (faculty_id) REFERENCES users(id)
);

-- 5. ATTENDANCE
CREATE TABLE IF NOT EXISTS attendance (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timetable_id        INTEGER NOT NULL,
    student_id          INTEGER NOT NULL,
    date                TEXT    NOT NULL,
    entry_time          TEXT,
    exit_time           TEXT,
    status              TEXT    NOT NULL DEFAULT 'Absent'
                            CHECK(status IN ('Present','Absent','Late')),
    selfie_filepath     TEXT,
    verification_method TEXT    NOT NULL DEFAULT 'Dual-Key'
                            CHECK(verification_method IN ('Dual-Key','Faculty_Override')),
    flagged_for_audit   INTEGER NOT NULL DEFAULT 0,
    device_info         TEXT,
    geo_lat             REAL,
    geo_lng             REAL,
    geo_accuracy        REAL,
    geo_distance        INTEGER,
    geo_trust_score     INTEGER,
    geo_verdict         TEXT CHECK(geo_verdict IN ('strong','moderate','weak','reject','denied','no_data') OR geo_verdict IS NULL),
    created_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE(timetable_id, student_id, date),
    FOREIGN KEY (timetable_id) REFERENCES timetables(id),
    FOREIGN KEY (student_id)   REFERENCES users(id)
);

-- 6. SCHEDULE REQUESTS
CREATE TABLE IF NOT EXISTS schedule_requests (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    timetable_id            INTEGER NOT NULL,
    requested_by_faculty_id INTEGER NOT NULL,
    request_type            TEXT    NOT NULL CHECK(request_type IN ('Cancel','Reschedule')),
    reason                  TEXT,
    new_date                TEXT,
    new_start_time          TEXT,
    new_end_time            TEXT,
    admin_status            TEXT    NOT NULL DEFAULT 'Pending'
                                CHECK(admin_status IN ('Pending','Approved','Rejected')),
    reviewed_by_admin_id    INTEGER,
    reviewed_at             TEXT,
    created_at              TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (timetable_id)            REFERENCES timetables(id),
    FOREIGN KEY (requested_by_faculty_id) REFERENCES users(id),
    FOREIGN KEY (reviewed_by_admin_id)    REFERENCES users(id)
);

-- 7. OTP TOKENS
CREATE TABLE IF NOT EXISTS otp_tokens (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    otp_code        TEXT    NOT NULL,
    purpose         TEXT    NOT NULL CHECK(purpose IN ('signup','password_reset')),
    expires_at      TEXT    NOT NULL,
    is_used         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 8. ACTIVE SESSIONS (UPDATED WITH GEOLOCATION COLUMNS)
CREATE TABLE IF NOT EXISTS active_sessions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    timetable_id        INTEGER NOT NULL,
    faculty_id          INTEGER NOT NULL,
    current_pin         TEXT,
    current_qr_data     TEXT,
    token_generated_at  TEXT,
    session_phase       TEXT    NOT NULL DEFAULT 'entry'
                            CHECK(session_phase IN ('entry','exit')),
    started_at          TEXT    NOT NULL DEFAULT (datetime('now')),
    ended_at            TEXT,
    teacher_lat         REAL,
    teacher_lng         REAL,
    allowed_radius      INTEGER DEFAULT 50,
    FOREIGN KEY (timetable_id) REFERENCES timetables(id),
    FOREIGN KEY (faculty_id)   REFERENCES users(id)
);

-- 9. RATE LIMITS (track PIN validation attempts)
CREATE TABLE IF NOT EXISTS rate_limits (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    action          TEXT    NOT NULL,
    attempted_at    TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 10. AUDIT LOG (tracks all admin/faculty actions)
CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    user_role       TEXT    NOT NULL,
    action          TEXT    NOT NULL,
    target_type     TEXT,
    target_id       INTEGER,
    details         TEXT,
    ip_address      TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now'))
);

-- 11. NOTIFICATIONS
CREATE TABLE IF NOT EXISTS notifications (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL,
    title           TEXT    NOT NULL,
    message         TEXT    NOT NULL,
    is_read         INTEGER NOT NULL DEFAULT 0,
    link            TEXT,
    created_at      TEXT    NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- 12. DEVICE LOCKS (NEW TABLE ADDED)
CREATE TABLE IF NOT EXISTS device_locks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      INTEGER,
    student_id      INTEGER,
    device_info     TEXT,
    locked_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_users_email          ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_role            ON users(role);
CREATE INDEX IF NOT EXISTS idx_subjects_code         ON subjects(subject_code);
CREATE INDEX IF NOT EXISTS idx_attendance_date       ON attendance(date);
CREATE INDEX IF NOT EXISTS idx_timetable_day         ON timetables(day_of_week);
CREATE INDEX IF NOT EXISTS idx_timetable_faculty     ON timetables(faculty_id);
CREATE INDEX IF NOT EXISTS idx_batches_join_code     ON batches(join_code);
CREATE INDEX IF NOT EXISTS idx_rate_limits_user      ON rate_limits(user_id, action);
CREATE INDEX IF NOT EXISTS idx_audit_log_user        ON audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user    ON notifications(user_id, is_read);
"""


def init_db(app):
    with app.app_context():
        db = get_db()
        db.executescript(SQL_SCHEMA)
        db.commit()
    app.teardown_appcontext(close_db)


def seed_admin(app):
    from app.utils import hash_password
    with app.app_context():
        db = get_db()
        row = db.execute("SELECT COUNT(*) as c FROM users").fetchone()
        if row["c"] == 0:
            name = app.config["ADMIN_NAME"]
            email = app.config["ADMIN_EMAIL"]
            password = app.config["ADMIN_PASSWORD"]
            db.execute(
                """INSERT INTO users (role, name, email, password_hash, is_verified)
                   VALUES ('Admin', ?, ?, ?, 1)""",
                (name, email, hash_password(password)),
            )
            db.commit()
            app.logger.info(f"Default Admin seeded: {email} / {password}")