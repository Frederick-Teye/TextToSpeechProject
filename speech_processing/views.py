from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

from document_processing.models import DocumentPage
from speech_processing.models import Audio, SiteSettings, DocumentSharing
from speech_processing.services import AudioGenerationService
from speech_processing.tasks import generate_audio_task, check_audio_generation_status
import logging

logger = logging.getLogger(__name__)


@require_http_methods(["POST"])
@login_required
def generate_audio(request, page_id):
    """
    Generate audio for a specific page.
    POST /speech/generate/<page_id>/
    Body: {"voice_id": "Joanna"}
    """
    try:
        # Parse request body
        data = json.loads(request.body)
        voice_id = data.get("voice_id")

        if not voice_id:
            return JsonResponse(
                {"success": False, "error": "Voice ID is required"}, status=400
            )

        # Get the page
        page = get_object_or_404(DocumentPage, id=page_id)

        # Check permissions and quotas
        service = AudioGenerationService()
        allowed, error_msg = service.check_generation_allowed(
            request.user, page, voice_id
        )

        if not allowed:
            return JsonResponse({"success": False, "error": error_msg}, status=403)

        # Create audio record
        audio = service.create_audio_record(page, voice_id, request.user)

        # Trigger async generation task
        generate_audio_task.delay(audio.id)

        return JsonResponse(
            {
                "success": True,
                "message": "Audio generation started",
                "audio_id": audio.id,
                "status": audio.status,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        logger.error(f"Audio generation error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred during audio generation"},
            status=500,
        )


@require_http_methods(["GET"])
@login_required
def audio_status(request, audio_id):
    """
    Check the status of audio generation.
    GET /speech/audio/<audio_id>/status/
    """
    try:
        audio = get_object_or_404(Audio, id=audio_id)

        # Check if user has access to this audio
        page = audio.page
        document = page.document

        has_access = (
            document.user == request.user
            or DocumentSharing.objects.filter(
                document=document, shared_with=request.user
            ).exists()
        )

        if not has_access:
            return JsonResponse(
                {"success": False, "error": "You don't have access to this audio"},
                status=403,
            )

        return JsonResponse(
            {
                "success": True,
                "audio_id": audio.id,
                "status": audio.status,
                "lifetime_status": audio.lifetime_status,
                "voice": audio.voice,
                "generated_by": audio.generated_by.email,
                "created_at": audio.created_at.isoformat(),
                "error_message": audio.error_message,
                "s3_url": audio.get_s3_url() if audio.status == "COMPLETED" else None,
            }
        )

    except Exception as e:
        logger.error(f"Audio status error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )


@require_http_methods(["GET"])
@login_required
def download_audio(request, audio_id):
    """
    Get a presigned URL for downloading audio.
    GET /speech/audio/<audio_id>/download/
    """
    try:
        audio = get_object_or_404(Audio, id=audio_id)

        # Check if user has access
        page = audio.page
        document = page.document

        has_access = (
            document.user == request.user
            or DocumentSharing.objects.filter(
                document=document, shared_with=request.user
            ).exists()
        )

        if not has_access:
            return JsonResponse(
                {"success": False, "error": "You don't have access to this audio"},
                status=403,
            )

        if audio.status != "COMPLETED":
            return JsonResponse(
                {"success": False, "error": "Audio is not ready for download"},
                status=400,
            )

        # Generate presigned URL
        service = AudioGenerationService()
        download_url = service.get_presigned_url(audio, expiration=3600)  # 1 hour

        if not download_url:
            return JsonResponse(
                {"success": False, "error": "Failed to generate download URL"},
                status=500,
            )

        # Update last_played_at (since download implies playing)
        from django.utils import timezone

        audio.last_played_at = timezone.now()
        audio.save()

        return JsonResponse(
            {
                "success": True,
                "download_url": download_url,
                "voice": audio.voice,
                "expires_in": 3600,
            }
        )

    except Exception as e:
        logger.error(f"Audio download error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )


@require_http_methods(["POST"])
@login_required
def play_audio(request, audio_id):
    """
    Mark audio as played (update last_played_at).
    POST /speech/audio/<audio_id>/play/
    """
    try:
        audio = get_object_or_404(Audio, id=audio_id)

        # Check if user has access
        page = audio.page
        document = page.document

        has_access = (
            document.user == request.user
            or DocumentSharing.objects.filter(
                document=document, shared_with=request.user
            ).exists()
        )

        if not has_access:
            return JsonResponse(
                {"success": False, "error": "You don't have access to this audio"},
                status=403,
            )

        # Update last_played_at
        from django.utils import timezone

        audio.last_played_at = timezone.now()
        audio.save()

        return JsonResponse({"success": True, "message": "Play timestamp updated"})

    except Exception as e:
        logger.error(f"Audio play error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )


@require_http_methods(["DELETE", "POST"])
@login_required
def delete_audio(request, audio_id):
    """
    Delete an audio file (soft delete).
    Only document owner can delete.
    DELETE /speech/audio/<audio_id>/delete/ or POST with _method=DELETE
    """
    try:
        audio = get_object_or_404(Audio, id=audio_id)

        # Check if user is the document owner
        document = audio.page.document

        if document.user != request.user:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Only the document owner can delete audio files",
                },
                status=403,
            )

        # Soft delete
        from django.utils import timezone
        from speech_processing.models import AudioLifetimeStatus

        audio.lifetime_status = AudioLifetimeStatus.DELETED
        audio.deleted_at = timezone.now()
        audio.save()

        return JsonResponse({"success": True, "message": "Audio deleted successfully"})

    except Exception as e:
        logger.error(f"Audio delete error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )


@require_http_methods(["GET"])
@login_required
def page_audios(request, page_id):
    """
    Get all active audios for a specific page.
    GET /speech/page/<page_id>/audios/
    """
    try:
        page = get_object_or_404(DocumentPage, id=page_id)
        document = page.document

        # Check if user has access
        has_access = (
            document.user == request.user
            or DocumentSharing.objects.filter(
                document=document, shared_with=request.user
            ).exists()
        )

        if not has_access:
            return JsonResponse(
                {"success": False, "error": "You don't have access to this page"},
                status=403,
            )

        # Get active audios
        from speech_processing.models import AudioLifetimeStatus

        audios = Audio.objects.filter(
            page=page, lifetime_status=AudioLifetimeStatus.ACTIVE
        ).select_related("generated_by")

        # Get site settings for quota
        settings_obj = SiteSettings.get_settings()

        # Calculate available voices
        used_voices = list(audios.values_list("voice", flat=True))
        from speech_processing.models import TTSVoice

        all_voices = [v.value for v in TTSVoice]
        available_voices = [v for v in all_voices if v not in used_voices]

        # Serialize audios
        audios_data = []
        for audio in audios:
            audios_data.append(
                {
                    "id": audio.id,
                    "voice": audio.voice,
                    "status": audio.status,
                    "generated_by": audio.generated_by.email,
                    "created_at": audio.created_at.isoformat(),
                    "last_played_at": (
                        audio.last_played_at.isoformat()
                        if audio.last_played_at
                        else None
                    ),
                    "s3_url": (
                        audio.get_s3_url() if audio.status == "COMPLETED" else None
                    ),
                    "days_until_expiry": audio.days_until_expiry(),
                    "error_message": audio.error_message,
                }
            )

        return JsonResponse(
            {
                "success": True,
                "audios": audios_data,
                "quota": {
                    "used": audios.count(),
                    "max": settings_obj.max_audios_per_page,
                    "available": settings_obj.max_audios_per_page - audios.count(),
                },
                "voices": {"used": used_voices, "available": available_voices},
                "is_owner": document.user == request.user,
            }
        )

    except Exception as e:
        logger.error(f"Page audios error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )
