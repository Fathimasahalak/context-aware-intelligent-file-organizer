
import unittest
import threading
import sqlite3
import os
import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_db, get_connection
from ml.semantic_search import SemanticSearch
from ml.filename_cluster import run_filename_clustering

class TestStability(unittest.TestCase):
    def setUp(self):
        self.test_db = "stability_test.db"
        if os.path.exists(self.test_db):
            try: os.remove(self.test_db)
            except: pass
        init_db(self.test_db)
        
        # Add some data
        conn = get_connection(self.test_db)
        cur = conn.cursor()
        for i in range(50):
            cur.execute("INSERT INTO files (path, searchable_text) VALUES (?, ?)", 
                        (f"file_{i}.txt", f"content about topic {i % 5}"))
        conn.commit()
        conn.close()

    def tearDown(self):
        if os.path.exists(self.test_db):
            try: os.remove(self.test_db)
            except: pass
        # Clean up cache files created by SemanticSearch
        for f in ["data/file_embeddings.npy", "data/file_ids.npy"]:
            if os.path.exists(f):
                try: os.remove(f)
                except: pass

    def test_concurrent_searches(self):
        """Simulate multiple threads searching simultaneously."""
        searcher = SemanticSearch(db_path=self.test_db)
        searcher.load_files()
        
        errors = []
        def search_task():
            try:
                for _ in range(10):
                    searcher.search("topic 1", top_k=5)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=search_task) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        
        self.assertEqual(len(errors), 0, f"Concurrent searches produced errors: {errors}")

    def test_concurrent_clustering_and_search(self):
        """Simulate clustering running while searches are happening."""
        searcher = SemanticSearch(db_path=self.test_db)
        searcher.load_files()
        
        errors = []
        stop_event = threading.Event()

        def search_loop():
            try:
                while not stop_event.is_set():
                    searcher.search("topic 2", top_k=5)
                    time.sleep(0.1)
            except Exception as e:
                errors.append(e)

        def cluster_task():
            try:
                for _ in range(3):
                    run_filename_clustering(db_path=self.test_db)
                    time.sleep(0.2)
            except Exception as e:
                errors.append(e)

        t1 = threading.Thread(target=search_loop)
        t2 = threading.Thread(target=cluster_task)
        
        t1.start()
        t2.start()
        
        t2.join()
        stop_event.set()
        t1.join()
        
        self.assertEqual(len(errors), 0, f"Concurrent operations produced errors: {errors}")

if __name__ == "__main__":
    unittest.main()
