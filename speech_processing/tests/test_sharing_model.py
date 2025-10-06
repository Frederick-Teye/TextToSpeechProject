"""
Unit tests for DocumentSharing and SiteSettings models.
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.db import IntegrityError
from document_processing.models import Document
from speech_processing.models import (
    DocumentSharing,
    SharingPermission,
    SiteSettings,
)

User = get_user_model()


class DocumentSharingModelTests(TestCase):
    """Test DocumentSharing model permissions and constraints."""

    def setUp(self):
        """Create test users and document."""
        self.owner = User.objects.create_user(username="testuser1", email="owner@example.com", password="testpass123"
        )
        self.collaborator = User.objects.create_user(username="testuser2", email="collaborator@example.com", password="testpass123"
        )
        self.viewer = User.objects.create_user(username="testuser3", email="viewer@example.com", password="testpass123"
        )
        self.document = Document.objects.create(
            user=self.owner, title="Test Document", source_content="test.pdf", source_type="FILE", status="COMPLETED"
        )

    def test_can_generate_audio_with_collaborator_permission(self):
        """Test can_generate_audio returns True for COLLABORATOR."""
        sharing = DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.collaborator,
            shared_by=self.owner,
            permission=SharingPermission.COLLABORATOR,
        )
        self.assertTrue(sharing.can_generate_audio())

    def test_can_generate_audio_with_can_share_permission(self):
        """Test can_generate_audio returns True for CAN_SHARE."""
        sharing = DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.collaborator,
            shared_by=self.owner,
            permission=SharingPermission.CAN_SHARE,
        )
        self.assertTrue(sharing.can_generate_audio())

    def test_can_generate_audio_with_view_only_permission(self):
        """Test can_generate_audio returns False for VIEW_ONLY."""
        sharing = DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.viewer,
            shared_by=self.owner,
            permission=SharingPermission.VIEW_ONLY,
        )
        self.assertFalse(sharing.can_generate_audio())

    def test_can_share_with_can_share_permission(self):
        """Test can_share returns True only for CAN_SHARE."""
        sharing = DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.collaborator,
            shared_by=self.owner,
            permission=SharingPermission.CAN_SHARE,
        )
        self.assertTrue(sharing.can_share())

    def test_can_share_with_collaborator_permission(self):
        """Test can_share returns False for COLLABORATOR."""
        sharing = DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.collaborator,
            shared_by=self.owner,
            permission=SharingPermission.COLLABORATOR,
        )
        self.assertFalse(sharing.can_share())

    def test_can_share_with_view_only_permission(self):
        """Test can_share returns False for VIEW_ONLY."""
        sharing = DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.viewer,
            shared_by=self.owner,
            permission=SharingPermission.VIEW_ONLY,
        )
        self.assertFalse(sharing.can_share())

    def test_unique_together_constraint(self):
        """Test that duplicate share (same document + user) raises error."""
        # Create first share
        DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.collaborator,
            shared_by=self.owner,
            permission=SharingPermission.VIEW_ONLY,
        )

        # Try to create duplicate - should fail
        with self.assertRaises(IntegrityError):
            DocumentSharing.objects.create(
                document=self.document,
                shared_with=self.collaborator,  # Same user
                shared_by=self.owner,
                permission=SharingPermission.COLLABORATOR,
            )

    def test_can_share_same_document_with_different_users(self):
        """Test document can be shared with multiple users."""
        user2 = User.objects.create_user(username="testuser4", email="user2@example.com", password="testpass123"
        )
        user3 = User.objects.create_user(username="testuser5", email="user3@example.com", password="testpass123"
        )

        # Share with first user
        sharing1 = DocumentSharing.objects.create(
            document=self.document,
            shared_with=user2,
            shared_by=self.owner,
            permission=SharingPermission.VIEW_ONLY,
        )

        # Share with second user
        sharing2 = DocumentSharing.objects.create(
            document=self.document,
            shared_with=user3,
            shared_by=self.owner,
            permission=SharingPermission.COLLABORATOR,
        )

        self.assertEqual(
            DocumentSharing.objects.filter(document=self.document).count(), 2
        )

    def test_permission_levels_hierarchy(self):
        """Test that permission levels have correct hierarchy."""
        # Create shares with different permission levels
        view_only_share = DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.viewer,
            shared_by=self.owner,
            permission=SharingPermission.VIEW_ONLY,
        )

        doc2 = Document.objects.create(
            user=self.owner, title="Doc 2", source_content="test2.pdf", source_type="FILE", status="COMPLETED"
        )
        collaborator_share = DocumentSharing.objects.create(
            document=doc2,
            shared_with=self.collaborator,
            shared_by=self.owner,
            permission=SharingPermission.COLLABORATOR,
        )

        doc3 = Document.objects.create(
            user=self.owner, title="Doc 3", source_content="test3.pdf", source_type="FILE", status="COMPLETED"
        )
        can_share_share = DocumentSharing.objects.create(
            document=doc3,
            shared_with=self.collaborator,
            shared_by=self.owner,
            permission=SharingPermission.CAN_SHARE,
        )

        # VIEW_ONLY: can't generate or share
        self.assertFalse(view_only_share.can_generate_audio())
        self.assertFalse(view_only_share.can_share())

        # COLLABORATOR: can generate but can't share
        self.assertTrue(collaborator_share.can_generate_audio())
        self.assertFalse(collaborator_share.can_share())

        # CAN_SHARE: can both generate and share
        self.assertTrue(can_share_share.can_generate_audio())
        self.assertTrue(can_share_share.can_share())


class SiteSettingsModelTests(TestCase):
    """Test SiteSettings singleton pattern."""

    def tearDown(self):
        """Clean up all SiteSettings instances after each test."""
        SiteSettings.objects.all().delete()

    def test_get_settings_creates_instance_if_none_exists(self):
        """Test get_settings creates instance with defaults if none exists."""
        # Ensure no settings exist
        SiteSettings.objects.all().delete()

        settings = SiteSettings.get_settings()
        self.assertIsNotNone(settings)
        self.assertEqual(settings.max_audios_per_page, 4)
        self.assertEqual(settings.audio_retention_months, 6)
        self.assertTrue(settings.audio_generation_enabled)

    def test_get_settings_returns_existing_instance(self):
        """Test get_settings returns existing instance if one exists."""
        # Create settings instance first
        first_call = SiteSettings.get_settings()
        first_call.max_audios_per_page = 5
        first_call.audio_retention_months = 12
        first_call.audio_generation_enabled = False
        first_call.save()

        # Get settings should return same instance
        settings = SiteSettings.get_settings()
        self.assertEqual(settings.id, first_call.id)
        self.assertEqual(settings.max_audios_per_page, 5)
        self.assertEqual(settings.audio_retention_months, 12)
        self.assertFalse(settings.audio_generation_enabled)

    def test_only_one_instance_allowed(self):
        """Test that save() prevents creation of second instance."""
        # Create first instance
        settings1 = SiteSettings.objects.create(max_audios_per_page=4)

        # Try to create second instance - should raise validation error
        settings2 = SiteSettings(max_audios_per_page=5)

        with self.assertRaises(Exception):  # Will raise in save()
            settings2.save()

        # Only one instance should exist
        self.assertEqual(SiteSettings.objects.count(), 1)

    def test_default_values(self):
        """Test that default values are set correctly."""
        settings = SiteSettings.get_settings()

        self.assertEqual(settings.max_audios_per_page, 4)
        self.assertEqual(settings.audio_retention_months, 6)
        self.assertEqual(settings.expiry_warning_days, 30)
        self.assertTrue(settings.audio_generation_enabled)
        self.assertTrue(settings.enable_email_notifications)
        self.assertTrue(settings.enable_in_app_notifications)

    def test_can_update_existing_settings(self):
        """Test that existing settings can be updated."""
        settings = SiteSettings.get_settings()
        original_id = settings.id

        # Update settings
        settings.max_audios_per_page = 10
        settings.audio_retention_months = 12
        settings.save()

        # Refresh and verify
        settings.refresh_from_db()
        self.assertEqual(settings.id, original_id)  # Same instance
        self.assertEqual(settings.max_audios_per_page, 10)
        self.assertEqual(settings.audio_retention_months, 12)

    def test_settings_str_representation(self):
        """Test string representation of settings."""
        settings = SiteSettings.get_settings()
        str_repr = str(settings)
        self.assertIn("Site Settings", str_repr)
