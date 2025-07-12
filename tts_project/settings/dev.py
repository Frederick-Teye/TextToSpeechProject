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

# Social Account Providers (for local development)
# Use empty string defaults if environment variables are not set.
# This allows the app to start without crashing if keys are missing.
SOCIALACCOUNT_PROVIDERS = {
    "google": {
        "APP": {
            "client_id": config("GOOGLE_CLIENT_ID", default=""),
            "secret": config(
                "GOOGLE_SECRET", default=""
            ),  # Corrected 'SECRETE' to 'SECRET'
            "key": "",
        }
    },
    "github": {
        "APP": {
            "client_id": config("GITHUB_CLIENT_ID", default=""),
            "secret": config(
                "GITHUB_SECRET", default=""
            ),  # Corrected 'SECRETE' to 'SECRET'
            "key": "",
        },
        "VERIFIED_EMAIL": True,
    },
}



