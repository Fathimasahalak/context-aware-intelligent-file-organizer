import sys
import os
import logging

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from ml.semantic_search import get_semantic_searcher
from config import DB_PATH
import sqlite3

def debug_live_scores():
    print(f"--- DIAGNOSING REAL AI SCORES ---")
    print(f"Database: {DB_PATH}")
    
    # 1. Initialize the real searcher (this loads the model)
    print("Loading AI Model (BERT)...")
    searcher = get_semantic_searcher()
    
    # 2. Define queries to test
    queries = ["cat", "docx"]
    
    for query in queries:
        print(f"\nResults for query: '{query}'")
        print(f"{'Score':<10} | {'File Path'}")
        print("-" * 60)
        
        # We manually call the model to see RAW scores before our app's filtering
        model = searcher.get_model()
        if not model:
            print("Error: Could not load model.")
            return
            
        query_vec = model.encode([query])
        
        # Get all files and their text from DB
        from database import get_connection
        conn = get_connection(DB_PATH)
        cur = conn.cursor()
        cur.execute("SELECT path, searchable_text FROM files")
        files = cur.fetchall()
        conn.close()
        
        results = []
        from sklearn.metrics.pairwise import cosine_similarity
        
        for path, text in files:
            # Get the real embedding for this specific file
            # (Note: In production we use the cached searcher.vectors, 
            # but here we re-encode to be 100% sure we see the raw behavior)
            file_vec = model.encode([text if text else os.path.basename(path)])
            score = float(cosine_similarity(query_vec, file_vec)[0][0])
            results.append((score, path))
            
        # Sort by raw AI score
        results.sort(key=lambda x: x[0], reverse=True)
        
        for score, path in results:
            status = " [PASS]" if score >= 0.6 else " [FAIL]" if score < 0.45 else " [?] "
            print(f"{score:<10.4f} | {os.path.basename(path)}{status}")

if __name__ == "__main__":
    # Suppress noise
    logging.getLogger("sentence_transformers").setLevel(logging.WARNING)
    debug_live_scores()
