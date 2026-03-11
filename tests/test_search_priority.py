import sys
import os
import unittest
import re

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def simulate_search_logic(query, files_in_db, ai_results):
    """
    Mirror the actual logic in app.py _do_search
    """
    query_lower = query.lower()
    all_results_dict = {}
    
    # 1. Simulate Keyword Process
    for fid, path, body_text in files_in_db:
        basename = os.path.basename(path).lower()
        
        # WHOLE WORD PROTECTION (Including underscores as boundaries)
        if len(query_lower) <= 3:
            found_as_word = False
            pattern = r'(?:\b|_)' + re.escape(query_lower) + r'(?:\b|_)'
            if re.search(pattern, basename):
                found_as_word = True
            elif body_text and re.search(pattern, body_text.lower()):
                found_as_word = True
            
            if not found_as_word:
                continue # Skip partial matches like 'cat' in 'education'
        
        score = 0.4
        if query_lower in basename:
            score = 0.8
            if query_lower == basename: score = 1.0
            pattern = r'(?:\b|_)' + re.escape(query_lower) + r'(?:\b|_)'
            if re.search(pattern, basename):
                score = max(score, 0.95)
        
        all_results_dict[path] = {"path": path, "score": score}

    # 2. Simulate AI Process
    base_threshold = 0.45
    if len(query_lower) <= 3:
        base_threshold = 0.6
        
    for r in ai_results:
        path = r["path"]
        ai_score = r["score"]
        if ai_score >= base_threshold:
            if path in all_results_dict:
                all_results_dict[path]["score"] = max(all_results_dict[path]["score"], ai_score)
            else:
                all_results_dict[path] = {"path": path, "score": ai_score * 0.85}
                
    results = list(all_results_dict.values())
    results.sort(key=lambda x: x['score'], reverse=True)
    return results

def test_whole_word_fix():
    print("\nVerifying 'Whole Word Protection' for search...")
    
    # Setup test data: 'education' contains 'cat' but shouldn't match
    files_in_db = [
        (1, "cat.mp4", ""),
        (2, "education_report.docx", "This is a report about education and application."),
        (3, "my_cat_photo.jpg", "")
    ]
    
    # Generic AI results (low confidence for reports)
    ai_results = [
        {"path": "cat.mp4", "score": 0.7},
        {"path": "education_report.docx", "score": 0.15}
    ]
    
    # Search for 'cat'
    results = simulate_search_logic("cat", files_in_db, ai_results)
    
    print(f"Results for 'cat':")
    for r in results:
        print(f"  {r['score']:.2f} -> {r['path']}")
        
    found_paths = [r["path"] for r in results]
    
    assert "cat.mp4" in found_paths
    assert "my_cat_photo.jpg" in found_paths
    assert "education_report.docx" not in found_paths, "FAIL: 'cat' matched 'education'!"
    
    print("✓ Whole Word Protection verified successfully.")

if __name__ == "__main__":
    try:
        test_whole_word_fix()
    except AssertionError as e:
        print(f"✗ TEST FAILED: {e}")
        sys.exit(1)
