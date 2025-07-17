from django.test import TransactionTestCase, Client  # FIX: Use TransactionTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch

from document_processing.models import Document, SourceType, TextStatus

User = get_user_model()


class DocumentViewsIntegrationTests(TransactionTestCase):
    # Required for TransactionTestCase with foreign keys in some DBs
    reset_sequences = True

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="tester", email="tester@example.com", password="pass"
        )
        self.client.force_login(self.user)

    @patch("document_processing.views.upload_to_s3")
    @patch("document_processing.views.transaction.on_commit")  # Mock the on_commit hook
    def test_file_upload_success_flow(self, mock_on_commit, mock_upload_s3):
        # Arrange
        mock_upload_s3.return_value = "uploads/1/test.pdf"
        url = reverse("document_processing:upload")
        dummy_file = SimpleUploadedFile(
            "test.pdf", b"%PDF-...", content_type="application/pdf"
        )

        # Act
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

        # Assert that the document was created with the correct initial state
        self.assertEqual(doc.status, TextStatus.PENDING)
        self.assertEqual(doc.source_content, "uploads/1/test.pdf")

        # Assert that the task was queued via transaction.on_commit
        mock_on_commit.assert_called_once()

    def test_non_owner_is_forbidden_from_detail_page(self):
        other_user = User.objects.create_user(username="other", password="p")
        other_doc = Document.objects.create(user=other_user, title="Other's Doc")
        response = self.client.get(
            reverse("document_processing:detail", args=[other_doc.id])
        )
        self.assertEqual(response.status_code, 403)
