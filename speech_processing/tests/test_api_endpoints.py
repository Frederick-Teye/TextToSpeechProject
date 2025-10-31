"""
Integration tests for audio generation and management API endpoints.
Tests permissions, quota enforcement, and audio lifecycle.
"""

import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from document_processing.models import Document, DocumentPage
from speech_processing.models import (
    Audio,
    AudioGenerationStatus,
    AudioLifetimeStatus,
    TTSVoice,
    SiteSettings,
)

User = get_user_model()


class GenerateAudioAPITests(TestCase):
    """Test POST /speech/generate/<page_id>/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.owner = User.objects.create_user(
            username="testuser28", email="owner@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="testuser29", email="other@example.com", password="testpass123"
        )

        self.document = Document.objects.create(
            user=self.owner,
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

        # Ensure settings exist
        self.settings = SiteSettings.get_settings()
        self.settings.audio_generation_enabled = True
        self.settings.max_audios_per_page = 4
        self.settings.save()

    @patch("speech_processing.tasks.generate_audio_task.delay")
    def test_generate_audio_success(self, mock_task):
        """Test successful audio generation by owner."""
        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:generate_audio", kwargs={"page_id": self.page.id}
        )
        response = self.client.post(
            url,
            data=json.dumps({"voice_id": "Joanna"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertIn("audio_id", data)
        self.assertEqual(data["status"], "PENDING")

        # Verify audio was created in database
        audio = Audio.objects.get(id=data["audio_id"])
        self.assertEqual(audio.voice, TTSVoice.JOANNA)
        self.assertEqual(audio.status, AudioGenerationStatus.PENDING)
        self.assertEqual(audio.generated_by, self.owner)

        # Verify task was called
        mock_task.assert_called_once_with(audio.id)

    def test_generate_audio_unauthenticated(self):
        """Test generation fails for unauthenticated user."""
        url = reverse(
            "speech_processing:generate_audio", kwargs={"page_id": self.page.id}
        )
        response = self.client.post(
            url,
            data=json.dumps({"voice_id": "Joanna"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 302)  # Redirect to login

    def test_generate_audio_unauthorized_user(self):
        """Test generation fails for user without access."""
        self.client.login(email="other@example.com", password="testpass123")

        url = reverse(
            "speech_processing:generate_audio", kwargs={"page_id": self.page.id}
        )
        response = self.client.post(
            url,
            data=json.dumps({"voice_id": "Matthew"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("permission", data["error"].lower())

    @patch("speech_processing.tasks.generate_audio_task.delay")
    def test_generate_audio_quota_exceeded(self, mock_task):
        """Test generation fails when quota is full."""
        self.client.login(email="owner@example.com", password="testpass123")

        # Create 4 audios (at quota limit)
        voices = [TTSVoice.JOANNA, TTSVoice.MATTHEW, TTSVoice.IVY, TTSVoice.JOEY]
        for voice in voices:
            Audio.objects.create(
                page=self.page,
                voice=voice,
                generated_by=self.owner,
                s3_key=f"audios/{voice}.mp3",
            )

        # Try to create 5th audio
        url = reverse(
            "speech_processing:generate_audio", kwargs={"page_id": self.page.id}
        )
        response = self.client.post(
            url,
            data=json.dumps({"voice_id": "Kendra"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("quota", data["error"].lower())

        # Task should not be called
        mock_task.assert_not_called()

    @patch("speech_processing.tasks.generate_audio_task.delay")
    def test_generate_audio_duplicate_voice(self, mock_task):
        """Test generation fails for duplicate active voice."""
        self.client.login(email="owner@example.com", password="testpass123")

        # Create audio with Joanna voice
        Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.owner,
            s3_key="audios/joanna.mp3",
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )

        # Try to create another with same voice
        url = reverse(
            "speech_processing:generate_audio", kwargs={"page_id": self.page.id}
        )
        response = self.client.post(
            url,
            data=json.dumps({"voice_id": "Joanna"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("voice", data["error"].lower())

        mock_task.assert_not_called()

    def test_generate_audio_missing_voice_id(self):
        """Test generation fails with missing voice_id."""
        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:generate_audio", kwargs={"page_id": self.page.id}
        )
        response = self.client.post(
            url, data=json.dumps({}), content_type="application/json"
        )

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("voice_id", data["error"].lower())

    def test_generate_audio_generation_disabled(self):
        """Test generation fails when globally disabled."""
        self.settings.audio_generation_enabled = False
        self.settings.save()

        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:generate_audio", kwargs={"page_id": self.page.id}
        )
        response = self.client.post(
            url,
            data=json.dumps({"voice_id": "Joanna"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("disabled", data["error"].lower())


class AudioStatusAPITests(TestCase):
    """Test GET /speech/audio/<audio_id>/status/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser30", email="test@example.com", password="testpass123"
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
        self.audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
        )

    def test_audio_status_success(self):
        """Test successful status check."""
        self.client.login(email="test@example.com", password="testpass123")

        url = reverse(
            "speech_processing:audio_status", kwargs={"audio_id": self.audio.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["status"], "COMPLETED")
        self.assertEqual(data["voice"], "Joanna")
        self.assertIn("s3_url", data)

    def test_audio_status_unauthenticated(self):
        """Test status check fails for unauthenticated user."""
        url = reverse(
            "speech_processing:audio_status", kwargs={"audio_id": self.audio.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 302)  # Redirect to login


class DownloadAudioAPITests(TestCase):
    """Test GET /speech/audio/<audio_id>/download/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser31", email="test@example.com", password="testpass123"
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
        self.audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.MATTHEW,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
        )

    @patch("speech_processing.services.AudioGenerationService.get_presigned_url")
    def test_download_audio_success(self, mock_presigned):
        """Test successful download URL generation."""
        mock_presigned.return_value = "https://s3.amazonaws.com/presigned_url"

        self.client.login(email="test@example.com", password="testpass123")

        url = reverse(
            "speech_processing:download_audio", kwargs={"audio_id": self.audio.id}
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["download_url"], "https://s3.amazonaws.com/presigned_url")

        # Verify last_played_at was updated
        self.audio.refresh_from_db()
        self.assertIsNotNone(self.audio.last_played_at)


class DeleteAudioAPITests(TestCase):
    """Test DELETE /speech/audio/<audio_id>/delete/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.owner = User.objects.create_user(
            username="testuser32", email="owner@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="testuser33", email="other@example.com", password="testpass123"
        )
        self.document = Document.objects.create(
            user=self.owner,
            title="Test Doc",
            source_content="test.pdf",
            source_type="FILE",
            status="COMPLETED",
        )
        self.page = DocumentPage.objects.create(
            document=self.document, page_number=1, markdown_content="Test content"
        )
        self.audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.IVY,
            generated_by=self.owner,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
        )

    def test_delete_audio_by_owner(self):
        """Test owner can delete audio."""
        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:delete_audio", kwargs={"audio_id": self.audio.id}
        )
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify soft delete
        self.audio.refresh_from_db()
        self.assertEqual(self.audio.lifetime_status, AudioLifetimeStatus.DELETED)
        self.assertIsNotNone(self.audio.deleted_at)

    def test_delete_audio_by_non_owner(self):
        """Test non-owner cannot delete audio."""
        self.client.login(email="other@example.com", password="testpass123")

        url = reverse(
            "speech_processing:delete_audio", kwargs={"audio_id": self.audio.id}
        )
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 403)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("permission", data["error"].lower())

        # Audio should not be deleted
        self.audio.refresh_from_db()
        self.assertEqual(self.audio.lifetime_status, AudioLifetimeStatus.ACTIVE)


class PageAudiosListAPITests(TestCase):
    """Test GET /speech/page/<page_id>/audios/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username="testuser34", email="test@example.com", password="testpass123"
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

        # Create 2 audios
        Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/joanna.mp3",
            status=AudioGenerationStatus.COMPLETED,
        )
        Audio.objects.create(
            page=self.page,
            voice=TTSVoice.MATTHEW,
            generated_by=self.user,
            s3_key="audios/matthew.mp3",
            status=AudioGenerationStatus.COMPLETED,
        )

    def test_list_page_audios_success(self):
        """Test successful listing of page audios."""
        self.client.login(email="test@example.com", password="testpass123")

        url = reverse("speech_processing:page_audios", kwargs={"page_id": self.page.id})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["audios"]), 2)
        self.assertEqual(data["quota"]["used"], 2)
        self.assertEqual(data["quota"]["max"], 4)
        self.assertEqual(data["quota"]["available"], 2)
        self.assertTrue(data["is_owner"])

        # Check available voices
        self.assertIn("Ivy", data["voices"]["available"])
        self.assertIn("Joey", data["voices"]["available"])
        self.assertIn("Joanna", data["voices"]["used"])
        self.assertIn("Matthew", data["voices"]["used"])
