"""
Admin dashboard views for speech processing analytics and monitoring.
"""

from django.shortcuts import render
from django.contrib.admin.views.decorators import staff_member_required
from django.http import JsonResponse
from django.db.models import Count, Q, Avg, Sum
from django.db.models.functions import TruncDate, TruncMonth
from django.utils import timezone
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from datetime import timedelta
import logging

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
from speech_processing.logging_utils import log_admin_action, get_client_ip, get_user_agent

User = get_user_model()
logger = logging.getLogger(__name__)

# Constants for input validation
MIN_DAYS = 1
MAX_DAYS = 365
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 500
MIN_PAGE_SIZE = 10


def validate_page_parameter(page_str, total_count, page_size=DEFAULT_PAGE_SIZE):
    """
    Validate and safely parse page number for pagination.

    Security validations:
    - Must be a valid integer
    - Must be within valid range
    - Prevents overflow attacks

    Args:
        page_str: Page number from query parameter
        total_count: Total number of items to paginate
        page_size: Items per page

    Returns:
        Tuple of (page_number: int, total_pages: int)
        Returns (1, pages) if invalid
    """
    try:
        page = int(page_str) if page_str else 1

        # Ensure page is positive
        if page < 1:
            logger.warning(f"Invalid page number: {page}. Defaulting to 1.")
            page = 1

        # Calculate total pages
        total_pages = (total_count + page_size - 1) // page_size

        # Ensure page doesn't exceed total
        if page > total_pages and total_pages > 0:
            logger.warning(
                f"Page {page} exceeds total pages {total_pages}. "
                f"Defaulting to last page."
            )
            page = total_pages

        return page, total_pages

    except (ValueError, TypeError):
        logger.warning(f"Invalid page parameter: {page_str}. Defaulting to 1.")
        return 1, 0


def validate_days_parameter(days_str, default=30):
    """
    Validate and sanitize the 'days' query parameter.

    Security validations:
    - Must be convertible to integer (prevents injection)
    - Must be between MIN_DAYS (1) and MAX_DAYS (365)
    - Prevents negative values, zero, or excessive queries

    Args:
        days_str: String value from query parameter
        default: Default value if validation fails (default: 30)

    Returns:
        Validated integer number of days (bounded 1-365)

    Example:
        >>> validate_days_parameter("30")
        30
        >>> validate_days_parameter("-100")
        30  # Returns default because negative
        >>> validate_days_parameter("999")
        365  # Returns MAX_DAYS because too large
        >>> validate_days_parameter("abc")
        30  # Returns default because non-numeric
    """
    try:
        days = int(days_str)

        # Validate bounds
        if days < MIN_DAYS:
            logger.warning(
                f"Dashboard query with invalid days parameter: {days} "
                f"(minimum {MIN_DAYS}). Using default."
            )
            return default

        if days > MAX_DAYS:
            logger.warning(
                f"Dashboard query with excessive days parameter: {days} "
                f"(maximum {MAX_DAYS}). Limiting to {MAX_DAYS}."
            )
            return MAX_DAYS

        return days

    except (ValueError, TypeError):
        logger.warning(
            f"Dashboard query with non-numeric days parameter: {days_str}. "
            f"Using default."
        )
        return default


@staff_member_required
def dashboard_home(request):
    """
    Main admin dashboard with overview statistics.
    """
    # Log dashboard access
    log_admin_action(
        user=request.user,
        action='VIEW_DASHBOARD',
        description='Accessed admin dashboard',
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    
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
    # Log analytics access
    log_admin_action(
        user=request.user,
        action='VIEW_ANALYTICS',
        description='Viewed analytics dashboard',
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    
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

    Security:
    - Validates and bounds 'period' query parameter (1-365 days)
    - Prevents negative values and excessive queries
    """
    # Log analytics data access
    log_admin_action(
        user=request.user,
        action='VIEW_ANALYTICS',
        description=f'Accessed analytics data with period={request.GET.get("period", "30")}',
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    
    period = request.GET.get("period", "30")  # days

    # Validate the days parameter
    days = validate_days_parameter(period, default=30)

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

    Security:
    - Validates and bounds 'days' query parameter (1-365 days)
    - Prevents negative values and excessive queries
    - Paginates results to prevent memory exhaustion
    """
    # Get filter parameters with validation
    days_param = request.GET.get("days", "7")
    days = validate_days_parameter(days_param, default=7)

    page_num = request.GET.get("page", "1")

    start_date = timezone.now() - timedelta(days=days)

    # Get failed audios
    failed_audios_qs = (
        Audio.objects.filter(
            status=AudioGenerationStatus.FAILED, created_at__gte=start_date
        )
        .select_related("generated_by", "page__document")
        .order_by("-created_at")
    )

    # Error statistics (computed before pagination)
    total_errors = failed_audios_qs.count()
    unique_errors = failed_audios_qs.values("error_message").distinct().count()

    # Error frequency
    error_frequency = (
        failed_audios_qs.values("error_message")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Affected users
    affected_users = (
        failed_audios_qs.values("generated_by__email")
        .annotate(count=Count("id"))
        .order_by("-count")[:10]
    )

    # Paginate the results
    page, total_pages = validate_page_parameter(
        page_num, total_errors, DEFAULT_PAGE_SIZE
    )
    start_idx = (page - 1) * DEFAULT_PAGE_SIZE
    end_idx = start_idx + DEFAULT_PAGE_SIZE
    failed_audios = failed_audios_qs[start_idx:end_idx]

    context = {
        "failed_audios": failed_audios,
        "total_errors": total_errors,
        "unique_errors": unique_errors,
        "error_frequency": error_frequency,
        "affected_users": affected_users,
        "days": days,
        "current_page": page,
        "total_pages": total_pages,
        "page_size": DEFAULT_PAGE_SIZE,
    }

    return render(request, "speech_processing/error_monitoring.html", context)


@staff_member_required
def user_activity(request):
    """
    User activity report showing detailed user actions.

    Security:
    - Validates and bounds 'days' query parameter (1-365 days)
    - Prevents negative values and excessive queries
    """
    # Get filter parameters with validation
    days_param = request.GET.get("days", "30")
    days = validate_days_parameter(days_param, default=30)
    user_email = request.GET.get("user", "")

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
