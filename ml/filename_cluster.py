import os
import re
import sqlite3
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import KMeans

DB_PATH = os.path.join("data", "file_logs.db")


def clean_filename(path):
    name = os.path.basename(path)
    name = os.path.splitext(name)[0]
    name = name.lower()
    name = re.sub(r'[_\-]', ' ', name)
    name = re.sub(r'\d+', '', name)
    return name.strip()


def auto_label_cluster(words):
    study_keywords = {"assignment", "notes",
                      "os", "dbms", "math", "study", "syllabus", "timet"}
    work_keywords = {"invoice", "resume",
                     "report", "project", "offer", "salary"}

    words_set = set(words)

    if words_set & study_keywords:
        return "Study"
    if words_set & work_keywords:
        return "Work"
    return "Personal"


def run_filename_clustering(k=3):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id, path FROM files")
    rows = cur.fetchall()

    if len(rows) < k:
        print("Not enough files for clustering.")
        return

    file_ids = []
    texts = []

    for fid, path in rows:
        file_ids.append(fid)
        texts.append(clean_filename(path))

    vectorizer = TfidfVectorizer()
    X = vectorizer.fit_transform(texts)

    model = KMeans(n_clusters=k, random_state=42)
    clusters = model.fit_predict(X)

    feature_names = vectorizer.get_feature_names_out()

    cluster_keywords = {}

    for i in range(k):
        center = model.cluster_centers_[i]
        top_indices = center.argsort()[-5:]
        keywords = [feature_names[j] for j in top_indices]
        cluster_keywords[i] = keywords

    for fid, cluster_id in zip(file_ids, clusters):
        label = auto_label_cluster(cluster_keywords[cluster_id])

        cur.execute("""
            UPDATE files
            SET cluster_id = ?, cluster_label = ?
            WHERE id = ?
        """, (int(cluster_id), label, fid))

    conn.commit()
    conn.close()

    print("Clustering complete.")
