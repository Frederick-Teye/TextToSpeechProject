"""
Utilities for Celery task monitoring and failure notifications.

This module provides helpers for:
- Logging task failures to database
- Sending email alerts to admins
- Tracking task retry attempts
- Investigating task execution issues
"""

import logging
import traceback
from django.core.mail import mail_admins
from django.template.loader import render_to_string
from django.conf import settings
from document_processing.models import TaskFailureAlert

logger = logging.getLogger(__name__)


def log_task_failure(
    task_name,
    error_exception,
    task_args=None,
    task_kwargs=None,
    document_id=None,
    user_id=None,
    retry_count=0,
    send_email=True,
):
    """
    Log a task failure to the database and optionally send email alert.
    
    This function should be called in Celery task exception handlers to
    track failures, enable investigation, and alert admins.
    
    Args:
        task_name: Name of the failed task (e.g., 'parse_document_task')
        error_exception: The exception that was raised
        task_args: Positional arguments passed to task (list or tuple)
        task_kwargs: Keyword arguments passed to task (dict)
        document_id: ID of related document, if applicable
        user_id: ID of user who triggered task, if applicable
        retry_count: Number of retry attempts so far
        send_email: Whether to send email alert to admins (default: True)
    
    Returns:
        TaskFailureAlert instance
    
    Example:
        try:
            do_something()
        except Exception as e:
            alert = log_task_failure(
                task_name='parse_document_task',
                error_exception=e,
                task_kwargs={'document_id': doc.id},
                document_id=doc.id,
                user_id=request.user.id,
            )
    """
    from document_processing.models import Document
    from django.contrib.auth import get_user_model
    
    User = get_user_model()
    
    # Get error details
    error_message = str(error_exception)
    error_traceback = traceback.format_exc()
    
    # Determine task name display
    TASK_CHOICES_MAP = {
        'parse_document_task': 'parse_document_task',
        'generate_audio_task': 'generate_audio_task',
        'cleanup_task': 'cleanup_task',
    }
    task_name_display = TASK_CHOICES_MAP.get(task_name, 'other')
    
    # Get related objects
    document = None
    user = None
    
    if document_id:
        try:
            document = Document.objects.get(id=document_id)
        except Document.DoesNotExist:
            pass
    
    if user_id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            pass
    
    # Convert args/kwargs to lists/dicts for JSON serialization
    args_list = list(task_args) if task_args else []
    kwargs_dict = dict(task_kwargs) if task_kwargs else {}
    
    # Create alert record
    try:
        alert = TaskFailureAlert.objects.create(
            task_name=task_name_display,
            document=document,
            user=user,
            error_message=error_message,
            error_traceback=error_traceback,
            task_args=args_list,
            task_kwargs=kwargs_dict,
            retry_count=retry_count,
            status='NEW',
            email_sent=False,
        )
        
        logger.error(
            f"Task failure logged: {task_name} - {error_message[:100]}",
            extra={
                'task_name': task_name,
                'alert_id': alert.id,
                'document_id': document_id,
                'user_id': user_id,
            }
        )
        
        # Send email alert if enabled and email is configured
        if send_email and should_send_alert_email(task_name_display):
            try:
                send_task_failure_email(alert)
            except Exception as email_error:
                logger.error(f"Failed to send alert email: {email_error}")
        
        return alert
    
    except Exception as db_error:
        # If we can't save to DB, at least log it
        logger.error(
            f"Failed to log task failure to database: {db_error}",
            extra={
                'task_name': task_name,
                'error_message': error_message,
            }
        )
        return None


def send_task_failure_email(alert):
    """
    Send email alert to admins about a task failure.
    
    Args:
        alert: TaskFailureAlert instance
    """
    subject = f"Task Failure Alert: {alert.get_task_name_display()}"
    
    # Build context for email template
    context = {
        'alert': alert,
        'task_name': alert.get_task_name_display(),
        'error_message': alert.error_message,
        'document_title': alert.document.title if alert.document else 'N/A',
        'user_email': alert.user.email if alert.user else 'N/A',
        'created_at': alert.created_at,
        'dashboard_url': f"{settings.SITE_URL}/admin/document_processing/taskfailurealert/{alert.id}/change/" if hasattr(settings, 'SITE_URL') else '/admin/',
    }
    
    # Try to render HTML email, fall back to plain text
    try:
        html_message = render_to_string('emails/task_failure_alert.html', context)
    except Exception:
        html_message = None
    
    # Plain text version
    message = f"""
Task Failure Alert

Task: {alert.get_task_name_display()}
Status: {alert.get_status_display()}
Created: {alert.created_at}

Error Message:
{alert.error_message}

Related Document: {alert.document.title if alert.document else 'N/A'}
Related User: {alert.user.email if alert.user else 'N/A'}

For full details, see: {context['dashboard_url']}

Retry Count: {alert.retry_count}
""".strip()
    
    # Send email to admins
    mail_admins(
        subject=subject,
        message=message,
        html_message=html_message,
        fail_silently=True,
    )
    
    # Mark as sent
    alert.email_sent = True
    from django.utils import timezone
    alert.email_sent_at = timezone.now()
    alert.save(update_fields=['email_sent', 'email_sent_at'])
    
    logger.info(f"Alert email sent for failure ID {alert.id}")


def should_send_alert_email(task_name):
    """
    Determine if alert email should be sent for this task.
    
    Args:
        task_name: Name of task from TaskFailureAlert.TASK_CHOICES
    
    Returns:
        True if email should be sent, False otherwise
    """
    # Get configuration from settings or use defaults
    config = getattr(settings, 'TASK_FAILURE_ALERTS', {})
    
    # Default to sending for all tasks unless configured otherwise
    enabled_tasks = config.get('enabled_tasks', ['parse_document_task', 'generate_audio_task'])
    
    return task_name in enabled_tasks


def get_recent_failures(days=7, task_name=None, status=None):
    """
    Get recent task failures for analysis or monitoring.
    
    Args:
        days: Number of days to look back (default: 7)
        task_name: Filter by task name (optional)
        status: Filter by status (optional)
    
    Returns:
        QuerySet of TaskFailureAlert instances
    """
    from django.utils import timezone
    from datetime import timedelta
    
    start_date = timezone.now() - timedelta(days=days)
    
    query = TaskFailureAlert.objects.filter(created_at__gte=start_date)
    
    if task_name:
        query = query.filter(task_name=task_name)
    
    if status:
        query = query.filter(status=status)
    
    return query.order_by('-created_at')


def get_failure_summary():
    """
    Get a summary of recent task failures.
    
    Returns:
        Dict with summary statistics
    """
    from django.utils import timezone
    from datetime import timedelta
    from django.db.models import Count
    
    past_24h = timezone.now() - timedelta(hours=24)
    past_7d = timezone.now() - timedelta(days=7)
    
    all_failures = TaskFailureAlert.objects.all()
    recent_24h = all_failures.filter(created_at__gte=past_24h)
    recent_7d = all_failures.filter(created_at__gte=past_7d)
    
    unresolved = all_failures.filter(status__in=['NEW', 'ACKNOWLEDGED', 'INVESTIGATING'])
    
    by_task = recent_7d.values('task_name').annotate(count=Count('id')).order_by('-count')
    
    return {
        'total': all_failures.count(),
        'last_24h': recent_24h.count(),
        'last_7d': recent_7d.count(),
        'unresolved': unresolved.count(),
        'by_task': list(by_task),
        'critical': unresolved.filter(retry_count__gte=3).count(),
    }
