from django.test import TransactionTestCase, Client  # FIX: Use TransactionTestCase
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from unittest.mock import patch, MagicMock

from document_processing.models import (
    Document,
    SourceType,
    TextStatus,
    TaskFailureAlert,
)

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
        url = reverse("document_processing:document_upload")
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
            response, reverse("document_processing:document_detail", args=[doc.id])
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
            reverse("document_processing:document_detail", args=[other_doc.id])
        )
        self.assertEqual(response.status_code, 403)


class DocumentRetryTests(TransactionTestCase):
    """Tests for the document retry functionality."""

    reset_sequences = True

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="retry_tester", email="retry@example.com", password="pass"
        )
        self.client.force_login(self.user)


class DocumentRetryTests(TransactionTestCase):
    """Tests for the document retry functionality."""

    reset_sequences = True

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username="retry_tester", email="retry@example.com", password="pass"
        )
        self.client.force_login(self.user)

    @patch("document_processing.views.getattr")
    @patch("document_processing.views.transaction.on_commit")
    def test_retry_failed_document_success(self, mock_on_commit, mock_getattr):
        """Test successful retry of a failed document."""
        # Mock getattr to return False for 'limited' attribute
        original_getattr = getattr

        def mock_getattr_func(obj, name, *args, **kwargs):
            if name == "limited":
                return False
            return original_getattr(obj, name, *args, **kwargs)

        mock_getattr.side_effect = mock_getattr_func

        # Create unique user for this test
        import uuid

        username = f"retry_success_{uuid.uuid4().hex[:8]}"
        test_user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass"
        )
        self.client.force_login(test_user)

        # Create a failed document
        failed_doc = Document.objects.create(
            user=test_user,
            title="Failed Document",
            source_type=SourceType.FILE,
            source_content="failed.pdf",
            status=TextStatus.FAILED,
            error_message="Original processing error",
        )

        # Create some pages to ensure they get cleared
        from document_processing.models import DocumentPage

        DocumentPage.objects.create(
            document=failed_doc, page_number=1, markdown_content="Old content"
        )

        url = reverse("document_processing:document_retry", args=[failed_doc.id])

        # Act
        response = self.client.post(url)

        # Assert
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("queued", data["message"])

        # Refresh document from database
        failed_doc.refresh_from_db()
        self.assertEqual(failed_doc.status, TextStatus.PENDING)
        self.assertIsNone(failed_doc.error_message)

        # Check that pages were cleared
        self.assertEqual(failed_doc.pages.count(), 0)

        # Check that task was queued
        mock_on_commit.assert_called_once()

    @patch("document_processing.views.getattr")
    def test_retry_non_failed_document_fails(self, mock_getattr):
        """Test that retrying a non-failed document returns an error."""
        # Mock getattr to return False for 'limited' attribute
        original_getattr = getattr

        def mock_getattr_func(obj, name, *args, **kwargs):
            if name == "limited":
                return False
            return original_getattr(obj, name, *args, **kwargs)

        mock_getattr.side_effect = mock_getattr_func

        # Create unique user for this test
        import uuid

        username = f"retry_non_failed_{uuid.uuid4().hex[:8]}"
        test_user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass"
        )
        self.client.force_login(test_user)

        # Create a completed document
        completed_doc = Document.objects.create(
            user=test_user,
            title="Completed Document",
            source_type=SourceType.TEXT,
            source_content="Some text",
            status=TextStatus.COMPLETED,
        )

        url = reverse("document_processing:document_retry", args=[completed_doc.id])

        # Act
        response = self.client.post(url)

        # Assert
        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Only failed documents can be retried", data["error"])

    def test_retry_nonexistent_document_fails(self):
        """Test retrying a non-existent document."""
        # Create unique user for this test
        import uuid

        username = f"retry_nonexistent_{uuid.uuid4().hex[:8]}"
        test_user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass"
        )
        self.client.force_login(test_user)

        url = reverse("document_processing:document_retry", args=[99999])

        # Act
        response = self.client.post(url)

        # Assert - should return 404 for non-existent document
        self.assertEqual(response.status_code, 404)
        # Note: Django returns HTML error pages for 404s, not JSON

    @patch("document_processing.views.getattr")
    def test_retry_other_users_document_fails(self, mock_getattr):
        """Test that users cannot retry other users' documents."""
        # Mock getattr to return False for 'limited' attribute
        original_getattr = getattr

        def mock_getattr_func(obj, name, *args, **kwargs):
            if name == "limited":
                return False
            return original_getattr(obj, name, *args, **kwargs)

        mock_getattr.side_effect = mock_getattr_func

        # Create unique user for this test
        import uuid

        username = f"retry_other_user_{uuid.uuid4().hex[:8]}"
        test_user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass"
        )
        self.client.force_login(test_user)

        other_user = User.objects.create_user(username="other_user", password="pass")
        other_doc = Document.objects.create(
            user=other_user, title="Other's Failed Doc", status=TextStatus.FAILED
        )

        url = reverse("document_processing:document_retry", args=[other_doc.id])

        # Act
        response = self.client.post(url)

        # Assert - should return 403 for permission denied
        self.assertEqual(response.status_code, 403)
        # Note: Django returns HTML error pages for permission errors, not JSON

    @patch("document_processing.views.getattr")
    def test_retry_get_request_fails(self, mock_getattr):
        """Test that GET requests to retry endpoint are rejected."""
        # Mock getattr to return False for 'limited' attribute
        original_getattr = getattr

        def mock_getattr_func(obj, name, *args, **kwargs):
            if name == "limited":
                return False
            return original_getattr(obj, name, *args, **kwargs)

        mock_getattr.side_effect = mock_getattr_func

        # Create unique user for this test
        import uuid

        username = f"retry_get_{uuid.uuid4().hex[:8]}"
        test_user = User.objects.create_user(
            username=username, email=f"{username}@example.com", password="pass"
        )
        self.client.force_login(test_user)

        failed_doc = Document.objects.create(
            user=test_user, title="Failed Document", status=TextStatus.FAILED
        )

        url = reverse("document_processing:document_retry", args=[failed_doc.id])

        # Act
        response = self.client.get(url)

        # Assert
        self.assertEqual(response.status_code, 405)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("Invalid request method", data["error"])
