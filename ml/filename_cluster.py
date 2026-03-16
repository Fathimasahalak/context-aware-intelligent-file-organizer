import os
import re
import logging
import json
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

from config import DB_PATH, DOCUMENT_EXTENSIONS, CLUSTERING_CLUSTERS, DEFAULT_CATEGORIES
from core.database import get_connection


def clean_filename(path):
    name = os.path.basename(path)
    name = os.path.splitext(name)[0]
    name = name.lower()
    name = re.sub(r'[_\-]', ' ', name)
    name = re.sub(r'\d+', '', name)
    return name.strip()


def update_category_fingerprint(category_name):
    """
    Update the keyword fingerprint for a category based on the files in it.
    This is called when a user renames a cluster or moves a file.
    """
    conn = get_connection(DB_PATH)
    try:
        cur = conn.cursor()
        
        # Get all files currently in this category
        cur.execute("SELECT path, searchable_text FROM files WHERE cluster_label = ?", (category_name,))
        rows = cur.fetchall()
        
        if not rows:
            return

        corpus = []
        for path, text in rows:
            combined = f"{clean_filename(path)} {text or ''}"
            corpus.append(combined)
            
        # Extract top keywords using TF-IDF
        # We use a broader max_features for better fingerprinting
        vectorizer = TfidfVectorizer(stop_words='english', max_features=50, ngram_range=(1, 2))
        X = vectorizer.fit_transform(corpus)
        
        # Sum weights across all files in category
        weights = np.asarray(X.sum(axis=0)).ravel()
        feature_names = vectorizer.get_feature_names_out()
        
        # Create {word: weight} dict
        # Store top 20 keywords for the learned fingerprint
        fingerprint = {feature_names[i]: float(weights[i]) for i in weights.argsort()[::-1][:20]}
        
        # Save to user_categories
        cur.execute("""
            INSERT INTO user_categories (name, keywords)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET keywords = excluded.keywords
        """, (category_name, json.dumps(fingerprint)))
        
        conn.commit()
        logging.info(f"Updated fingerprint for learned category: {category_name}")
    except Exception as e:
        logging.error(f"Failed to update fingerprint for {category_name}: {e}")
    finally:
        conn.close()


from sklearn.metrics.pairwise import cosine_similarity
from ml.semantic_search import get_semantic_searcher

def run_filename_clustering(k=None, db_path=DB_PATH):
    """
    Semantic Clustering using Centroid Similarity (K-Means style).
    Uses BERT embeddings for high accuracy and anchors to user-defined categories.
    """
    searcher = get_semantic_searcher(db_path)
    model = searcher.get_model()
    if not model:
        logging.error("AI Model not available for clustering.")
        return

    conn = get_connection(db_path)
    cur = conn.cursor()

    # 1. Load Known Categories (Learned + Default)
    # Get User Categories
    cur.execute("SELECT name, keywords FROM user_categories")
    user_cats = {row[0]: json.loads(row[1]) for row in cur.fetchall() if row[1]}
    
    # 2. Build Category "Anchor" Vectors
    category_anchors = {}
    
    # Encode User Categories (High Priority)
    for name, keywords in user_cats.items():
        # Create a descriptive string for the category to get a good vector
        kw_str = " ".join(list(keywords.keys())[:5])
        anchor_text = f"{name} {kw_str}"
        category_anchors[name] = model.encode([anchor_text])[0]
        
    # Encode Default Categories (if not already covered by user)
    for name, keywords in DEFAULT_CATEGORIES.items():
        if name not in category_anchors:
            kw_str = " ".join(keywords[:5])
            anchor_text = f"{name} {kw_str}"
            category_anchors[name] = model.encode([anchor_text])[0]

    if not category_anchors:
        conn.close()
        return

    # 3. Fetch all document files and their vectors
    # We always call load_files to ensure we have the latest additions indexed
    searcher.load_files()
        
    file_vectors = searcher.vectors
    file_ids = searcher.file_ids
    file_paths = searcher.file_paths
    
    if len(file_vectors) == 0:
        conn.close()
        return

    # 4. Assign Files to Best Cluster (Nearest Centroid)
    anchor_names = list(category_anchors.keys())
    anchor_matrix = np.array([category_anchors[name] for name in anchor_names])
    
    # Calculate similarity between all files and all category anchors
    # sims shape: (num_files, num_anchors)
    sims = cosine_similarity(file_vectors, anchor_matrix)
    
    update_data = []
    for i in range(len(file_ids)):
        fid = int(file_ids[i])
        path = file_paths[i]
        
        # Check if it's a document
        if os.path.splitext(path.lower())[1] not in DOCUMENT_EXTENSIONS:
            continue
            
        # Get best matching anchor
        best_anchor_idx = np.argmax(sims[i])
        best_score = sims[i][best_anchor_idx]
        
        if best_score > 0.25: # Reasonable similarity threshold
            label = anchor_names[best_anchor_idx]
            update_data.append((best_anchor_idx, label, fid))
        else:
            # Fallback for very unique files
            ext = os.path.splitext(path.lower())[1][1:].upper()
            update_data.append((None, f"{ext} Documents", fid))

    # 5. Batch Update Database
    if update_data:
        cur.executemany("UPDATE files SET cluster_id = ?, cluster_label = ? WHERE id = ? AND is_manual_label = 0", update_data)
        conn.commit()

    conn.close()
    logging.info(f"Semantic clustering complete. Updated {len(update_data)} files.")
