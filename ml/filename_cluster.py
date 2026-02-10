import os
import re
import sqlite3
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from collections import Counter

from config import DB_PATH, DOCUMENT_EXTENSIONS, CLUSTERING_CLUSTERS


def clean_filename(path):
    name = os.path.basename(path)
    name = os.path.splitext(name)[0]
    name = name.lower()
    name = re.sub(r'[_\-]', ' ', name)
    name = re.sub(r'\d+', '', name)
    return name.strip()


def get_cluster_label(tfidf_matrix, model, cluster_id, feature_names):
    """
    Generate a label for the cluster based on the top terms in the cluster center.
    """
    # Get the centroid for this cluster
    centroid = model.cluster_centers_[cluster_id]
    
    # Sort features by weight in the centroid
    top_indices = centroid.argsort()[::-1]
    
    # Get top 3 terms
    top_terms = [feature_names[i] for i in top_indices[:3]]
    
    # Create a label (e.g., "Invoice / Report")
    label = " / ".join([t.title() for t in top_terms])
    return label


def run_filename_clustering(k=None, db_path=DB_PATH):
    """Cluster files by filename + content using KMeans (Dynamic)"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    # Fetch document files
    cur.execute("SELECT id, path, searchable_text FROM files")
    all_rows = cur.fetchall()
    
    # Filter to only documents
    rows = []
    for r in all_rows:
        fid, path, text = r
        if os.path.splitext(path.lower())[1] in DOCUMENT_EXTENSIONS:
            rows.append((fid, path, text))
    
    num_files = len(rows)
    
    # Dynamic cluster count based on file count
    if k is None:
        if num_files < 2:
            print(f"Not enough documents to cluster (found {num_files}, need at least 2).")
            conn.close()
            return
        elif num_files <= 4:
            k = 2
        elif num_files <= 10:
            k = 3
        elif num_files <= 20:
            k = 4
        else:
            k = 5
    
    # Ensure k doesn't exceed file count
    k = min(k, num_files)
    
    print(f"Clustering {num_files} documents into {k} groups...")

    # Prepare text data for clustering
    # We combine filename (cleaned) + searchable text (first 500 chars)
    corpus = []
    for _, path, text in rows:
        fname_cleaned = clean_filename(path)
        content_snippet = (text or "")[:500]  # Use start of content for better context
        combined = f"{fname_cleaned} {content_snippet}"
        corpus.append(combined)

    # Vectorize
    vectorizer = TfidfVectorizer(stop_words='english', max_features=1000)
    X = vectorizer.fit_transform(corpus)
    
    # Cluster
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    kmeans.fit(X)
    
    # Generate labels for each cluster
    feature_names = vectorizer.get_feature_names_out()
    cluster_labels = {}
    
    for i in range(k):
        label = get_cluster_label(X, kmeans, i, feature_names)
        cluster_labels[i] = label
        print(f"Cluster {i}: {label}")

    # Update database
    for idx, (fid, _, _) in enumerate(rows):
        cluster_id = int(kmeans.labels_[idx])
        label = cluster_labels[cluster_id]
        
        cur.execute("""
            UPDATE files
            SET cluster_id = ?, cluster_label = ?
            WHERE id = ?
        """, (cluster_id, label, fid))
    
    # Clear clustering for non-docs
    doc_ids = {r[0] for r in rows}
    all_ids = {r[0] for r in all_rows}
    non_doc_ids = all_ids - doc_ids
    
    for fid in non_doc_ids:
        cur.execute("UPDATE files SET cluster_id = NULL, cluster_label = NULL WHERE id = ?", (fid,))

    conn.commit()
    conn.close()
    print(f"Clustering complete. Updated {len(rows)} files.")
