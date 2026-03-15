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
        vectorizer = TfidfVectorizer(stop_words='english', max_features=20)
        X = vectorizer.fit_transform(corpus)
        
        # Sum weights across all files in category
        weights = np.asarray(X.sum(axis=0)).ravel()
        feature_names = vectorizer.get_feature_names_out()
        
        # Create {word: weight} dict
        fingerprint = {feature_names[i]: float(weights[i]) for i in weights.argsort()[::-1][:10]}
        
        # Save to user_categories
        cur.execute("""
            INSERT INTO user_categories (name, keywords)
            VALUES (?, ?)
            ON CONFLICT(name) DO UPDATE SET keywords = excluded.keywords
        """, (category_name, json.dumps(fingerprint)))
        
        conn.commit()
        logging.info(f"Updated fingerprint for category: {category_name}")
    except Exception as e:
        logging.error(f"Failed to update fingerprint for {category_name}: {e}")
    finally:
        conn.close()


def get_cluster_label(model, cluster_id, feature_names):
    """
    Generate a label for the cluster based on the top terms in the cluster center,
    matching against user-defined categories first.
    """
    # Get the centroid for this cluster
    centroid = model.cluster_centers_[cluster_id]
    top_indices = centroid.argsort()[::-1]
    top_terms = [feature_names[i] for i in top_indices[:15]] # Get even more terms
    
    # 1. Check against User Categories (Learned)
    best_user_cat = None
    max_user_score = 0
    
    try:
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT name, keywords FROM user_categories")
        user_cats = cur.fetchall()
        conn.close()
        
        for name, keywords_json in user_cats:
            if not keywords_json: continue
            keywords = json.loads(keywords_json)
            # Calculate overlap score
            score = 0
            for term in top_terms[:10]:
                if term in keywords:
                    score += keywords[term]
            
            if score > max_user_score:
                max_user_score = score
                best_user_cat = name
    except: pass
    
    if best_user_cat and max_user_score > 0.2: # Lowered threshold for better detection
        return best_user_cat

    # 2. Check against Default Mappings (from config/JSON)
    best_category = None
    best_score = 0
    for category, keywords in DEFAULT_CATEGORIES.items():
        score = sum((5 - i) for i, term in enumerate(top_terms[:5]) if term in keywords)
        if score > best_score:
            best_score = score
            best_category = category
    
    if best_category and best_score >= 3:
        return best_category
    
    # 3. Fallback: Top terms
    noise_words = {"the", "and", "for", "with", "this", "that"}
    filtered_terms = [t for t in top_terms[:3] if len(t) > 2 and t not in noise_words]
    
    if not filtered_terms:
        return top_terms[0].title()
        
    return " & ".join([t.title() for t in filtered_terms])


def run_filename_clustering(k=None, db_path=DB_PATH):
    """Cluster files by filename + content using KMeans (Dynamic)"""
    conn = get_connection(db_path)
    cur = conn.cursor()

    # Fetch document files
    cur.execute("SELECT id, path, searchable_text, cluster_label, is_manual_label FROM files")
    all_rows = cur.fetchall()
    
    # Filter to only documents
    rows = []
    for r in all_rows:
        fid, path, text, label, manual = r
        if os.path.splitext(path.lower())[1] in DOCUMENT_EXTENSIONS:
            rows.append({
                "id": fid, "path": path, "text": text, 
                "label": label, "manual": manual
            })
    
    num_files = len(rows)
    if num_files < 2:
        conn.close()
        return
    
    if k is None:
        if num_files <= 3: k = 2
        elif num_files <= 5: k = 3
        elif num_files <= 10: k = 5
        elif num_files <= 20: k = 6
        else: k = 8
    k = min(k, num_files)
    
    # Prepare corpus
    corpus = []
    for r in rows:
        combined = f"{clean_filename(r['path'])} {r['text'] or ''}"
        corpus.append(combined)

    vectorizer = TfidfVectorizer(stop_words='english', max_features=2000)
    try:
        X = vectorizer.fit_transform(corpus)
    except:
        conn.close()
        return
    
    kmeans = KMeans(n_clusters=k, random_state=42, n_init=10)
    kmeans.fit(X)
    
    feature_names = vectorizer.get_feature_names_out()
    cluster_labels = {}
    
    for i in range(k):
        # 1. Check if cluster contains manually labeled files
        manual_labels = [rows[j]['label'] for j in range(num_files) if kmeans.labels_[j] == i and rows[j]['manual']]
        
        if manual_labels:
            # Use most frequent manual label in this cluster
            from collections import Counter
            best_label = Counter(manual_labels).most_common(1)[0][0]
            cluster_labels[i] = best_label
        else:
            # 2. Use smart labeling logic
            cluster_labels[i] = get_cluster_label(kmeans, i, feature_names)

    # Update database
    update_data = []
    for idx, r in enumerate(rows):
        cluster_id = int(kmeans.labels_[idx])
        label = cluster_labels[cluster_id]
        # If user manually set a label for THIS specific file, don't overwrite it with cluster label
        # unless the cluster label was derived from manual labels anyway.
        # Actually, for consistency, we set the whole cluster to the manual label if there's overlap.
        update_data.append((cluster_id, label, r['id']))
        
    cur.executemany("UPDATE files SET cluster_id = ?, cluster_label = ? WHERE id = ?", update_data)
    
    # Clear clustering for non-docs
    doc_ids = {r['id'] for r in rows}
    all_ids = {r[0] for r in all_rows}
    non_doc_ids = list(all_ids - doc_ids)
    if non_doc_ids:
        cur.executemany("UPDATE files SET cluster_id = NULL, cluster_label = NULL WHERE id = ?", [(fid,) for fid in non_doc_ids])

    conn.commit()
    conn.close()
    logging.info(f"Clustering complete. Updated {len(rows)} files.")
