import os
import pdfplumber


def extract_text_from_pdf(path):
    if not path.lower().endswith(".pdf"):
        return ""
    try:
        with pdfplumber.open(path) as pdf:
            pages_text = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages_text)
    except Exception as e:
        print(f"Error reading PDF {path}: {e}")
        return ""


def clean_filename_text(path):
    name = os.path.basename(path)
    name = os.path.splitext(name)[0]
    return name.replace("_", " ").replace("-", " ").lower()


def get_searchable_text(path):
    filename_text = clean_filename_text(path)
    pdf_text = extract_text_from_pdf(path)
    combined_text = f"{filename_text} {pdf_text}"
    return combined_text.strip()
