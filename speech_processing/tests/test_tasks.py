"""
Unit tests for Celery tasks.
Tests audio generation, audit log export, and expiry checks.
"""

import json
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch, MagicMock, call
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from document_processing.models import Document, DocumentPage
from speech_processing.models import (
    Audio,
    AudioGenerationStatus,
    AudioLifetimeStatus,
    TTSVoice,
    SiteSettings,
    AudioAccessLog,
    AudioAction,
)
from speech_processing.tasks import (
    generate_audio_task,
    export_audit_logs_to_s3,
    check_expired_audios,
)

User = get_user_model()


class GenerateAudioTaskTests(TestCase):
    """Test generate_audio_task Celery task."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="testuser25", email="test@example.com", password="testpass123"
        )
        self.document = Document.objects.create(
            user=self.user,
            title="Test Doc",
            source_content="test.pdf",
            source_type="FILE",
            status="COMPLETED",
        )
        self.page = DocumentPage.objects.create(
            document=self.document,
            page_number=1,
            markdown_content="Test content for audio generation.",
        )
        self.audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            status=AudioGenerationStatus.PENDING,
        )

    @patch("speech_processing.services.PollyService.generate_audio")
    def test_generate_audio_task_success(self, mock_generate):
        """Test successful audio generation task execution."""
        # Mock should return just the s3_key string, not a dict
        mock_generate.return_value = "audios/test-audio-123.mp3"

        # Execute task
        generate_audio_task(self.audio.id)

        # Verify audio was updated
        self.audio.refresh_from_db()
        self.assertEqual(self.audio.status, AudioGenerationStatus.COMPLETED)
        self.assertEqual(self.audio.s3_key, "audios/test-audio-123.mp3")

        # Verify service was called
        mock_generate.assert_called_once()

        # Verify audit log was created
        audit_log = AudioAccessLog.objects.filter(
            user=self.user, action=AudioAction.GENERATE
        ).first()
        self.assertIsNotNone(audit_log)
        self.assertEqual(audit_log.audio, self.audio)

    @patch("speech_processing.services.PollyService.generate_audio")
    def test_generate_audio_task_failure(self, mock_generate):
        """Test audio generation task handles failures."""
        mock_generate.side_effect = Exception("AWS Polly error")

        # Execute task (should handle exception gracefully and set status to FAILED)
        result = generate_audio_task(self.audio.id)

        # Verify result indicates failure
        self.assertFalse(result["success"])
        self.assertIn("AWS Polly error", result["message"])

        # Verify audio status was updated to failed
        self.audio.refresh_from_db()
        self.assertEqual(self.audio.status, AudioGenerationStatus.FAILED)
        self.assertIn("AWS Polly error", self.audio.error_message or "")

    @patch("speech_processing.services.PollyService.generate_audio")
    def test_generate_audio_task_retry_on_transient_error(self, mock_generate):
        """Test task retries on transient errors."""
        # Simulate transient error
        mock_generate.side_effect = Exception("Connection timeout")

        # Execute task - it will retry and eventually fail
        result = generate_audio_task(self.audio.id)

        # After max_retries is reached, task should fail
        self.assertFalse(result["success"])
        self.assertIn("Connection timeout", result["message"])

        # Verify status is FAILED after all retries exhausted
        self.audio.refresh_from_db()
        self.assertEqual(self.audio.status, AudioGenerationStatus.FAILED)

    def test_generate_audio_task_audio_not_found(self):
        """Test task handles missing audio gracefully."""
        # Should not raise exception
        generate_audio_task(99999)

        # Audio should not be created
        self.assertEqual(Audio.objects.count(), 1)  # Only the setUp audio


class ExportAuditLogsTaskTests(TestCase):
    """Test export_audit_logs_to_s3 Celery task."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="testuser26", email="test@example.com", password="testpass123"
        )
        self.document = Document.objects.create(
            user=self.user,
            title="Test Doc",
            source_content="test.pdf",
            source_type="FILE",
            status="COMPLETED",
        )

        # Create audit logs
        for i in range(5):
            AudioAccessLog.objects.create(
                user=self.user,
                action=AudioAction.GENERATE,
                document=self.document,
            )

    @patch("boto3.client")
    def test_export_audit_logs_success(self, mock_boto_client):
        """Test successful audit log export to S3."""
        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Execute task
        start_date = timezone.now() - timedelta(days=1)
        end_date = timezone.now() + timedelta(days=1)
        export_audit_logs_to_s3(
            start_date.isoformat(), end_date.isoformat(), self.user.id
        )

        # Verify S3 put_object was called
        self.assertTrue(mock_s3.put_object.called)
        call_args = mock_s3.put_object.call_args

        # Verify bucket and key
        self.assertIn("Bucket", call_args.kwargs)
        self.assertIn("Key", call_args.kwargs)
        self.assertTrue(call_args.kwargs["Key"].startswith("audit-logs/"))
        self.assertTrue(call_args.kwargs["Key"].endswith(".jsonl"))

        # Verify content is valid JSON Lines with logs
        content = call_args.kwargs["Body"]
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        logs = [json.loads(line) for line in content.split("\n") if line.strip()]
        self.assertEqual(len(logs), 5)
        self.assertEqual(logs[0]["user_email"], "test@example.com")
        self.assertEqual(logs[0]["action"], "GENERATE")

    @patch("boto3.client")
    def test_export_audit_logs_filters_by_user(self, mock_boto_client):
        """Test export filters logs by user."""
        # Create logs for another user
        other_user = User.objects.create_user(
            username="otheruser", email="other@example.com", password="testpass123"
        )
        for i in range(3):
            AudioAccessLog.objects.create(
                user=other_user,
                action=AudioAction.PLAY,
                document=self.document,
            )

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Export only test user's logs
        start_date = timezone.now() - timedelta(days=1)
        end_date = timezone.now() + timedelta(days=1)
        export_audit_logs_to_s3(
            start_date.isoformat(), end_date.isoformat(), self.user.id
        )

        # Verify only test user's logs were exported
        call_args = mock_s3.put_object.call_args
        content = call_args.kwargs["Body"]
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        logs = [json.loads(line) for line in content.split("\n") if line.strip()]
        self.assertEqual(len(logs), 5)  # Not 8

    @patch("boto3.client")
    def test_export_audit_logs_filters_by_date_range(self, mock_boto_client):
        """Test export filters logs by date range."""
        # Create old logs
        old_date = timezone.now() - timedelta(days=10)
        old_log = AudioAccessLog.objects.create(
            user=self.user,
            action=AudioAction.DOWNLOAD,
            document=self.document,
        )
        old_log.timestamp = old_date
        old_log.save()

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Export only recent logs (last 2 days)
        start_date = timezone.now() - timedelta(days=2)
        end_date = timezone.now() + timedelta(days=1)
        export_audit_logs_to_s3(
            start_date.isoformat(), end_date.isoformat(), self.user.id
        )

        # Verify only recent logs were exported
        call_args = mock_s3.put_object.call_args
        content = call_args.kwargs["Body"]
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        logs = [json.loads(line) for line in content.split("\n") if line.strip()]
        self.assertEqual(len(logs), 5)  # Not 6 (old log excluded)


class CheckExpiredAudiosTaskTests(TestCase):
    """Test check_expired_audios Celery task."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(
            username="testuser27", email="test@example.com", password="testpass123"
        )
        self.document = Document.objects.create(
            user=self.user,
            title="Test Doc",
            source_content="test.pdf",
            source_type="FILE",
            status="COMPLETED",
        )
        self.page = DocumentPage.objects.create(
            document=self.document, page_number=1, markdown_content="Test content"
        )

        # Ensure settings exist
        self.settings = SiteSettings.get_settings()

    def test_check_expired_audios_deletes_expired(self):
        """Test task soft-deletes expired audios."""
        # Enable auto-deletion
        self.settings.auto_delete_expired_enabled = True
        self.settings.save()

        # Create expired audio (created 7 months ago)
        expired_audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/expired.mp3",
            status=AudioGenerationStatus.COMPLETED,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        expired_audio.created_at = timezone.now() - timedelta(days=210)
        expired_audio.save()

        # Create recent audio
        recent_audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.MATTHEW,
            generated_by=self.user,
            s3_key="audios/recent.mp3",
            status=AudioGenerationStatus.COMPLETED,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )

        # Execute task
        check_expired_audios()

        # Verify expired audio was soft-deleted
        expired_audio.refresh_from_db()
        self.assertEqual(expired_audio.lifetime_status, AudioLifetimeStatus.EXPIRED)
        self.assertIsNotNone(expired_audio.deleted_at)

        # Verify recent audio was not deleted
        recent_audio.refresh_from_db()
        self.assertEqual(recent_audio.lifetime_status, AudioLifetimeStatus.ACTIVE)
        self.assertIsNone(recent_audio.deleted_at)

    @patch("django.core.mail.send_mail")
    def test_check_expired_audios_sends_warning_emails(self, mock_send_mail):
        """Test task sends warning emails for audios nearing expiry."""
        # Create audio that needs warning (created ~5 months ago, expires in ~25 days)
        warning_audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.IVY,
            generated_by=self.user,
            s3_key="audios/warning.mp3",
            status=AudioGenerationStatus.COMPLETED,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        warning_audio.created_at = timezone.now() - timedelta(days=155)
        warning_audio.save()

        # Execute task
        check_expired_audios()

        # Verify warning email was sent
        self.assertTrue(mock_send_mail.called)
        call_args = mock_send_mail.call_args
        self.assertIn("expir", call_args.kwargs["subject"].lower())
        self.assertIn(self.user.email, call_args.kwargs["recipient_list"])

    @patch("django.core.mail.send_mail")
    def test_check_expired_audios_no_warning_for_recent(self, mock_send_mail):
        """Test task does not send warnings for recently created audios."""
        # Create recent audio (created 1 month ago)
        recent_audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOEY,
            generated_by=self.user,
            s3_key="audios/recent.mp3",
            status=AudioGenerationStatus.COMPLETED,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        recent_audio.created_at = timezone.now() - timedelta(days=30)
        recent_audio.save()

        # Execute task
        check_expired_audios()

        # Verify no warning email was sent
        mock_send_mail.assert_not_called()

    def test_check_expired_audios_respects_settings(self):
        """Test task respects auto-deletion setting."""
        # Disable auto-deletion
        self.settings.auto_delete_expired_enabled = False
        self.settings.save()

        # Create expired audio
        expired_audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.KENDRA,
            generated_by=self.user,
            s3_key="audios/expired.mp3",
            status=AudioGenerationStatus.COMPLETED,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        expired_audio.created_at = timezone.now() - timedelta(days=210)
        expired_audio.save()

        # Execute task
        check_expired_audios()

        # Verify audio was NOT deleted (auto-deletion disabled)
        expired_audio.refresh_from_db()
        self.assertEqual(expired_audio.lifetime_status, AudioLifetimeStatus.ACTIVE)

    def test_check_expired_audios_handles_last_played_at(self):
        """Test task uses last_played_at for expiry calculation when available."""
        # Create audio created 7 months ago but played recently
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JUSTIN,
            generated_by=self.user,
            s3_key="audios/played_recently.mp3",
            status=AudioGenerationStatus.COMPLETED,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        audio.created_at = timezone.now() - timedelta(days=210)
        audio.last_played_at = timezone.now() - timedelta(days=30)
        audio.save()

        # Execute task
        check_expired_audios()

        # Verify audio was NOT deleted (last_played_at is recent)
        audio.refresh_from_db()
        self.assertEqual(audio.lifetime_status, AudioLifetimeStatus.ACTIVE)

    @patch("boto3.client")
    def test_check_expired_audios_cleans_up_s3(self, mock_boto_client):
        """Test task removes S3 files for expired audios."""
        # Enable S3 cleanup in settings
        self.settings.auto_delete_expired_enabled = True
        self.settings.save()

        mock_s3 = MagicMock()
        mock_boto_client.return_value = mock_s3

        # Create expired audio
        expired_audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.KIMBERLY,
            generated_by=self.user,
            s3_key="audios/expired.mp3",
            status=AudioGenerationStatus.COMPLETED,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        expired_audio.created_at = timezone.now() - timedelta(days=210)
        expired_audio.save()

        # Execute task
        check_expired_audios()

        # Verify S3 deletion was called
        mock_s3.delete_object.assert_called_once()
