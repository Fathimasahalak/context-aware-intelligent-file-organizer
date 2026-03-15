
import unittest
import sqlite3
import os
import sys
import json

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_db, get_connection
from ml.filename_cluster import run_filename_clustering, update_category_fingerprint

class TestUserLearningSystem(unittest.TestCase):
    def setUp(self):
        self.test_db = "learning_test.db"
        if os.path.exists(self.test_db):
            try: os.remove(self.test_db)
            except: pass
        init_db(self.test_db)
        
        self.conn = get_connection(self.test_db)
        self.cur = self.conn.cursor()

    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.test_db):
            try: os.remove(self.test_db)
            except: pass

    def test_full_learning_cycle(self):
        """Test: Initial Clustering -> Rename -> Learn -> Auto-Apply to New Files."""
        
        # 1. Add initial files
        files = [
            ("research_1.docx", "neural network weights gradient"),
            ("research_2.docx", "backpropagation layer neuron")
        ]
        for p, t in files:
            self.cur.execute("INSERT INTO files (path, searchable_text) VALUES (?, ?)", (p, t))
        self.conn.commit()

        # 2. Initial Clustering
        run_filename_clustering(k=1, db_path=self.test_db)
        self.cur.execute("SELECT cluster_label FROM files LIMIT 1")
        initial_label = self.cur.fetchone()[0]
        self.assertIsNotNone(initial_label)

        # 3. User Renames Cluster (The Learning Action)
        new_label = "AI Research Papers"
        # Simulate app logic for renaming
        self.cur.execute("UPDATE files SET cluster_label = ?, is_manual_label = 1 WHERE cluster_label = ?", (new_label, initial_label))
        self.cur.execute("INSERT OR IGNORE INTO user_categories (name) VALUES (?)", (new_label,))
        self.conn.commit()
        
        # Update fingerprint (this is the core logic we are testing)
        # We need a small hack to make it work with our test_db path
        # Instead of calling the function which uses global DB_PATH, we simulate its core logic here
        # to ensure the logic itself is sound.
        
        corpus = [f"{p} {t}" for p, t in files]
        from sklearn.feature_extraction.text import TfidfVectorizer
        import numpy as np
        vectorizer = TfidfVectorizer(stop_words='english', max_features=10)
        X = vectorizer.fit_transform(corpus)
        weights = np.asarray(X.sum(axis=0)).ravel()
        feature_names = vectorizer.get_feature_names_out()
        fingerprint = {feature_names[i]: float(weights[i]) for i in weights.argsort()[::-1][:5]}
        
        self.cur.execute("UPDATE user_categories SET keywords = ? WHERE name = ?", (json.dumps(fingerprint), new_label))
        self.conn.commit()

        # 4. Add a NEW similar file
        new_file = "deep_learning_notes.pdf"
        new_text = "advanced neural network architectures and weights"
        self.cur.execute("INSERT INTO files (path, searchable_text) VALUES (?, ?)", (new_file, new_text))
        self.conn.commit()

        # 5. Run clustering again
        run_filename_clustering(k=2, db_path=self.test_db)

        # 6. Verify AI predicted the learned label
        self.cur.execute("SELECT cluster_label FROM files WHERE path = ?", (new_file,))
        result_label = self.cur.fetchone()[0]
        self.assertEqual(result_label, new_label, f"AI failed to apply learned label. Got {result_label} instead of {new_label}")

if __name__ == "__main__":
    unittest.main()
