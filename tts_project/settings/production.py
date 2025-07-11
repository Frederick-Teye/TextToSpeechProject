from .base import *
from decouple import config, Csv
import dj_database_url
import os

DEBUG = False

# Security: Ensure SECRET_KEY is always from environment variables in production
SECRET_KEY = config("DJANGO_SECRET_KEY")

# Allowed hosts on Heroku
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS", cast=Csv()
)  # ALLOWED_HOSTS will be a comma-separated string on Heroku

# Production Database (Heroku Postgres Add-on)
DATABASES = {"default": dj_database_url.parse(config("DATABASE_URL"))}

# Static files storage for production (WhiteNoise for efficiency)
# WhiteNoise will serve static files directly from your Django app
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# AWS S3 for media files (user uploads and generated audio)
# DEFAULT_FILE_STORAGE is set in base.py to 'storages.backends.s3boto3.S3Boto3Storage'
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME, AWS_DEFAULT_REGION are from env
# The caching headers (AWS_HEADERS) are defined in base.py and will apply here.

# Security Enhancements (Highly Recommended for Production)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config(
    "SECURE_SSL_REDIRECT", default=True, cast=bool
)  # Redirect HTTP to HTTPS
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)
SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS", default=31536000, cast=int
)  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True, cast=bool
)
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=True, cast=bool)
X_FRAME_OPTIONS = "DENY"  # Protects against clickjacking
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True

# Logging configuration for production
# Directs logs to console (Heroku collects these)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
        },
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.getenv("DJANGO_LOG_LEVEL", "INFO"),
        },
        # Add specific loggers for your apps here if needed
        "document_processing": {
            "handlers": ["console"],
            "level": "INFO",  # Or 'DEBUG' if you want more verbose logs for your app
            "propagate": False,
        },
        "celery": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}


# Email settings for production (real SMTP server)
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST")  # e.g., smtp.sendgrid.net, smtp.mailgun.org
EMAIL_PORT = config("EMAIL_PORT", cast=int)  # e.g., 587 or 465
EMAIL_USE_TLS = config("EMAIL_USE_TLS", cast=bool, default=True)  # Use TLS for security
EMAIL_HOST_USER = config("EMAIL_HOST_USER")  # Your SMTP username
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD")  # Your SMTP password
DEFAULT_FROM_EMAIL = config(
    "DEFAULT_FROM_EMAIL", default="no-reply@yourdomain.com"
)  # Your actual sender email
