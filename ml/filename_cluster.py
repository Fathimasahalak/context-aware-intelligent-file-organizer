import os
import re
import logging
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

from config import DB_PATH, DOCUMENT_EXTENSIONS, CLUSTERING_CLUSTERS
from core.database import get_connection


def clean_filename(path):
    name = os.path.basename(path)
    name = os.path.splitext(name)[0]
    name = name.lower()
    name = re.sub(r'[_\-]', ' ', name)
    name = re.sub(r'\d+', '', name)
    return name.strip()



from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score


def generate_auto_label(file_ids, db_path):
    """
    Improved Labeling: Identifies the 'Medoid' (most central file) 
    of the cluster and weights its content higher for the label.
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    
    placeholders = ','.join('?' * len(file_ids))
    cur.execute(f"SELECT id, path, searchable_text FROM files WHERE id IN ({placeholders})", file_ids)
    rows = cur.fetchall()
    conn.close()
    
    if not rows:
        return "Misc Documents"

    # Identify the 'representative' file (for now, the one with the most content)
    # In a full Medoid approach, we'd use the vector closest to the mean
    rows_sorted = sorted(rows, key=lambda x: len(x[2]) if x[2] else 0, reverse=True)
    representative = rows_sorted[0]
    
    corpus = []
    for fid, path, text in rows:
        clean_name = clean_filename(path)
        # Weight the representative file and filenames more
        weight = 3 if fid == representative[0] else 1
        entry = f"{clean_name} {text or ''} " * weight
        corpus.append(entry)

    try:
        vectorizer = TfidfVectorizer(
            stop_words='english', 
            max_features=20,
            ngram_range=(1, 2),
            token_pattern=r'(?u)\b[a-zA-Z]{3,}\b'
        )
        X = vectorizer.fit_transform(corpus)
        weights = np.asarray(X.sum(axis=0)).ravel()
        feature_names = vectorizer.get_feature_names_out()
        
        sorted_indices = weights.argsort()[::-1]
        selected = []
        for i in sorted_indices:
            label = feature_names[i].title()
            if not any(label.lower() in e.lower() or e.lower() in label.lower() for e in selected):
                selected.append(label)
            if len(selected) >= 2: # Keep labels concise: 2 strong concepts
                break
                
        return " & ".join(selected) if selected else "General Files"
    except:
        return "Archive / Documents"


from ml.semantic_search import get_semantic_searcher

def run_filename_clustering(k=None, db_path=DB_PATH):
    """
    Hierarchical Agglomerative Clustering with Silhouette Analysis.
    Finds the most natural grouping structure for the files.
    """
    searcher = get_semantic_searcher(db_path)
    if not searcher.get_model():
        return

    searcher.load_files()
    if searcher.vectors is None or len(searcher.vectors) < 4:
        # Fallback for very small libraries
        logging.info("Too few files for hierarchical analysis.")
        return
        
    # 1. Prepare Hybrid Vectors (Content + Name)
    # Increased filename weight to 0.5 to better separate files by their descriptive names
    if searcher.name_vectors is not None and len(searcher.name_vectors) == len(searcher.vectors):
        clustering_vectors = (searcher.vectors * 0.5) + (searcher.name_vectors * 0.5)
    else:
        clustering_vectors = searcher.vectors

    n_samples = len(clustering_vectors)
    file_ids = searcher.file_ids
    file_paths = searcher.file_paths

    # 2. Silhouette Analysis to find optimal K (Number of clusters)
    # We test K from 2 to min(15, n-1)
    best_k = 2
    if k is None:
        max_k = min(15, n_samples - 1)
        best_score = -1
        
        for temp_k in range(2, max_k + 1):
            model = AgglomerativeClustering(n_clusters=temp_k)
            labels = model.fit_predict(clustering_vectors)
            score = silhouette_score(clustering_vectors, labels)
            
            if score > best_score:
                best_score = score
                best_k = temp_k
        
        logging.info(f"Silhouette Analysis chose optimal K={best_k} (score: {best_score:.2f})")
    else:
        best_k = k

    # 3. Final Hierarchical Clustering
    # 'ward' linkage minimizes variance within clusters (very clean groups)
    agg_cluster = AgglomerativeClustering(n_clusters=best_k, linkage='ward')
    cluster_assignments = agg_cluster.fit_predict(clustering_vectors)

    # 4. Group results
    clusters = {}
    for i, cid in enumerate(cluster_assignments):
        if cid not in clusters:
            clusters[cid] = []
        clusters[cid].append({
            "id": file_ids[i],
            "path": file_paths[i]
        })

    # 5. Update Database
    conn = get_connection(db_path)
    cur = conn.cursor()
    update_data = []
    
    for cid, files in clusters.items():
        cluster_file_ids = [f["id"] for f in files]
        
        # Priority: Manual Label -> Auto-label
        placeholders = ','.join('?' * len(cluster_file_ids))
        cur.execute(f"SELECT cluster_label FROM files WHERE id IN ({placeholders}) AND is_manual_label = 1 LIMIT 1", cluster_file_ids)
        row = cur.fetchone()
        
        label = row[0] if row else generate_auto_label(cluster_file_ids, db_path)

        for f in files:
            update_data.append((cid, label, f["id"]))

    if update_data:
        cur.executemany("""
            UPDATE files 
            SET cluster_id = ?, cluster_label = ? 
            WHERE id = ? AND is_manual_label = 0
        """, update_data)
        conn.commit()

    conn.close()
    logging.info(f"Hierarchical clustering complete. Created {best_k} groups.")
