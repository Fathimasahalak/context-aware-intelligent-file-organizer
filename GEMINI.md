# FileSense - AI-Powered File Manager

FileSense is a modern, intelligent file management application that helps users organize and find their files using machine learning. It provides features like semantic search, automated file categorization (clustering), and smart priority ranking based on file usage.

## Project Overview

- **Main Technologies:** Python 3.x, `customtkinter` (UI), SQLite (Database).
- **AI/ML Stack:** `sentence-transformers` (BERT/Semantic Search), `scikit-learn` (KMeans Clustering), `pdfplumber` (PDF extraction), `pytesseract` (OCR).
- **Key Features:**
  - **Smart Priority:** Automatically identifies and highlights files you use most frequently or recently.
  - **Automated Categories:** Groups files into logical clusters (e.g., "Work Documents", "Educational Materials") using name and content analysis.
  - **Semantic Search:** Find files by meaning and context, not just exact filenames.
  - **User Learning:** The AI learns your personal organizational style when you move files or rename categories.

## Architecture

- `app.py`: The entry point and main GUI application using `customtkinter`.
- `config.py`: Centralized configuration for database paths, supported file extensions, and ML model parameters.
- `categories.json`: External dictionary of default category keywords for the AI.
- `core/`:
  - `database.py`: Manages the SQLite database schema (`data/file_logs.db`) and connections.
  - `text_extractor.py`: Utility for extracting searchable text from `.pdf`, `.docx`, `.txt`, and images (OCR).
  - `logger.py`: Handles session logging for file access.
- `ml/`:
  - `semantic_search.py`: Implements vector-based search using `all-MiniLM-L6-v2`.
  - `filename_cluster.py`: Performs dynamic KMeans clustering on file metadata and user learning logic.
  - `recommendation.py`: Ranks files for the "Smart Priority" view.
- `components/`: UI building blocks (Sidebar, Toolbar, FileList).
- `utils/`: Cross-platform utilities (Path handling, Shell integration).

## Building and Running

### Prerequisites

- Python 3.8+
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed on your system path (required for image text extraction).

### Setup

1.  **Create a virtual environment:**
    ```bash
    python -m venv .venv
    source .venv/bin/activate  # On Windows: .venv\Scripts\activate
    ```
2.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

### Running the Application

```bash
python app.py
```

### Running Tests

```bash
pytest
# Or for a specific integration test:
python tests/test_integration.py
```

## Development Conventions

- **Database:** All persistent data is stored in `data/file_logs.db`. Ensure the `data/` directory exists.
- **ML Models:** The `SentenceTransformer` model is a singleton managed in `ml/semantic_search.py` to optimize memory usage.
- **Caching:** Semantic embeddings and IDs are cached in `data/file_embeddings.npy` and `data/file_ids.npy` to speed up search initialization.
- **UI Styling:** Follows Material Design 3 principles. UI constants (colors, fonts, radii) are defined in `theme.py`.
- **Text Extraction:** PDF extraction is limited to the first few pages (defined in `config.py`) to maintain performance.
- **Logging:** Use the standard `logging` module. Logs are written to `logs/file_organizer.log` by default.
