# AttendX — Anti-Proxy Web Attendance Portal

A high-security, web-based attendance and class management system that eliminates "buddy punching" (proxy attendance) using **time-based dual-key tokens** and **live selfie verification**, without relying on specialized external hardware.

Built with **Python / Flask**, **SQLite**, and **vanilla HTML/CSS/JS** — no heavy frontend frameworks, no ORM dependencies. Runs with just `pip install flask python-dotenv`.

---

## How It Works

### The Dual-Key Anti-Cheat System

When a Faculty member starts a class session, the system generates two simultaneous credentials projected on the classroom screen:

1. **A 4-digit PIN** displayed in large text
2. **A QR code** containing a signed JSON payload

Both credentials **refresh every 15 seconds** with a visible countdown timer. When the timer hits zero, the old tokens are **instantly invalidated server-side** — they can never be reused.

**Entry (High Friction):** Students submit the current PIN or scan the QR, then must snap a **live selfie** via the HTML5 Camera API. This proves physical presence in the classroom at that exact moment.

**Exit (Low Friction):** Students only need the PIN/QR — no selfie required — preventing bottlenecks at the door.

**Audit Roulette:** The backend randomly flags **5%** of all selfies for visual review on the Faculty dashboard. Students don't know which submissions get flagged, creating a psychological deterrent against spoofing.

### Why This Stops Proxy Attendance

| Attack Vector | Defense |
|---|---|
| Friend shares the PIN via text | PIN expires in 15 seconds — by the time it arrives, it's invalid |
| Screenshot of QR code | QR payload includes a timestamp + HMAC signature; expired codes are rejected server-side |
| Pre-recorded selfie | Selfie is captured live via Camera API at the moment of submission, tied to the current token |
| Replay attack | Each token cycle has a unique nonce; old tokens are overwritten in the database |

---

## Features by Role

### Admin (The Architect)
- Manage Faculty accounts (add/edit/delete with temporary passwords)
- Manage Students (view, assign to Batches, delete)
- Create and manage Batches and Subjects
- Build the Master Timetable with **conflict detection** (prevents double-booking batches or faculty)
- Review and approve/reject Faculty schedule change requests

### Faculty (The Facilitator)
- Dashboard showing today's scheduled classes with one-click session start
- **Projector Display** — full-screen QR + PIN with 15-second countdown timer
- **Live Roster** — auto-refreshing attendance list during active sessions
- **Manual Override** — quick-search to mark a student present if their phone dies
- Phase switching (Entry → Exit) during session
- Submit Cancel/Reschedule requests to Admin
- Attendance history with **Audit Roulette** flagged selfie review panel

### Student (The End-User)
- Dashboard showing today's classes with live session indicators
- **Check-in page** with two input methods:
  - **PIN Entry** — 4-digit auto-advancing input boxes
  - **QR Scanner** — uses device camera + BarcodeDetector API
- **Selfie Capture** — front camera opens automatically after entry validation
- Weekly timetable view
- Personal attendance history with percentage tracking

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, Flask 3.x |
| Database | SQLite (dev) — designed for PostgreSQL/MySQL migration |
| Frontend | Vanilla HTML5, CSS3, JavaScript (no frameworks) |
| Auth | Session-based with Werkzeug scrypt password hashing |
| QR Signing | HMAC-SHA256 with app secret key |
| Camera | HTML5 `getUserMedia` + `BarcodeDetector` APIs |
| Email | Stubbed to console (dev); SMTP-ready for production |

**Minimal dependencies:** The entire app runs on `flask` and `python-dotenv`. Everything else (auth, DB, password hashing, QR generation) uses Flask/Werkzeug built-ins and Python stdlib.

---

## Project Structure

```
attendance_project/
├── run.py                          # Entry point — python run.py
├── requirements.txt                # pip dependencies
├── .env                            # Environment config (SECRET_KEY, SMTP, etc.)
│
└── app/
    ├── __init__.py                 # App factory (create_app)
    ├── config.py                   # Settings loaded from .env
    ├── models.py                   # SQLite schema (8 tables) + DB helpers
    ├── utils.py                    # Password hashing, OTP, role decorators
    │
    ├── routes/
    │   ├── __init__.py             # Blueprint registration
    │   ├── auth_routes.py          # Login, signup, OTP verify, password reset
    │   ├── admin_routes.py         # Full CRUD for users/batches/subjects/timetable
    │   ├── faculty_routes.py       # Dashboard, session page, attendance, requests
    │   ├── student_routes.py       # Dashboard, check-in, timetable, history
    │   └── api_routes.py           # JSON API for Dual-Key engine + roster
    │
    ├── services/
    │   ├── dual_key_engine.py      # Token generation, validation, QR signing
    │   ├── email_service.py        # SMTP sender (dev mode logs to console)
    │   └── scheduler.py            # (Planned) APScheduler daily digest
    │
    ├── static/
    │   ├── css/style.css           # Complete design system (~1400 lines)
    │   ├── js/dual_key.js          # Faculty projector polling engine
    │   ├── js/student_checkin.js   # Student PIN/QR/selfie handler
    │   └── uploads/selfies/        # Stored selfie images
    │
    └── templates/
        ├── base.html               # Root layout (fonts, flash messages)
        ├── dashboard_base.html     # Sidebar + main content layout
        ├── auth/                   # login, signup, verify_otp, forgot/reset password
        ├── admin/                  # dashboard, manage_* (6 pages)
        ├── faculty/                # dashboard, class_session, timetable, attendance, requests
        └── student/                # dashboard, checkin, timetable, attendance
```

---

## Database Schema

8 tables with enforced foreign keys and constraints:

| Table | Purpose |
|---|---|
| `users` | All roles (Admin/Faculty/Student) with batch assignment |
| `batches` | Class groups (e.g., CSE-2024-A) |
| `subjects` | Course catalog with unique codes |
| `timetables` | Master schedule linking subject + batch + faculty + day/time |
| `attendance` | Per-student per-class per-date records with selfie paths |
| `active_sessions` | Live Dual-Key sessions with current PIN/QR + phase |
| `otp_tokens` | Time-expiring 6-digit codes for signup/password reset |
| `schedule_requests` | Faculty → Admin cancel/reschedule workflow |

Key constraints: unique attendance per student/class/date, timetable conflict detection, foreign key cascades.

---

## Getting Started

### Prerequisites
- Python 3.10 or higher
- Windows 11 (or any OS — the app is cross-platform)

### Installation

```bash
# Clone or copy the project
cd attendance_project

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# Install dependencies (minimum)
pip install flask python-dotenv

# Optional: better QR codes (scannable by phone cameras)
pip install qrcode[pil] Pillow
```

### Configuration

Edit `.env` to set your secret key:

```env
SECRET_KEY=your-random-64-character-string-here
```

For email (optional — OTP codes print to terminal in dev mode):

```env
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-gmail-app-password
MAIL_DEFAULT_SENDER=your-email@gmail.com
```

Then flip `DEV_MODE = False` in `app/services/email_service.py`.

### Run

```bash
python run.py
```

Open **http://127.0.0.1:5000** in your browser.

### Default Admin Account

On first launch, the system auto-seeds:

| Email | Password |
|---|---|
| `admin@attendance.local` | `admin123` |

**Change this immediately in production.**

---

## Quick Test Walkthrough

1. **Admin Setup**
   - Login as admin → Create a Batch (e.g., "CSE-2024-A")
   - Create a Subject (e.g., CS101 — Data Structures)
   - Add a Faculty member (temporary password auto-set)
   - Add a Timetable slot for today's day of week

2. **Student Registration**
   - Open an incognito window → Sign Up
   - Check terminal for the 6-digit OTP → Verify
   - Admin assigns student to the batch

3. **Run a Session**
   - Faculty logs in → Dashboard → Start Session on today's class
   - The projector display shows QR + PIN with 15-second countdown
   - Student logs in → Dashboard → Mark Entry → Type PIN → Snap selfie
   - Faculty clicks "Switch to EXIT" → Student marks exit (no selfie)
   - Faculty clicks "End Session"

4. **Review**
   - Faculty → Attendance page shows records + flagged selfies
   - Student → My Attendance shows their history
   - Admin → Dashboard shows system-wide stats

---

## API Endpoints

All endpoints return JSON and require session authentication.

| Method | Endpoint | Role | Description |
|---|---|---|---|
| `POST` | `/api/session/start` | Faculty | Start a Dual-Key session |
| `POST` | `/api/session/end` | Faculty | End session, invalidate all tokens |
| `POST` | `/api/session/switch-phase` | Faculty | Toggle entry ↔ exit |
| `GET` | `/api/session/<id>/token` | Faculty | Poll for fresh PIN + QR (every 14s) |
| `POST` | `/api/session/<id>/validate` | Student | Submit PIN or QR for validation |
| `POST` | `/api/session/<id>/selfie` | Student | Upload base64 selfie after entry |
| `GET` | `/api/session/<id>/roster` | Faculty | Live attendance roster |
| `POST` | `/api/session/<id>/override` | Faculty | Manual check-in for a student |

---

## Security Design

**Password Storage:** Werkzeug scrypt hashing (ships with Flask — no extra dependencies).

**Token Lifecycle:** PIN + QR are generated server-side, stored in `active_sessions`, and overwritten every 15 seconds. Old tokens cannot be replayed — the DB only stores the *current* pair.

**QR Payload Signing:** Each QR encodes a JSON object with `session_id`, `pin`, `timestamp`, `nonce`, and an `HMAC-SHA256` signature truncated to 16 hex chars. The server verifies the signature before accepting.

**OTP Security:** 6-digit codes expire after 5 minutes. Requesting a new OTP invalidates all previous unused codes. The forgot-password flow never reveals whether an email is registered.

**Batch Enforcement:** Students can only check into classes assigned to their batch. The server validates `user.batch_id == timetable.batch_id` before recording attendance.

**Audit Roulette:** 5% of selfies are randomly flagged (`flagged_for_audit = True`) and surfaced on the Faculty dashboard for visual review.

---

## Roadmap

- [ ] **APScheduler Daily Digest** — 8 AM email with each person's schedule for the day
- [ ] **Email Notifications** — auto-email affected students when Admin approves schedule changes
- [ ] **PostgreSQL Migration** — swap SQLite for production database
- [ ] **Rate Limiting** — throttle API endpoints to prevent brute-force PIN guessing
- [ ] **Selfie AI Verification** — optional face-match against student profile photo
- [ ] **Export** — CSV/PDF attendance reports for Admin
- [ ] **PWA Support** — installable mobile app via service worker

---

## License

This project is for educational purposes. See your institution's policies before deploying in a production environment.
