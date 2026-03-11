import os
import sys
import subprocess
import logging

def open_path(path):
    """Cross-platform path opening"""
    try:
        # Normalize for OS
        path = os.path.normpath(os.path.abspath(path))
        
        if sys.platform == 'win32':
            os.startfile(path)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', path])
        else:
            subprocess.Popen(['xdg-open', path])
    except Exception as e:
        logging.error(f"Failed to open path {path}: {e}")
        raise e

def normalize_path(path):
    """Consistent path normalization for comparison and storage"""
    if not path:
        return ""
    return os.path.normpath(os.path.abspath(path))
