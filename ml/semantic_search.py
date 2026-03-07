from sklearn.metrics.pairwise import cosine_similarity
from sentence_transformers import SentenceTransformer
import numpy as np
import sqlite3
import os
import logging
import threading

# Silence verbose BERT loading logs
logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
logging.getLogger("transformers").setLevel(logging.ERROR)
logging.getLogger("huggingface_hub").setLevel(logging.ERROR)
os.environ["TOKENIZERS_PARALLELISM"] = "false"

# Global singletons and locks
_shared_model = None
_model_lock = threading.Lock()
_shared_searcher = None
_searcher_lock = threading.Lock()


from config import DB_PATH
import os
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
EMBEDDING_CACHE = os.path.join(_project_root, "data", "file_embeddings.npy")
ID_CACHE = os.path.join(_project_root, "data", "file_ids.npy")

MAX_CACHE_FILES = 10000 # Increased for better scalability


class SemanticSearch:
    def __init__(self, db_path=None):
        self.model = None
        self.file_ids = []
        self.file_paths = []
        self.vectors = None
        self.db_path = db_path or DB_PATH

    def load_model(self):
        global _shared_model
        with _model_lock:
            if _shared_model is None:
                model_name = 'all-MiniLM-L6-v2'
                try:
                    # Attempt 1: 100% Offline Load (No internet ping)
                    logging.info(f"Loading {model_name} from local cache...")
                    _shared_model = SentenceTransformer(model_name, local_files_only=True)
                except Exception:
                    # Attempt 2: Download if missing (First run only)
                    logging.info(f"{model_name} not found locally. Connecting to HuggingFace to download AI model...")
                    max_retries = 2
                    for attempt in range(max_retries):
                        try:
                            _shared_model = SentenceTransformer(model_name, local_files_only=False)
                            logging.info("Model downloaded and loaded successfully.")
                            break
                        except Exception as e:
                            logging.error(f"Download failed on attempt {attempt + 1}: {e}")
                            if attempt < max_retries - 1:
                                import time
                                time.sleep(3)
                            else:
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
        """Sync database files with the semantic vector cache."""
        from database import get_connection
        conn = get_connection(self.db_path)
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
            self.file_ids = []
            self.file_paths = []
            self.vectors = np.array([])
            return

        # Current files in database
        db_ids = [r[0] for r in rows]
        db_paths = [r[1] for r in rows]
        db_texts = [r[2] for r in rows]

        # Limit cache size to prevent excessive disk usage
        if len(db_ids) > MAX_CACHE_FILES:
            logging.warning(f"Warning: Too many files ({len(db_ids)}) for caching. Limiting to {MAX_CACHE_FILES} most recent.")
            db_ids = db_ids[-MAX_CACHE_FILES:]
            db_paths = db_paths[-MAX_CACHE_FILES:]
            db_texts = db_texts[-MAX_CACHE_FILES:]

        # Load existing cache if available
        cached_ids = []
        cached_vectors = None
        if os.path.exists(ID_CACHE) and os.path.exists(EMBEDDING_CACHE):
            try:
                cached_ids = np.load(ID_CACHE).tolist()
                cached_vectors = np.load(EMBEDDING_CACHE)
            except Exception as e:
                logging.warning(f"Failed to load embedding cache: {e}")

        # Map for fast lookup: ID -> Vector
        id_to_vec = {}
        if cached_vectors is not None and len(cached_ids) == len(cached_vectors):
            for i, fid in enumerate(cached_ids):
                id_to_vec[fid] = cached_vectors[i]

        # Determine which files need new embeddings
        final_vectors = []
        new_texts = []
        new_text_indices = []

        for i, fid in enumerate(db_ids):
            if fid in id_to_vec:
                # Existing vector found
                final_vectors.append(id_to_vec[fid])
            else:
                # Missing vector: Mark for encoding
                final_vectors.append(None) # Placeholder
                new_texts.append(db_texts[i])
                new_text_indices.append(i)

        # Compute new embeddings if needed
        if new_texts:
            model = self.get_model()
            if model:
                logging.info(f"Embedding {len(new_texts)} new files...")
                new_vecs = model.encode(new_texts, show_progress_bar=True)
                # Fill placeholders
                for i, vec in enumerate(new_vecs):
                    final_vectors[new_text_indices[i]] = vec
            else:
                # Fallback: remove placeholders if model failed
                logging.error("Model unavailable. New files will not be searchable semantically.")
                final_vectors = [v for v in final_vectors if v is not None]
                db_ids = [db_ids[i] for i, v in enumerate(final_vectors) if v is not None]
                db_paths = [db_paths[i] for i, v in enumerate(final_vectors) if v is not None]

        # Convert back to numpy and update instance state
        if final_vectors:
            self.vectors = np.array(final_vectors)
            self.file_ids = db_ids
            self.file_paths = db_paths
            # Update cache on disk for next run
            self.save_cache()
        else:
            self.vectors = np.array([])
            self.file_ids = []
            self.file_paths = []


    def save_cache(self):
        np.save(ID_CACHE, np.array(self.file_ids))
        np.save(EMBEDDING_CACHE, self.vectors)

    def search(self, query, top_k=10):
        if self.vectors is None or len(self.file_ids) == 0:
            return []

        model = self.get_model()
        if model is None:
            return []

        # Safety: truncate extremely long queries
        if len(query) > 500:
            query = query[:500]

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


def get_semantic_searcher(db_path=None):
    """Get or create the shared SemanticSearch instance with thread safety."""
    global _shared_searcher
    with _searcher_lock:
        if _shared_searcher is None:
            _shared_searcher = SemanticSearch(db_path)
            _shared_searcher.load_files()
    return _shared_searcher

def reset_semantic_searcher():
    """Reset the shared instance (useful for testing)."""
    global _shared_searcher
    _shared_searcher = None
