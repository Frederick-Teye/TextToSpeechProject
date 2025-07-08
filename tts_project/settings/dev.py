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

# Optionally, for Debug Toolbar (if you install it later)
# INSTALLED_APPS += ['debug_toolbar']
# MIDDLEWARE += ['debug_toolbar.middleware.DebugToolbarMiddleware']
# INTERNAL_IPS = ['127.0.0.1']
