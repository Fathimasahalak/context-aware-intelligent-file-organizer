import sys
import os
import tempfile
import shutil

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ml.semantic_search import SemanticSearch
import sqlite3
import numpy as np

def test_search_after_deletion():
    """Test that search works correctly after files are deleted"""
    
    # Create temp database
    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, "test.db")
    
    try:
        # Setup database
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                path TEXT,
                searchable_text TEXT,
                access_count INTEGER DEFAULT 0,
                total_time INTEGER DEFAULT 0,
                last_opened TEXT,
                cluster_id INTEGER,
                cluster_label TEXT
            )
        """)
        
        # Insert test files
        files = [
            (1, "invoice_jan.pdf", "Invoice for January services rendered"),
            (2, "invoice_feb.pdf", "Invoice for February consulting work"),
            (3, "notes.txt", "Meeting notes from project discussion"),
        ]
        
        for fid, path, text in files:
            cur.execute(
                "INSERT INTO files(id, path, searchable_text) VALUES (?,?,?)",
                (fid, path, text)
            )
        conn.commit()
        conn.close()
        
        # Create searcher and load files
        searcher = SemanticSearch(db_path=test_db)
        searcher.load_files()
        
        # Verify initial state
        assert len(searcher.file_ids) == 3, f"Expected 3 files, got {len(searcher.file_ids)}"
        
        # Search for "invoice"
        results = searcher.search("invoice", top_k=5)
        assert len(results) >= 2, f"Expected at least 2 invoice results, got {len(results)}"
        
        # Delete one file from database
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        cur.execute("DELETE FROM files WHERE id = 1")
        conn.commit()
        conn.close()
        
        # Remove from searcher
        searcher.remove_file("invoice_jan.pdf")
        
        # Verify removal
        assert len(searcher.file_ids) == 2, f"Expected 2 files after deletion, got {len(searcher.file_ids)}"
        
        # Search again - should NOT crash
        results = searcher.search("invoice", top_k=5)
        assert len(results) >= 1, f"Expected at least 1 invoice result after deletion, got {len(results)}"
        
        # Reload from cache (simulates app restart)
        searcher2 = SemanticSearch(db_path=test_db)
        searcher2.load_files()
        
        # Should have synced with database and removed deleted file
        assert len(searcher2.file_ids) == 2, f"Expected 2 files after reload, got {len(searcher2.file_ids)}"
        
        # Search should still work
        results = searcher2.search("invoice", top_k=5)
        assert len(results) >= 1, f"Expected results after reload, got {len(results)}"
        
        print("✓ Search after deletion test PASSED")
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_search_after_deletion()
