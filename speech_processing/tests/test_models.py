"""
Unit tests for Audio model.
Tests quota enforcement, voice uniqueness, expiry logic, and soft delete.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import timedelta
from document_processing.models import Document, DocumentPage
from speech_processing.models import (
    Audio,
    AudioGenerationStatus,
    AudioLifetimeStatus,
    TTSVoice,
    SiteSettings,
)

User = get_user_model()


class AudioModelQuotaTests(TestCase):
    """Test quota enforcement (max 4 audios per page lifetime)."""

    def setUp(self):
        """Create test user, document, and page."""
        self.user = User.objects.create_user(username="testuser21", email="test@example.com", password="testpass123"
        )
        self.document = Document.objects.create(
            user=self.user,
            title="Test Document",
            source_content="test.pdf", source_type="FILE",
            status="COMPLETED",
        )
        self.page = DocumentPage.objects.create(
            document=self.document,
            page_number=1,
            markdown_content="Test content for TTS generation.",
        )

        # Ensure SiteSettings exists with default max_audios_per_page = 4
        self.settings = SiteSettings.get_settings()
        self.settings.max_audios_per_page = 4
        self.settings.save()

    def test_can_create_audio_within_quota(self):
        """Test that audios can be created when under quota."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/test1.mp3",
            status=AudioGenerationStatus.COMPLETED,
        )
        self.assertEqual(audio.page, self.page)
        self.assertEqual(audio.voice, TTSVoice.JOANNA)

    def test_quota_enforcement_max_4_audios(self):
        """Test that 5th audio creation fails (max 4 allowed)."""
        # Create 4 audios (at quota limit)
        voices = [TTSVoice.JOANNA, TTSVoice.MATTHEW, TTSVoice.IVY, TTSVoice.JOEY]
        for voice in voices:
            Audio.objects.create(
                page=self.page,
                voice=voice,
                generated_by=self.user,
                s3_key=f"audios/{voice}.mp3",
                status=AudioGenerationStatus.COMPLETED,
            )

        # Try to create 5th audio - should fail
        with self.assertRaises(ValidationError) as cm:
            audio = Audio(
                page=self.page,
                voice=TTSVoice.KENDRA,
                generated_by=self.user,
                s3_key="audios/kendra.mp3",
            )
            audio.clean()  # This should raise ValidationError

        self.assertIn("Maximum 4 audios per page", str(cm.exception))

    def test_deleted_audios_count_toward_quota(self):
        """Test that soft-deleted audios still count toward lifetime quota."""
        # Create 3 audios
        for i, voice in enumerate([TTSVoice.JOANNA, TTSVoice.MATTHEW, TTSVoice.IVY]):
            Audio.objects.create(
                page=self.page,
                voice=voice,
                generated_by=self.user,
                s3_key=f"audios/{voice}.mp3",
            )

        # Soft delete one audio
        audio_to_delete = Audio.objects.get(voice=TTSVoice.IVY)
        audio_to_delete.lifetime_status = AudioLifetimeStatus.DELETED
        audio_to_delete.deleted_at = timezone.now()
        audio_to_delete.save()

        # Should still be able to create 1 more (total lifetime = 4)
        audio4 = Audio(
            page=self.page,
            voice=TTSVoice.JOEY,
            generated_by=self.user,
            s3_key="audios/joey.mp3",
        )
        audio4.clean()  # Should not raise
        audio4.save()

        # But 5th should fail
        with self.assertRaises(ValidationError):
            audio5 = Audio(
                page=self.page,
                voice=TTSVoice.KENDRA,
                generated_by=self.user,
                s3_key="audios/kendra.mp3",
            )
            audio5.clean()

    def test_expired_audios_count_toward_quota(self):
        """Test that expired audios count toward lifetime quota."""
        # Create 4 audios, mark one as expired
        voices = [TTSVoice.JOANNA, TTSVoice.MATTHEW, TTSVoice.IVY, TTSVoice.JOEY]
        for voice in voices:
            Audio.objects.create(
                page=self.page,
                voice=voice,
                generated_by=self.user,
                s3_key=f"audios/{voice}.mp3",
            )

        # Mark one as expired
        audio_to_expire = Audio.objects.get(voice=TTSVoice.JOEY)
        audio_to_expire.lifetime_status = AudioLifetimeStatus.EXPIRED
        audio_to_expire.save()

        # Quota should still be full (4 audios lifetime)
        with self.assertRaises(ValidationError):
            audio5 = Audio(
                page=self.page,
                voice=TTSVoice.KENDRA,
                generated_by=self.user,
                s3_key="audios/kendra.mp3",
            )
            audio5.clean()


class AudioModelVoiceUniquenessTests(TestCase):
    """Test voice uniqueness constraint (no duplicate active voices per page)."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(username="testuser22", email="test@example.com", password="testpass123"
        )
        self.document = Document.objects.create(
            user=self.user, title="Test Document", source_content="test.pdf", source_type="FILE", status="COMPLETED"
        )
        self.page = DocumentPage.objects.create(
            document=self.document, page_number=1, markdown_content="Test content"
        )

    def test_cannot_create_duplicate_active_voice(self):
        """Test that duplicate active voice on same page fails."""
        # Create first audio with Joanna voice
        Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/joanna1.mp3",
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )

        # Try to create second audio with same voice - should fail in clean()
        with self.assertRaises(ValidationError) as cm:
            audio2 = Audio(
                page=self.page,
                voice=TTSVoice.JOANNA,
                generated_by=self.user,
                s3_key="audios/joanna2.mp3",
                lifetime_status=AudioLifetimeStatus.ACTIVE,
            )
            audio2.clean()

        self.assertIn("Voice Joanna is already used", str(cm.exception))

    def test_can_reuse_voice_after_deletion(self):
        """Test that voice can be reused after original is soft-deleted."""
        # Create audio with Joanna voice
        audio1 = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/joanna1.mp3",
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )

        # Soft delete it
        audio1.lifetime_status = AudioLifetimeStatus.DELETED
        audio1.deleted_at = timezone.now()
        audio1.save()

        # Should be able to create new audio with same voice
        audio2 = Audio(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/joanna2.mp3",
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        audio2.clean()  # Should not raise
        audio2.save()
        self.assertEqual(audio2.voice, TTSVoice.JOANNA)

    def test_can_reuse_voice_after_expiry(self):
        """Test that voice can be reused after original expires."""
        # Create audio with Matthew voice
        audio1 = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.MATTHEW,
            generated_by=self.user,
            s3_key="audios/matthew1.mp3",
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )

        # Mark as expired
        audio1.lifetime_status = AudioLifetimeStatus.EXPIRED
        audio1.save()

        # Should be able to create new audio with same voice
        audio2 = Audio(
            page=self.page,
            voice=TTSVoice.MATTHEW,
            generated_by=self.user,
            s3_key="audios/matthew2.mp3",
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        audio2.clean()  # Should not raise
        audio2.save()
        self.assertEqual(audio2.voice, TTSVoice.MATTHEW)

    def test_different_pages_can_have_same_voice(self):
        """Test that different pages can have audios with same voice."""
        # Create second page
        page2 = DocumentPage.objects.create(
            document=self.document, page_number=2, markdown_content="Different content"
        )

        # Create audio on first page
        Audio.objects.create(
            page=self.page,
            voice=TTSVoice.IVY,
            generated_by=self.user,
            s3_key="audios/ivy_page1.mp3",
        )

        # Create audio on second page with same voice - should succeed
        audio2 = Audio(
            page=page2,
            voice=TTSVoice.IVY,
            generated_by=self.user,
            s3_key="audios/ivy_page2.mp3",
        )
        audio2.clean()  # Should not raise
        audio2.save()
        self.assertEqual(audio2.voice, TTSVoice.IVY)


class AudioModelExpiryTests(TestCase):
    """Test expiry logic (is_expired, days_until_expiry, needs_expiry_warning)."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(username="testuser23", email="test@example.com", password="testpass123"
        )
        self.document = Document.objects.create(
            user=self.user, title="Test Document", source_content="test.pdf", source_type="FILE", status="COMPLETED"
        )
        self.page = DocumentPage.objects.create(
            document=self.document, page_number=1, markdown_content="Test content"
        )

        # Set retention to 6 months (180 days)
        self.settings = SiteSettings.get_settings()
        self.settings.audio_retention_months = 6
        self.settings.save()

    def test_is_expired_never_played_not_expired(self):
        """Test audio created recently (never played) is not expired."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=None,  # Never played
        )
        self.assertFalse(audio.is_expired())

    def test_is_expired_never_played_is_expired(self):
        """Test audio created 7 months ago (never played) is expired."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=None,
        )

        # Manually set created_at to 7 months ago
        audio.created_at = timezone.now() - timedelta(days=210)
        audio.save()

        self.assertTrue(audio.is_expired())

    def test_is_expired_recently_played(self):
        """Test audio played recently is not expired."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.MATTHEW,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=timezone.now() - timedelta(days=30),  # 1 month ago
        )
        self.assertFalse(audio.is_expired())

    def test_is_expired_old_play_date(self):
        """Test audio not played for 7 months is expired."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.IVY,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=timezone.now() - timedelta(days=210),  # 7 months
        )
        self.assertTrue(audio.is_expired())

    def test_days_until_expiry_never_played(self):
        """Test days_until_expiry calculation for never-played audio."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOEY,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=None,
        )

        # Should be ~180 days (6 months)
        days = audio.days_until_expiry()
        self.assertGreater(days, 175)
        self.assertLess(days, 181)

    def test_days_until_expiry_recently_played(self):
        """Test days_until_expiry after recent play."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.KENDRA,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=timezone.now() - timedelta(days=150),  # 5 months ago
        )

        # Should be ~30 days left (180 - 150)
        days = audio.days_until_expiry()
        self.assertGreater(days, 28)
        self.assertLess(days, 32)

    def test_days_until_expiry_expired_audio(self):
        """Test days_until_expiry returns 0 for expired audio."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.KIMBERLY,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=timezone.now() - timedelta(days=200),  # 6.5 months
        )

        days = audio.days_until_expiry()
        self.assertEqual(days, 0)

    def test_needs_expiry_warning_no_warning_needed(self):
        """Test needs_expiry_warning returns False for recently played audio."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.SALLI,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=timezone.now() - timedelta(days=30),  # 1 month ago
        )

        # 150 days left, no warning needed
        self.assertFalse(audio.needs_expiry_warning())

    def test_needs_expiry_warning_warning_needed(self):
        """Test needs_expiry_warning returns True when 25 days left."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JUSTIN,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=timezone.now() - timedelta(days=155),  # ~25 days left
        )

        self.assertTrue(audio.needs_expiry_warning())

    def test_needs_expiry_warning_already_expired(self):
        """Test needs_expiry_warning returns False for expired audio."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=timezone.now() - timedelta(days=200),  # Expired
        )

        self.assertFalse(audio.needs_expiry_warning())

    def test_get_expiry_date_never_played(self):
        """Test get_expiry_date calculation for never-played audio."""
        now = timezone.now()
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.MATTHEW,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=None,
        )

        expiry_date = audio.get_expiry_date()
        expected_expiry = audio.created_at + timedelta(days=180)

        # Should be within 1 minute of expected
        diff = abs((expiry_date - expected_expiry).total_seconds())
        self.assertLess(diff, 60)

    def test_get_expiry_date_with_play_date(self):
        """Test get_expiry_date uses last_played_at when available."""
        play_date = timezone.now() - timedelta(days=100)
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.IVY,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            status=AudioGenerationStatus.COMPLETED,
            last_played_at=play_date,
        )

        expiry_date = audio.get_expiry_date()
        expected_expiry = play_date + timedelta(days=180)

        diff = abs((expiry_date - expected_expiry).total_seconds())
        self.assertLess(diff, 60)


class AudioModelSoftDeleteTests(TestCase):
    """Test soft delete behavior."""

    def setUp(self):
        """Create test data."""
        self.user = User.objects.create_user(username="testuser24", email="test@example.com", password="testpass123"
        )
        self.document = Document.objects.create(
            user=self.user, title="Test Document", source_content="test.pdf", source_type="FILE", status="COMPLETED"
        )
        self.page = DocumentPage.objects.create(
            document=self.document, page_number=1, markdown_content="Test content"
        )

    def test_soft_delete_sets_lifetime_status(self):
        """Test soft delete changes lifetime_status to DELETED."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/test.mp3",
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )

        # Soft delete
        audio.lifetime_status = AudioLifetimeStatus.DELETED
        audio.deleted_at = timezone.now()
        audio.save()

        # Refresh from DB
        audio.refresh_from_db()
        self.assertEqual(audio.lifetime_status, AudioLifetimeStatus.DELETED)
        self.assertIsNotNone(audio.deleted_at)

    def test_soft_delete_record_remains_in_database(self):
        """Test soft-deleted audio still exists in database."""
        audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.MATTHEW,
            generated_by=self.user,
            s3_key="audios/test.mp3",
        )

        audio_id = audio.id

        # Soft delete
        audio.lifetime_status = AudioLifetimeStatus.DELETED
        audio.save()

        # Should still exist in database
        self.assertTrue(Audio.objects.filter(id=audio_id).exists())

    def test_soft_delete_allows_voice_reuse(self):
        """Test that soft-deleting an audio allows voice reuse."""
        # Create and soft-delete first audio
        audio1 = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.IVY,
            generated_by=self.user,
            s3_key="audios/ivy1.mp3",
        )
        audio1.lifetime_status = AudioLifetimeStatus.DELETED
        audio1.save()

        # Should be able to create new audio with same voice
        audio2 = Audio(
            page=self.page,
            voice=TTSVoice.IVY,
            generated_by=self.user,
            s3_key="audios/ivy2.mp3",
        )
        audio2.clean()  # Should not raise
        audio2.save()
        self.assertEqual(audio2.voice, TTSVoice.IVY)
