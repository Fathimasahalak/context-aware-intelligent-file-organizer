
import os
import json
import logging
import sys
import shutil

def get_app_data_dir():
    """Returns a system-specific, non-synced directory for app data."""
    if sys.platform == 'win32':
        # %LOCALAPPDATA% is not synced by Roaming Profiles or OneDrive
        base = os.environ.get('LOCALAPPDATA', os.path.expanduser('~\\AppData\\Local'))
    elif sys.platform == 'darwin':
        base = os.path.expanduser('~/Library/Application Support')
    else:
        # Linux/Unix following XDG Base Directory Specification
        base = os.environ.get('XDG_DATA_HOME', os.path.expanduser('~/.local/share'))
    
    path = os.path.join(base, 'FileSense')
    os.makedirs(path, exist_ok=True)
    return path

DATA_DIR = get_app_data_dir()
DB_PATH = os.path.join(DATA_DIR, "file_logs.db")
LOG_DIR = os.path.join(DATA_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)

def migrate_legacy_data():
    """Migrates existing data from the project root to the new system-specific DATA_DIR."""
    project_root = os.path.dirname(os.path.abspath(__file__))
    legacy_data = os.path.join(project_root, "data")
    legacy_logs = os.path.join(project_root, "logs")
    
    # 1. Migrate database and AI cache files
    if os.path.exists(legacy_data) and os.path.isdir(legacy_data):
        for item in os.listdir(legacy_data):
            old_path = os.path.join(legacy_data, item)
            new_path = os.path.join(DATA_DIR, item)
            
            # Skip moving if it's already in the destination or if it's not a file
            if os.path.isfile(old_path) and not os.path.exists(new_path):
                try:
                    shutil.move(old_path, new_path)
                    print(f"Migrated {item} to {DATA_DIR}")
                except Exception as e:
                    print(f"Failed to migrate {item}: {e}")
        
        # Cleanup legacy directory if empty
        try:
            if not os.listdir(legacy_data):
                os.rmdir(legacy_data)
        except: pass

    # 2. Migrate log files
    if os.path.exists(legacy_logs) and os.path.isdir(legacy_logs):
        for item in os.listdir(legacy_logs):
            old_path = os.path.join(legacy_logs, item)
            new_path = os.path.join(LOG_DIR, item)
            
            if os.path.isfile(old_path) and not os.path.exists(new_path):
                try:
                    shutil.move(old_path, new_path)
                except: pass
        
        # Cleanup legacy directory if empty
        try:
            if not os.listdir(legacy_logs):
                os.rmdir(legacy_logs)
        except: pass

# Run migration once on import
migrate_legacy_data()

# File Extensions
DOCUMENT_EXTENSIONS = {'.pdf', '.txt', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv', '.md', '.html', '.htm', '.jpg', '.png', '.jpeg', '.gif', '.bmp'}

# Model Settings
MAX_PDF_PAGES = 5
CLUSTERING_CLUSTERS = 5
