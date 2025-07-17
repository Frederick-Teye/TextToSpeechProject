from django.test import TestCase
from django.contrib.auth import get_user_model
from unittest.mock import patch
import requests

from document_processing.models import Document, DocumentPage, TextStatus, SourceType
from document_processing.tasks import parse_document_task

User = get_user_model()


class ParseDocumentTaskSuccessTests(TestCase):
    """Tests for the 'happy path' where everything works correctly."""

    def setUp(self):
        self.user = User.objects.create_user(username="tasker", password="p")

    def test_text_source_creates_one_page(self):
        # Arrange
        long_text = "This is some raw text that is long enough to pass the minimum content length check."
        doc = Document.objects.create(
            user=self.user,
            title="Raw Text Doc",
            source_type=SourceType.TEXT,
            source_content=long_text,
        )
        # Act
        parse_document_task(doc.id)
        # Assert
        doc.refresh_from_db()
        self.assertEqual(doc.status, TextStatus.COMPLETED)
        self.assertEqual(doc.pages.count(), 1)
        self.assertEqual(doc.pages.first().markdown_content, long_text)

    @patch("document_processing.tasks.requests.get")
    def test_url_source_is_markdownified(self, mock_get):
        # Arrange
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = "<h1>A Webpage Title</h1><p>Some content.</p>"
        doc = Document.objects.create(
            user=self.user,
            title="Web Doc",
            source_type=SourceType.URL,
            source_content="http://fake-example.com",
        )
        # Act
        parse_document_task(doc.id)
        # Assert
        doc.refresh_from_db()
        self.assertEqual(doc.status, TextStatus.COMPLETED)
        page = doc.pages.first()
        self.assertIsNotNone(page)
        self.assertIn("# A Webpage Title", page.markdown_content)


class ParseDocumentTaskFailureTests(TestCase):
    """Tests for the 'unhappy path' to ensure robust error handling."""

    def setUp(self):
        self.user = User.objects.create_user(username="fail_tester", password="p")

    @patch("document_processing.tasks.requests.get")
    def test_task_fails_gracefully_on_bad_url(self, mock_get):
        # Arrange: Mock a network error
        mock_get.side_effect = requests.RequestException("Connection timed out")
        doc = Document.objects.create(
            user=self.user,
            title="Bad URL",
            source_type=SourceType.URL,
            source_content="http://a-bad-url.com",
        )
        # Act
        parse_document_task(doc.id)
        # Assert
        doc.refresh_from_db()
        self.assertEqual(doc.status, TextStatus.FAILED)
        self.assertIn("fetch URL content", doc.error_message)

    @patch("document_processing.tasks.boto3.client")
    @patch("document_processing.tasks._process_pdf")
    def test_task_fails_gracefully_on_corrupted_pdf(self, mock_process_pdf, mock_boto):
        # Arrange: Mock the PDF processor to simulate a corruption error
        mock_process_pdf.side_effect = Exception("Cannot open corrupted PDF")
        mock_boto.return_value.download_fileobj.return_value = None
        doc = Document.objects.create(
            user=self.user,
            title="Corrupted PDF",
            source_type=SourceType.FILE,
            source_content="files/corrupted.pdf",
        )
        # Act
        parse_document_task(doc.id)
        # Assert
        doc.refresh_from_db()
        self.assertEqual(doc.status, TextStatus.FAILED)
        self.assertIn("corrupted or invalid file", doc.error_message)

    @patch("document_processing.tasks.boto3.client")
    @patch("document_processing.tasks._process_pdf")
    def test_task_fails_gracefully_on_empty_content(self, mock_process_pdf, mock_boto):
        # Arrange: Mock the processor to return content below the minimum length
        mock_process_pdf.return_value = [{"page_number": 1, "markdown": "abc"}]
        mock_boto.return_value.download_fileobj.return_value = None
        doc = Document.objects.create(
            user=self.user,
            title="Empty Doc",
            source_type=SourceType.FILE,
            source_content="files/empty.pdf",
        )
        # Act
        parse_document_task(doc.id)
        # Assert
        doc.refresh_from_db()
        self.assertEqual(doc.status, TextStatus.FAILED)
        self.assertIn("no readable text", doc.error_message)
