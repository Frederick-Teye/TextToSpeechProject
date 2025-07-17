from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from document_processing.forms import DocumentUploadForm
from document_processing.models import SourceType


class DocumentUploadFormTests(TestCase):

    def test_file_source_requires_file(self):
        form = DocumentUploadForm(
            data={"source_type": SourceType.FILE, "title": "TestDoc"}, files={}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("file", form.errors)

    def test_file_source_with_file_is_valid(self):
        dummy = SimpleUploadedFile("test.md", b"# Hello", content_type="text/markdown")
        form = DocumentUploadForm(
            data={"source_type": SourceType.FILE, "title": "TestDoc"},
            files={"file": dummy},
        )
        self.assertTrue(form.is_valid())

    def test_url_source_requires_url(self):
        form = DocumentUploadForm(
            data={"source_type": SourceType.URL, "title": "TestDoc"}, files={}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("url", form.errors)

    def test_url_source_with_url_is_valid(self):
        form = DocumentUploadForm(
            data={
                "source_type": SourceType.URL,
                "title": "TestDoc",
                "url": "http://example.com",
            },
            files={},
        )
        self.assertTrue(form.is_valid())

    def test_text_source_requires_text(self):
        form = DocumentUploadForm(
            data={"source_type": SourceType.TEXT, "title": "TestDoc"}, files={}
        )
        self.assertFalse(form.is_valid())
        self.assertIn("text", form.errors)

    def test_text_source_with_text_is_valid(self):
        form = DocumentUploadForm(
            data={
                "source_type": SourceType.TEXT,
                "title": "TestDoc",
                "text": "Some raw text content.",
            },
            files={},
        )
        self.assertTrue(form.is_valid())
