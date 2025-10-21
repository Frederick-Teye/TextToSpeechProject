from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
import json

from document_processing.models import DocumentPage
from speech_processing.models import Audio, SiteSettings, DocumentSharing, AudioAction
from speech_processing.services import AudioGenerationService
from speech_processing.tasks import generate_audio_task, check_audio_generation_status
from speech_processing.logging_utils import (
    audit_log,
    log_generation_start,
    log_share_action,
    get_client_ip,
    get_user_agent,
)
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

        # Log generation start
        log_generation_start(
            user=request.user,
            page=page,
            voice=voice_id,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

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
@audit_log(AudioAction.DOWNLOAD, extract_audio=lambda kwargs: kwargs.get("audio_id"))
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
@audit_log(AudioAction.PLAY, extract_audio=lambda kwargs: kwargs.get("audio_id"))
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
@audit_log(AudioAction.DELETE, extract_audio=lambda kwargs: kwargs.get("audio_id"))
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

        service = AudioGenerationService()

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
                        service.get_presigned_url(audio)
                        if audio.status == "COMPLETED"
                        else None
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
                "preferred_voice": request.user.preferred_voice_id or "", 
            }
        )

    except Exception as e:
        logger.error(f"Page audios error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )


# ============================================================================
# SHARING AND PERMISSIONS VIEWS
# ============================================================================


@require_http_methods(["POST"])
@login_required
def share_document(request, document_id):
    """
    Share a document with another user.
    POST /speech/share/<document_id>/
    Body: {
        "email": "user@example.com",
        "permission": "VIEW_ONLY|COLLABORATOR|CAN_SHARE"
    }
    """
    from document_processing.models import Document
    from django.contrib.auth import get_user_model
    from speech_processing.models import SharingPermission

    User = get_user_model()

    try:
        data = json.loads(request.body)
        email = data.get("email")
        permission = data.get("permission", "VIEW_ONLY")

        if not email:
            return JsonResponse(
                {"success": False, "error": "Email is required"}, status=400
            )

        # Get the document
        document = get_object_or_404(Document, id=document_id)

        # Check if user has permission to share
        if document.user != request.user:
            # Check if user has CAN_SHARE permission
            try:
                sharing = DocumentSharing.objects.get(
                    document=document, shared_with=request.user
                )
                if not sharing.can_share():
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "You don't have permission to share this document",
                        },
                        status=403,
                    )
            except DocumentSharing.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "You don't have access to this document",
                    },
                    status=403,
                )

        # Get the user to share with
        try:
            user_to_share = User.objects.get(email=email)
        except User.DoesNotExist:
            return JsonResponse(
                {"success": False, "error": f"User with email '{email}' not found"},
                status=404,
            )

        # Check if trying to share with self
        if user_to_share == document.user:
            return JsonResponse(
                {"success": False, "error": "Cannot share document with yourself"},
                status=400,
            )

        # Validate permission level
        valid_permissions = [p.value for p in SharingPermission]
        if permission not in valid_permissions:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Invalid permission. Must be one of: {', '.join(valid_permissions)}",
                },
                status=400,
            )

        # Create or update sharing
        sharing, created = DocumentSharing.objects.update_or_create(
            document=document,
            shared_with=user_to_share,
            defaults={"permission": permission, "shared_by": request.user},
        )

        # Log the share action
        log_share_action(
            user=request.user,
            document=document,
            action=AudioAction.SHARE,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        action = "shared" if created else "updated"
        return JsonResponse(
            {
                "success": True,
                "message": f"Document {action} successfully with {email}",
                "sharing_id": sharing.id,
                "permission": sharing.permission,
                "created": created,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        logger.error(f"Share document error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred while sharing"},
            status=500,
        )


@require_http_methods(["DELETE", "POST"])
@login_required
def unshare_document(request, sharing_id):
    """
    Remove document sharing.
    DELETE /speech/unshare/<sharing_id>/
    Only document owner or the person who shared can unshare.
    """
    try:
        sharing = get_object_or_404(DocumentSharing, id=sharing_id)

        # Check permissions: owner or person who shared can unshare
        if sharing.document.user != request.user and sharing.shared_by != request.user:
            return JsonResponse(
                {
                    "success": False,
                    "error": "You don't have permission to remove this share",
                },
                status=403,
            )

        document_title = sharing.document.title
        shared_with_email = sharing.shared_with.email
        document = sharing.document

        sharing.delete()

        # Log the unshare action
        log_share_action(
            user=request.user,
            document=document,
            action=AudioAction.UNSHARE,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )

        return JsonResponse(
            {
                "success": True,
                "message": f"Removed access for {shared_with_email} to '{document_title}'",
            }
        )

    except Exception as e:
        logger.error(f"Unshare document error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )


@require_http_methods(["GET"])
@login_required
def document_shares(request, document_id):
    """
    Get all shares for a document.
    GET /speech/document/<document_id>/shares/
    """
    from document_processing.models import Document

    try:
        document = get_object_or_404(Document, id=document_id)

        # Check if user has access
        if document.user != request.user:
            # Check if user has CAN_SHARE permission
            try:
                sharing = DocumentSharing.objects.get(
                    document=document, shared_with=request.user
                )
                if not sharing.can_share():
                    return JsonResponse(
                        {
                            "success": False,
                            "error": "You don't have permission to view shares",
                        },
                        status=403,
                    )
            except DocumentSharing.DoesNotExist:
                return JsonResponse(
                    {
                        "success": False,
                        "error": "You don't have access to this document",
                    },
                    status=403,
                )

        # Get all shares
        shares = DocumentSharing.objects.filter(document=document).select_related(
            "shared_with", "shared_by"
        )

        shares_data = []
        for share in shares:
            shares_data.append(
                {
                    "id": share.id,
                    "shared_with": {
                        "id": share.shared_with.id,
                        "email": share.shared_with.email,
                        "name": share.shared_with.get_full_name()
                        or share.shared_with.email,
                    },
                    "permission": share.permission,
                    "can_generate_audio": share.can_generate_audio(),
                    "can_share": share.can_share(),
                    "shared_by": {
                        "email": share.shared_by.email,
                        "name": share.shared_by.get_full_name()
                        or share.shared_by.email,
                    },
                    "created_at": share.created_at.isoformat(),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "document": {
                    "id": document.id,
                    "title": document.title,
                    "owner": {
                        "email": document.user.email,
                        "name": document.user.get_full_name() or document.user.email,
                    },
                },
                "shares": shares_data,
                "total": len(shares_data),
                "is_owner": document.user == request.user,
            }
        )

    except Exception as e:
        logger.error(f"Document shares error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )


@require_http_methods(["GET"])
@login_required
def shared_with_me(request):
    """
    Get all documents shared with the current user.
    GET /speech/shared-with-me/
    """
    try:
        # Get all documents shared with user
        shares = (
            DocumentSharing.objects.filter(shared_with=request.user)
            .select_related("document", "document__user", "shared_by")
            .order_by("-created_at")
        )

        documents_data = []
        for share in shares:
            document = share.document
            documents_data.append(
                {
                    "sharing_id": share.id,
                    "document": {
                        "id": document.id,
                        "title": document.title,
                        "status": document.status,
                        "created_at": document.created_at.isoformat(),
                        "owner": {
                            "email": document.user.email,
                            "name": document.user.get_full_name()
                            or document.user.email,
                        },
                    },
                    "permission": share.permission,
                    "can_generate_audio": share.can_generate_audio(),
                    "can_share": share.can_share(),
                    "shared_by": {
                        "email": share.shared_by.email,
                        "name": share.shared_by.get_full_name()
                        or share.shared_by.email,
                    },
                    "shared_at": share.created_at.isoformat(),
                }
            )

        return JsonResponse(
            {
                "success": True,
                "documents": documents_data,
                "total": len(documents_data),
            }
        )

    except Exception as e:
        logger.error(f"Shared with me error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )


@require_http_methods(["PATCH", "POST"])
@login_required
def update_share_permission(request, sharing_id):
    """
    Update permission level for an existing share.
    PATCH /speech/share/<sharing_id>/permission/
    Body: {"permission": "VIEW_ONLY|COLLABORATOR|CAN_SHARE"}
    """
    from speech_processing.models import SharingPermission

    try:
        data = json.loads(request.body)
        new_permission = data.get("permission")

        if not new_permission:
            return JsonResponse(
                {"success": False, "error": "Permission is required"}, status=400
            )

        sharing = get_object_or_404(DocumentSharing, id=sharing_id)

        # Check if user has permission to modify
        if sharing.document.user != request.user and sharing.shared_by != request.user:
            return JsonResponse(
                {
                    "success": False,
                    "error": "You don't have permission to modify this share",
                },
                status=403,
            )

        # Validate permission level
        valid_permissions = [p.value for p in SharingPermission]
        if new_permission not in valid_permissions:
            return JsonResponse(
                {
                    "success": False,
                    "error": f"Invalid permission. Must be one of: {', '.join(valid_permissions)}",
                },
                status=400,
            )

        old_permission = sharing.permission
        sharing.permission = new_permission
        sharing.save()

        return JsonResponse(
            {
                "success": True,
                "message": f"Permission updated from {old_permission} to {new_permission}",
                "sharing_id": sharing.id,
                "permission": sharing.permission,
                "shared_with": sharing.shared_with.email,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"success": False, "error": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        logger.error(f"Update share permission error: {str(e)}")
        return JsonResponse(
            {"success": False, "error": "An error occurred"}, status=500
        )
