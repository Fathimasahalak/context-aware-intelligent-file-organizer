import sqlite3
import os

DB_PATH = os.path.join("data", "file_logs.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

try:
    cur.execute("ALTER TABLE files ADD COLUMN searchable_text TEXT")
except sqlite3.OperationalError:
    # Column already exists
    pass

conn.commit()
conn.close()

print("Searchable text column ensured.")
