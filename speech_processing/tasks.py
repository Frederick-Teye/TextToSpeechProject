"""
Celery tasks for audio generation and processing.
"""

from celery import shared_task
from django.contrib.auth import get_user_model
from speech_processing.services import AudioGenerationService
from speech_processing.models import Audio, AudioGenerationStatus
import logging

logger = logging.getLogger(__name__)
User = get_user_model()


@shared_task(bind=True, max_retries=3)
def generate_audio_task(self, audio_id):
    """
    Async task to generate audio using AWS Polly.

    Args:
        audio_id: ID of the Audio model instance

    Returns:
        dict with 'success' and 'message' keys
    """
    try:
        # Get the audio record
        audio = Audio.objects.get(id=audio_id)

        # Update status to GENERATING
        audio.status = AudioGenerationStatus.GENERATING
        audio.save()

        logger.info(f"Starting audio generation task for audio {audio_id}")

        # Initialize service
        service = AudioGenerationService()

        # Generate audio
        s3_key = service.polly_service.generate_audio(
            text=audio.page.markdown_content,
            voice_id=audio.voice,
            document_id=audio.page.document.id,
            page_number=audio.page.page_number,
        )

        # Update audio record
        audio.s3_key = s3_key
        audio.status = AudioGenerationStatus.COMPLETED
        audio.save()

        logger.info(f"Audio generation task completed for audio {audio_id}")

        return {
            "success": True,
            "message": f"Audio generated successfully: {s3_key}",
            "audio_id": audio_id,
        }

    except Audio.DoesNotExist:
        logger.error(f"Audio {audio_id} not found")
        return {"success": False, "message": f"Audio {audio_id} not found"}

    except Exception as e:
        logger.error(f"Audio generation task failed for audio {audio_id}: {str(e)}")

        # Update audio status to FAILED
        try:
            audio = Audio.objects.get(id=audio_id)
            audio.status = AudioGenerationStatus.FAILED
            audio.error_message = str(e)
            audio.save()
        except Audio.DoesNotExist:
            pass

        # Retry the task if retries available
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60 * (2**self.request.retries))

        return {"success": False, "message": str(e), "audio_id": audio_id}


@shared_task
def check_audio_generation_status(audio_id):
    """
    Check the status of audio generation.
    Used for polling from frontend.

    Args:
        audio_id: ID of the Audio model instance

    Returns:
        dict with status information
    """
    try:
        audio = Audio.objects.get(id=audio_id)

        return {
            "audio_id": audio_id,
            "status": audio.status,
            "lifetime_status": audio.lifetime_status,
            "voice": audio.voice,
            "error_message": audio.error_message,
            "s3_url": (
                audio.get_s3_url()
                if audio.status == AudioGenerationStatus.COMPLETED
                else None
            ),
        }

    except Audio.DoesNotExist:
        return {
            "audio_id": audio_id,
            "status": "NOT_FOUND",
            "error_message": "Audio not found",
        }
