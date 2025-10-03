import json
from django.shortcuts import render
from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt


@require_http_methods(["POST"])
@login_required
def update_voice_preference(request):
    """Update the user's preferred voice ID."""
    try:
        data = json.loads(request.body)
        voice_id = data.get("voice_id")

        if not voice_id:
            return JsonResponse(
                {"status": "error", "message": "Voice ID is required"}, status=400
            )

        # List of valid voice IDs to prevent invalid data
        VALID_VOICES = [
            "Joanna",
            "Matthew",
            "Salli",
            "Kimberly",
            "Kendra",
            "Justin",
            "Joey",
            "Ivy",
        ]

        if voice_id not in VALID_VOICES:
            return JsonResponse(
                {"status": "error", "message": "Invalid voice ID"}, status=400
            )

        # Update the user's preferred voice
        request.user.preferred_voice_id = voice_id
        request.user.save()

        return JsonResponse(
            {
                "status": "success",
                "message": f"Voice preference updated to {voice_id}",
                "voice_id": voice_id,
            }
        )

    except json.JSONDecodeError:
        return JsonResponse(
            {"status": "error", "message": "Invalid JSON data"}, status=400
        )
    except Exception as e:
        return JsonResponse(
            {"status": "error", "message": "An error occurred"}, status=500
        )
