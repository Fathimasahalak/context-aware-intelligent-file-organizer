from database import get_connection


def fetch_files():
    conn = get_connection()
    cur = conn.cursor()

    rows = cur.execute("""
        SELECT id, path, access_count, total_time, last_opened
        FROM files
    """).fetchall()

    conn.close()

    files = []

    for r in rows:
        files.append({
            "id": r[0],
            "path": r[1],
            "access_count": r[2],
            "total_time": r[3],
            "last_opened": r[4]
        })

    return files
