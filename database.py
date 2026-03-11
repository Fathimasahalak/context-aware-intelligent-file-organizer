import sqlite3
import os
import logging

from config import DB_PATH
logging.info(f"USING DATABASE: {os.path.abspath(DB_PATH)}")


def get_connection(db_path=None):
    path = db_path or DB_PATH
    # Ensure data directory exists
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    # Add timeout for multi-threaded access
    return sqlite3.connect(path, timeout=10.0)


def init_db(db_path=None):
    conn = get_connection(db_path)
    cur = conn.cursor()

    # Base Schema
    cur.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT UNIQUE COLLATE NOCASE,
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
    
    # Schema Migration / Verification
    # Check for columns that might be missing in older DB versions
    cur.execute("PRAGMA table_info(files)")
    columns = [info[1] for info in cur.fetchall()]
    
    required_columns = {
        "cluster_id": "INTEGER",
        "cluster_label": "TEXT",
        "searchable_text": "TEXT"
    }
    
    for col_name, col_type in required_columns.items():
        if col_name not in columns:
            logging.info(f"Migrating database: Adding column '{col_name}' to 'files' table.")
            try:
                cur.execute(f"ALTER TABLE files ADD COLUMN {col_name} {col_type}")
            except Exception as e:
                logging.error(f"Failed to add column {col_name}: {e}")

    conn.commit()
    cur.execute("PRAGMA journal_mode = WAL")
    conn.commit()
    conn.close()
