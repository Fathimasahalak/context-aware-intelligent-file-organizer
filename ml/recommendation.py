import os
import logging
import numpy as np
from datetime import datetime, timedelta
from collections import Counter
from sklearn.metrics.pairwise import cosine_similarity

from config import DB_PATH
from ml.semantic_search import get_semantic_searcher
from core.database import get_connection

# Updated weights (balanced)
W_RECENCY = 0.30
W_FREQ = 0.35
W_CONTEXT = 0.25
W_CLUSTER = 0.10


def get_smart_priority_files(limit=20):
    conn = get_connection(DB_PATH)
    cur = conn.cursor()

    # 1. Fetch files
    cur.execute("""
        SELECT id, path, access_count, last_opened, cluster_id, total_time 
        FROM files 
        WHERE last_opened IS NOT NULL
    """)
    rows = cur.fetchall()

    if not rows:
        conn.close()
        return []

    # 2. Recent sessions (context)
    cur.execute("""
        SELECT file_id, open_time FROM sessions 
        ORDER BY open_time DESC LIMIT 50
    """)
    sessions = cur.fetchall()

    recent_session_ids = []
    recent_24h_counts = Counter()

    now = datetime.now()
    for fid, t in sessions:
        try:
            t = datetime.fromisoformat(t)
            if len(recent_session_ids) < 5:
                recent_session_ids.append(fid)

            if (now - t) < timedelta(hours=24):
                recent_24h_counts[fid] += 1
        except:
            continue

    conn.close()

    # Build map
    file_map = {r[0]: {
        "path": r[1],
        "count": r[2],
        "last_opened": r[3],
        "cluster_id": r[4],
        "total_time": r[5] or 0
    } for r in rows}

    file_ids = list(file_map.keys())

    # 3. Context similarity
    searcher = get_semantic_searcher()
    id_to_idx = {fid: i for i, fid in enumerate(searcher.file_ids)}

    max_context_similarities = np.zeros(len(searcher.file_ids))
    recent_clusters = []

    decay_weights = [1.0, 0.8, 0.6, 0.4, 0.2]

    if searcher.vectors is not None and len(searcher.vectors) > 0:
        for i, fid in enumerate(recent_session_ids):
            if fid in id_to_idx:
                idx = id_to_idx[fid]
                target_vec = searcher.vectors[idx]

                sims = cosine_similarity([target_vec], searcher.vectors)[0]
                w = decay_weights[min(i, len(decay_weights)-1)]

                max_context_similarities = np.maximum(
                    max_context_similarities,
                    sims * w
                )

                if fid in file_map and file_map[fid]["cluster_id"] is not None:
                    recent_clusters.append(file_map[fid]["cluster_id"])

    # Precompute normalization
    counts = [r[2] for r in rows]
    max_count = max(1, max(counts))

    times = [r[5] or 0 for r in rows]
    max_time = max(1, max(times))

    max_recent = max(1, max(recent_24h_counts.values()) if recent_24h_counts else 1)

    cluster_freq = Counter(recent_clusters)

    scores = []

    for fid in file_ids:
        data = file_map[fid]

        # --- RECENCY (exponential decay) ---
        recency_score = 0.0
        days_diff = 999

        try:
            last_dt = datetime.fromisoformat(data["last_opened"])
            diff = now - last_dt
            days_diff = diff.total_seconds() / 86400.0

            recency_score = np.exp(-days_diff / 3.0)

            # "Just now" boost
            if diff.total_seconds() < 900:
                recency_score = min(1.0, recency_score + 0.2)

        except:
            pass

        # --- FREQUENCY + BURST ---
        freq_part = np.log(1 + data["count"]) / np.log(1 + max_count)
        time_part = np.log(1 + data["total_time"]) / np.log(1 + max_time)

        base_freq = (freq_part * 0.6) + (time_part * 0.4)

        burst = recent_24h_counts.get(fid, 0)
        burst_score = np.log(1 + burst) / np.log(1 + max_recent)

        freq_score = 0.5 * base_freq + 0.5 * burst_score

        # --- CONTEXT (smooth power scaling) ---
        context_score = 0.0
        if fid in id_to_idx:
            idx = id_to_idx[fid]
            raw_sim = max_context_similarities[idx]
            context_score = raw_sim ** 3

        # --- CLUSTER (frequency-based) ---
        cluster_score = 0.0
        if data["cluster_id"] is not None and recent_clusters:
            cluster_score = cluster_freq.get(
                data["cluster_id"], 0
            ) / len(recent_clusters)

        # --- FINAL SCORE ---
        final_score = (
            W_RECENCY * recency_score +
            W_FREQ * freq_score +
            W_CONTEXT * context_score +
            W_CLUSTER * cluster_score
        )

        # Boost recent session files
        if fid in recent_session_ids:
            final_score = min(1.0, final_score + 0.15)

        # Penalize stale files
        if days_diff > 30:
            final_score *= 0.7

        scores.append({
            "path": data["path"],
            "score": final_score,
            "last_opened": data["last_opened"],
            "debug": {
                "recency": round(recency_score, 3),
                "freq": round(freq_score, 3),
                "context": round(context_score, 3),
                "cluster": round(cluster_score, 3)
            }
        })

    # Sort
    scores.sort(key=lambda x: x["score"], reverse=True)

    return scores[:limit]