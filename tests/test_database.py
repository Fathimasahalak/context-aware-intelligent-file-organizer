import unittest
import tempfile
import os
from database import init_db, get_connection


class TestDatabase(unittest.TestCase):
    def setUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name

    def tearDown(self):
        os.unlink(self.db_path)

    def test_get_connection(self):
        conn = get_connection(self.db_path)
        self.assertIsNotNone(conn)
        conn.close()

    def test_init_db(self):
        init_db(self.db_path)
        conn = get_connection(self.db_path)
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cur.fetchall()]
        self.assertIn('files', tables)
        self.assertIn('sessions', tables)
        conn.close()


if __name__ == '__main__':
    unittest.main()
