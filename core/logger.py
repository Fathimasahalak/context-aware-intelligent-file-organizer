import time
import os
from datetime import datetime
from core.database import get_connection

open_sessions = {}


def start_file_session(file_path):
    # Normalize path to ensure consistency
    file_path = os.path.normpath(os.path.abspath(file_path))
    
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM files WHERE lower(path) = lower(?)", (file_path,))
    row = cur.fetchone()

    now_str = datetime.now().isoformat()
    if row is None:
        # Note: searchable_text should be handled by the caller (app.py) 
        # to keep logger.py focused on session tracking
        cur.execute(
            "INSERT INTO files(path, access_count, total_time, last_opened) VALUES (?,1,0,?)",
            (file_path, now_str)
        )
        file_id = cur.lastrowid
    else:
        file_id = row[0]
        # UPDATE immediately when session starts for UI accuracy
        cur.execute("""
            UPDATE files 
            SET last_opened = ?, 
                access_count = access_count + 1 
            WHERE id = ?
        """, (now_str, file_id))

    conn.commit()
    conn.close()

    open_sessions[file_path] = {
        "file_id": file_id,
        "start_time": time.time(),
        "iso_start": now_str
    }


def end_file_session(file_path):
    file_path = os.path.normpath(os.path.abspath(file_path))
    
    if file_path not in open_sessions:
        return

    session = open_sessions[file_path]
    start_time = session["start_time"]
    iso_start = session["iso_start"]
    duration = max(1, int(time.time() - start_time))
    file_id = session["file_id"]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sessions(file_id, open_time, close_time, duration)
        VALUES (?, ?, ?, ?)
    """, (
        file_id,
        iso_start,
        datetime.now().isoformat(),
        duration
    ))

    # Only update duration on close, access_count/last_opened were handled on start
    cur.execute("""
        UPDATE files
        SET total_time = total_time + ?
        WHERE id = ?
    """, (duration, file_id))

    conn.commit()
    conn.close()

    del open_sessions[file_path]


def remove_file_session(file_path):
    """Clean up any active session for a deleted file."""
    file_path = os.path.normpath(os.path.abspath(file_path))
    if file_path in open_sessions:
        del open_sessions[file_path]
