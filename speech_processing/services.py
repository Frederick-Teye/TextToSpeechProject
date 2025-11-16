"""
Audio generation service using AWS Polly.
Handles TTS generation, chunking, merging, and S3 upload.
"""

import boto3
import botocore.exceptions
import logging
from io import BytesIO
from datetime import datetime
from typing import Tuple, Optional
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from pydub import AudioSegment

from speech_processing.models import (
    Audio,
    AudioGenerationStatus,
    AudioLifetimeStatus,
    SiteSettings,
    TTSVoice,
)

logger = logging.getLogger(__name__)


class AudioGenerationError(Exception):
    """
    Custom exception for audio generation errors.

    This exception is used for all user-facing audio generation failures
    and includes a message safe to show to users (no credentials, paths, or details).
    """

    pass


class PollyService:
    """Service for interacting with AWS Polly for TTS generation."""

    # Use settings constant for Polly character limit
    MAX_CHARS_PER_REQUEST = settings.POLLY_MAX_CHARS_PER_REQUEST

    def __init__(self):
        """Initialize Polly and S3 clients."""
        self.polly_client = boto3.client(
            "polly",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )

    def chunk_text(self, text: str) -> list[str]:
        """
        Split text into chunks that fit within Polly's character limit.
        Tries to split on sentence boundaries for natural audio.

        Args:
            text: The text to chunk

        Returns:
            List of text chunks, each <= MAX_CHARS_PER_REQUEST characters

        Raises:
            AudioGenerationError: If text cannot be chunked properly
        """
        if len(text) <= self.MAX_CHARS_PER_REQUEST:
            return [text]

        chunks = []
        current_chunk = ""

        # Split on sentence boundaries (., !, ?)
        sentences = text.replace("!", ".").replace("?", ".").split(".")

        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue

            # If single sentence is too long, split on spaces
            if len(sentence) > self.MAX_CHARS_PER_REQUEST:
                words = sentence.split()
                temp_chunk = ""
                for word in words:
                    if len(temp_chunk) + len(word) + 1 <= self.MAX_CHARS_PER_REQUEST:
                        temp_chunk += word + " "
                    else:
                        if temp_chunk:
                            chunks.append(temp_chunk.strip())
                        temp_chunk = word + " "
                if temp_chunk:
                    chunks.append(temp_chunk.strip())
            else:
                # Add sentence to current chunk if it fits
                if len(current_chunk) + len(sentence) + 2 <= self.MAX_CHARS_PER_REQUEST:
                    current_chunk += sentence + ". "
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = sentence + ". "

        if current_chunk:
            chunks.append(current_chunk.strip())

        return chunks if chunks else [text[: self.MAX_CHARS_PER_REQUEST]]

    def synthesize_speech(self, text: str, voice_id: str) -> bytes:
        """
        Call Polly to synthesize speech for a single text chunk.

        This method handles various AWS Polly error scenarios:
        - ThrottlingException: AWS service is overloaded
        - InvalidParameterValue: Voice ID or other parameter is invalid
        - ServiceUnavailable: AWS service is down
        - ConnectionError: Network issue
        - NoCredentialsError: AWS credentials not found

        Args:
            text: Text to synthesize (max 3000 chars)
            voice_id: Valid Polly voice ID (e.g., "Joanna")

        Returns:
            Bytes containing MP3 audio data

        Raises:
            AudioGenerationError: With user-friendly message describing the error

        """
        try:
            response = self.polly_client.synthesize_speech(
                Text=text,
                OutputFormat="mp3",
                VoiceId=voice_id,
                Engine="standard",  # Use 'neural' for higher quality if needed
                LanguageCode="en-US",
            )

            # Read the audio stream
            if "AudioStream" in response:
                return response["AudioStream"].read()
            else:
                raise AudioGenerationError("No audio stream in Polly response")

        except botocore.exceptions.ClientError as e:
            # AWS service returned an error response
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]

            if error_code == "ThrottlingException":
                logger.warning(f"Polly throttled: {error_message}")
                raise AudioGenerationError(
                    "AWS service is busy. Please try again in a moment."
                )
            elif error_code == "InvalidParameterValue":
                logger.warning(f"Invalid Polly parameter: {error_message}")
                raise AudioGenerationError(
                    f"Invalid voice or text format. Please try a different voice."
                )
            elif error_code == "ServiceUnavailable":
                logger.warning(f"Polly service unavailable: {error_message}")
                raise AudioGenerationError(
                    "Audio service is temporarily unavailable. Please try again later."
                )
            elif error_code == "AccessDenied":
                logger.error(f"Access denied to Polly: {error_message}")
                raise AudioGenerationError(
                    "System error: AWS access issue. Please contact support."
                )
            else:
                logger.error(f"Polly AWS error ({error_code}): {error_message}")
                raise AudioGenerationError(
                    f"Audio generation failed. Please try again later."
                )

        except botocore.exceptions.ConnectionError as e:
            logger.error(f"Connection error to Polly: {str(e)}")
            raise AudioGenerationError(
                "Network error connecting to audio service. Please try again."
            )

        except botocore.exceptions.NoCredentialsError:
            logger.critical("AWS credentials not configured for Polly")
            raise AudioGenerationError(
                "System configuration error. Please contact support."
            )

        except Exception as e:
            # Unexpected error - log for debugging but don't expose details
            logger.exception(f"Unexpected error in Polly synthesis: {str(e)}")
            raise AudioGenerationError(
                "An unexpected error occurred. Please try again later."
            )

    def merge_audio_chunks(self, audio_chunks: list[bytes]) -> bytes:
        """
        Merge multiple audio chunks into a single audio file.
        Uses pydub for audio manipulation.

        Args:
            audio_chunks: List of MP3 audio data as bytes

        Returns:
            Merged MP3 audio data as bytes

        Raises:
            AudioGenerationError: If chunks cannot be merged or are empty
        """
        if not audio_chunks:
            raise AudioGenerationError("No audio chunks to merge")

        if len(audio_chunks) == 1:
            return audio_chunks[0]

        try:
            # Load first chunk
            combined = AudioSegment.from_mp3(BytesIO(audio_chunks[0]))

            # Append remaining chunks
            for chunk_bytes in audio_chunks[1:]:
                chunk_audio = AudioSegment.from_mp3(BytesIO(chunk_bytes))
                combined += chunk_audio

            # Export to bytes
            output = BytesIO()
            combined.export(output, format="mp3", bitrate="128k")
            output.seek(0)
            return output.read()

        except Exception as e:
            logger.error(f"Audio merging error: {str(e)}")
            raise AudioGenerationError(f"Failed to merge audio chunks: {str(e)}")

    def upload_to_s3(self, audio_bytes: bytes, s3_key: str) -> str:
        """
        Upload audio bytes to S3.

        Handles S3-specific errors:
        - NoCredentialsError: AWS credentials not found
        - ClientError: S3 service errors (access denied, bucket not found, etc.)
        - ConnectionError: Network issues

        Args:
            audio_bytes: MP3 audio data as bytes
            s3_key: S3 object key/path for the audio file

        Returns:
            The S3 key if upload successful

        Raises:
            AudioGenerationError: With user-friendly error message
        """
        try:
            self.s3_client.put_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=s3_key,
                Body=audio_bytes,
                ContentType="audio/mpeg",
                CacheControl=f"public, max-age={settings.POLLY_AUDIO_CACHE_SECONDS}",
            )
            logger.info(f"Successfully uploaded audio to S3: {s3_key}")
            return s3_key

        except botocore.exceptions.ClientError as e:
            error_code = e.response["Error"]["Code"]
            error_message = e.response["Error"]["Message"]

            if error_code == "NoSuchBucket":
                logger.critical(
                    f"S3 bucket not found: {settings.AWS_STORAGE_BUCKET_NAME}"
                )
                raise AudioGenerationError(
                    "System error: Storage bucket not configured. Contact support."
                )
            elif error_code == "AccessDenied":
                logger.critical(
                    f"Access denied to S3 bucket: {settings.AWS_STORAGE_BUCKET_NAME}"
                )
                raise AudioGenerationError(
                    "System error: Cannot access storage. Contact support."
                )
            else:
                logger.error(f"S3 error ({error_code}): {error_message}")
                raise AudioGenerationError(
                    "Failed to save audio file. Please try again later."
                )

        except botocore.exceptions.ConnectionError as e:
            logger.error(f"Connection error to S3: {str(e)}")
            raise AudioGenerationError(
                "Network error accessing storage. Please try again."
            )

        except botocore.exceptions.NoCredentialsError:
            logger.critical("AWS credentials not configured for S3")
            raise AudioGenerationError(
                "System configuration error. Please contact support."
            )

        except Exception as e:
            logger.exception(f"Unexpected error uploading to S3: {str(e)}")
            raise AudioGenerationError(
                "An unexpected error occurred while saving audio. Try again later."
            )

    def generate_s3_key(self, document_id: int, page_number: int, voice_id: str) -> str:
        """
        Generate a unique S3 key for the audio file.

        Args:
            document_id: ID of the document
            page_number: Page number within the document
            voice_id: Polly voice identifier (e.g., 'Joanna')

        Returns:
            S3 key in format: audios/document_{id}/page_{num}/voice_{voice}_{timestamp}.mp3
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"audios/document_{document_id}/page_{page_number}/voice_{voice_id}_{timestamp}.mp3"

    def generate_audio(
        self, text: str, voice_id: str, document_id: int, page_number: int
    ) -> str:
        """
        Full audio generation pipeline:
        1. Chunk text
        2. Synthesize each chunk with Polly
        3. Merge chunks
        4. Upload to S3
        5. Return S3 key

        Args:
            text: The text content to convert to audio
            voice_id: Polly voice identifier
            document_id: ID of the document
            page_number: Page number within the document

        Returns:
            S3 key of the generated audio file

        Raises:
            AudioGenerationError: If any step in the pipeline fails
        """
        logger.info(
            f"Starting audio generation for document {document_id}, page {page_number}, voice {voice_id}"
        )

        # Validate voice
        if voice_id not in [v.value for v in TTSVoice]:
            raise AudioGenerationError(f"Invalid voice: {voice_id}")

        # Validate text
        if not text or not text.strip():
            raise AudioGenerationError("Text cannot be empty")

        try:
            # Step 1: Chunk text
            text_chunks = self.chunk_text(text)
            logger.info(f"Split text into {len(text_chunks)} chunks")

            # Step 2: Synthesize each chunk
            audio_chunks = []
            for i, chunk in enumerate(text_chunks):
                logger.info(f"Synthesizing chunk {i+1}/{len(text_chunks)}")
                audio_bytes = self.synthesize_speech(chunk, voice_id)
                audio_chunks.append(audio_bytes)

            # Step 3: Merge chunks if multiple
            if len(audio_chunks) > 1:
                logger.info(f"Merging {len(audio_chunks)} audio chunks")
                final_audio = self.merge_audio_chunks(audio_chunks)
            else:
                final_audio = audio_chunks[0]

            # Step 4: Upload to S3
            s3_key = self.generate_s3_key(document_id, page_number, voice_id)
            self.upload_to_s3(final_audio, s3_key)

            logger.info(f"Audio generation complete: {s3_key}")
            return s3_key

        except AudioGenerationError:
            raise
        except Exception as e:
            logger.error(f"Unexpected error during audio generation: {str(e)}")
            raise AudioGenerationError(f"Audio generation failed: {str(e)}")


class AudioGenerationService:
    """
    High-level service for audio generation with business logic.
    Handles permissions, quotas, and database operations.
    """

    def __init__(self):
        self.polly_service = PollyService()

    def check_generation_allowed(
        self, user, page, voice_id: str
    ) -> tuple[bool, Optional[str]]:
        """
        Check if audio generation is allowed.

        Args:
            user: User attempting to generate audio
            page: DocumentPage instance
            voice_id: Polly voice identifier

        Returns:
            Tuple of (allowed: bool, error_message: Optional[str])
            If allowed=True, error_message will be None
            If allowed=False, error_message contains reason
        """
        # Check global settings
        settings_obj = SiteSettings.get_settings()
        if not settings_obj.audio_generation_enabled:
            return False, "Audio generation is currently disabled by administrators."

        # Check lifetime quota
        total_audios = Audio.objects.filter(page=page).count()
        if total_audios >= settings_obj.max_audios_per_page:
            return (
                False,
                f"Maximum {settings_obj.max_audios_per_page} audios per page reached (lifetime quota).",
            )

        # Check voice uniqueness
        existing_voice = Audio.objects.filter(
            page=page, voice=voice_id, lifetime_status=AudioLifetimeStatus.ACTIVE
        ).exists()
        if existing_voice:
            return (
                False,
                f"Voice {voice_id} is already used for this page. Please choose a different voice or delete the existing audio.",
            )

        # Check user permissions
        document = page.document
        if document.user == user:
            # Owner can always generate
            return True, None

        # Check if user has sharing permission
        from speech_processing.models import DocumentSharing

        try:
            sharing = DocumentSharing.objects.get(document=document, shared_with=user)
            if not sharing.can_generate_audio():
                return (
                    False,
                    "You don't have permission to generate audio for this document.",
                )
            return True, None
        except DocumentSharing.DoesNotExist:
            return False, "You don't have access to this document."

    def create_audio_record(self, page, voice_id: str, user) -> "Audio":
        """
        Create an Audio record in the database with PENDING status.
        Uses database-level locking to prevent race conditions where multiple
        requests try to create the same voice for the page.

        Args:
            page: DocumentPage instance
            voice_id: Polly voice identifier
            user: User creating the audio

        Returns:
            Audio instance with PENDING status

        Raises:
            AudioGenerationError: If voice already exists (duplicate detected)
                                or database error occurs.
        """
        try:
            with transaction.atomic():
                # Lock the page to prevent concurrent voice creation
                # This uses SELECT FOR UPDATE at the database level
                page_locked = type(page).objects.select_for_update().get(pk=page.pk)

                # Check one more time if voice already exists (double-check pattern)
                # This is our race condition prevention - check AFTER locking
                existing = Audio.objects.filter(
                    page=page_locked,
                    voice=voice_id,
                    lifetime_status=AudioLifetimeStatus.ACTIVE,
                ).exists()

                if existing:
                    raise AudioGenerationError(
                        f"Voice {voice_id} is already being used for this page. "
                        f"Please refresh and try again."
                    )

                # Now safe to create - we hold the lock
                audio = Audio.objects.create(
                    page=page_locked,
                    voice=voice_id,
                    generated_by=user,
                    s3_key="",  # Will be updated after generation
                    status=AudioGenerationStatus.PENDING,
                    lifetime_status=AudioLifetimeStatus.ACTIVE,
                )
                return audio

        except IntegrityError as e:
            # Database unique constraint was violated
            # This shouldn't happen due to locking, but handle it just in case
            logger.error(f"Integrity error creating audio record: {str(e)}")
            raise AudioGenerationError(
                "Voice already used for this page. Please try a different voice."
            )
        except AudioGenerationError:
            # Re-raise our custom errors
            raise
        except Exception as e:
            # Catch any other database or unexpected errors
            logger.error(f"Error creating audio record: {str(e)}")
            raise AudioGenerationError(f"Failed to create audio record: {str(e)}")

    def generate_audio_for_page(self, page, voice_id: str, user) -> tuple[bool, any]:
        """
        Generate audio for a page with the specified voice.
        This is the main entry point for audio generation.

        Args:
            page: DocumentPage instance
            voice_id: Polly voice identifier
            user: User requesting audio generation

        Returns:
            Tuple of (success: bool, result: Audio or str)
            If success=True, result is the Audio instance
            If success=False, result is an error message string
        """
        # Check if generation is allowed
        allowed, error_msg = self.check_generation_allowed(user, page, voice_id)
        if not allowed:
            logger.warning(
                f"Audio generation blocked for user {user.id}, page {page.id}: {error_msg}"
            )
            return False, error_msg

        # Create audio record
        audio = self.create_audio_record(page, voice_id, user)

        try:
            # Update status to GENERATING
            audio.status = AudioGenerationStatus.GENERATING
            audio.save()

            # Generate audio
            s3_key = self.polly_service.generate_audio(
                text=page.markdown_content,
                voice_id=voice_id,
                document_id=page.document.id,
                page_number=page.page_number,
            )

            # Update audio record with S3 key and COMPLETED status
            audio.s3_key = s3_key
            audio.status = AudioGenerationStatus.COMPLETED
            audio.save()

            logger.info(f"Audio generated successfully: {audio.id}")
            return True, audio

        except AudioGenerationError as e:
            # Mark as FAILED
            audio.status = AudioGenerationStatus.FAILED
            audio.error_message = str(e)
            audio.save()
            logger.error(f"Audio generation failed: {str(e)}")
            return False, str(e)
        except Exception as e:
            # Unexpected error
            audio.status = AudioGenerationStatus.FAILED
            audio.error_message = f"Unexpected error: {str(e)}"
            audio.save()
            logger.error(f"Unexpected error during audio generation: {str(e)}")
            return False, "An unexpected error occurred during audio generation."

    def get_presigned_url(
        self, audio: "Audio", expiration: int = None
    ) -> Optional[str]:
        """
        Generate a presigned URL for downloading an audio file.

        Intelligently handles both new CloudFront-signed URLs and legacy S3 URLs:

        For NEW audio files (post-CloudFront implementation):
        - Uses CloudFront signed URLs for both development and production
        - Provides: time-limited access, cryptographic signing (RSA-SHA1),
          global CDN distribution, better caching and performance

        For OLD audio files (pre-CloudFront implementation):
        - Falls back to S3 presigned URLs directly (maintains compatibility)
        - Existing audio files continue to work without re-generation

        This ensures backward compatibility while enabling new features:
        - Time-limited access (default: 1 hour)
        - Reduced S3 request load for new files
        - IP restriction capability (optional)
        - Seamless migration path for users

        Args:
            audio: Audio instance
            expiration: URL expiration time in seconds (default: configured AUDIO_PRESIGNED_URL_EXPIRATION_SECONDS)

        Returns:
            Signed CloudFront URL string (new files), S3 presigned URL (old/fallback), or None if all fail
        """
        if expiration is None:
            expiration = settings.AUDIO_PRESIGNED_URL_EXPIRATION_SECONDS

        try:
            # Always try CloudFront signed URLs first (for new audio files)
            from core.cloudfront_utils import (
                get_audio_signed_url,
                CloudFrontSigningError,
            )

            try:
                logger.debug(f"Generating CloudFront signed URL for audio {audio.id}")
                return get_audio_signed_url(audio, expiration_seconds=expiration)
            except CloudFrontSigningError as e:
                logger.warning(
                    f"CloudFront signing failed for audio {audio.id}: {str(e)}"
                )
                # Fallback to direct S3 presigned URL
                # This handles:
                # 1. Old audio files (pre-CloudFront implementation)
                # 2. CloudFront configuration issues
                # 3. Missing/invalid private keys
                logger.info(f"Falling back to S3 presigned URL for audio {audio.id}")
                return self._get_s3_presigned_url(audio, expiration)

        except Exception as e:
            logger.error(f"Failed to generate download URL for audio: {str(e)}")
            return None

    def _get_s3_presigned_url(self, audio: "Audio", expiration: int) -> Optional[str]:
        """
        Generate a direct S3 presigned URL for downloading an audio file.

        This is used as a fallback in production or for development environments.
        S3 presigned URLs provide direct access to S3 objects without requiring
        AWS credentials, but are less secure than CloudFront signed URLs.

        Args:
            audio: Audio instance
            expiration: URL expiration time in seconds

        Returns:
            S3 presigned URL string, or None if generation fails
        """
        try:
            url = self.polly_service.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.AWS_STORAGE_BUCKET_NAME,
                    "Key": audio.s3_key,
                },
                ExpiresIn=expiration,
            )
            logger.debug(f"Generated S3 presigned URL for audio {audio.id}")
            return url
        except Exception as e:
            logger.error(f"Failed to generate S3 presigned URL: {str(e)}")
            return None
