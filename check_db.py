import sqlite3
import os

db_path = os.path.abspath("data/file_logs.db")
print("CHECKING DATABASE:", db_path)

conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("\n========== FILES TABLE ==========")
files_rows = cur.execute("SELECT * FROM files").fetchall()
if not files_rows:
    print("(empty)")
else:
    for row in files_rows:
        print(row)

print("\n========== SESSIONS TABLE ==========")
sessions_rows = cur.execute("SELECT * FROM sessions").fetchall()
if not sessions_rows:
    print("(empty)")
else:
    for row in sessions_rows:
        print(row)

print("\n========== ORPHAN SESSION CHECK ==========")

orphans = cur.execute("""
SELECT DISTINCT s.file_id
FROM sessions s
LEFT JOIN files f ON s.file_id = f.id
WHERE f.id IS NULL
""").fetchall()

if not orphans:
    print("✅ No orphan sessions found. Database is consistent.")
else:
    print("❌ Orphan file_ids found in sessions table:")
    for o in orphans:
        print("   file_id =", o[0])

print("\n========== SUMMARY ==========")
print("Files count   :", len(files_rows))
print("Sessions count:", len(sessions_rows))
print("Orphan count  :", len(orphans))

conn.close()
