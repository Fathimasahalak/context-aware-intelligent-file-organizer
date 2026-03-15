
import os
import json
import logging

# Database
DB_PATH = os.path.join("data", "file_logs.db")

# File Extensions
DOCUMENT_EXTENSIONS = {'.pdf', '.txt', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv', '.md', '.html', '.htm', '.jpg', '.png', '.jpeg', '.gif', '.bmp'}

# Model Settings
MAX_PDF_PAGES = 5
CLUSTERING_CLUSTERS = 5

# Load Category Mappings from external JSON
CATEGORIES_FILE = "categories.json"
DEFAULT_CATEGORIES = {}

if os.path.exists(CATEGORIES_FILE):
    try:
        with open(CATEGORIES_FILE, 'r') as f:
            DEFAULT_CATEGORIES = json.load(f)
    except Exception as e:
        logging.error(f"Failed to load categories.json: {e}")
else:
    logging.warning("categories.json not found, using empty defaults.")
