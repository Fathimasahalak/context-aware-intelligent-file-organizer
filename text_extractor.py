import os
import logging
import pdfplumber
import zipfile
import xml.etree.ElementTree as ET
import subprocess

# File extensions that should have full content indexed
from config import DOCUMENT_EXTENSIONS, MAX_PDF_PAGES


def is_tesseract_available():
    """Check if Tesseract OCR is installed and available in the system path."""
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except (ImportError, EnvironmentError, Exception):
        return False


def extract_text_from_pdf(path, max_pages=MAX_PDF_PAGES):
    if not path.lower().endswith(".pdf"):
        return ""
    try:
        with pdfplumber.open(path) as pdf:
            # Limit pages to prevent freezing on large files
            pages = pdf.pages[:max_pages]
            pages_text = [page.extract_text() or "" for page in pages]
        return "\n".join(pages_text)
    except Exception as e:
        logging.error(f"Error reading PDF {path}: {e}")
        return ""


def clean_filename_text(path):
    name = os.path.basename(path)
    name = os.path.splitext(name)[0]
    return name.replace("_", " ").replace("-", " ").lower()


def get_searchable_text(path, max_pages=MAX_PDF_PAGES):
    _, ext = os.path.splitext(path)
    ext = ext.lower()
    
    # Include filename + extension for better searchability
    filename_text = clean_filename_text(path)
    ext_text = ext.replace('.', '')  # "pdf", "docx", etc.
    
    content_text = ""
    
    if ext == '.txt':
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content_text = f.read()
        except Exception as e:
            logging.error(f"Error reading text file {path}: {e}")
    
    elif ext == '.pdf':
        content_text = extract_text_from_pdf(path, max_pages=max_pages)
    
    elif ext == '.docx':
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                with zf.open('word/document.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    
                    # More robust extraction: find all text nodes in order
                    # This captures text in paragraphs, tables, etc.
                    text_parts = []
                    for node in root.iter():
                        if node.tag.endswith('}t') and node.text:
                            text_parts.append(node.text)
                        # Add space for line breaks
                        elif node.tag.endswith('}p'):
                            text_parts.append('\n')
                            
                    content_text = ''.join(text_parts)
        except Exception as e:
            logging.error(f"Error reading docx {path}: {e}")
            content_text = ""
    
    elif ext in ['.jpg', '.png', '.jpeg', '.gif', '.bmp']:
        try:
            import pytesseract
            from PIL import Image
            
            with Image.open(path) as img:
                content_text = pytesseract.image_to_string(img)
        except (ImportError, EnvironmentError, Exception) as e:
            logging.warning(f"OCR extraction failed for {path}: {e}")
            content_text = ""
    
    # Add more file types as needed (e.g., .pptx, .xlsx, .html)
    
    combined_text = f"{filename_text} {ext_text} {content_text}"
    return combined_text.strip()
