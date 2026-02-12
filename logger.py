import time
import os
from datetime import datetime
from database import get_connection

open_sessions = {}


def start_file_session(file_path):
    # Normalize path to ensure consistency
    file_path = os.path.normpath(os.path.abspath(file_path))
    
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM files WHERE lower(path) = lower(?)", (file_path,))
    row = cur.fetchone()

    if row is None:
        # Note: searchable_text should be handled by the caller (app.py) 
        # to keep logger.py focused on session tracking
        cur.execute(
            "INSERT INTO files(path, access_count, total_time, last_opened) VALUES (?,0,0,?)",
            (file_path, datetime.now().isoformat())
        )
        file_id = cur.lastrowid
    else:
        file_id = row[0]

    conn.commit()
    conn.close()

    open_sessions[file_path] = {
        "file_id": file_id,
        "start_time": time.time()
    }


def end_file_session(file_path):
    file_path = os.path.normpath(os.path.abspath(file_path))
    
    if file_path not in open_sessions:
        # Fallback: if no start was recorded, just log a quick access
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("UPDATE files SET access_count = access_count + 1, last_opened = ? WHERE lower(path) = lower(?)", 
                   (datetime.now().isoformat(), file_path))
        conn.commit()
        conn.close()
        return

    session = open_sessions[file_path]
    start_time = session["start_time"]
    duration = max(1, int(time.time() - start_time))
    file_id = session["file_id"]

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO sessions(file_id, open_time, close_time, duration)
        VALUES (?, ?, ?, ?)
    """, (
        file_id,
        datetime.fromtimestamp(start_time).isoformat(),
        datetime.now().isoformat(),
        duration
    ))

    cur.execute("""
        UPDATE files
        SET access_count = access_count + 1,
            total_time = total_time + ?,
            last_opened = ?
        WHERE id = ?
    """, (duration, datetime.now().isoformat(), file_id))

    conn.commit()
    conn.close()

    del open_sessions[file_path]
