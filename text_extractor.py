import os
import logging
import pdfplumber
import zipfile
import xml.etree.ElementTree as ET

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
        logging.error(f"Error reading PDF {path}: {e}")
        return ""


def clean_filename_text(path):
    name = os.path.basename(path)
    name = os.path.splitext(name)[0]
    return name.replace("_", " ").replace("-", " ").lower()


def get_searchable_text(path):
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
        content_text = extract_text_from_pdf(path)
    
    elif ext == '.docx':
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                with zf.open('word/document.xml') as f:
                    tree = ET.parse(f)
                    root = tree.getroot()
                    ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
                    paragraphs = root.findall('.//w:p', ns)
                    content_text = '\n'.join(''.join(t.text for t in p.findall('.//w:t', ns) if t.text) for p in paragraphs)
        except Exception as e:
            logging.error(f"Error reading docx {path}: {e}")
            content_text = ""
    
    elif ext in ['.jpg', '.png', '.jpeg', '.gif', '.bmp']:
        try:
            import pytesseract
            from PIL import Image
            img = Image.open(path)
            content_text = pytesseract.image_to_string(img)
        except ImportError:
            logging.warning("pytesseract or PIL not installed, cannot extract from images")
        except Exception as e:
            logging.error(f"Error reading image {path}: {e}")
    
    # Add more file types as needed (e.g., .pptx, .xlsx, .html)
    
    combined_text = f"{filename_text} {ext_text} {content_text}"
    return combined_text.strip()
