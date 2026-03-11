import os
import re
import logging
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

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
    
    # Define category mappings with broader keywords
    category_mappings = {
        "Work Documents": ["report", "project", "work", "business", "meeting", "email", "client", "office", "presentation", "brief", "strategy", "plan", "proposal"],
        "Personal Files": ["personal", "goals", "life", "diary", "journal", "health", "hobby", "todo", "family", "private"],
        "Educational Materials": ["study", "course", "tutorial", "lesson", "basics", "guide", "ml", "machine", "learning", "data", "algorithm", "college", "university", "lecture", "homework", "exam", "assignment", "textbook", "notes", "education"],
        "Financial Documents": ["invoice", "bill", "budget", "expense", "tax", "receipt", "bank", "statement", "finance", "payment", "salary", "investment", "money"],
        "Creative Projects": ["design", "art", "music", "video", "photo", "portfolio", "story", "tale", "novel", "writing", "script", "sketch", "creative", "draft"],
        "Technical Docs": ["code", "programming", "api", "manual", "spec", "config", "cybersecurity", "security", "documentation", "readme", "dev", "tech", "setup", "install", "git", "hub", "log"],
        "Media Files": ["image", "video", "audio", "photo", "media", "picture", "album", "clip", "stream", "png", "jpg", "mp3", "mp4"],
        "Archives": ["archive", "backup", "old", "history", "legacy", "collection", "zip", "tar", "rar"],
        "General Planning": ["schedule", "plan", "time", "calendar", "timetable", "agenda", "tasks", "list", "table", "weekly", "daily", "monthly"]
    }
    
    # Find the best matching category with a weighted score
    best_category = None
    best_score = 0
    for category, keywords in category_mappings.items():
        # Weight the top terms more heavily (top 1 = 3 pts, top 2 = 2 pts, etc.)
        score = sum((5 - i) for i, term in enumerate(top_terms) if term in keywords)
        if score > best_score:
            best_score = score
            best_category = category
    
    # Require a minimum score to use a category label
    if best_category and best_score >= 3:
        return best_category
    
    # Fallback: Clean and combine top terms for a more descriptive label
    # Skip very short words (<=2 chars) or common noise words
    noise_words = {"the", "and", "for", "with", "this", "that"}
    filtered_terms = [t for t in top_terms[:3] if len(t) > 2 and t not in noise_words]
    
    if not filtered_terms:
        # If no good terms, use the top one anyway
        return top_terms[0].title()
        
    return " & ".join([t.title() for t in filtered_terms])


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
        if num_files <= 3:
            k = 2
        elif num_files <= 5:
            k = 3
        elif num_files <= 10:
            k = 5
        elif num_files <= 20:
            k = 6
        else:
            k = 8
    
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

    # Update database - Optimized with executemany
    update_data = []
    for idx, (fid, _, _) in enumerate(rows):
        cluster_id = int(kmeans.labels_[idx])
        label = cluster_labels[cluster_id]
        update_data.append((cluster_id, label, fid))
        
    cur.executemany("""
        UPDATE files
        SET cluster_id = ?, cluster_label = ?
        WHERE id = ?
    """, update_data)
    
    # Clear clustering for non-docs
    doc_ids = {r[0] for r in rows}
    all_ids = {r[0] for r in all_rows}
    non_doc_ids = list(all_ids - doc_ids)
    
    if non_doc_ids:
        cur.executemany("UPDATE files SET cluster_id = NULL, cluster_label = NULL WHERE id = ?", [(fid,) for fid in non_doc_ids])

    conn.commit()
    conn.close()
    logging.info(f"Clustering complete. Updated {len(rows)} files.")
