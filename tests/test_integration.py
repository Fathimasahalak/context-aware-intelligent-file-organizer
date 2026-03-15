"""
Comprehensive End-to-End Integration Test
Tests the entire FileSense workflow
"""
import sys
import os
import tempfile
import shutil
import sqlite3

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import init_db
from core.logger import start_file_session, end_file_session
from ml.filename_cluster import run_filename_clustering
from ml.semantic_search import SemanticSearch
from ml.recommendation import get_smart_priority_files
from core.text_extractor import get_searchable_text

def test_end_to_end():
    """Test complete workflow: add files → cluster → search → delete → verify"""
    
    print("=" * 60)
    print("COMPREHENSIVE END-TO-END TEST")
    print("=" * 60)
    
    # Create temp directory
    temp_dir = tempfile.mkdtemp()
    test_db = os.path.join(temp_dir, "test.db")
    
    try:
        # 1. Initialize database
        print("\n[1/7] Initializing database...")
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                path TEXT UNIQUE,
                searchable_text TEXT,
                access_count INTEGER DEFAULT 0,
                total_time INTEGER DEFAULT 0,
                last_opened TEXT,
                cluster_id INTEGER,
                cluster_label TEXT,
                is_manual_label INTEGER DEFAULT 0
            )
        """)
        cur.execute("""
            CREATE TABLE sessions (
                id INTEGER PRIMARY KEY,
                file_id INTEGER,
                open_time TEXT,
                close_time TEXT,
                duration INTEGER
            )
        """)
        cur.execute("""
            CREATE TABLE user_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE,
                keywords TEXT
            )
        """)
        conn.commit()
        conn.close()
        print("✓ Database initialized")
        
        # 2. Add test files
        print("\n[2/7] Adding test files...")
        test_files = [
            ("invoice_jan.pdf", "Invoice for January 2024 services rendered to client"),
            ("invoice_feb.pdf", "Invoice for February 2024 consulting work"),
            ("project_report.docx", "Final project report for Q1 2024 deliverables"),
            ("meeting_notes.txt", "Notes from weekly team meeting discussion"),
            ("math_homework.pdf", "Calculus homework assignment chapter 5"),
        ]
        
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        for i, (path, text) in enumerate(test_files, 1):
            cur.execute(
                "INSERT INTO files(id, path, searchable_text, access_count, last_opened) VALUES (?,?,?,?,datetime('now'))",
                (i, path, text, i)  # Higher ID = more recent
            )
        conn.commit()
        conn.close()
        print(f"✓ Added {len(test_files)} files")
        
        # 3. Test clustering
        print("\n[3/7] Testing dynamic clustering...")
        run_filename_clustering(db_path=test_db)
        
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        cur.execute("SELECT COUNT(DISTINCT cluster_id) FROM files WHERE cluster_id IS NOT NULL")
        num_clusters = cur.fetchone()[0]
        conn.close()
        assert num_clusters >= 2, f"Expected at least 2 clusters, got {num_clusters}"
        print(f"✓ Created {num_clusters} clusters")
        
        # 4. Test semantic search
        print("\n[4/7] Testing semantic search...")
        searcher = SemanticSearch(db_path=test_db)
        searcher.load_files()
        
        results = searcher.search("invoice", top_k=5)
        assert len(results) >= 2, f"Expected at least 2 invoice results, got {len(results)}"
        print(f"✓ Search returned {len(results)} results for 'invoice'")
        
        # 5. Test file deletion
        print("\n[5/7] Testing file deletion...")
        conn = sqlite3.connect(test_db)
        cur = conn.cursor()
        cur.execute("DELETE FROM files WHERE id = 1")
        conn.commit()
        conn.close()
        
        searcher.remove_file("invoice_jan.pdf")
        assert len(searcher.file_ids) == 4, f"Expected 4 files after deletion, got {len(searcher.file_ids)}"
        print("✓ File deleted from database and search index")
        
        # 6. Test cache persistence
        print("\n[6/7] Testing cache persistence...")
        searcher2 = SemanticSearch(db_path=test_db)
        searcher2.load_files()
        assert len(searcher2.file_ids) == 4, f"Expected 4 files after reload, got {len(searcher2.file_ids)}"
        print("✓ Cache correctly synced with database")
        
        # 7. Test search after deletion
        print("\n[7/7] Testing search after deletion...")
        results = searcher2.search("invoice", top_k=5)
        assert len(results) >= 1, f"Expected at least 1 result, got {len(results)}"
        print(f"✓ Search works after deletion ({len(results)} results)")
        
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise
        
    finally:
        # Cleanup
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    test_end_to_end()
