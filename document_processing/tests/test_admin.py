from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.admin.sites import AdminSite
from unittest.mock import patch

from document_processing.models import (
    Document,
    SourceType,
    TextStatus,
    TaskFailureAlert,
)
from document_processing.admin import TaskFailureAlertAdmin

User = get_user_model()


class TaskFailureAlertAdminTests(TestCase):
    """Tests for the TaskFailureAlert admin functionality."""

    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="pass"
        )
        self.client.force_login(self.admin_user)

        # Create regular user for documents
        self.regular_user = User.objects.create_user(
            username="user", email="user@example.com", password="pass"
        )

        # Create admin site and admin instance
        self.site = AdminSite()
        self.task_admin = TaskFailureAlertAdmin(TaskFailureAlert, self.site)

    @patch("document_processing.admin.transaction.on_commit")
    def test_retry_failed_tasks_admin_action_success(self, mock_on_commit):
        """Test successful admin retry of failed tasks."""
        # Create a failed document
        failed_doc = Document.objects.create(
            user=self.regular_user,
            title="Failed Document",
            source_type=SourceType.FILE,
            source_content="failed.pdf",
            status=TextStatus.FAILED,
        )

        # Create a task failure alert
        alert = TaskFailureAlert.objects.create(
            task_name="parse_document_task",
            document=failed_doc,
            user=self.regular_user,
            error_message="Processing failed",
            status="NEW",
        )

        # Call the admin action directly instead of using the client
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.http import HttpRequest

        request = HttpRequest()
        request.method = "POST"
        request.user = self.admin_user
        request.POST = {"action": "retry_failed_tasks", "_selected_action": [alert.id]}
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = TaskFailureAlert.objects.filter(id=alert.id)
        from document_processing.admin import retry_failed_tasks

        retry_failed_tasks(self.task_admin, request, queryset)

        # Refresh objects from database
        alert.refresh_from_db()
        failed_doc.refresh_from_db()

        # Check that alert status was updated
        self.assertEqual(alert.status, "ACKNOWLEDGED")
        self.assertEqual(alert.retry_count, 1)
        self.assertIn("Retried at", alert.resolution_notes)

        # Check that document status was reset
        self.assertEqual(failed_doc.status, TextStatus.PENDING)
        self.assertIsNone(failed_doc.error_message)

        # Check that task was queued
        mock_on_commit.assert_called_once()

    def test_retry_failed_tasks_admin_action_skips_resolved(self):
        """Test that resolved alerts are skipped in admin retry action."""
        # Create a resolved alert
        resolved_alert = TaskFailureAlert.objects.create(
            task_name="parse_document_task",
            user=self.regular_user,
            error_message="Processing failed",
            status="RESOLVED",
        )

        # Call the admin action directly
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.http import HttpRequest

        request = HttpRequest()
        request.method = "POST"
        request.user = self.admin_user
        request.POST = {
            "action": "retry_failed_tasks",
            "_selected_action": [resolved_alert.id],
        }
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = TaskFailureAlert.objects.filter(id=resolved_alert.id)
        from document_processing.admin import retry_failed_tasks

        retry_failed_tasks(self.task_admin, request, queryset)

        # Alert should remain unchanged
        resolved_alert.refresh_from_db()
        self.assertEqual(resolved_alert.status, "RESOLVED")
        self.assertEqual(resolved_alert.retry_count, 0)

    def test_retry_failed_tasks_admin_action_handles_audio_tasks(self):
        """Test that audio task failures are retried successfully."""
        from speech_processing.models import Audio, AudioGenerationStatus

        # Create a document and page for the audio
        doc = Document.objects.create(
            user=self.regular_user, title="Test Document", status=TextStatus.COMPLETED
        )
        from document_processing.models import DocumentPage

        page = DocumentPage.objects.create(
            document=doc, page_number=1, markdown_content="Test content"
        )

        # Create a failed audio
        failed_audio = Audio.objects.create(
            page=page,
            voice="Ivy",
            generated_by=self.regular_user,
            status=AudioGenerationStatus.FAILED,
            error_message="Audio generation failed",
        )

        # Create an audio task failure alert with proper task_kwargs
        audio_alert = TaskFailureAlert.objects.create(
            task_name="generate_audio_task",
            user=self.regular_user,
            error_message="Audio generation failed",
            status="NEW",
            task_kwargs={"audio_id": failed_audio.id},
        )

        # Call the admin action directly
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.http import HttpRequest

        request = HttpRequest()
        request.method = "POST"
        request.user = self.admin_user
        request.POST = {
            "action": "retry_failed_tasks",
            "_selected_action": [audio_alert.id],
        }
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = TaskFailureAlert.objects.filter(id=audio_alert.id)
        from document_processing.admin import retry_failed_tasks

        retry_failed_tasks(self.task_admin, request, queryset)

        # Refresh objects from database
        audio_alert.refresh_from_db()
        failed_audio.refresh_from_db()

        # Check that alert status was updated
        self.assertEqual(audio_alert.status, "ACKNOWLEDGED")
        self.assertEqual(audio_alert.retry_count, 1)
        self.assertIn("Retried at", audio_alert.resolution_notes)

        # Check that audio status was reset
        self.assertEqual(failed_audio.status, AudioGenerationStatus.PENDING)
        self.assertIsNone(failed_audio.error_message)

    @patch("document_processing.admin.transaction.on_commit")
    def test_retry_failed_tasks_admin_action_handles_errors(self, mock_on_commit):
        """Test that admin retry handles task queuing errors gracefully."""
        # Mock transaction.on_commit to raise an exception
        mock_on_commit.side_effect = Exception("Queue error")

        # Create a failed document and alert
        failed_doc = Document.objects.create(
            user=self.regular_user, title="Failed Document", status=TextStatus.FAILED
        )

        alert = TaskFailureAlert.objects.create(
            task_name="parse_document_task",
            document=failed_doc,
            user=self.regular_user,
            error_message="Processing failed",
            status="NEW",
        )

        # Call the admin action directly
        from django.contrib.messages.storage.fallback import FallbackStorage
        from django.http import HttpRequest

        request = HttpRequest()
        request.method = "POST"
        request.user = self.admin_user
        request.POST = {"action": "retry_failed_tasks", "_selected_action": [alert.id]}
        request.session = {}
        request._messages = FallbackStorage(request)

        queryset = TaskFailureAlert.objects.filter(id=alert.id)
        from document_processing.admin import retry_failed_tasks

        retry_failed_tasks(self.task_admin, request, queryset)

        # Alert should remain in NEW status
        alert.refresh_from_db()
        self.assertEqual(alert.status, "NEW")
        self.assertEqual(alert.retry_count, 0)
