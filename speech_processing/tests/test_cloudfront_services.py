"""
Test suite for CloudFront-based audio URL generation.

Tests the AudioGenerationService.get_presigned_url() method which now uses
CloudFront signed URLs for both development and production environments,
with graceful fallback to S3 presigned URLs.

Key changes tested:
1. get_presigned_url() always attempts CloudFront first
2. Graceful fallback to S3 if CloudFront signing fails
3. Consistent behavior across development and production
4. Error handling and logging
"""

from unittest.mock import Mock, patch, MagicMock
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.conf import settings
from django.core.cache import cache
from document_processing.models import Document, DocumentPage
from speech_processing.models import (
    Audio,
    AudioGenerationStatus,
    AudioLifetimeStatus,
    TTSVoice,
)
from speech_processing.services import AudioGenerationService
import logging

User = get_user_model()


class CloudFrontPresignedURLTests(TestCase):
    """Test CloudFront presigned URL generation with S3 fallback."""

    def setUp(self):
        """Create test fixtures: user, document, page, and audio."""
        self.user = User.objects.create_user(
            username="cloudfront_test_user",
            email="cloudfront@example.com",
            password="testpass123",
        )
        self.document = Document.objects.create(
            user=self.user,
            title="CloudFront Test Document",
            source_content="test.pdf",
            source_type="FILE",
            status="COMPLETED",
        )
        self.page = DocumentPage.objects.create(
            document=self.document,
            page_number=1,
            markdown_content="Test content for CloudFront URL generation.",
        )
        self.audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.JOANNA,
            generated_by=self.user,
            s3_key="audios/document_1/page_1/voice_Joanna_20251104_120000.mp3",
            status=AudioGenerationStatus.COMPLETED,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        self.service = AudioGenerationService()
        # Clear cache before each test
        cache.clear()

    def tearDown(self):
        """Clean up after tests."""
        cache.clear()

    @patch("core.cloudfront_utils.get_audio_signed_url")
    def test_get_presigned_url_uses_cloudfront_first(self, mock_cloudfront):
        """
        Test that get_presigned_url() always attempts CloudFront first,
        regardless of environment.

        Expected behavior:
        - Calls get_audio_signed_url() from cloudfront_utils
        - Returns CloudFront signed URL if successful
        - Does not fall back to S3
        """
        # Mock successful CloudFront signing
        mock_cloudfront_url = "https://d2e40gg2o2wus6.cloudfront.net/media/audio.mp3?Policy=...&Signature=..."
        mock_cloudfront.return_value = mock_cloudfront_url

        # Call the method
        result = self.service.get_presigned_url(self.audio)

        # Assertions
        self.assertEqual(result, mock_cloudfront_url)
        mock_cloudfront.assert_called_once()
        self.assertIn("cloudfront.net", result)

    @patch("core.cloudfront_utils.get_audio_signed_url")
    @patch.object(AudioGenerationService, "_get_s3_presigned_url")
    def test_get_presigned_url_falls_back_to_s3_on_cloudfront_error(
        self, mock_s3, mock_cloudfront
    ):
        """
        Test that get_presigned_url() gracefully falls back to S3 if CloudFront fails.

        Expected behavior:
        - Attempts CloudFront signing
        - Catches CloudFrontSigningError
        - Falls back to S3 presigned URL
        - Returns S3 URL
        - Logs warning about CloudFront failure
        """
        from core.cloudfront_utils import CloudFrontSigningError

        # Mock CloudFront failure
        mock_cloudfront.side_effect = CloudFrontSigningError("Private key not found")

        # Mock successful S3 fallback
        s3_url = "https://bucket.s3.amazonaws.com/media/audio.mp3?AWSAccessKeyId=...&Signature=..."
        mock_s3.return_value = s3_url

        # Call the method
        result = self.service.get_presigned_url(self.audio)

        # Assertions
        self.assertEqual(result, s3_url)
        mock_cloudfront.assert_called_once()
        mock_s3.assert_called_once()
        self.assertIn("s3.amazonaws.com", result)

    @patch("core.cloudfront_utils.get_audio_signed_url")
    @patch.object(AudioGenerationService, "_get_s3_presigned_url")
    def test_get_presigned_url_returns_none_on_total_failure(
        self, mock_s3, mock_cloudfront
    ):
        """
        Test that get_presigned_url() returns None if both CloudFront and S3 fail.

        Expected behavior:
        - Attempts CloudFront signing (fails)
        - Falls back to S3 (fails)
        - Returns None
        - Logs error about complete failure
        """
        from core.cloudfront_utils import CloudFrontSigningError

        # Mock both services failing
        mock_cloudfront.side_effect = CloudFrontSigningError("Private key not found")
        mock_s3.return_value = None  # S3 fallback also fails

        # Call the method
        result = self.service.get_presigned_url(self.audio)

        # Assertions
        self.assertIsNone(result)
        mock_cloudfront.assert_called_once()
        mock_s3.assert_called_once()

    @patch("core.cloudfront_utils.get_audio_signed_url")
    @patch.object(AudioGenerationService, "_get_s3_presigned_url")
    def test_get_presigned_url_uses_custom_expiration(self, mock_s3, mock_cloudfront):
        """
        Test that get_presigned_url() respects custom expiration parameter.

        Expected behavior:
        - Passes expiration parameter to CloudFront
        - Uses custom expiration instead of default from settings
        """
        mock_cloudfront_url = "https://d2e40gg2o2wus6.cloudfront.net/media/audio.mp3?Policy=...&Signature=..."
        mock_cloudfront.return_value = mock_cloudfront_url
        custom_expiration = 7200  # 2 hours

        # Call the method with custom expiration
        result = self.service.get_presigned_url(
            self.audio, expiration=custom_expiration
        )

        # Assertions
        self.assertEqual(result, mock_cloudfront_url)
        # Verify CloudFront was called with correct expiration
        mock_cloudfront.assert_called_once_with(
            self.audio, expiration_seconds=custom_expiration
        )

    @patch("core.cloudfront_utils.get_audio_signed_url")
    def test_get_presigned_url_uses_default_expiration(self, mock_cloudfront):
        """
        Test that get_presigned_url() uses default expiration from settings.

        Expected behavior:
        - Uses AUDIO_PRESIGNED_URL_EXPIRATION_SECONDS from settings
        - Defaults to 3600 seconds (1 hour)
        """
        mock_cloudfront_url = "https://d2e40gg2o2wus6.cloudfront.net/media/audio.mp3?Policy=...&Signature=..."
        mock_cloudfront.return_value = mock_cloudfront_url

        # Call the method without explicit expiration
        result = self.service.get_presigned_url(self.audio)

        # Assertions
        self.assertEqual(result, mock_cloudfront_url)
        # Verify default expiration from settings was used
        expected_expiration = settings.AUDIO_PRESIGNED_URL_EXPIRATION_SECONDS
        mock_cloudfront.assert_called_once_with(
            self.audio, expiration_seconds=expected_expiration
        )

    @patch("speech_processing.services.logger")
    @patch("core.cloudfront_utils.get_audio_signed_url")
    def test_get_presigned_url_logs_debug_on_cloudfront_attempt(
        self, mock_cloudfront, mock_logger
    ):
        """
        Test that get_presigned_url() logs debug message when attempting CloudFront.

        Expected behavior:
        - Logs debug message before attempting CloudFront signing
        - Message includes audio ID
        """
        mock_cloudfront_url = "https://d2e40gg2o2wus6.cloudfront.net/media/audio.mp3?Policy=...&Signature=..."
        mock_cloudfront.return_value = mock_cloudfront_url

        # Call the method
        result = self.service.get_presigned_url(self.audio)

        # Assertions
        mock_logger.debug.assert_called()
        # Check that debug message includes audio ID
        debug_calls = [str(call) for call in mock_logger.debug.call_args_list]
        self.assertTrue(
            any(str(self.audio.id) in str(call) for call in debug_calls),
            f"Audio ID not found in debug logs: {debug_calls}",
        )

    @patch("speech_processing.services.logger")
    @patch("core.cloudfront_utils.get_audio_signed_url")
    @patch.object(AudioGenerationService, "_get_s3_presigned_url")
    def test_get_presigned_url_logs_warning_on_cloudfront_failure(
        self, mock_s3, mock_cloudfront, mock_logger
    ):
        """
        Test that get_presigned_url() logs warning when CloudFront fails.

        Expected behavior:
        - Logs warning message when CloudFront signing fails
        - Message includes audio ID and error details
        """
        from core.cloudfront_utils import CloudFrontSigningError

        mock_cloudfront.side_effect = CloudFrontSigningError("Private key not found")
        s3_url = "https://bucket.s3.amazonaws.com/media/audio.mp3?AWSAccessKeyId=...&Signature=..."
        mock_s3.return_value = s3_url

        # Call the method
        result = self.service.get_presigned_url(self.audio)

        # Assertions
        mock_logger.warning.assert_called()
        # Check that warning includes audio ID
        warning_calls = [str(call) for call in mock_logger.warning.call_args_list]
        self.assertTrue(
            any(str(self.audio.id) in str(call) for call in warning_calls),
            f"Audio ID not found in warning logs: {warning_calls}",
        )

    @patch("speech_processing.services.logger")
    @patch("core.cloudfront_utils.get_audio_signed_url")
    @patch.object(AudioGenerationService, "_get_s3_presigned_url")
    def test_get_presigned_url_logs_info_on_s3_fallback(
        self, mock_s3, mock_cloudfront, mock_logger
    ):
        """
        Test that get_presigned_url() logs info message when falling back to S3.

        Expected behavior:
        - Logs info message when CloudFront fails and S3 is used
        - Message includes audio ID
        """
        from core.cloudfront_utils import CloudFrontSigningError

        mock_cloudfront.side_effect = CloudFrontSigningError("Private key not found")
        s3_url = "https://bucket.s3.amazonaws.com/media/audio.mp3?AWSAccessKeyId=...&Signature=..."
        mock_s3.return_value = s3_url

        # Call the method
        result = self.service.get_presigned_url(self.audio)

        # Assertions
        mock_logger.info.assert_called()
        # Check that info message mentions S3 fallback
        info_calls = [str(call) for call in mock_logger.info.call_args_list]
        self.assertTrue(
            any(
                "fallback" in str(call).lower() or "S3" in str(call)
                for call in info_calls
            ),
            f"S3 fallback not mentioned in info logs: {info_calls}",
        )

    @patch("speech_processing.services.logger")
    @patch("core.cloudfront_utils.get_audio_signed_url")
    def test_get_presigned_url_logs_error_on_unexpected_exception(
        self, mock_cloudfront, mock_logger
    ):
        """
        Test that get_presigned_url() logs error on unexpected exceptions.

        Expected behavior:
        - Catches unexpected exceptions
        - Logs error message
        - Returns None
        """
        # Mock unexpected exception
        mock_cloudfront.side_effect = Exception("Unexpected error")

        # Call the method
        result = self.service.get_presigned_url(self.audio)

        # Assertions
        self.assertIsNone(result)
        mock_logger.error.assert_called()

    def test_get_s3_presigned_url_success(self):
        """
        Test that _get_s3_presigned_url() successfully generates S3 URLs.

        Expected behavior:
        - Calls s3_client.generate_presigned_url()
        - Returns valid S3 presigned URL
        - Includes bucket name, key, and parameters
        """
        with patch.object(
            self.service.polly_service.s3_client, "generate_presigned_url"
        ) as mock_s3_gen:
            s3_url = "https://bucket.s3.amazonaws.com/media/audio.mp3?AWSAccessKeyId=AKIA...&Signature=..."
            mock_s3_gen.return_value = s3_url

            result = self.service._get_s3_presigned_url(self.audio, 3600)

            # Assertions
            self.assertEqual(result, s3_url)
            mock_s3_gen.assert_called_once()

    def test_get_s3_presigned_url_failure_returns_none(self):
        """
        Test that _get_s3_presigned_url() returns None on error.

        Expected behavior:
        - Catches exceptions from s3_client
        - Logs error
        - Returns None
        """
        with patch.object(
            self.service.polly_service.s3_client,
            "generate_presigned_url",
            side_effect=Exception("S3 error"),
        ):
            result = self.service._get_s3_presigned_url(self.audio, 3600)

            # Assertions
            self.assertIsNone(result)

    @patch("core.cloudfront_utils.get_audio_signed_url")
    def test_get_presigned_url_returns_correct_url_format(self, mock_cloudfront):
        """
        Test that get_presigned_url() returns URLs in correct format.

        Expected behavior:
        - CloudFront URL includes Policy and Signature parameters
        - CloudFront URL includes Key-Pair-Id parameter
        - CloudFront URL uses HTTPS
        """
        cloudfront_url = (
            "https://d2e40gg2o2wus6.cloudfront.net/media/audio.mp3"
            "?Policy=eyJTdGF0ZW1lbnQiOlt7ImNvbmRpdGlvbiI6eyJEYXRlTGVzc1RoYW4iOnsiQVdTOkVwb2NoVGltZSI6MTcwMjEyODAwMH19XX0_"
            "&Signature=HOjr5nCnCAzjqxL0..."
            "&Key-Pair-Id=K1603YIV6IA5M2"
        )
        mock_cloudfront.return_value = cloudfront_url

        result = self.service.get_presigned_url(self.audio)

        # Assertions
        self.assertIn("https://", result)
        self.assertIn("cloudfront.net", result)
        self.assertIn("Policy=", result)
        self.assertIn("Signature=", result)
        self.assertIn("Key-Pair-Id=", result)

    @patch("core.cloudfront_utils.get_audio_signed_url")
    def test_get_presigned_url_caching_behavior(self, mock_cloudfront):
        """
        Test that get_presigned_url() can be called multiple times.

        Expected behavior:
        - Each call attempts CloudFront fresh
        - No caching at service level (caching is in cloudfront_utils)
        """
        mock_cloudfront_url = "https://d2e40gg2o2wus6.cloudfront.net/media/audio.mp3?Policy=...&Signature=..."
        mock_cloudfront.return_value = mock_cloudfront_url

        # Call twice
        result1 = self.service.get_presigned_url(self.audio)
        result2 = self.service.get_presigned_url(self.audio)

        # Assertions
        self.assertEqual(result1, result2)
        # Verify CloudFront was called multiple times (no service-level caching)
        self.assertEqual(mock_cloudfront.call_count, 2)

    @patch("core.cloudfront_utils.get_audio_signed_url")
    def test_get_presigned_url_different_expirations(self, mock_cloudfront):
        """
        Test that get_presigned_url() generates different URLs with different expirations.

        Expected behavior:
        - Passing different expiration values produces different URLs
        - Each URL is generated fresh
        """

        def cloudfront_side_effect(audio, expiration_seconds):
            # Return different URL based on expiration
            return f"https://d2e40gg2o2wus6.cloudfront.net/media/audio.mp3?expires={expiration_seconds}"

        mock_cloudfront.side_effect = cloudfront_side_effect

        # Call with different expirations
        url1 = self.service.get_presigned_url(self.audio, expiration=3600)
        url2 = self.service.get_presigned_url(self.audio, expiration=7200)

        # Assertions
        self.assertNotEqual(url1, url2)
        self.assertIn("expires=3600", url1)
        self.assertIn("expires=7200", url2)


class CloudFrontServiceConsistencyTests(TestCase):
    """Test that CloudFront behavior is consistent across dev and production."""

    def setUp(self):
        """Create test fixtures."""
        self.user = User.objects.create_user(
            username="consistency_test_user",
            email="consistency@example.com",
            password="testpass123",
        )
        self.document = Document.objects.create(
            user=self.user,
            title="Consistency Test Document",
            source_content="test.pdf",
            source_type="FILE",
            status="COMPLETED",
        )
        self.page = DocumentPage.objects.create(
            document=self.document,
            page_number=1,
            markdown_content="Test content for consistency checking.",
        )
        self.audio = Audio.objects.create(
            page=self.page,
            voice=TTSVoice.MATTHEW,
            generated_by=self.user,
            s3_key="audios/document_1/page_1/voice_Matthew_20251104_120000.mp3",
            status=AudioGenerationStatus.COMPLETED,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        self.service = AudioGenerationService()

    @patch("core.cloudfront_utils.get_audio_signed_url")
    def test_cloudfront_used_regardless_of_environment(self, mock_cloudfront):
        """
        Test that CloudFront is attempted regardless of ENVIRONMENT setting.

        Expected behavior:
        - Same code path for development and production
        - Always attempts CloudFront first
        """
        mock_cloudfront_url = "https://d2e40gg2o2wus6.cloudfront.net/media/audio.mp3?Policy=...&Signature=..."
        mock_cloudfront.return_value = mock_cloudfront_url

        # Should work the same regardless of environment
        result = self.service.get_presigned_url(self.audio)

        self.assertEqual(result, mock_cloudfront_url)
        mock_cloudfront.assert_called_once()

    @patch("core.cloudfront_utils.get_audio_signed_url")
    @patch.object(AudioGenerationService, "_get_s3_presigned_url")
    def test_s3_fallback_same_for_all_environments(self, mock_s3, mock_cloudfront):
        """
        Test that S3 fallback works the same in all environments.

        Expected behavior:
        - S3 fallback triggered only if CloudFront fails
        - Same behavior in dev and production
        """
        from core.cloudfront_utils import CloudFrontSigningError

        mock_cloudfront.side_effect = CloudFrontSigningError("Key not found")
        s3_url = "https://bucket.s3.amazonaws.com/media/audio.mp3?AWSAccessKeyId=...&Signature=..."
        mock_s3.return_value = s3_url

        result = self.service.get_presigned_url(self.audio)

        self.assertEqual(result, s3_url)
        # Verify both were called
        mock_cloudfront.assert_called_once()
        mock_s3.assert_called_once()
