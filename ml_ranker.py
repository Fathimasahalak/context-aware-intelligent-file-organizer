import time
from datetime import datetime


def normalize(value, max_value):
    if max_value == 0:
        return 0
    return value / max_value


def compute_scores(files):
    """
    files: list of dicts from database
    returns: same list with 'score'
    """

    if not files:
        return []

    max_access = max(f["access_count"] for f in files)
    max_time = max(f["total_time"] for f in files)

    now = time.time()

    for f in files:
        recency_seconds = now - \
            datetime.fromisoformat(f["last_opened"]).timestamp()
        recency_score = 1 / (recency_seconds + 1)

        access_norm = normalize(f["access_count"], max_access)
        time_norm = normalize(f["total_time"], max_time)

        score = (
            0.4 * access_norm +
            0.4 * time_norm +
            0.2 * recency_score
        )

        f["score"] = round(score, 4)

    return files


def rank_files(files):
    return sorted(files, key=lambda x: x["score"], reverse=True)
