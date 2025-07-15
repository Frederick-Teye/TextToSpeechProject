from .base import *
from decouple import config
import dj_database_url

DEBUG = True

# Allow connections from localhost and the web service in Docker
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# Database settings for local PostgreSQL via Docker Compose
# The 'db' hostname resolves to the PostgreSQL container in the Docker network
DATABASES = {
    "default": dj_database_url.parse(
        config(
            "DATABASE_URL",
            default=f"postgres://{config('DB_USER')}:{config('DB_PASSWORD')}@{config('DB_HOST')}:{config('DB_PORT')}/{config('DB_NAME')}",
        )
    )
}

# Static and Media files for local development (saved to local disk)
# This will use local file system storage rather than S3 during development
DEFAULT_FILE_STORAGE = "django.core.files.storage.FileSystemStorage"
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# Email settings for local development (console backend)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
# DEFAULT_FROM_EMAIL = "webmaster@localhost"  # A dummy email for dev
DEFAULT_FROM_EMAIL = "webmaster@localhost"

# Optionally, for Debug Toolbar (if you install it later)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']


# Session cookie settings for local development (crucial for allauth password reset)
# Use False for local HTTP development, True for HTTPS in production
SESSION_COOKIE_SECURE = False
# 'Lax' allows the cookie to be sent with top-level navigations, which is needed
# for clicking links from emails. 'Strict' can prevent this.
SESSION_COOKIE_SAMESITE = "Lax"

APPEND_SLASH = True
PREPEND_WWW = False


# tts_project/settings/dev.py or base.py
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "level": "DEBUG",  # Set to DEBUG to see all messages, including INFO
            "class": "logging.StreamHandler",
            "formatter": "simple",  # Or 'verbose' for more detail
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",  # Ensure Django's default logger captures INFO
            "propagate": False,
        },
        "core": {  # Add a logger for your 'core' app
            "handlers": ["console"],
            "level": "INFO",  # Set to INFO or DEBUG to see your custom logs
            "propagate": False,
        },
        "allauth": {  # Optionally, add a logger for allauth if you want its internal logs
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
    "root": {  # Fallback for anything not caught by specific loggers
        "handlers": ["console"],
        "level": "WARNING",  # Default to WARNING for root to avoid too much noise
    },
}

# Allauth settings
# Set password reset timeout to a very large value for local debugging (e.g., 1 hour = 3600 seconds)
# Default is 259200 seconds (3 days)
ACCOUNT_PASSWORD_RESET_TIMEOUT = 3600  # 1 hour
