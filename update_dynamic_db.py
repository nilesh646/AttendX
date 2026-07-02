# import sqlite3

# conn = sqlite3.connect("attendance.db")
# cursor = conn.cursor()

# try:
#     cursor.execute("ALTER TABLE active_sessions ADD COLUMN teacher_lat REAL;")
#     cursor.execute("ALTER TABLE active_sessions ADD COLUMN teacher_lng REAL;")
#     cursor.execute("ALTER TABLE active_sessions ADD COLUMN allowed_radius INTEGER NOT NULL DEFAULT 50;")
#     conn.commit()
#     print("Successfully added Dynamic Geolocation to active_sessions!")
# except sqlite3.OperationalError as e:
#     print(f"Notice: {e}")

# conn.close()
import sqlite3
import os

# Ensure this points to where your database actually lives
# If it's inside an 'instance' folder, change this to "instance/attendance.db"
DB_PATH = "attendance.db" 

if not os.path.exists(DB_PATH):
    print(f"❌ Could not find {DB_PATH}! Please check the path.")
    exit()

db = sqlite3.connect(DB_PATH)
cursor = db.cursor()

print("🛠️ Upgrading Database to v2.7...")

# 1. Add missing columns to the attendance table
new_columns = [
    "device_info TEXT",
    "geo_lat REAL",
    "geo_lng REAL",
    "geo_accuracy REAL",
    "geo_distance REAL",
    "geo_trust_score INTEGER",
    "geo_verdict TEXT"
]

for col in new_columns:
    try:
        cursor.execute(f"ALTER TABLE attendance ADD COLUMN {col}")
        print(f"✅ Added column: {col.split()[0]}")
    except sqlite3.OperationalError:
        print(f"⏭️ Column {col.split()[0]} already exists, skipping.")

# 2. Create the new hardware locks table
cursor.execute("""
CREATE TABLE IF NOT EXISTS device_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER,
    student_id INTEGER,
    device_info TEXT,
    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")
print("✅ Ensured 'device_locks' table exists.")

# 3. Ensure active_sessions has the teacher location columns
session_columns = [
    "teacher_lat REAL",
    "teacher_lng REAL",
    "allowed_radius INTEGER DEFAULT 50"
]

for col in session_columns:
    try:
        cursor.execute(f"ALTER TABLE active_sessions ADD COLUMN {col}")
        print(f"✅ Added column to active_sessions: {col.split()[0]}")
    except sqlite3.OperationalError:
        print(f"⏭️ Column {col.split()[0]} already exists in active_sessions, skipping.")


db.commit()
db.close()
print("\n🎉 Database upgrade complete! You can now start the server.")