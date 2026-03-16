# 📁 FileSense

FileSense is an AI-powered file management application that helps you organize and find your documents using semantic search, automated clustering, and smart priority ranking.

## ✨ Features

- **📂 Smart Categories:** Automatically groups files (Work, Finance, Legal, etc.) using BERT-based semantic clustering.
- **🔍 Semantic Search:** Find files by meaning and context, not just exact filenames.
- **⭐ Smart Priority:** Highlights the files you use most frequently or recently using a hybrid ranking algorithm.
- **🧠 User Learning:** The AI learns your personal organizational style when you move files or rename categories.
- **📄 Text Extraction:** Supports PDF, DOCX, TXT, and images (via OCR).

## 🚀 Getting Started

### Prerequisites

- **Python 3.8+**
- **Tesseract OCR:** Required for extracting text from images.
  - [Install Tesseract](https://github.com/tesseract-ocr/tesseract) and ensure it's in your system PATH.

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd Context-aware-intelligent-file
   ```

2. **Set up a virtual environment:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

### Running the App

```bash
python app.py
```

## 🛠️ Project Structure

- `app.py`: Main GUI application (CustomTkinter).
- `core/`: Database management, logging, and text extraction logic.
- `ml/`: AI models for semantic search, clustering, and recommendations.
- `components/`: Reusable UI components (Sidebar, File List, etc.).
- `utils/`: Path handling and cross-platform utilities.
- `data/`: Local storage for the SQLite database and AI embeddings (ignored by git).

## 🧪 Testing

Run the included test suite to verify functionality:
```bash
python tests/test_clustering.py
python tests/test_database.py
# ... and other test files
```

## ⚖️ License

This project is licensed under the MIT License.
