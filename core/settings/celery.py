from __future__ import absolute_import, unicode_literals
import os
from celery import Celery
from celery.schedules import crontab

# Set the default Django settings module
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")

# Create a Celery instance named 'core'
app = Celery("core")

# Load configuration from Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Autodiscover tasks
app.autodiscover_tasks()

# Celery Beat schedule for periodic tasks
app.conf.beat_schedule = {
    "export-audit-logs-monthly": {
        "task": "speech_processing.tasks.export_audit_logs_to_s3",
        "schedule": crontab(
            day_of_month="1", hour="2", minute="0"
        ),  # 1st of month at 2:00 AM
        "options": {
            "expires": 3600 * 12,  # Expire after 12 hours if not run
        },
    },
    "check-expired-audios-daily": {
        "task": "speech_processing.tasks.check_expired_audios",
        "schedule": crontab(hour="0", minute="0"),  # Daily at midnight
        "options": {
            "expires": 3600 * 6,  # Expire after 6 hours if not run
        },
    },
}
