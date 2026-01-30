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


def auto_label_cluster(words, file_texts):
    """Auto-label cluster based on keywords in top words and filenames"""
    import re
    
    study_keywords = {"assignment", "notes", "os", "dbms", "math", "study", 
                      "syllabus", "timetable", "exam", "lecture", "course", "class"}
    work_keywords = {"invoice", "resume", "report", "project", "offer", "salary",
                     "proposal", "contract", "meeting", "document", "presentation"}
    
    # Count matches for each category
    study_matches = 0
    work_matches = 0
    
    # Check top TF-IDF words (higher weight)
    for word in words:
        if word in study_keywords:
            study_matches += 2
        if word in work_keywords:
            work_matches += 2
    
    # Check in filenames - split on underscores and remove extensions
    for filename in file_texts:
        # Remove extension
        name_only = os.path.splitext(filename)[0].lower()
        # Split on underscores, hyphens, and spaces
        filename_words = re.split(r'[_\-\s]+', name_only)
        
        for fword in filename_words:
            if fword in study_keywords:
                study_matches += 1
            if fword in work_keywords:
                work_matches += 1
    
    # Return based on highest score
    if study_matches > work_matches and study_matches > 0:
        return "Study"
    elif work_matches > 0:
        return "Work"
    else:
        return "Personal"


def run_filename_clustering(k=None):
    """Cluster files by filename similarity and auto-label them"""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Only cluster documents, not movies/videos
    DOCUMENT_EXTENSIONS = {'.pdf', '.txt', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv'}
    
    cur.execute("SELECT id, path FROM files")
    all_rows = cur.fetchall()
    
    # Filter to only documents
    rows = [(fid, path) for fid, path in all_rows 
            if os.path.splitext(path.lower())[1] in DOCUMENT_EXTENSIONS]
    
    if len(rows) < 1:
        print("No document files to cluster.")
        return

    # For each file, determine its category directly from its filename
    # This is more reliable than TF-IDF clustering on small datasets
    for fid, path in rows:
        basename = os.path.basename(path).lower()
        label = auto_label_cluster([], [basename])
        
        cur.execute("""
            UPDATE files
            SET cluster_id = 0, cluster_label = ?
            WHERE id = ?
        """, (label, fid))
    
    # Mark non-documents as unclustered
    for fid, path in all_rows:
        if os.path.splitext(path.lower())[1] not in DOCUMENT_EXTENSIONS:
            cur.execute("UPDATE files SET cluster_id = NULL, cluster_label = NULL WHERE id = ?", (fid,))

    conn.commit()
    conn.close()

    print(f"Clustering complete. Labeled {len(rows)} documents.")
