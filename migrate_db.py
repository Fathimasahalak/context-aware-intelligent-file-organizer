import sqlite3
import os

DB_PATH = os.path.join("data", "file_logs.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Add columns if not exist
try:
    cur.execute("ALTER TABLE files ADD COLUMN cluster_id INTEGER")
except:
    pass

try:
    cur.execute("ALTER TABLE files ADD COLUMN cluster_label TEXT")
except:
    pass

conn.commit()
conn.close()

print("Database migration complete.")
