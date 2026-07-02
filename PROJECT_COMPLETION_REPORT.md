# Project Completion Report

## AttendX — Anti-Proxy Web Attendance Portal

**Version:** 2.0  
**Date:** March 2026  
**Platform:** Windows 11 / Python / Flask  
**Status:** MVP Complete — Ready for Deployment

---

## 1. Project Overview

AttendX is a high-security, web-based attendance and class management system designed for educational institutions. It solves the persistent problem of **proxy attendance (buddy punching)** — where one student marks attendance on behalf of another — by combining time-based cryptographic tokens with live biometric verification.

The system requires no specialized hardware. It operates entirely through standard web browsers, using a classroom projector to display rotating credentials and student smartphones to verify presence through selfie capture.

**The core innovation** is the Dual-Key Engine: a QR code and 4-digit PIN that refresh every 15 seconds with HMAC-SHA256 signing, making it mathematically impossible to share valid credentials before they expire. Combined with mandatory live selfie verification on entry and a random audit system, the platform creates multiple layers of anti-cheat protection that work together to ensure only physically present students can mark attendance.

---

## 2. Core Features

### Authentication & Onboarding
- Universal login for all three roles (Admin, Faculty, Student) with automatic role-based dashboard redirection
- Student self-registration with email OTP verification (6-digit code, 5-minute expiry)
- Forgot password flow with OTP-based identity verification
- Change password from any dashboard without requiring email/SMTP
- Password strength meter with real-time visual feedback
- Session timeout configurable via environment variables (default 8 hours)

### Admin Dashboard (The Architect)
- System-wide statistics: Admins, Faculty, Students, Batches, Subjects, Pending Requests
- Multi-admin support with full CRUD — any admin can create other admins
- Safety guards: cannot delete yourself, cannot delete the last admin
- Faculty management: add with temporary password, edit, delete with full cascade cleanup
- Student management: view all, inline batch assignment dropdown, delete with cascade
- Batch management with **Google Classroom-style join codes**: auto-generated 6-character alphanumeric codes, regenerate, enable/disable
- Subject management with unique codes and timetable usage tracking
- Master timetable builder with **double conflict detection** (batch overlap + faculty overlap)
- Schedule request handling: approve/reject with automatic email notifications to affected students
- **Attendance reports** with filters (batch, subject, date range) and CSV export
- **Audit log**: every action tracked with user, role, IP address, timestamp
- Input sanitization on all form fields to prevent XSS

### Faculty Dashboard (The Facilitator)
- Time-aware greeting with today's scheduled classes
- One-click session start with LIVE indicator on dashboard
- **Projector Display**: QR code + 4-digit PIN side by side, 15-second countdown timer with color transitions (blue → orange → red), animated PIN refresh, phase label (ENTRY/EXIT)
- **Live Roster**: auto-refreshes every 5 seconds showing entry/exit times, verification method, audit flags
- **Manual Override**: search bar to mark students present when their phone fails (recorded as "Faculty_Override")
- Phase switching: Entry (high friction + selfie) → Exit (low friction, no selfie)
- Weekly timetable view with today highlighted
- Attendance history with searchable records and CSV export
- **Audit Roulette panel**: flagged selfie thumbnails displayed alongside student profile photos for visual comparison
- Schedule change requests: submit Cancel/Reschedule with reason, track approval status
- Automatic notification to admins when requests are submitted

### Student Dashboard (The End-User)
- Attendance summary: Present count, Absent count, overall percentage
- Today's classes with smart status flow: "Not started" → "● LIVE + Mark Entry" → "✓ Entry Recorded" → "✓ Complete"
- **Join Class page**: enter 6-character alphanumeric code to self-enroll in a batch (like Google Classroom)
- Leave batch option with confirmation
- Check-in page with two input methods:
  - PIN entry: 4 auto-advancing digit boxes with paste support
  - QR scanner: rear camera via BarcodeDetector API
- **Selfie capture** (entry only): front camera opens automatically after valid token, circular shutter button, preview with retake option
- Exit check-in: token only, no selfie (prevents door bottlenecks)
- Already-recorded detection prevents duplicate submissions
- Batch enforcement: blocked from checking into classes their batch isn't enrolled in
- Weekly timetable and personal attendance history with CSV export
- Notification bell with unread count
- Change password from sidebar

### Dual-Key Anti-Cheat Engine
- 4-digit random PIN regenerated every 15 seconds server-side
- HMAC-SHA256 signed QR payload containing session ID, PIN, Unix timestamp, random nonce, and truncated signature
- Server-side token validation: checks current PIN match, token age (15s + 2s network grace), QR signature integrity
- Tampered QR detection: altered payloads rejected via constant-time comparison
- Nonce per refresh cycle prevents cross-cycle replay attacks
- Instant invalidation: ending a session wipes PIN and QR data from the database
- **Audit Roulette**: 5% of selfies randomly flagged for visual review (configurable)
- **Late marking**: auto-marks "Late" if entry occurs after configurable threshold past class start time
- **Rate limiting**: 5 PIN attempts per 60 seconds per student, then HTTP 429 lockout
- **Geolocation verification** (optional): GPS check against campus coordinates with configurable radius

### Notification System
- Faculty receives notifications when students check in
- Admins receive notifications when faculty submit schedule requests
- Students receive notifications when schedule changes are approved/rejected
- Unread count badge in sidebar navigation
- Dedicated notifications page with read/unread status

### Reporting & Export
- Admin: filtered attendance reports (by batch, subject, date range) with summary statistics
- Admin: one-click CSV export with all filters applied
- Faculty: CSV export of all attendance records for their classes
- Student: CSV export of personal attendance history

### Audit & Accountability
- Full audit log tracking: logins, user creation/deletion, session starts/ends, manual overrides, schedule requests, batch joins
- Each entry records: user ID, role, action, target type/ID, details, IP address, timestamp
- Searchable admin page with 200 most recent entries

---

## 3. Technology Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| **Backend** | Python 3.10+, Flask 3.x | Web framework, routing, session management |
| **Database** | SQLite 3 (raw, no ORM) | 11 tables with foreign keys, indexes, constraints |
| **Frontend** | HTML5, CSS3, Vanilla JavaScript | Zero frontend framework dependencies |
| **Auth** | Werkzeug scrypt (ships with Flask) | Password hashing, no extra packages |
| **QR Signing** | HMAC-SHA256 (Python hashlib/hmac) | Cryptographic token integrity |
| **QR Images** | qrcode + Pillow (optional) | Scannable QR code generation |
| **Camera** | HTML5 getUserMedia API | Selfie capture and QR scanning |
| **QR Scanning** | BarcodeDetector API (browser) | Client-side QR decoding |
| **Config** | python-dotenv | Environment variable management |
| **Styling** | Custom CSS design system | 1,515 lines, CSS variables, responsive |
| **Fonts** | Google Fonts (DM Sans, Outfit, JetBrains Mono) | Typography |

**Minimal dependencies:** The entire application runs on just `flask` and `python-dotenv`. The QR code library (`qrcode` + `Pillow`) is optional — the engine falls back to an SVG pattern without it.

---

## 4. How It Works

### Authentication Flow
1. Students self-register with email + password
2. A 6-digit OTP is generated, stored with a 5-minute expiry, and printed to the terminal (or sent via SMTP in production)
3. After OTP verification, the account is activated
4. On login, the server validates credentials against scrypt hashes, writes user info into Flask's signed session cookie, and redirects to the role-appropriate dashboard

### Classroom Join Flow
1. Admin creates a batch → system auto-generates a unique 6-character code (e.g., `BVCM3H`)
2. Admin shares the code with students (verbally, on board, via message)
3. Student logs in → clicks "Join Class" → enters the code
4. Server validates: code exists, joining is enabled, and assigns the student to that batch
5. Student immediately sees their timetable and can check into live sessions

### Attendance Session Flow
1. Faculty opens their dashboard, sees today's scheduled classes
2. Faculty clicks "Start Session" → backend creates an `active_sessions` row with a fresh PIN + signed QR payload
3. The projector page polls `GET /api/session/<id>/token` every 14 seconds, receiving a new PIN + QR image each time
4. A countdown timer ticks from 15 to 0, then the frontend displays the new tokens
5. **Student Entry**: Student opens their dashboard, sees the LIVE class, clicks "Mark Entry", types the 4-digit PIN (or scans QR), and the server validates:
   - Token matches the current value in the database
   - Token age is ≤ 17 seconds (15 + 2s grace)
   - QR signature is valid (HMAC check)
   - Student belongs to the correct batch
   - Rate limit not exceeded (5 attempts per minute)
6. If valid: attendance recorded as "Present" (or "Late" if past threshold), selfie camera opens
7. 5% of selfies are randomly flagged for audit review
8. Faculty switches to EXIT phase → students submit token only (no selfie)
9. Faculty clicks "End Session" → all tokens wiped from database, session closed

### Security Layers
- **15-second token expiry**: PIN shared via text arrives after it's already invalid
- **HMAC signing**: QR payload cannot be forged without the server's secret key
- **Nonce per cycle**: prevents replaying tokens from a previous refresh
- **Live selfie**: proves physical presence at the moment of submission
- **Audit roulette**: 5% random flagging creates psychological deterrent
- **Rate limiting**: prevents brute-forcing the 10,000 possible PINs
- **Batch enforcement**: server verifies enrollment before recording attendance
- **Geolocation** (optional): GPS check against campus coordinates

---

## 5. Installation & Setup

### Prerequisites
- Python 3.10 or higher installed
- Windows 11 (or any OS — cross-platform)

### Step-by-Step

```bash
# 1. Extract the project
cd C:\Projects\attendx_v2

# 2. Create virtual environment
python -m venv venv

# 3. Activate it
venv\Scripts\activate

# 4. Install dependencies
pip install flask python-dotenv qrcode[pil] Pillow

# 5. (Optional) Edit .env before first run
#    Change ADMIN_EMAIL, ADMIN_PASSWORD, SECRET_KEY

# 6. Run
python run.py
```

Open `http://127.0.0.1:5000` in your browser.

### Default Admin
- **Email:** `admin@attendance.local`
- **Password:** `admin123`
- These are configurable in `.env` before first boot

### OTP Codes
In development mode, OTP codes print directly to the terminal window. For real email delivery, configure SMTP credentials in `.env` and set `DEV_MODE = False` in `app/services/email_service.py`.

### Quick Test Flow
1. Login as Admin → Create Batch (note the join code) → Create Subject → Add Faculty → Add Timetable slot for today
2. Open incognito → Student Signup → Verify OTP from terminal → Join Class with code
3. Faculty login → Start Session → QR + PIN displayed
4. Student → Mark Entry → Type PIN → Snap selfie
5. Faculty → Switch to Exit → Student marks exit
6. Faculty → End Session → Check attendance history

---

## 6. Future Improvements

### High Priority
- **Face recognition**: Compare entry selfie against stored profile photo using a lightweight ML model (e.g., face_recognition library) to auto-detect spoofing
- **WebSocket real-time updates**: Replace polling with WebSocket connections for instant roster updates and notification delivery
- **PostgreSQL migration**: Production-ready database with connection pooling, proper migrations, and backup scheduling
- **Automated test suite**: Convert all integration tests to pytest with fixtures, runnable via `pytest tests/` in CI/CD

### Medium Priority
- **Docker deployment**: `Dockerfile` + `docker-compose.yml` for one-command cloud deployment
- **PWA (Progressive Web App)**: Service worker + manifest.json so students can install the app on their phone home screen
- **Batch analytics dashboard**: Visual charts (Chart.js) showing attendance trends per batch, subject, and time period
- **Bulk CSV import**: Upload a CSV of student names/emails to create accounts and assign batches in one step
- **Semester management**: Archive old semesters, create new ones with fresh timetables while preserving historical data
- **Multi-language support**: i18n framework for Hindi, regional languages

### Nice to Have
- **Dark mode toggle**: CSS variables already support theming, just needs a preference switch
- **IP allowlisting**: Restrict check-ins to campus network IP ranges
- **Global search**: Universal search bar across students, faculty, subjects, batches
- **Scheduled reports**: Auto-email weekly attendance summaries to department heads
- **Parent portal**: Read-only attendance view for parents/guardians with email alerts on absences
- **API documentation**: Swagger/OpenAPI spec for the JSON endpoints
- **Mobile-optimized projector view**: Fullscreen mode for tablets used as session displays

---

## Project Statistics

| Metric | Count |
|--------|-------|
| Total Files | 54 |
| Python Code | 2,859 lines |
| HTML Templates | 3,085 lines |
| CSS | 1,515 lines |
| JavaScript | 465 lines |
| **Total Code** | **7,924 lines** |
| URL Routes | 67 |
| Database Tables | 11 |
| API Endpoints | 9 (JSON) |
| User Roles | 3 (Admin, Faculty, Student) |

---

*Report generated: March 2026*  
*Built with: Python, Flask, SQLite, HTML/CSS/JS*  
*Architecture: Monolith MVP, session-based auth, raw SQL*
