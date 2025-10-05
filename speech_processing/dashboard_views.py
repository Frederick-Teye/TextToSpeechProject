"""
Admin dashboard views for speech processing analytics and monitoring.
"""

from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.db.models import Count, Q, Avg, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from datetime import timedelta

from speech_processing.models import (
    Audio,
    AudioAccessLog,
    DocumentSharing,
    SiteSettings,
    AudioGenerationStatus,
    AudioLifetimeStatus,
    AudioAction,
)
from document_processing.models import Document
from django.contrib.auth import get_user_model

User = get_user_model()


@staff_member_required
def dashboard_home(request):
    """
    Main admin dashboard with overview statistics.
    """
    # Calculate date ranges
    now = timezone.now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)

    # Overall statistics
    total_audios = Audio.objects.count()
    active_audios = Audio.objects.filter(
        lifetime_status=AudioLifetimeStatus.ACTIVE
    ).count()
    deleted_audios = Audio.objects.filter(
        lifetime_status=AudioLifetimeStatus.DELETED
    ).count()

    # Generation statistics
    completed_audios = Audio.objects.filter(
        status=AudioGenerationStatus.COMPLETED
    ).count()
    failed_audios = Audio.objects.filter(status=AudioGenerationStatus.FAILED).count()
    generating_audios = Audio.objects.filter(
        status=AudioGenerationStatus.GENERATING
    ).count()

    # Calculate success rate
    total_generated = completed_audios + failed_audios
    success_rate = (
        (completed_audios / total_generated * 100) if total_generated > 0 else 0
    )

    # User statistics
    total_users = User.objects.count()
    active_users_week = (
        AudioAccessLog.objects.filter(timestamp__gte=week_ago)
        .values("user")
        .distinct()
        .count()
    )
    active_users_month = (
        AudioAccessLog.objects.filter(timestamp__gte=month_ago)
        .values("user")
        .distinct()
        .count()
    )

    # Document statistics
    total_documents = Document.objects.count()
    shared_documents = DocumentSharing.objects.values("document").distinct().count()

    # Recent activity (last 24 hours)
    audios_today = Audio.objects.filter(created_at__gte=today_start).count()
    plays_today = AudioAccessLog.objects.filter(
        action=AudioAction.PLAY, timestamp__gte=today_start
    ).count()
    downloads_today = AudioAccessLog.objects.filter(
        action=AudioAction.DOWNLOAD, timestamp__gte=today_start
    ).count()

    # Top voices
    top_voices = (
        Audio.objects.filter(lifetime_status=AudioLifetimeStatus.ACTIVE)
        .values("voice")
        .annotate(count=Count("id"))
        .order_by("-count")[:5]
    )

    # Recent errors
    recent_errors = (
        Audio.objects.filter(status=AudioGenerationStatus.FAILED)
        .select_related("generated_by", "page__document")
        .order_by("-created_at")[:10]
    )

    # Site settings
    settings = SiteSettings.get_settings()

    context = {
        "total_audios": total_audios,
        "active_audios": active_audios,
        "deleted_audios": deleted_audios,
        "completed_audios": completed_audios,
        "failed_audios": failed_audios,
        "generating_audios": generating_audios,
        "success_rate": round(success_rate, 1),
        "total_users": total_users,
        "active_users_week": active_users_week,
        "active_users_month": active_users_month,
        "total_documents": total_documents,
        "shared_documents": shared_documents,
        "audios_today": audios_today,
        "plays_today": plays_today,
        "downloads_today": downloads_today,
        "top_voices": top_voices,
        "recent_errors": recent_errors,
        "settings": settings,
    }

    return render(request, "speech_processing/dashboard_home.html", context)


@staff_member_required
def analytics_view(request):
    """
    Detailed analytics page with charts and trends.
    """
    settings = SiteSettings.get_settings()

    context = {
        "settings": settings,
    }

    return render(request, "speech_processing/analytics.html", context)


@staff_member_required
def analytics_data(request):
    """
    API endpoint for analytics chart data.
    Returns JSON data for frontend charts.
    """
    period = request.GET.get("period", "30")  # days

    try:
        days = int(period)
    except ValueError:
        days = 30

    start_date = timezone.now() - timedelta(days=days)

    # Audio generation trend
    audio_trend = (
        Audio.objects.filter(created_at__gte=start_date)
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(
            total=Count("id"),
            completed=Count("id", filter=Q(status=AudioGenerationStatus.COMPLETED)),
            failed=Count("id", filter=Q(status=AudioGenerationStatus.FAILED)),
        )
        .order_by("date")
    )

    # User activity trend
    activity_trend = (
        AudioAccessLog.objects.filter(timestamp__gte=start_date)
        .annotate(date=TruncDate("timestamp"))
        .values("date")
        .annotate(
            plays=Count("id", filter=Q(action=AudioAction.PLAY)),
            downloads=Count("id", filter=Q(action=AudioAction.DOWNLOAD)),
            generations=Count("id", filter=Q(action=AudioAction.GENERATE)),
        )
        .order_by("date")
    )

    # Voice usage distribution
    voice_distribution = (
        Audio.objects.filter(lifetime_status=AudioLifetimeStatus.ACTIVE)
        .values("voice")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Action distribution
    action_distribution = (
        AudioAccessLog.objects.filter(timestamp__gte=start_date)
        .values("action")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    # Top users by audio generation
    top_generators = (
        Audio.objects.filter(created_at__gte=start_date)
        .values("generated_by__email")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Top users by activity
    top_active_users = (
        AudioAccessLog.objects.filter(timestamp__gte=start_date)
        .values("user__email")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Error rate by day
    error_trend = (
        Audio.objects.filter(
            created_at__gte=start_date, status=AudioGenerationStatus.FAILED
        )
        .annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("date")
    )

    return JsonResponse(
        {
            "success": True,
            "period": days,
            "audio_trend": list(audio_trend),
            "activity_trend": list(activity_trend),
            "voice_distribution": list(voice_distribution),
            "action_distribution": list(action_distribution),
            "top_generators": list(top_generators),
            "top_active_users": list(top_active_users),
            "error_trend": list(error_trend),
        }
    )


@staff_member_required
def error_monitoring(request):
    """
    Error monitoring page showing failed audio generations.
    """
    # Get filter parameters
    days = request.GET.get("days", "7")
    try:
        days = int(days)
    except ValueError:
        days = 7

    start_date = timezone.now() - timedelta(days=days)

    # Get failed audios
    failed_audios = (
        Audio.objects.filter(
            status=AudioGenerationStatus.FAILED, created_at__gte=start_date
        )
        .select_related("generated_by", "page__document")
        .order_by("-created_at")
    )

    # Error statistics
    total_errors = failed_audios.count()
    unique_errors = failed_audios.values("error_message").distinct().count()

    # Error frequency
    error_frequency = (
        failed_audios.values("error_message")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Affected users
    affected_users = (
        failed_audios.values("generated_by__email")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    context = {
        "failed_audios": failed_audios[:50],  # Limit to 50 for performance
        "total_errors": total_errors,
        "unique_errors": unique_errors,
        "error_frequency": error_frequency,
        "affected_users": affected_users,
        "days": days,
    }

    return render(request, "speech_processing/error_monitoring.html", context)


@staff_member_required
def user_activity(request):
    """
    User activity report showing detailed user actions.
    """
    # Get filter parameters
    days = request.GET.get("days", "30")
    user_email = request.GET.get("user", "")

    try:
        days = int(days)
    except ValueError:
        days = 30

    start_date = timezone.now() - timedelta(days=days)

    # Base query
    logs = AudioAccessLog.objects.filter(timestamp__gte=start_date).select_related(
        "user", "audio", "document"
    )

    # Filter by user if specified
    if user_email:
        logs = logs.filter(user__email__icontains=user_email)

    # Activity statistics
    total_actions = logs.count()
    unique_users = logs.values("user").distinct().count()

    # Action breakdown
    action_breakdown = (
        logs.values("action").annotate(count=Count("id")).order_by("-count")
    )

    # User activity ranking
    user_ranking = (
        logs.values("user__email", "user__first_name", "user__last_name")
        .annotate(
            total_actions=Count("id"),
            generations=Count("id", filter=Q(action=AudioAction.GENERATE)),
            plays=Count("id", filter=Q(action=AudioAction.PLAY)),
            downloads=Count("id", filter=Q(action=AudioAction.DOWNLOAD)),
            deletes=Count("id", filter=Q(action=AudioAction.DELETE)),
        )
        .order_by("-total_actions")[:50]
    )

    # Recent activity log
    recent_logs = logs.order_by("-timestamp")[:100]

    context = {
        "total_actions": total_actions,
        "unique_users": unique_users,
        "action_breakdown": action_breakdown,
        "user_ranking": user_ranking,
        "recent_logs": recent_logs,
        "days": days,
        "user_email": user_email,
    }

    return render(request, "speech_processing/user_activity.html", context)


@staff_member_required
def settings_control(request):
    """
    Settings control panel for toggling feature flags.
    """
    settings = SiteSettings.get_settings()

    if request.method == "POST":
        # Handle form submission
        audio_enabled = request.POST.get("audio_generation_enabled") == "on"
        sharing_enabled = request.POST.get("sharing_enabled") == "on"

        try:
            max_audios = int(request.POST.get("max_audios_per_page", 4))
        except ValueError:
            max_audios = 4

        # Update settings
        settings.audio_generation_enabled = audio_enabled
        settings.sharing_enabled = sharing_enabled
        settings.max_audios_per_page = max_audios
        settings.save()

        return JsonResponse(
            {"success": True, "message": "Settings updated successfully"}
        )

    context = {
        "settings": settings,
    }

    return render(request, "speech_processing/settings_control.html", context)
