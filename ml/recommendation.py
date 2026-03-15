import os
import logging
import numpy as np
from datetime import datetime
from sklearn.metrics.pairwise import cosine_similarity

from config import DB_PATH
from ml.semantic_search import get_semantic_searcher
from core.database import get_connection

# Weights for the hybrid score
W_RECENCY = 0.4
W_FREQ = 0.3
W_CONTEXT = 0.3


def get_smart_priority_files(limit=20):
    """
    Returns a list of files sorted by Smart Priority Score.
    Score = Recency + Frequency + Context (Similarity to last opened)
    """
    conn = get_connection(DB_PATH)
    cur = conn.cursor()
    
    # 1. Get all files with stats
    cur.execute("""
        SELECT id, path, access_count, last_opened 
        FROM files 
        WHERE last_opened IS NOT NULL
    """)
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return []

    # Local Cache of data
    file_map = {r[0]: {"path": r[1], "count": r[2], "last_opened": r[3]} for r in rows}
    file_ids = list(file_map.keys())
    
    # 2. Identify Last Opened File (Context)
    # Sort by last_opened descending
    sorted_by_date = sorted(rows, key=lambda x: x[3] or "", reverse=True)
    last_file_id = sorted_by_date[0][0]
    last_file_path = sorted_by_date[0][1]
    
    logging.info(f"Context: Recommending based on last file '{os.path.basename(last_file_path)}'")

    # 3. Get Semantic Embeddings
    # Use singleton to prevent multiple BERT model loads
    searcher = get_semantic_searcher()
    
    # Map file_id to vector index
    id_to_idx = {fid: i for i, fid in enumerate(searcher.file_ids)}
    
    # context vector
    similarities = None
    if last_file_id in id_to_idx:
        context_idx = id_to_idx[last_file_id]
        
        # Safety check: ensure index is valid and vectors exist
        if searcher.vectors is not None and len(searcher.vectors) > 0 and context_idx < len(searcher.vectors):
            context_vector = searcher.vectors[context_idx]
            
            # Calculate similarities for all files
            # Reshape for single sample
            similarities = cosine_similarity([context_vector], searcher.vectors)[0]
    
    # Fallback for similarities
    if similarities is None:
        num_vectors = len(searcher.vectors) if searcher.vectors is not None else 0
        similarities = np.zeros(num_vectors)

    # 4. Calculate Scores
    scores = []
    now = datetime.now()

    # Pre-calculate max values for normalization
    counts = [r[2] for r in rows]
    max_count = max(1, max(counts) if counts else 1)
    
    for fid in file_ids:
        data = file_map[fid]
        
        # --- Recency Score (Exponential Decay) ---
        last_opened_str = data["last_opened"]
        try:
            last_dt = datetime.fromisoformat(last_opened_str)
            days_diff = (now - last_dt).total_seconds() / 86400.0
            # Score is 1.0 for now, 0.5 for 7 days ago, etc.
            # 1 / (1 + days/7)
            recency_score = 1.0 / (1.0 + (days_diff / 7.0))
        except:
            recency_score = 0.0
            
        # --- Frequency Score (Log Scale) ---
        # Logarithmic to dampen effect of huge counts
        # score = log(1 + count) / log(1 + max_count)
        freq_score = np.log(1 + data["count"]) / np.log(1 + max_count)
        
        # --- Context Score ---
        context_score = 0.0
        if fid in id_to_idx:
            idx = id_to_idx[fid]
            if idx < len(similarities):
                context_score = max(0, similarities[idx]) # Clip negative cosine sim
        
        # Weighted Sum
        final_score = (W_RECENCY * recency_score) + \
                      (W_FREQ * freq_score) + \
                      (W_CONTEXT * context_score)
        
        scores.append({
            "path": data["path"],
            "score": final_score,
            "last_opened": data["last_opened"],
            "reasons": {
                "Recency": f"{recency_score:.2f}",
                "Freq": f"{freq_score:.2f}",
                "Context": f"{context_score:.2f}"
            }
        })

    # 5. Sort and Return
    scores.sort(key=lambda x: x["score"], reverse=True)
    
    return scores[:limit]
