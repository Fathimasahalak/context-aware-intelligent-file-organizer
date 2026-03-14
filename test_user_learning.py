
import sqlite3
import os
import json
from ml.filename_cluster import run_filename_clustering, update_category_fingerprint
from database import init_db, get_connection
from config import DB_PATH

def setup_test_data():
    """Setup a fresh test environment with some initial files."""
    if os.path.exists(DB_PATH):
        try: os.remove(DB_PATH)
        except: pass
    init_db()
    
    conn = get_connection()
    cur = conn.cursor()
    
    test_files = [
        # Group 1: Research
        ("C:/Users/test/research_paper_v1.docx", "Abstract: This study explores neural networks..."),
        ("C:/Users/test/data_analysis.xlsx", "Column A: Neural weights, Column B: Accuracy"),
        # Group 2: Personal
        ("C:/Users/test/my_diary.txt", "Today I went to the park and thought about life."),
        ("C:/Users/test/weekend_goals.docx", "Goals for Saturday: Clean room, buy groceries.")
    ]
    
    for path, text in test_files:
        cur.execute("INSERT OR REPLACE INTO files (path, searchable_text, access_count, last_opened) VALUES (?, ?, 1, datetime('now'))", (path, text))
    
    conn.commit()
    conn.close()

def test_scenario():
    print("--- SCENARIO 1: Initial Clustering ---")
    run_filename_clustering()
    
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT path, cluster_label FROM files")
    print("Initial state:")
    for row in cur.fetchall():
        print(f"  - {os.path.basename(row[0])}: [{row[1]}]")

    print("\n--- SCENARIO 2: User Renames a Category ---")
    # Let's say the AI labeled the research group as 'Educational Materials' or similar
    # We find the cluster label for research_paper
    cur.execute("SELECT cluster_label FROM files WHERE path LIKE '%research%' LIMIT 1")
    old_label = cur.fetchone()[0]
    new_label = "Deep Learning Project"
    
    print(f"Renaming '{old_label}' to '{new_label}'...")
    cur.execute("UPDATE files SET cluster_label = ?, is_manual_label = 1 WHERE cluster_label = ?", (new_label, old_label))
    cur.execute("INSERT OR IGNORE INTO user_categories (name) VALUES (?)", (new_label,))
    conn.commit()
    
    # Trigger fingerprint update (learning)
    update_category_fingerprint(new_label)
    
    # DEBUG: Check user_categories
    cur.execute("SELECT name, keywords FROM user_categories")
    print("Learned Categories in DB:")
    for name, keywords in cur.fetchall():
        print(f"  - {name}: {keywords[:100]}...")

    print("\n--- SCENARIO 3: User Moves a File ---")
    # User moves a specific file to a new category
    move_path = "C:/Users/test/my_diary.txt"
    move_label = "Secret Journal"
    print(f"Moving '{os.path.basename(move_path)}' to '{move_label}'...")
    cur.execute("UPDATE files SET cluster_label = ?, is_manual_label = 1 WHERE path = ?", (move_label, move_path))
    cur.execute("INSERT OR IGNORE INTO user_categories (name) VALUES (?)", (move_label,))
    conn.commit()
    update_category_fingerprint(move_label)

    print("\n--- SCENARIO 4: Testing AI Learning (The Big One) ---")
    # Now we add a NEW file that looks like the 'Deep Learning' group
    # and a NEW file that looks like the 'Secret Journal'
    new_files = [
        ("C:/Users/test/cnn_model_results.docx", "Results from the Convolutional Neural Network training... weights and accuracy logs."),
        ("C:/Users/test/midnight_thoughts.txt", "Today I thought about stars and life in the park.")
    ]
    for path, text in new_files:
        cur.execute("INSERT OR REPLACE INTO files (path, searchable_text, access_count, last_opened) VALUES (?, ?, 1, datetime('now'))", (path, text))
    conn.commit()
    
    print("Re-running clustering...")
    run_filename_clustering()
    
    cur.execute("SELECT path, cluster_label, is_manual_label FROM files WHERE path LIKE '%cnn%' OR path LIKE '%midnight%'")
    print("AI's new guesses for unknown files:")
    for row in cur.fetchall():
        manual_str = "(Manual)" if row[2] else "(AI Predicted)"
        print(f"  - {os.path.basename(row[0])}: [{row[1]}] {manual_str}")

    conn.close()

if __name__ == "__main__":
    setup_test_data()
    test_scenario()
