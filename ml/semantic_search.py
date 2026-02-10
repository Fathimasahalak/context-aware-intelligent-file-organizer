from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import numpy as np
import sqlite3
import os


from config import DB_PATH
EMBEDDING_CACHE = os.path.join("data", "file_embeddings.npy")
ID_CACHE = os.path.join("data", "file_ids.npy")


class SemanticSearch:
    def __init__(self, db_path=None):
        self.model = None
        self.file_ids = []
        self.file_paths = []
        self.vectors = None
        self.db_path = db_path or DB_PATH

    def load_model(self):
        if self.model is None:
            self.model = SentenceTransformer('all-MiniLM-L6-v2')

    def load_files(self):
        conn = sqlite3.connect(self.db_path)
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT id, path, searchable_text 
                FROM files 
                WHERE searchable_text IS NOT NULL AND searchable_text != ''
                ORDER BY id ASC
            """)
            rows = cur.fetchall()
        finally:
            conn.close()

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

        # CRITICAL FIX: Remove deleted files from cache
        # Build set of current file IDs from database
        current_ids_set = set(self.file_ids)
        
        # Find indices of cached entries that still exist
        valid_indices = []
        valid_ids = []
        for i, cached_id in enumerate(cached_ids):
            if cached_id in current_ids_set:
                valid_indices.append(i)
                valid_ids.append(cached_id)
        
        # Filter cached vectors to only valid entries
        if valid_indices:
            cached_ids = valid_ids
            cached_vectors = cached_vectors[valid_indices]
        else:
            # All cached entries are stale, start fresh
            cached_ids = []
            cached_vectors = np.array([])

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
            if len(cached_vectors) > 0:
                cached_vectors = np.vstack([cached_vectors, new_vectors])
            else:
                cached_vectors = new_vectors

            np.save(ID_CACHE, np.array(cached_ids))
            np.save(EMBEDDING_CACHE, cached_vectors)

        self.vectors = cached_vectors

    def save_cache(self):
        np.save(ID_CACHE, np.array(self.file_ids))
        np.save(EMBEDDING_CACHE, self.vectors)

    def search(self, query, top_k=10):
        if self.vectors is None or len(self.file_ids) == 0:
            return []

        self.load_model()
        query_vec = self.model.encode([query])
        
        # Handle case where vectors might be 1D (empty case)
        if len(self.vectors.shape) == 1:
            return []
        
        similarities = cosine_similarity(query_vec, self.vectors)[0]

        top_indices = np.argsort(similarities)[::-1][:top_k]

        results = []
        for idx in top_indices:
            # Safety check: ensure index is within bounds
            if idx < len(self.file_ids) and idx < len(self.file_paths):
                results.append({
                    "file_id": self.file_ids[idx],
                    "path": self.file_paths[idx],
                    "score": float(similarities[idx])
                })

        return results

    def remove_file(self, file_path):
        """Remove a file from the index in-memory (fast)"""
        if file_path not in self.file_paths:
            return
            
        try:
            # simple O(N) lookup, fine for <100k files
            idx = self.file_paths.index(file_path)
            
            # Remove from lists
            del self.file_ids[idx]
            del self.file_paths[idx]
            
            # Remove from vectors (numpy delete is O(N))
            if self.vectors is not None:
                self.vectors = np.delete(self.vectors, idx, axis=0)
                
            # Update cache on disk so next load is correct
            self.save_cache()
            print(f"Removed {os.path.basename(file_path)} from index.")
            
        except Exception as e:
            print(f"Error removing file from index: {e}")
