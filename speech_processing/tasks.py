"""
Celery tasks for audio generation and processing.
"""

from celery import shared_task
from django.contrib.auth import get_user_model
from speech_processing.services import AudioGenerationService
from speech_processing.models import Audio, AudioGenerationStatus
from speech_processing.logging_utils import log_generation_complete
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

        # Log successful generation
        log_generation_complete(audio=audio, status=AudioGenerationStatus.COMPLETED)

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

            # Log failed generation
            log_generation_complete(
                audio=audio, status=AudioGenerationStatus.FAILED, error_message=str(e)
            )
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


@shared_task
def export_audit_logs_to_s3():
    """
    Export audit logs to S3 in JSON Lines format.
    Should be run monthly via Celery Beat.

    Exports logs from the previous month and stores them in S3
    at: audit-logs/YYYY/MM/audit-logs-YYYY-MM.jsonl

    Returns:
        dict with success status and details
    """
    import json
    import boto3
    from datetime import datetime, timedelta
    from django.utils import timezone
    from django.conf import settings
    from speech_processing.models import AudioAccessLog
    from io import StringIO

    try:
        # Calculate date range for previous month
        today = timezone.now()
        first_day_this_month = today.replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )
        last_day_prev_month = first_day_this_month - timedelta(days=1)
        first_day_prev_month = last_day_prev_month.replace(day=1)

        # Format for S3 key
        year = last_day_prev_month.year
        month = last_day_prev_month.month

        logger.info(f"Exporting audit logs for {year}-{month:02d}")

        # Query logs for the previous month
        logs = (
            AudioAccessLog.objects.filter(
                timestamp__gte=first_day_prev_month, timestamp__lt=first_day_this_month
            )
            .select_related("user", "audio", "document")
            .order_by("timestamp")
        )

        log_count = logs.count()

        if log_count == 0:
            logger.info(f"No audit logs found for {year}-{month:02d}")
            return {
                "success": True,
                "message": f"No audit logs found for {year}-{month:02d}",
                "log_count": 0,
            }

        # Convert logs to JSON Lines format
        jsonl_data = StringIO()

        for log in logs:
            log_dict = {
                "timestamp": log.timestamp.isoformat(),
                "user_id": log.user.id,
                "user_email": log.user.email,
                "action": log.action,
                "status": log.status,
                "audio_id": log.audio.id if log.audio else None,
                "audio_voice": log.audio.voice if log.audio else None,
                "document_id": log.document.id if log.document else None,
                "document_title": log.document.title if log.document else None,
                "ip_address": log.ip_address,
                "user_agent": log.user_agent,
                "error_message": log.error_message,
            }
            jsonl_data.write(json.dumps(log_dict) + "\n")

        # Upload to S3
        s3_client = boto3.client(
            "s3",
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_S3_REGION_NAME,
        )

        s3_key = f"audit-logs/{year}/{month:02d}/audit-logs-{year}-{month:02d}.jsonl"
        bucket_name = settings.AWS_STORAGE_BUCKET_NAME

        s3_client.put_object(
            Bucket=bucket_name,
            Key=s3_key,
            Body=jsonl_data.getvalue().encode("utf-8"),
            ContentType="application/x-ndjson",
            ServerSideEncryption="AES256",
        )

        logger.info(
            f"Successfully exported {log_count} audit logs to s3://{bucket_name}/{s3_key}"
        )

        return {
            "success": True,
            "message": f"Exported {log_count} audit logs for {year}-{month:02d}",
            "log_count": log_count,
            "s3_key": s3_key,
            "month": f"{year}-{month:02d}",
        }

    except Exception as e:
        logger.error(f"Failed to export audit logs: {str(e)}")
        return {
            "success": False,
            "message": f"Failed to export audit logs: {str(e)}",
            "error": str(e),
        }
