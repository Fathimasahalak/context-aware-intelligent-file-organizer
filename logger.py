import time
from datetime import datetime
from database import get_connection
from text_extractor import get_searchable_text

open_sessions = {}


def start_file_session(file_path):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT id FROM files WHERE path = ?", (file_path,))
    row = cur.fetchone()

    if row is None:
        searchable_text = get_searchable_text(file_path)
        cur.execute(
            "INSERT INTO files(path, access_count, total_time, last_opened, searchable_text) VALUES (?,0,0,?,?)",
            (file_path, datetime.now().isoformat(), searchable_text)
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
    if file_path not in open_sessions:
        return

    session = open_sessions[file_path]
    start_time = session["start_time"]
    duration = int(time.time() - start_time)
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
