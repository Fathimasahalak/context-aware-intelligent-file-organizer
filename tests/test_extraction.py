import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text_extractor import extract_text_from_pdf, clean_filename_text
from config import MAX_PDF_PAGES

class TestTextExtractor(unittest.TestCase):
    
    def test_clean_filename(self):
        self.assertEqual(clean_filename_text("My_Resume_2024.pdf"), "my resume 2024")
        self.assertEqual(clean_filename_text("Data-Analysis-Report.docx"), "data analysis report")

    @patch('pdfplumber.open')
    def test_pdf_page_limit(self, mock_open):
        # Mock PDF object
        mock_pdf = MagicMock()
        mock_open.return_value.__enter__.return_value = mock_pdf
        
        # Create 10 dummy pages
        mock_pages = [MagicMock() for _ in range(10)]
        for i, p in enumerate(mock_pages):
            p.extract_text.return_value = f"Page {i+1}"
        
        mock_pdf.pages = mock_pages
        
        # Call extraction
        text = extract_text_from_pdf("dummy.pdf")
        
        # Check that only MAX_PDF_PAGES were accessed
        # Note: We slice the pages list in the code: pdf.pages[:MAX_PDF_PAGES]
        # verifying exactly how it was called is tricky without implementation details,
        # but we can verify the OUTPUT text contains only first 5 pages.
        
        expected_text = "\n".join([f"Page {i+1}" for i in range(MAX_PDF_PAGES)])
        self.assertEqual(text, expected_text)

if __name__ == '__main__':
    unittest.main()
