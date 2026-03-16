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
FILENAME_EMBEDDING_CACHE = os.path.join(_project_root, "data", "filename_embeddings.npy")
ID_CACHE = os.path.join(_project_root, "data", "file_ids.npy")

MAX_CACHE_FILES = 10000 # Increased for better scalability


class SemanticSearch:
    def __init__(self, db_path=None):
        self.model = None
        self.file_ids = []
        self.file_paths = []
        self.vectors = None
        self.name_vectors = None
        self.db_path = db_path or DB_PATH
        self._load_lock = threading.Lock()

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

    def load_files(self, force_rebuild=False):
        """Sync database files with the semantic vector cache efficiently."""
        with self._load_lock:
            from core.database import get_connection
            
            # 1. Load DB state (Lightweight)
            conn = get_connection(self.db_path)
            cur = conn.cursor()
            try:
                cur.execute("SELECT id, path FROM files ORDER BY id ASC")
                db_rows = cur.fetchall()
            finally:
                conn.close()

            if not db_rows:
                self.file_ids = []
                self.file_paths = []
                self.vectors = np.array([])
                self.name_vectors = np.array([])
                self.save_cache()
                return

            db_id_map = {row[0]: row[1] for row in db_rows}
            db_ids = set(db_id_map.keys())

            # 2. Load Cache
            cached_ids = []
            cached_vectors = None
            cached_name_vectors = None
            
            if not force_rebuild and os.path.exists(ID_CACHE) and os.path.exists(EMBEDDING_CACHE):
                try:
                    cached_ids = np.load(ID_CACHE).tolist()
                    cached_vectors = np.load(EMBEDDING_CACHE)
                    if os.path.exists(FILENAME_EMBEDDING_CACHE):
                        cached_name_vectors = np.load(FILENAME_EMBEDDING_CACHE)
                    
                    # Validation
                    if len(cached_ids) != len(cached_vectors):
                        logging.warning("Cache size mismatch. Rebuilding.")
                        cached_ids = []
                        cached_vectors = None
                        cached_name_vectors = None
                except Exception as e:
                    logging.warning(f"Cache corrupt: {e}")
                    cached_ids = []

            # 3. Identify Changes
            cached_id_set = set(cached_ids)
            
            # A. Deletions (In cache but not in DB)
            ids_to_remove = cached_id_set - db_ids
            if ids_to_remove:
                logging.info(f"Removing {len(ids_to_remove)} obsolete files from index...")
                indices_to_keep = [i for i, fid in enumerate(cached_ids) if fid in db_ids]
                
                if cached_vectors is not None:
                    cached_vectors = cached_vectors[indices_to_keep]
                if cached_name_vectors is not None:
                    cached_name_vectors = cached_name_vectors[indices_to_keep]
                cached_ids = [cached_ids[i] for i in indices_to_keep]

            # B. Additions (In DB but not in cache)
            ids_to_add = list(db_ids - set(cached_ids))
            if ids_to_add:
                logging.info(f"Indexing {len(ids_to_add)} new files...")
                
                # Batch fetch text for new files only
                conn = get_connection(self.db_path)
                cur = conn.cursor()
                
                # Split into chunks to avoid too many SQL variables
                chunk_size = 900
                
                model = self.get_model()
                if not model:
                    logging.error("Model unavailable. Skipping indexing.")
                    return

                for i in range(0, len(ids_to_add), chunk_size):
                    chunk_ids = ids_to_add[i:i + chunk_size]
                    placeholders = ',' .join('?' * len(chunk_ids))
                    cur.execute(f"SELECT id, path, searchable_text FROM files WHERE id IN ({placeholders})", chunk_ids)
                    new_rows = cur.fetchall()
                    
                    # Use a dictionary to maintain DB order
                    row_map = {row[0]: row for row in new_rows}
                    
                    texts_to_encode = []
                    names_to_encode = []
                    for fid in chunk_ids:
                        if fid not in row_map: continue
                        fid, path, text = row_map[fid]
                        filename = os.path.basename(path)
                        name_no_ext = os.path.splitext(filename)[0].replace('_', ' ').replace('-', ' ')
                        
                        names_to_encode.append(name_no_ext)
                        texts_to_encode.append(text if (text and text.strip()) else name_no_ext)
                    
                    if names_to_encode:
                        name_vectors = model.encode(names_to_encode, show_progress_bar=True)
                        if cached_name_vectors is None or len(cached_name_vectors) == 0:
                            cached_name_vectors = name_vectors
                        else:
                            cached_name_vectors = np.concatenate([cached_name_vectors, name_vectors], axis=0)
                    
                    if texts_to_encode:
                        vectors = model.encode(texts_to_encode, show_progress_bar=True)
                        if cached_vectors is None or len(cached_vectors) == 0:
                            cached_vectors = vectors
                        else:
                            cached_vectors = np.concatenate([cached_vectors, vectors], axis=0)
                
                conn.close()
                cached_ids.extend(ids_to_add)

            # 4. Update Memory & Cache
            self.file_ids = cached_ids
            # Reconstruct paths list in correct order corresponding to IDs
            self.file_paths = [db_id_map.get(fid, "UNKNOWN") for fid in self.file_ids]
            self.vectors = cached_vectors if cached_vectors is not None else np.array([])
            self.name_vectors = cached_name_vectors if cached_name_vectors is not None else np.array([])
            
            self.save_cache()
            logging.info(f"Search index synced. Total: {len(self.file_ids)}")



    def save_cache(self):
        np.save(ID_CACHE, np.array(self.file_ids))
        np.save(EMBEDDING_CACHE, self.vectors)
        np.save(FILENAME_EMBEDDING_CACHE, self.name_vectors)

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
        
        # Calculate similarities for both content and filename
        body_sims = cosine_similarity(query_vec, self.vectors)[0]
        
        if self.name_vectors is not None and len(self.name_vectors) == len(self.vectors):
            name_sims = cosine_similarity(query_vec, self.name_vectors)[0]
            
            # --- Improved Combination Logic ---
            # 1. Start with a balanced weighted average
            # (Increase body weight to 0.5 to respect "overall contents" more)
            weighted_sims = (name_sims * 0.5) + (body_sims * 0.5)
            
            # 2. Use np.maximum to ensure that if EITHER the name OR the content 
            # is an extremely strong match, we don't penalize it by averaging with a weak match.
            # We use a slight multiplier (0.95) on the max to keep pure matches very high.
            similarities = np.maximum(weighted_sims, np.maximum(name_sims, body_sims) * 0.95)
        else:
            similarities = body_sims

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
            if self.name_vectors is not None and len(self.name_vectors) > idx:
                self.name_vectors = np.delete(self.name_vectors, idx, axis=0)
                
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
