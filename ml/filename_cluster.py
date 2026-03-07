import os
import re
import logging
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans
from collections import Counter

# Add parent directory to path for imports
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import DB_PATH, DOCUMENT_EXTENSIONS, CLUSTERING_CLUSTERS
from database import get_connection


def clean_filename(path):
    name = os.path.basename(path)
    name = os.path.splitext(name)[0]
    name = name.lower()
    name = re.sub(r'[_\-]', ' ', name)
    name = re.sub(r'\d+', '', name)
    return name.strip()


def get_cluster_label(model, cluster_id, feature_names):
    """
    Generate a label for the cluster based on the top terms in the cluster center.
    """
    # Get the centroid for this cluster
    centroid = model.cluster_centers_[cluster_id]
    
    # Sort features by weight in the centroid
    top_indices = centroid.argsort()[::-1]
    
    # Get top 5 terms for better matching
    top_terms = [feature_names[i] for i in top_indices[:5]]
    
    # Define category mappings
    category_mappings = {
        "Work Documents": ["report", "project", "work", "business", "meeting", "email"],
        "Personal Files": ["personal", "goals", "life", "diary", "journal"],
        "Educational Materials": ["study", "course", "tutorial", "lesson", "basics", "guide", "ml", "machine", "learning", "data", "algorithm", "college", "university", "lecture", "homework"],
        "Financial Documents": ["invoice", "bill", "budget", "expense", "tax", "receipt", "bank", "statement"],
        "Creative Projects": ["design", "art", "music", "video", "photo", "portfolio", "story", "tale", "novel"],
        "Technical Docs": ["code", "programming", "api", "manual", "spec", "config", "cybersecurity", "security", "documentation", "readme"],
        "Media Files": ["image", "video", "audio", "photo", "media", "picture"],
        "Archives": ["archive", "backup", "old", "history"]
    }
    
    # Find the best matching category
    best_category = None
    best_score = 0
    for category, keywords in category_mappings.items():
        score = sum(1 for term in top_terms if term in keywords)
        if score > best_score:
            best_score = score
            best_category = category
    
    if best_category and best_score > 0:
        return best_category
    
    # Fallback to top 3 terms
    top_terms_short = [feature_names[i] for i in top_indices[:3]]
    label = " ".join([t.title() for t in top_terms_short])
    return label


def run_filename_clustering(k=None, db_path=DB_PATH):
    """Cluster files by filename + content using KMeans (Dynamic)"""
    conn = get_connection(db_path)
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
    
    if num_files < 2:
        logging.warning(f"Not enough documents to cluster (found {num_files}, need at least 2).")
        conn.close()
        return
    
    # Dynamic cluster count based on file count
    if k is None:
        if num_files <= 4:
            k = 2
        elif num_files <= 10:
            k = 3
        elif num_files <= 20:
            k = 4
        else:
            k = 5
    
    # Ensure k doesn't exceed file count
    k = min(k, num_files)
    
    logging.info(f"Clustering {num_files} documents into {k} groups...")
    
    # Prepare text data for clustering
    corpus = []
    for _, path, text in rows:
        fname_cleaned = clean_filename(path)
        content_snippet = text or ""
        combined = f"{fname_cleaned} {content_snippet}"
        corpus.append(combined)

    # Vectorize
    vectorizer = TfidfVectorizer(stop_words='english', max_features=2000)
    try:
        X = vectorizer.fit_transform(corpus)
    except ValueError as e:
        logging.error(f"Vectorization failed: {e}")
        conn.close()
        return
    
    # Cluster
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    kmeans.fit(X)
    
    # Generate labels for each cluster
    feature_names = vectorizer.get_feature_names_out()
    cluster_labels = {}
    
    for i in range(k):
        label = get_cluster_label(kmeans, i, feature_names)
        cluster_labels[i] = label

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
    logging.info(f"Clustering complete. Updated {len(rows)} files.")
