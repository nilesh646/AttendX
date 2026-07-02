import sqlite3

# Connect to your existing database
conn = sqlite3.connect('attendance.db')
cursor = conn.cursor()

# Run the table creation command
cursor.execute('''
CREATE TABLE IF NOT EXISTS device_locks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    device_id TEXT NOT NULL,
    locked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(session_id, student_id),
    UNIQUE(session_id, device_id)
)
''')

conn.commit()
conn.close()
print("✅ Success: device_locks table created permanently!")