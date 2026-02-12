
import os

# Database
DB_PATH = os.path.join("data", "file_logs.db")

# Colors
COLORS = {
    "Study": "#4A90E2",        # Professional blue
    "Work": "#7ED321",         # Fresh green
    "Personal": "#F5A623",     # Warm orange
    None: "#2C3E50"            # Dark gray
}

# File Extensions
DOCUMENT_EXTENSIONS = {'.pdf', '.txt', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx', '.csv', '.md', '.jpg', '.png', '.jpeg', '.gif', '.bmp'}

# Model Settings
MAX_PDF_PAGES = 5
CLUSTERING_CLUSTERS = 5
