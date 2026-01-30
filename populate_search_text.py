import sqlite3
import os
from text_extractor import get_searchable_text

DB_PATH = os.path.join("data", "file_logs.db")

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute("SELECT id, path FROM files")
rows = cur.fetchall()

for fid, path in rows:
    text = get_searchable_text(path)
    cur.execute("UPDATE files SET searchable_text = ? WHERE id = ?", (text, fid))
    print(f"Updated searchable text for file id {fid}")

conn.commit()
conn.close()
print("Finished updating searchable text.")
