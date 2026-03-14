import unittest
import sqlite3
import os
import sys

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.filename_cluster import run_filename_clustering

class TestClustering(unittest.TestCase):

    def setUp(self):
        # Create a temporary database
        self.test_db = "test_files.db"
        if os.path.exists(self.test_db):
            try: os.remove(self.test_db)
            except: pass
            
        self.conn = sqlite3.connect(self.test_db)
        self.cur = self.conn.cursor()
        
        # Create table with all required columns
        self.cur.execute("""
            CREATE TABLE files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT,
                searchable_text TEXT,
                cluster_id INTEGER,
                cluster_label TEXT,
                is_manual_label INTEGER DEFAULT 0
            )
        """)
        self.cur.execute("""
            CREATE TABLE user_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                keywords TEXT
            )
        """)
        
        # Insert dummy data
        data = [
            ("invoice_jan.pdf", "payment for services invoice"),
            ("invoice_feb.pdf", "bill amount due"),
            ("assignment_1.docx", "homework study math"),
            ("notes_os.txt", "operating systems lecture notes"),
            ("project_proposal.doc", "work project plan timeline"),
        ]
        
        for path, text in data:
            self.cur.execute("INSERT INTO files (path, searchable_text) VALUES (?, ?)", (path, text))
            
        self.conn.commit()
        
    def tearDown(self):
        self.conn.close()
        if os.path.exists(self.test_db):
            os.remove(self.test_db)
            
    def test_clustering_runs(self):
        # Run clustering with 2 clusters (Study vs Work)
        # We need to pass the custom db path
        run_filename_clustering(k=2, db_path=self.test_db)
        
        # Verify clusters are assigned
        self.cur.execute("SELECT count(*) FROM files WHERE cluster_id IS NOT NULL")
        count = self.cur.fetchone()[0]
        self.assertEqual(count, 5)
        
        # Verify labels are generated
        self.cur.execute("SELECT distinct cluster_label FROM files")
        labels = self.cur.fetchall()
        self.assertEqual(len(labels), 2)
        
        # Check specific assignments (invoice should be separate from notes)
        self.cur.execute("SELECT cluster_id FROM files WHERE path LIKE 'invoice%'")
        invoice_ids = [r[0] for r in self.cur.fetchall()]
        
        self.cur.execute("SELECT cluster_id FROM files WHERE path LIKE 'notes%'")
        notes_ids = [r[0] for r in self.cur.fetchall()]
        
        # Invoices should be in same cluster
        self.assertEqual(len(set(invoice_ids)), 1)
        
        # Notes should be in different cluster than invoices
        self.assertNotEqual(invoice_ids[0], notes_ids[0])

if __name__ == '__main__':
    unittest.main()
