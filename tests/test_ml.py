import unittest
from ml.filename_cluster import clean_filename
from ml.semantic_search import SemanticSearch


class TestFilenameCluster(unittest.TestCase):
    def test_clean_filename_basic(self):
        self.assertEqual(clean_filename("Invoice Jan 2024.pdf"), "invoice jan")

    def test_clean_filename_numbers(self):
        self.assertEqual(clean_filename("Report 2023_v2.docx"), "report  v")

    def test_clean_filename_special_chars(self):
        self.assertEqual(clean_filename("My-File_Name (1).txt"), "my file name ()")


class TestSemanticSearch(unittest.TestCase):
    def test_search_empty(self):
        searcher = SemanticSearch()
        results = searcher.search("test")
        self.assertEqual(results, [])


if __name__ == '__main__':
    unittest.main()
