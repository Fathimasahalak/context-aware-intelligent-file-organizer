import os
import logging
import numpy as np
from datetime import datetime
from collections import Counter
from sklearn.metrics.pairwise import cosine_similarity

from config import DB_PATH
from ml.semantic_search import get_semantic_searcher
from core.database import get_connection

# Weights for the hybrid score
W_RECENCY = 0.35
W_FREQ = 0.20
W_CONTEXT = 0.30
W_CLUSTER = 0.15

def get_smart_priority_files(limit=20):
    """
    Returns a list of files sorted by an improved Smart Priority Score.
    Score = Recency + Frequency + Context + Cluster Affinity
    """
    conn = get_connection(DB_PATH)
    cur = conn.cursor()
    
    # 1. Get all files with stats
    cur.execute("""
        SELECT id, path, access_count, last_opened, cluster_id, total_time 
        FROM files 
        WHERE last_opened IS NOT NULL
    """)
    rows = cur.fetchall()
    
    if not rows:
        conn.close()
        return []

    # 2. Get recent sessions for multi-file context (last 5 unique files)
    cur.execute("""
        SELECT DISTINCT file_id FROM sessions 
        ORDER BY open_time DESC LIMIT 5
    """)
    recent_session_ids = [r[0] for r in cur.fetchall()]
    
    # Fallback to last_opened if no sessions recorded
    if not recent_session_ids:
        cur.execute("SELECT id FROM files ORDER BY last_opened DESC LIMIT 3")
        recent_session_ids = [r[0] for r in cur.fetchall()]
        
    conn.close()

    # Local Cache of data
    file_map = {r[0]: {
        "path": r[1], 
        "count": r[2], 
        "last_opened": r[3], 
        "cluster_id": r[4],
        "total_time": r[5] or 0
    } for r in rows}
    file_ids = list(file_map.keys())
    
    # 3. Calculate Contextual Vector (Average of recent embeddings)
    searcher = get_semantic_searcher()
    id_to_idx = {fid: i for i, fid in enumerate(searcher.file_ids)}
    
    context_vector = None
    recent_clusters = []
    
    weights = [1.0, 0.8, 0.6, 0.4, 0.2] # Decay weight for context
    valid_vectors = []
    
    for i, fid in enumerate(recent_session_ids):
        if fid in id_to_idx:
            idx = id_to_idx[fid]
            if searcher.vectors is not None and idx < len(searcher.vectors):
                vec = searcher.vectors[idx]
                w = weights[min(i, len(weights)-1)]
                valid_vectors.append(vec * w)
                
                # Collect clusters for affinity
                if fid in file_map and file_map[fid]["cluster_id"] is not None:
                    recent_clusters.append(file_map[fid]["cluster_id"])

    if valid_vectors:
        context_vector = np.mean(valid_vectors, axis=0)

    # Calculate similarities to context
    similarities = None
    if context_vector is not None and searcher.vectors is not None and len(searcher.vectors) > 0:
        similarities = cosine_similarity([context_vector], searcher.vectors)[0]
    
    if similarities is None:
        num_vectors = len(searcher.vectors) if searcher.vectors is not None else 0
        similarities = np.zeros(num_vectors)

    # 4. Calculate Scores
    scores = []
    now = datetime.now()

    # Pre-calculate max values for normalization
    counts = [r[2] for r in rows]
    max_count = max(1, max(counts) if counts else 1)
    
    times = [r[5] or 0 for r in rows]
    max_time = max(1, max(times) if times else 1)
    
    # Most frequent cluster in recent history
    top_cluster = None
    if recent_clusters:
        top_cluster = Counter(recent_clusters).most_common(1)[0][0]
    
    for fid in file_ids:
        data = file_map[fid]
        
        # --- Recency Score (Exponential Decay) ---
        last_opened_str = data["last_opened"]
        try:
            last_dt = datetime.fromisoformat(last_opened_str)
            days_diff = (now - last_dt).total_seconds() / 86400.0
            # Faster decay (3 days half-life)
            recency_score = 1.0 / (1.0 + (days_diff / 3.0)) 
        except:
            recency_score = 0.0
            
        # --- Frequency & Importance Score ---
        # Combine access count and total time spent
        freq_part = np.log(1 + data["count"]) / np.log(1 + max_count)
        time_part = np.log(1 + data["total_time"]) / np.log(1 + max_time)
        freq_score = (freq_part * 0.6) + (time_part * 0.4)
        
        # --- Context Score ---
        context_score = 0.0
        if fid in id_to_idx:
            idx = id_to_idx[fid]
            if idx < len(similarities):
                context_score = max(0, similarities[idx])
        
        # --- Cluster Affinity ---
        cluster_score = 0.0
        if top_cluster is not None and data["cluster_id"] == top_cluster:
            cluster_score = 1.0
        elif data["cluster_id"] in recent_clusters:
            cluster_score = 0.5
        
        # Weighted Sum
        final_score = (W_RECENCY * recency_score) + \
                      (W_FREQ * freq_score) + \
                      (W_CONTEXT * context_score) + \
                      (W_CLUSTER * cluster_score)
        
        # Small boost for files explicitly in the last 5 sessions
        if fid in recent_session_ids:


            final_score = min(1.0, final_score + 0.05)

        scores.append({
            "path": data["path"],
            "score": final_score,
            "last_opened": data["last_opened"],
            "reasons": {
                "Recency": f"{recency_score:.2f}",
                "Freq": f"{freq_score:.2f}",
                "Context": f"{context_score:.2f}",
                "Cluster": f"{cluster_score:.2f}"
            }
        })

    # 5. Sort and Return
    scores.sort(key=lambda x: x["score"], reverse=True)
    
    return scores[:limit]
