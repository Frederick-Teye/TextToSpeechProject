"""
Audit logging utilities for speech processing.

This module provides decorators and helper functions for logging
audio-related actions to the AudioAccessLog model.
"""

from functools import wraps
from django.http import JsonResponse
from speech_processing.models import AudioAccessLog, AudioAction, AudioGenerationStatus
import logging

logger = logging.getLogger(__name__)


def get_client_ip(request):
    """
    Extract client IP address from request.
    Handles X-Forwarded-For header for proxied requests.
    """
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
    else:
        ip = request.META.get("REMOTE_ADDR")
    return ip


def get_user_agent(request):
    """Extract user agent string from request."""
    return request.META.get("HTTP_USER_AGENT", "")


def log_audio_action(
    user,
    action,
    audio=None,
    document=None,
    status=AudioGenerationStatus.COMPLETED,
    error_message=None,
    ip_address=None,
    user_agent=None,
):
    """
    Create an audit log entry for an audio action.

    Args:
        user: User who performed the action
        action: AudioAction choice (GENERATE, PLAY, DOWNLOAD, etc.)
        audio: Audio object (optional, for audio-specific actions)
        document: Document object (optional, for sharing actions)
        status: AudioGenerationStatus (COMPLETED or FAILED)
        error_message: Error message if action failed
        ip_address: Client IP address
        user_agent: User agent string

    Returns:
        AudioAccessLog instance
    """
    try:
        log_entry = AudioAccessLog.objects.create(
            user=user,
            audio=audio,
            document=document,
            action=action,
            status=status,
            error_message=error_message,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return log_entry
    except Exception as e:
        logger.error(f"Failed to create audit log: {e}")
        return None


def audit_log(action, extract_audio=None, extract_document=None):
    """
    Decorator to automatically log audio actions.

    Usage:
        @audit_log(AudioAction.PLAY, extract_audio=lambda view_kwargs: view_kwargs.get('audio_id'))
        @login_required
        def play_audio(request, audio_id):
            # ... view logic ...
            return JsonResponse({'success': True})

    Args:
        action: AudioAction choice
        extract_audio: Function to extract audio ID from view kwargs (optional)
        extract_document: Function to extract document ID from view kwargs (optional)
    """

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            # Execute the view
            response = view_func(request, *args, **kwargs)

            # Only log for authenticated users
            if not request.user.is_authenticated:
                return response

            # Determine success/failure from response
            status = AudioGenerationStatus.COMPLETED
            error_message = None

            if isinstance(response, JsonResponse):
                try:
                    # Parse response to check success
                    response_data = response.content.decode("utf-8")
                    import json

                    data = json.loads(response_data)

                    if not data.get("success", True):
                        status = AudioGenerationStatus.FAILED
                        error_message = data.get("error", "Unknown error")
                except:
                    pass

            # Extract audio and document if extractors provided
            audio = None
            document = None

            if extract_audio:
                try:
                    audio_id = extract_audio(kwargs)
                    if audio_id:
                        from speech_processing.models import Audio

                        audio = Audio.objects.filter(id=audio_id).first()
                except Exception as e:
                    logger.error(f"Failed to extract audio: {e}")

            if extract_document:
                try:
                    document_id = extract_document(kwargs)
                    if document_id:
                        from document_processing.models import Document

                        document = Document.objects.filter(id=document_id).first()
                except Exception as e:
                    logger.error(f"Failed to extract document: {e}")

            # Get client information
            ip_address = get_client_ip(request)
            user_agent = get_user_agent(request)

            # Create log entry
            log_audio_action(
                user=request.user,
                action=action,
                audio=audio,
                document=document,
                status=status,
                error_message=error_message,
                ip_address=ip_address,
                user_agent=user_agent,
            )

            return response

        return wrapper

    return decorator


def log_generation_start(user, page, voice, ip_address=None, user_agent=None):
    """
    Log the start of audio generation.
    Called when generation task is triggered.
    """
    return log_audio_action(
        user=user,
        action=AudioAction.GENERATE,
        audio=None,  # Audio doesn't exist yet
        document=page.document,
        status=AudioGenerationStatus.PENDING,
        error_message=None,
        ip_address=ip_address,
        user_agent=user_agent,
    )


def log_generation_complete(
    audio, status=AudioGenerationStatus.COMPLETED, error_message=None
):
    """
    Log the completion of audio generation.
    Called from Celery task when generation finishes.
    """
    return log_audio_action(
        user=audio.generated_by,
        action=AudioAction.GENERATE,
        audio=audio,
        document=audio.page.document,
        status=status,
        error_message=error_message,
        ip_address=None,  # Not available in Celery task
        user_agent=None,
    )


def log_share_action(
    user,
    document,
    action,
    ip_address=None,
    user_agent=None,
    status=AudioGenerationStatus.COMPLETED,
    error_message=None,
):
    """
    Log document sharing actions (SHARE, UNSHARE).
    """
    return log_audio_action(
        user=user,
        action=action,
        audio=None,
        document=document,
        status=status,
        error_message=error_message,
        ip_address=ip_address,
        user_agent=user_agent,
    )
