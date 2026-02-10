import os
import pdfplumber

# File extensions that should have full content indexed
from config import DOCUMENT_EXTENSIONS, MAX_PDF_PAGES


def extract_text_from_pdf(path):
    if not path.lower().endswith(".pdf"):
        return ""
    try:
        with pdfplumber.open(path) as pdf:
            # Limit pages to prevent freezing on large files
            pages = pdf.pages[:MAX_PDF_PAGES]
            pages_text = [page.extract_text() or "" for page in pages]
        return "\n".join(pages_text)
    except Exception as e:
        print(f"Error reading PDF {path}: {e}")
        return ""


def clean_filename_text(path):
    name = os.path.basename(path)
    name = os.path.splitext(name)[0]
    return name.replace("_", " ").replace("-", " ").lower()


def get_searchable_text(path):
    _, ext = os.path.splitext(path)
    
    # Only index document files
    if ext.lower() not in DOCUMENT_EXTENSIONS:
        return ""
    
    # Include filename + extension + content for better searchability
    filename_text = clean_filename_text(path)
    ext_text = ext.lower().replace('.', '')  # "pdf", "docx", etc.
    pdf_text = extract_text_from_pdf(path)
    combined_text = f"{filename_text} {ext_text} {pdf_text}"
    return combined_text.strip()
