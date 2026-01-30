import sqlite3
import os

DB_PATH = os.path.join("data", "file_logs.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("DELETE FROM sessions")
cur.execute("DELETE FROM files")

conn.commit()
conn.close()

print("Database cleared successfully.")
