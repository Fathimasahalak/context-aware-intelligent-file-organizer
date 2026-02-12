from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import numpy as np
import sqlite3
import os
import logging

# Silence verbose BERT loading logs
logging.getLogger("sentence_transformers").setLevel(logging.INFO) # Allow some info logs
logging.getLogger("transformers").setLevel(logging.WARNING) # Only show warnings/errors
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Global singleton for the model to prevent re-loading
_shared_model = None


from config import DB_PATH
import os
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
EMBEDDING_CACHE = os.path.join(_project_root, "data", "file_embeddings.npy")
ID_CACHE = os.path.join(_project_root, "data", "file_ids.npy")

MAX_CACHE_FILES = 1000


class SemanticSearch:
    def __init__(self, db_path=None):
        self.model = None
        self.file_ids = []
        self.file_paths = []
        self.vectors = None
        self.db_path = db_path or DB_PATH

    def load_model(self):
        global _shared_model
        if _shared_model is None:
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    logging.info(f"Loading AI model (BERT), attempt {attempt + 1}...")
                    from sentence_transformers import SentenceTransformer
                    _shared_model = SentenceTransformer('all-MiniLM-L6-v2')
                    logging.info("Model loaded successfully.")
                    break
                except Exception as e:
                    logging.error(f"Model loading failed on attempt {attempt + 1}: {e}")
                    if attempt < max_retries - 1:
                        import time
                        time.sleep(2)  # Wait before retry
                    else:
                        logging.error("All attempts failed.")
                        _shared_model = None
                        raise e
        self.model = _shared_model

    def get_model(self):
        if self.model is None:
            try:
                self.load_model()
            except Exception as e:
                logging.error(f"Model loading failed, search will not work: {e}")
                self.model = None
        return self.model

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

        if not rows:
            self.vectors = np.array([])
            return

        self.file_ids = [r[0] for r in rows]
        self.file_paths = [r[1] for r in rows]
        texts = [r[2] for r in rows]

        # Limit cache size to prevent excessive disk usage
        if len(self.file_ids) > MAX_CACHE_FILES:
            logging.warning(f"Warning: Too many files ({len(self.file_ids)}) for caching. Limiting to {MAX_CACHE_FILES} most recent.")
            self.file_ids = self.file_ids[-MAX_CACHE_FILES:]  # Keep most recent IDs
            self.file_paths = self.file_paths[-MAX_CACHE_FILES:]
            texts = texts[-MAX_CACHE_FILES:]

        model = self.get_model()
        if model is None:
            logging.error("Semantic model not available, skipping embedding.")
            self.vectors = np.array([])
            return

        # No cache → compute all
        if not os.path.exists(EMBEDDING_CACHE) or not os.path.exists(ID_CACHE):
            logging.info("No embedding cache found. Computing all...")
            self.vectors = model.encode(texts, show_progress_bar=True)
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
            logging.info(f"Embedding {len(new_entries)} new files...")
            new_vectors = model.encode(new_texts, show_progress_bar=True)

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

        model = self.get_model()
        if model is None:
            return []

        query_vec = model.encode([query])
        
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
        # Normalize path for comparison
        file_path = os.path.normpath(os.path.abspath(file_path))
        
        # Normalize all paths in self.file_paths for comparison
        norm_paths = [os.path.normpath(os.path.abspath(p)) for p in self.file_paths]
        
        if file_path not in norm_paths:
            logging.debug(f"File {file_path} not found in semantic index.")
            return
            
        try:
            idx = norm_paths.index(file_path)
            
            # Remove from lists
            del self.file_ids[idx]
            del self.file_paths[idx]
            
            # Remove from vectors
            if self.vectors is not None and len(self.vectors) > idx:
                self.vectors = np.delete(self.vectors, idx, axis=0)
                
            # Update cache on disk
            self.save_cache()
            logging.info(f"Removed {os.path.basename(file_path)} from semantic index.")
            
        except Exception as e:
            logging.error(f"Error removing file from index: {e}")


# Global singleton instance for SemanticSearch
_shared_searcher = None

def get_semantic_searcher(db_path=None):
    """Get or create the shared SemanticSearch instance.
    
    This ensures the BERT model is loaded only once across the application.
    """
    global _shared_searcher
    if _shared_searcher is None:
        _shared_searcher = SemanticSearch(db_path)
        _shared_searcher.load_files()
    return _shared_searcher

def reset_semantic_searcher():
    """Reset the shared instance (useful for testing)."""
    global _shared_searcher
    _shared_searcher = None
