"""
Integration tests for document sharing API endpoints.
Tests share creation, permission validation, and share management.
"""

import json
from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from document_processing.models import Document, DocumentPage
from speech_processing.models import DocumentSharing, SharingPermission

User = get_user_model()


class ShareDocumentAPITests(TestCase):
    """Test POST /documents/<document_id>/share/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.owner = User.objects.create_user(
            username="testuser6", email="owner@example.com", password="testpass123"
        )
        self.user_to_share = User.objects.create_user(
            username="testuser7", email="shared@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="testuser8", email="other@example.com", password="testpass123"
        )

        self.document = Document.objects.create(
            user=self.owner, title="Test Doc", source_content="test.pdf", source_type="FILE", status="COMPLETED"
        )

    def test_share_document_by_owner_success(self):
        """Test owner can share document with collaborator permission."""
        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:share_document",
            kwargs={"document_id": self.document.id},
        )
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "email": "shared@example.com",
                    "permission": "COLLABORATOR",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify share was created
        share = DocumentSharing.objects.get(
            document=self.document, shared_with=self.user_to_share
        )
        self.assertEqual(share.permission, SharingPermission.COLLABORATOR)
        self.assertEqual(share.shared_by, self.owner)

    def test_share_document_by_non_owner(self):
        """Test non-owner cannot share document."""
        self.client.login(email="other@example.com", password="testpass123")

        url = reverse(
            "speech_processing:share_document",
            kwargs={"document_id": self.document.id},
        )
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "email": "shared@example.com",
                    "permission": "VIEW_ONLY",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("permission", data["error"].lower())

    def test_share_document_with_can_share_permission(self):
        """Test user with CAN_SHARE permission can share document."""
        # Give other_user CAN_SHARE permission
        DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.other_user,
            shared_by=self.owner,
            permission=SharingPermission.CAN_SHARE,
        )

        self.client.login(email="other@example.com", password="testpass123")

        url = reverse(
            "speech_processing:share_document",
            kwargs={"document_id": self.document.id},
        )
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "email": "shared@example.com",
                    "permission": "VIEW_ONLY",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify share was created
        share = DocumentSharing.objects.get(
            document=self.document, shared_with=self.user_to_share
        )
        self.assertEqual(share.permission, SharingPermission.VIEW_ONLY)

    def test_share_document_invalid_email(self):
        """Test sharing with non-existent email fails gracefully."""
        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:share_document",
            kwargs={"document_id": self.document.id},
        )
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "email": "nonexistent@example.com",
                    "permission": "VIEW_ONLY",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("user", data["error"].lower())

    def test_share_document_duplicate_share(self):
        """Test sharing with already shared user fails."""
        # Create existing share
        DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.user_to_share,
            shared_by=self.owner,
            permission=SharingPermission.VIEW_ONLY,
        )

        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:share_document",
            kwargs={"document_id": self.document.id},
        )
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "email": "shared@example.com",
                    "permission": "COLLABORATOR",
                }
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("already", data["error"].lower())


class UnshareDocumentAPITests(TestCase):
    """Test DELETE /documents/<document_id>/unshare/<share_id>/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.owner = User.objects.create_user(
            username="testuser9", email="owner@example.com", password="testpass123"
        )
        self.shared_user = User.objects.create_user(
            username="testuser10", email="shared@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="testuser11", email="other@example.com", password="testpass123"
        )

        self.document = Document.objects.create(
            user=self.owner, title="Test Doc", source_content="test.pdf", source_type="FILE", status="COMPLETED"
        )
        self.share = DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.shared_user,
            shared_by=self.owner,
            permission=SharingPermission.COLLABORATOR,
        )

    def test_unshare_by_owner_success(self):
        """Test owner can remove share."""
        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:unshare_document",
            kwargs={"document_id": self.document.id, "share_id": self.share.id},
        )
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify share was deleted
        self.assertFalse(DocumentSharing.objects.filter(id=self.share.id).exists())

    def test_unshare_by_non_owner(self):
        """Test non-owner cannot remove share."""
        self.client.login(email="other@example.com", password="testpass123")

        url = reverse(
            "speech_processing:unshare_document",
            kwargs={"document_id": self.document.id, "share_id": self.share.id},
        )
        response = self.client.delete(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("permission", data["error"].lower())

        # Share should still exist
        self.assertTrue(DocumentSharing.objects.filter(id=self.share.id).exists())


class DocumentSharesListAPITests(TestCase):
    """Test GET /documents/<document_id>/shares/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.owner = User.objects.create_user(
            username="testuser12", email="owner@example.com", password="testpass123"
        )
        self.user1 = User.objects.create_user(
            username="testuser13", email="user1@example.com", password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="testuser14", email="user2@example.com", password="testpass123"
        )

        self.document = Document.objects.create(
            user=self.owner, title="Test Doc", source_content="test.pdf", source_type="FILE", status="COMPLETED"
        )

        # Create shares
        DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.user1,
            shared_by=self.owner,
            permission=SharingPermission.COLLABORATOR,
        )
        DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.user2,
            shared_by=self.owner,
            permission=SharingPermission.VIEW_ONLY,
        )

    def test_list_shares_by_owner(self):
        """Test owner can list all shares."""
        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:document_shares",
            kwargs={"document_id": self.document.id},
        )
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["shares"]), 2)

        # Check share details
        emails = [share["shared_with"]["email"] for share in data["shares"]]
        self.assertIn("user1@example.com", emails)
        self.assertIn("user2@example.com", emails)


class SharedWithMeAPITests(TestCase):
    """Test GET /documents/shared-with-me/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.owner1 = User.objects.create_user(
            username="testuser15", email="owner1@example.com", password="testpass123"
        )
        self.owner2 = User.objects.create_user(
            username="testuser16", email="owner2@example.com", password="testpass123"
        )
        self.shared_user = User.objects.create_user(
            username="testuser17", email="shared@example.com", password="testpass123"
        )

        self.doc1 = Document.objects.create(
            user=self.owner1, title="Doc 1", source_content="doc1.pdf", source_type="FILE", status="COMPLETED"
        )
        self.doc2 = Document.objects.create(
            user=self.owner2, title="Doc 2", source_content="doc2.pdf", source_type="FILE", status="COMPLETED"
        )

        # Share both documents with shared_user
        DocumentSharing.objects.create(
            document=self.doc1,
            shared_with=self.shared_user,
            shared_by=self.owner1,
            permission=SharingPermission.COLLABORATOR,
        )
        DocumentSharing.objects.create(
            document=self.doc2,
            shared_with=self.shared_user,
            shared_by=self.owner2,
            permission=SharingPermission.VIEW_ONLY,
        )

    def test_list_shared_with_me(self):
        """Test user can list documents shared with them."""
        self.client.login(email="shared@example.com", password="testpass123")

        url = reverse("speech_processing:shared_with_me")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(len(data["shared_documents"]), 2)

        # Check document titles
        titles = [doc["document"]["title"] for doc in data["shared_documents"]]
        self.assertIn("Doc 1", titles)
        self.assertIn("Doc 2", titles)

        # Check permissions
        perms = {
            doc["document"]["title"]: doc["permission"]
            for doc in data["shared_documents"]
        }
        self.assertEqual(perms["Doc 1"], "COLLABORATOR")
        self.assertEqual(perms["Doc 2"], "VIEW_ONLY")


class UpdateSharePermissionAPITests(TestCase):
    """Test PATCH /documents/<document_id>/shares/<share_id>/permission/ endpoint."""

    def setUp(self):
        """Create test data."""
        self.client = Client()
        self.owner = User.objects.create_user(
            username="testuser18", email="owner@example.com", password="testpass123"
        )
        self.shared_user = User.objects.create_user(
            username="testuser19", email="shared@example.com", password="testpass123"
        )
        self.other_user = User.objects.create_user(
            username="testuser20", email="other@example.com", password="testpass123"
        )

        self.document = Document.objects.create(
            user=self.owner, title="Test Doc", source_content="test.pdf", source_type="FILE", status="COMPLETED"
        )
        self.share = DocumentSharing.objects.create(
            document=self.document,
            shared_with=self.shared_user,
            shared_by=self.owner,
            permission=SharingPermission.VIEW_ONLY,
        )

    def test_update_permission_by_owner(self):
        """Test owner can update share permission."""
        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:update_share_permission",
            kwargs={"document_id": self.document.id, "share_id": self.share.id},
        )
        response = self.client.patch(
            url,
            data=json.dumps({"permission": "COLLABORATOR"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])

        # Verify permission was updated
        self.share.refresh_from_db()
        self.assertEqual(self.share.permission, SharingPermission.COLLABORATOR)

    def test_update_permission_by_non_owner(self):
        """Test non-owner cannot update permission."""
        self.client.login(email="other@example.com", password="testpass123")

        url = reverse(
            "speech_processing:update_share_permission",
            kwargs={"document_id": self.document.id, "share_id": self.share.id},
        )
        response = self.client.patch(
            url,
            data=json.dumps({"permission": "CAN_SHARE"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("permission", data["error"].lower())

        # Permission should not change
        self.share.refresh_from_db()
        self.assertEqual(self.share.permission, SharingPermission.VIEW_ONLY)

    def test_update_permission_invalid_value(self):
        """Test update fails with invalid permission value."""
        self.client.login(email="owner@example.com", password="testpass123")

        url = reverse(
            "speech_processing:update_share_permission",
            kwargs={"document_id": self.document.id, "share_id": self.share.id},
        )
        response = self.client.patch(
            url,
            data=json.dumps({"permission": "INVALID"}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("invalid", data["error"].lower())
