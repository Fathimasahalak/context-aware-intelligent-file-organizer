from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import numpy as np
import sqlite3
import os


DB_PATH = os.path.join("data", "file_logs.db")
EMBEDDING_CACHE = os.path.join("data", "file_embeddings.npy")
ID_CACHE = os.path.join("data", "file_ids.npy")


class SemanticSearch:
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH)
        self.cur = self.conn.cursor()
        self.model = None
        self.file_ids = []
        self.file_paths = []
        self.vectors = None

    def load_model(self):
        if self.model is None:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def load_files(self):
        self.cur.execute("""
            SELECT id, path, searchable_text 
            FROM files 
            WHERE searchable_text IS NOT NULL
            ORDER BY id ASC
        """)
        rows = self.cur.fetchall()

        self.file_ids = [r[0] for r in rows]
        self.file_paths = [r[1] for r in rows]
        texts = [r[2] for r in rows]

        self.load_model()

        # No cache → compute all
        if not os.path.exists(EMBEDDING_CACHE) or not os.path.exists(ID_CACHE):
            print("No embedding cache found. Computing all...")
            self.vectors = self.model.encode(texts, show_progress_bar=True)
            self.save_cache()
            return

        # Load existing cache
        cached_ids = np.load(ID_CACHE).tolist()
        cached_vectors = np.load(EMBEDDING_CACHE)

        # Detect new files
        new_entries = []
        new_texts = []

        for fid, text in zip(self.file_ids, texts):
            if fid not in cached_ids:
                new_entries.append(fid)
                new_texts.append(text)

        # Append new embeddings
        if new_entries:
            print(f"Embedding {len(new_entries)} new files...")
            new_vectors = self.model.encode(new_texts, show_progress_bar=True)

            cached_ids.extend(new_entries)
            cached_vectors = np.vstack([cached_vectors, new_vectors])

            np.save(ID_CACHE, np.array(cached_ids))
            np.save(EMBEDDING_CACHE, cached_vectors)

        self.vectors = cached_vectors

    def save_cache(self):
        np.save(ID_CACHE, np.array(self.file_ids))
        np.save(EMBEDDING_CACHE, self.vectors)

    def search(self, query, top_k=10):
        if self.vectors is None:
            return []

        self.load_model()
        query_vec = self.model.encode([query])
        similarities = cosine_similarity(query_vec, self.vectors)[0]

        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            results.append({
                "file_id": self.file_ids[idx],
                "path": self.file_paths[idx],
                "score": float(similarities[idx])
            })

        return results
