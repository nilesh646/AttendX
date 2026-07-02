import sqlite3

conn = sqlite3.connect("attendance.db")
cursor = conn.cursor()

cursor.execute("SELECT sql FROM sqlite_master WHERE name='active_sessions'")
result = cursor.fetchone()

print(result[0] if result else "Table not found")