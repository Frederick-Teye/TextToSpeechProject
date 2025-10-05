"""
Audio generation service using AWS Polly.
Handles TTS generation, chunking, merging, and S3 upload.
"""

import boto3
import logging
from io import BytesIO
from datetime import datetime
from django.conf import settings
from django.core.exceptions import ValidationError
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
    """Custom exception for audio generation errors."""

    pass


class PollyService:
    """Service for interacting with AWS Polly for TTS generation."""

    # Polly has a limit of 3000 characters per request
    MAX_CHARS_PER_REQUEST = 3000

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

    def chunk_text(self, text):
        """
        Split text into chunks that fit within Polly's character limit.
        Tries to split on sentence boundaries for natural audio.
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

    def synthesize_speech(self, text, voice_id):
        """
        Call Polly to synthesize speech for a single text chunk.
        Returns audio stream as bytes.
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

        except Exception as e:
            logger.error(f"Polly synthesis error: {str(e)}")
            raise AudioGenerationError(f"Failed to synthesize speech: {str(e)}")

    def merge_audio_chunks(self, audio_chunks):
        """
        Merge multiple audio chunks into a single audio file.
        Uses pydub for audio manipulation.
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

    def upload_to_s3(self, audio_bytes, s3_key):
        """
        Upload audio bytes to S3.
        Returns the S3 key.
        """
        try:
            self.s3_client.put_object(
                Bucket=settings.AWS_STORAGE_BUCKET_NAME,
                Key=s3_key,
                Body=audio_bytes,
                ContentType="audio/mpeg",
                CacheControl="public, max-age=31536000",  # Cache for 1 year
            )
            logger.info(f"Successfully uploaded audio to S3: {s3_key}")
            return s3_key

        except Exception as e:
            logger.error(f"S3 upload error: {str(e)}")
            raise AudioGenerationError(f"Failed to upload to S3: {str(e)}")

    def generate_s3_key(self, document_id, page_number, voice_id):
        """
        Generate a unique S3 key for the audio file.
        Format: audios/document_{id}/page_{num}/voice_{voice}_{timestamp}.mp3
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"audios/document_{document_id}/page_{page_number}/voice_{voice_id}_{timestamp}.mp3"

    def generate_audio(self, text, voice_id, document_id, page_number):
        """
        Full audio generation pipeline:
        1. Chunk text
        2. Synthesize each chunk with Polly
        3. Merge chunks
        4. Upload to S3
        5. Return S3 key
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

    def check_generation_allowed(self, user, page, voice_id):
        """
        Check if audio generation is allowed.
        Returns (allowed, error_message).
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

    def create_audio_record(self, page, voice_id, user):
        """
        Create an Audio record in the database with PENDING status.
        Returns the Audio instance.
        """
        audio = Audio.objects.create(
            page=page,
            voice=voice_id,
            generated_by=user,
            s3_key="",  # Will be updated after generation
            status=AudioGenerationStatus.PENDING,
            lifetime_status=AudioLifetimeStatus.ACTIVE,
        )
        return audio

    def generate_audio_for_page(self, page, voice_id, user):
        """
        Generate audio for a page with the specified voice.
        This is the main entry point for audio generation.

        Returns: (success, audio_or_error_message)
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

    def get_presigned_url(self, audio, expiration=3600):
        """
        Generate a presigned URL for downloading an audio file.
        URL expires after specified seconds (default: 1 hour).
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
            return url
        except Exception as e:
            logger.error(f"Failed to generate presigned URL: {str(e)}")
            return None
