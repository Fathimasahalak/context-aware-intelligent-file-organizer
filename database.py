import sqlite3
import os

DB_PATH = os.path.join("data", "file_logs.db")
print("USING DATABASE:", os.path.abspath(DB_PATH))


def get_connection():
    return sqlite3.connect(DB_PATH)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE,
        access_count INTEGER DEFAULT 0,
        total_time INTEGER DEFAULT 0,
        last_opened TEXT,
        cluster_id INTEGER,
        cluster_label TEXT,
        searchable_text TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        file_id INTEGER,
        open_time TEXT,
        close_time TEXT,
        duration INTEGER
    )
    """)

    conn.commit()
    conn.close()
