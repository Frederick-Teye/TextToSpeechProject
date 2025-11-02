from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from document_processing.utils import upload_to_s3, sanitize_filename


class SanitizeFilenameTests(TestCase):
    """Tests for the sanitize_filename function."""

    def test_preserves_pdf_extension(self):
        """Test that .pdf extension is preserved."""
        result = sanitize_filename("MARFO_JOHN_KUSI_MINI_PROJECT_REPORT.pdf")
        self.assertTrue(result.endswith("_pdf"), f"Expected to end with '_pdf', got: {result}")
        self.assertIn("marfo", result.lower())  # Check case-insensitive

    def test_preserves_docx_extension(self):
        """Test that .docx extension is preserved."""
        result = sanitize_filename("document.docx")
        self.assertTrue(result.endswith("_docx"), f"Expected to end with '_docx', got: {result}")

    def test_preserves_markdown_extension(self):
        """Test that .md extension is preserved."""
        result = sanitize_filename("notes.md")
        self.assertTrue(result.endswith("_md"), f"Expected to end with '_md', got: {result}")

    def test_handles_uppercase_extensions(self):
        """Test that uppercase extensions are converted to lowercase."""
        result = sanitize_filename("document.PDF")
        self.assertTrue(result.endswith("_pdf"), f"Expected to end with '_pdf', got: {result}")

    def test_sanitizes_special_characters(self):
        """Test that special characters are removed from filename."""
        result = sanitize_filename("my@document#name.pdf")
        self.assertNotIn("@", result)
        self.assertNotIn("#", result)
        self.assertTrue(result.endswith("_pdf"))

    def test_converts_spaces_to_underscores(self):
        """Test that spaces are converted to underscores."""
        result = sanitize_filename("my document.pdf")
        self.assertNotIn(" ", result)
        self.assertIn("_", result)
        self.assertTrue(result.endswith("_pdf"))

    def test_prevents_path_traversal(self):
        """Test that path traversal attempts are blocked."""
        result = sanitize_filename("../../../etc/passwd.txt")
        self.assertNotIn("/", result)
        self.assertNotIn("..", result)
        self.assertTrue(result.endswith("_txt"))

    def test_handles_null_bytes(self):
        """Test that null bytes are removed."""
        result = sanitize_filename("shell.php\x00.pdf")
        self.assertNotIn("\x00", result)
        self.assertTrue(result.endswith("_pdf"))

    def test_handles_file_without_extension(self):
        """Test that files without extension are handled."""
        result = sanitize_filename("README")
        self.assertIsNotNone(result)
        self.assertIn("readme", result.lower())  # Check case-insensitive

    def test_handles_dotfiles(self):
        """Test that hidden files (starting with dot) are handled."""
        result = sanitize_filename(".gitignore")
        self.assertIsNotNone(result)
        self.assertIn("gitignore", result.lower())  # Check case-insensitive

    def test_empty_name_uses_default(self):
        """Test that empty names use 'document' as fallback."""
        result = sanitize_filename("@#$%.pdf")
        self.assertIn("document", result)
        self.assertTrue(result.endswith("_pdf"))

    def test_unicode_normalization(self):
        """Test that unicode characters are handled."""
        result = sanitize_filename("café.pdf")
        self.assertIsNotNone(result)
        # Unicode should be normalized
        self.assertTrue(result.endswith("_pdf"))

    def test_multiple_consecutive_underscores_collapsed(self):
        """Test that multiple consecutive special characters are collapsed."""
        result = sanitize_filename("file___name.pdf")
        # Multiple underscores should be collapsed
        self.assertNotIn("___", result)
        self.assertTrue(result.endswith("_pdf"))

    def test_extension_with_multiple_dots(self):
        """Test that files with multiple dots preserve only the last extension."""
        result = sanitize_filename("archive.tar.gz")
        # The sanitizer should handle tar.gz as two extensions, keeping the last one
        self.assertIsNotNone(result)
        # tar.gz has multiple dots - the last one is .gz
        self.assertTrue(result.endswith("_gz"))


class UploadToS3Tests(TestCase):

    @patch("storages.backends.s3boto3.S3Boto3Storage.save")
    def test_upload_success_uses_uuid(self, mock_save):
        mock_save.return_value = "uploads/1/some-uuid_foo_txt"

        dummy = SimpleUploadedFile("foo.txt", b"bar")
        path = upload_to_s3(dummy, user_id=1, file_name="foo.txt")

        self.assertEqual(path, "media/uploads/1/some-uuid_foo_txt")
        mock_save.assert_called_once()

    @patch("storages.backends.s3boto3.S3Boto3Storage.save")
    def test_upload_failure_raises_exception(self, mock_save):
        dummy = SimpleUploadedFile("foo.txt", b"bar")
        # Configure the mock to raise an exception when called
        mock_save.side_effect = Exception("Failed to upload file to S3")

        # Assert that calling the function raises an exception
        with self.assertRaises(Exception):
            upload_to_s3(dummy, user_id=1, file_name="foo.txt")

    @patch("storages.backends.s3boto3.S3Boto3Storage.save")
    def test_upload_preserves_pdf_extension(self, mock_save):
        """Test that PDF files preserve .pdf extension through upload."""
        mock_save.return_value = "uploads/1/uuid123_report_pdf"
        
        dummy = SimpleUploadedFile("Annual_Report.pdf", b"PDF content")
        path = upload_to_s3(dummy, user_id=1, file_name="Annual_Report.pdf")
        
        # Verify the path contains the extension
        self.assertIn("_pdf", path)
        mock_save.assert_called_once()

