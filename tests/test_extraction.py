import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.text_extractor import extract_text_from_pdf, clean_filename_text, get_searchable_text
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
        
        # Expected text should contain only first MAX_PDF_PAGES
        expected_text = "\n".join([f"Page {i+1}" for i in range(MAX_PDF_PAGES)])
        self.assertEqual(text, expected_text)

    @patch('PIL.Image.open')
    def test_ocr_missing_dependency(self, mock_img_open):
        """Test that image extraction doesn't crash if OCR fails or is missing"""
        # We want to test the case where pytesseract might not be installed
        # In text_extractor.py, we have 'try: import pytesseract' inside get_searchable_text
        # To simulate it missing or failing, we can patch the import or just rely on 
        # the fact that it's NOT installed in this environment and see if it crashes.
        
        # Since it's actually not installed, let's see if get_searchable_text handles it
        try:
            text = get_searchable_text("test.jpg")
            # Should still return filename and extension
            self.assertIn("test", text)
            self.assertIn("jpg", text)
        except Exception as e:
            self.fail(f"get_searchable_text raised {type(e).__name__} unexpectedly!")

if __name__ == '__main__':
    unittest.main()
