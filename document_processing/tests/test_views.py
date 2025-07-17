from django.test import TestCase, Client, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from document_processing.models import Document, DocumentPage, SourceType, TextStatus

User = get_user_model()


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class DocumentViewsIntegrationTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="tester", email="tester@example.com", password="pass"
        )
        self.client.force_login(self.user)

    @patch("document_processing.views.upload_to_s3")
    @patch("document_processing.tasks._process_pdf")
    def test_file_upload_full_flow_success(self, mock_process_pdf, mock_upload_s3):
        # Arrange
        mock_upload_s3.return_value = "uploads/1/test.pdf"
        mock_process_pdf.return_value = [{"page_number": 1, "markdown": "# Hello PDF"}]
        url = reverse("document_processing:upload")
        dummy_file = SimpleUploadedFile(
            "test.pdf", b"%PDF-...", content_type="application/pdf"
        )

        # Act: This POST will trigger the view, which triggers the Celery task synchronously
        response = self.client.post(
            url,
            {"title": "My PDF", "source_type": SourceType.FILE, "file": dummy_file},
        )

        # Assert
        doc = Document.objects.first()
        self.assertIsNotNone(doc)
        self.assertRedirects(
            response, reverse("document_processing:detail", args=[doc.id])
        )

        # Assert the results of the background task
        doc.refresh_from_db()
        self.assertEqual(doc.status, TextStatus.COMPLETED)
        self.assertEqual(doc.pages.count(), 1)
        self.assertEqual(doc.pages.first().markdown_content, "# Hello PDF")
        mock_upload_s3.assert_called_once()
        mock_process_pdf.assert_called_once()

    def test_owner_can_see_detail_page(self):
        doc = Document.objects.create(user=self.user, title="My Doc")
        response = self.client.get(reverse("document_processing:detail", args=[doc.id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "My Doc")

    def test_non_owner_is_forbidden_from_detail_page(self):
        # Create a document owned by a different user
        other_user = User.objects.create_user(username="other", password="p")
        other_doc = Document.objects.create(user=other_user, title="Other's Doc")

        # As the logged-in self.user, try to access other_doc
        response = self.client.get(
            reverse("document_processing:detail", args=[other_doc.id])
        )
        self.assertEqual(response.status_code, 403)  # Assert Forbidden
