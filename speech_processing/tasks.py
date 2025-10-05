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


@shared_task
def check_expired_audios():
    """
    Check for expired and expiring audios.
    Should be run daily via Celery Beat.

    Actions performed:
    1. Send warning emails to users for audios expiring within 30 days
    2. Auto-delete expired audios (6 months after last_played_at or created_at)
    3. Log all actions

    Returns:
        dict with success status and statistics
    """
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.conf import settings
    from django.utils import timezone
    from speech_processing.models import Audio, AudioLifetimeStatus
    import boto3

    try:
        logger.info("Starting expired audios check task")

        # Get active audios only
        active_audios = Audio.objects.filter(
            lifetime_status=AudioLifetimeStatus.ACTIVE,
            status=AudioGenerationStatus.COMPLETED,
        ).select_related("generated_by", "page__document")

        warnings_sent = 0
        audios_deleted = 0
        errors = []

        # Track users who need warnings (to send one email per user)
        users_needing_warnings = {}

        # Check each audio
        for audio in active_audios:
            try:
                # Check if expired
                if audio.is_expired():
                    # Delete from S3
                    try:
                        s3_client = boto3.client(
                            "s3",
                            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
                            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
                            region_name=settings.AWS_S3_REGION_NAME,
                        )
                        s3_client.delete_object(
                            Bucket=settings.AWS_STORAGE_BUCKET_NAME, Key=audio.s3_key
                        )
                        logger.info(f"Deleted S3 object: {audio.s3_key}")
                    except Exception as s3_error:
                        logger.error(
                            f"Failed to delete S3 object {audio.s3_key}: {str(s3_error)}"
                        )
                        errors.append(
                            {
                                "audio_id": audio.id,
                                "action": "s3_delete",
                                "error": str(s3_error),
                            }
                        )

                    # Mark audio as expired
                    audio.lifetime_status = AudioLifetimeStatus.EXPIRED
                    audio.deleted_at = timezone.now()
                    audio.save()

                    audios_deleted += 1
                    logger.info(
                        f"Marked audio {audio.id} as expired (voice: {audio.voice}, user: {audio.generated_by.email})"
                    )

                # Check if needs warning (30 days before expiry)
                elif audio.needs_expiry_warning():
                    user_email = audio.generated_by.email
                    if user_email not in users_needing_warnings:
                        users_needing_warnings[user_email] = {
                            "user": audio.generated_by,
                            "audios": [],
                        }
                    users_needing_warnings[user_email]["audios"].append(audio)

            except Exception as audio_error:
                logger.error(f"Error processing audio {audio.id}: {str(audio_error)}")
                errors.append(
                    {
                        "audio_id": audio.id,
                        "action": "process",
                        "error": str(audio_error),
                    }
                )

        # Send warning emails (one per user with all their expiring audios)
        for user_email, data in users_needing_warnings.items():
            try:
                user = data["user"]
                audios = data["audios"]

                # Prepare email context
                context = {
                    "user": user,
                    "audios": audios,
                    "expiry_days": 30,
                }

                # Render email templates
                html_message = render_to_string(
                    "speech_processing/emails/expiry_warning.html", context
                )
                plain_message = render_to_string(
                    "speech_processing/emails/expiry_warning.txt", context
                )

                # Send email
                send_mail(
                    subject="Audio Files Expiring Soon - Action Required",
                    message=plain_message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user_email],
                    html_message=html_message,
                    fail_silently=False,
                )

                warnings_sent += 1
                logger.info(
                    f"Sent expiry warning email to {user_email} for {len(audios)} audios"
                )

            except Exception as email_error:
                logger.error(
                    f"Failed to send expiry warning to {user_email}: {str(email_error)}"
                )
                errors.append(
                    {
                        "user_email": user_email,
                        "action": "send_email",
                        "error": str(email_error),
                    }
                )

        # Prepare result
        result = {
            "success": True,
            "message": f"Expiry check completed: {audios_deleted} deleted, {warnings_sent} warnings sent",
            "audios_deleted": audios_deleted,
            "warnings_sent": warnings_sent,
            "total_checked": active_audios.count(),
            "timestamp": timezone.now().isoformat(),
        }

        if errors:
            result["errors"] = errors
            result["error_count"] = len(errors)

        logger.info(
            f"Expiry check completed: {audios_deleted} deleted, {warnings_sent} warnings sent, {len(errors)} errors"
        )

        return result

    except Exception as e:
        logger.error(f"Fatal error in expiry check task: {str(e)}")
        return {
            "success": False,
            "message": f"Fatal error in expiry check: {str(e)}",
            "error": str(e),
        }
