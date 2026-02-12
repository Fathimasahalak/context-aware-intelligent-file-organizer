import sqlite3
import os
import logging

from config import DB_PATH
logging.info(f"USING DATABASE: {os.path.abspath(DB_PATH)}")


def get_connection(db_path=None):
    path = db_path or DB_PATH
    return sqlite3.connect(path)


def init_db(db_path=None):
    conn = get_connection(db_path)
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
    cur.execute("PRAGMA journal_mode = DELETE")
    conn.commit()
    conn.close()
