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

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# Static on disk (fast local reloads)
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


# Allauth settings
# Set password reset timeout to a very large value for local debugging (e.g., 1 hour = 3600 seconds)
# Default is 259200 seconds (3 days)
ACCOUNT_PASSWORD_RESET_TIMEOUT = 3600  # 1 hour

# === CLOUDFRONT CONFIGURATION (for testing) ===
# In development, we use the same CloudFront domain as configured in .env
# This allows testing CloudFront signed URLs locally
CLOUDFRONT_DOMAIN = config('CLOUDFRONT_DOMAIN', default='d2e40gg2o2wus6.cloudfront.net')
CLOUDFRONT_KEY_ID = config('CLOUDFRONT_KEY_ID', default='')
CLOUDFRONT_PRIVATE_KEY = config('CLOUDFRONT_PRIVATE_KEY', default='')
CLOUDFRONT_EXPIRATION = 3600  # 1 hour

# Static CloudFront (no signing needed)
STATIC_CLOUDFRONT_DOMAIN = config('STATIC_CLOUDFRONT_DOMAIN', default='localhost:8000/static/')
