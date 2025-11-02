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

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/
STATIC_ROOT = BASE_DIR / "static_cdn"

# Static files storage for production (WhiteNoise for efficiency)
# WhiteNoise will serve static files directly from your Django app
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# AWS S3 for media files (user uploads and generated audio)
# DEFAULT_FILE_STORAGE is set in base.py to 'storages.backends.s3boto3.S3Boto3Storage'
# AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_STORAGE_BUCKET_NAME, AWS_DEFAULT_REGION are from env
# The caching headers (AWS_HEADERS) are defined in base.py and will apply here.

# Security Enhancements (Highly Recommended for Production)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True

# ==================== COOKIE SECURITY ====================
# These settings protect against session hijacking and CSRF attacks
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=True, cast=bool)
SESSION_COOKIE_HTTPONLY = config("SESSION_COOKIE_HTTPONLY", default=True, cast=bool)
SESSION_COOKIE_SAMESITE = config("SESSION_COOKIE_SAMESITE", default="Strict")
# Explanation of SESSION_COOKIE_SAMESITE options:
#   "Strict" - Cookie only sent in same-site requests (most secure)
#   "Lax" - Cookie sent on top-level navigations (default, more compatible)
#   "None" - Cookie sent in all requests (requires Secure flag)

CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=True, cast=bool)
CSRF_COOKIE_HTTPONLY = config("CSRF_COOKIE_HTTPONLY", default=True, cast=bool)
CSRF_COOKIE_SAMESITE = config("CSRF_COOKIE_SAMESITE", default="Strict")
# CSRF_COOKIE_HTTPONLY = True prevents JavaScript from accessing the CSRF token
# This makes CSRF attacks from JS much harder

# ==================== HTTP SECURITY HEADERS ====================
SECURE_HSTS_SECONDS = config(
    "SECURE_HSTS_SECONDS", default=31536000, cast=int
)  # 1 year
# Strict-Transport-Security: tells browsers to always use HTTPS
SECURE_HSTS_INCLUDE_SUBDOMAINS = config(
    "SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True, cast=bool
)
# Include subdomains in HSTS policy
SECURE_HSTS_PRELOAD = config("SECURE_HSTS_PRELOAD", default=True, cast=bool)
# Allow the site to be added to the HSTS preload list

# ==================== CONTENT SECURITY & CLICKJACKING ====================
X_FRAME_OPTIONS = "DENY"  # Protects against clickjacking (prevents embedding in iframes)
SECURE_BROWSER_XSS_FILTER = True  # Enables XSS protection header (X-XSS-Protection: 1; mode=block)
SECURE_CONTENT_TYPE_NOSNIFF = True  # Prevents MIME type sniffing (X-Content-Type-Options: nosniff)

# ==================== REFERRER POLICY ====================
# This controls what referrer information is sent to external sites
SECURE_REFERRER_POLICY = config(
    "SECURE_REFERRER_POLICY", 
    default="strict-origin-when-cross-origin"
)
# Explanation:
#   "strict-origin-when-cross-origin" - send origin only for cross-origin requests (default, recommended)
#   "no-referrer" - don't send referrer info at all (most private)
#   "same-origin" - only send to same site


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
