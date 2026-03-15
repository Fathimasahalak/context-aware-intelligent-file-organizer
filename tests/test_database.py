import unittest
import tempfile
import os
from core.database import init_db, get_connection


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

    def tearDown(self):
        try: os.unlink(self.db_path)
        except: pass

    def test_get_connection(self):
        conn = get_connection(self.db_path)
        self.assertIsNotNone(conn)
        conn.close()

    def test_init_db(self):
        init_db(self.db_path)
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        
        # Verify all tables
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        self.assertIn('files', tables)
        self.assertIn('sessions', tables)
        self.assertIn('user_categories', tables)
        self.assertIn('category_history', tables)
        
        # Verify specific columns in files table
        cur.execute("PRAGMA table_info(files)")
        columns = [row[1] for row in cur.fetchall()]
        self.assertIn('is_manual_label', columns)
        self.assertIn('cluster_id', columns)
        self.assertIn('cluster_label', columns)
        self.assertIn('searchable_text', columns)
        
        conn.close()


if __name__ == '__main__':
    unittest.main()
