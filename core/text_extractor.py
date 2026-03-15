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


def extract_text_from_docx(path):
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            with zf.open('word/document.xml') as f:
                tree = ET.parse(f)
                root = tree.getroot()
                # Find all text nodes
                text_parts = []
                for node in root.iter():
                    if node.tag.endswith('}t') and node.text:
                        text_parts.append(node.text)
                    elif node.tag.endswith('}p'):
                        text_parts.append('\n')
                return ''.join(text_parts)
    except Exception as e:
        logging.error(f"Error reading docx {path}: {e}")
        return ""


def extract_text_from_xlsx(path):
    try:
        with zipfile.ZipFile(path, 'r') as zf:
            # Excel stores text in sharedStrings.xml
            if 'xl/sharedStrings.xml' in zf.namelist():
                with zf.open('xl/sharedStrings.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    # Find all text elements
                    text_parts = []
                    for node in root.iter():
                        if node.tag.endswith('}t') and node.text:
                            text_parts.append(node.text)
                    return ' '.join(text_parts)
            return ""
    except Exception as e:
        logging.error(f"Error reading xlsx {path}: {e}")
        return ""


def extract_text_from_pptx(path):
    try:
        text_parts = []
        with zipfile.ZipFile(path, 'r') as zf:
            # Slides are in ppt/slides/slide*.xml
            slide_files = [f for f in zf.namelist() if f.startswith('ppt/slides/slide') and f.endswith('.xml')]
            for slide_file in sorted(slide_files):
                with zf.open(slide_file) as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    for node in root.iter():
                        if node.tag.endswith('}t') and node.text:
                            text_parts.append(node.text)
                    text_parts.append('\n')
        return ' '.join(text_parts)
    except Exception as e:
        logging.error(f"Error reading pptx {path}: {e}")
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
    
    if ext in ['.txt', '.md', '.csv', '.html', '.htm']:
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                content_text = f.read()
                # Simple HTML strip (optional, but keeps index cleaner)
                if ext in ['.html', '.htm']:
                    import re
                    content_text = re.sub('<[^<]+?>', ' ', content_text)
        except Exception as e:
            logging.error(f"Error reading text-like file {path}: {e}")
    
    elif ext == '.pdf':
        content_text = extract_text_from_pdf(path, max_pages=max_pages)
    
    elif ext == '.docx':
        content_text = extract_text_from_docx(path)
        
    elif ext == '.xlsx':
        content_text = extract_text_from_xlsx(path)
        
    elif ext == '.pptx':
        content_text = extract_text_from_pptx(path)
    
    elif ext in ['.jpg', '.png', '.jpeg', '.gif', '.bmp']:
        if is_tesseract_available():
            try:
                import pytesseract
                from PIL import Image
                with Image.open(path) as img:
                    content_text = pytesseract.image_to_string(img)
            except Exception as e:
                logging.warning(f"OCR extraction failed for {path}: {e}")
        else:
            logging.debug(f"Skipping OCR for {path} (Tesseract not found)")
    
    combined_text = f"{filename_text} {ext_text} {content_text}"
    return combined_text.strip()
