from .base import *
from decouple import config, Csv
import dj_database_url
from storages.backends.s3boto3 import S3Boto3Storage

# === DEBUGGING ===
DEBUG = False

# Security: Ensure SECRET_KEY is always from environment variables in production
SECRET_KEY = config("DJANGO_SECRET_KEY")

# Allowed hosts on Heroku
ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS", cast=Csv()
)  # ALLOWED_HOSTS will be a comma-separated string on Heroku

# Production Database (Heroku Postgres Add-on)
DATABASES = {"default": dj_database_url.parse(config("DATABASE_URL"))}

# === STATIC FILES (CSS, JS, Images) ===
# PUBLIC - served directly from CloudFront, NO signing needed
STATIC_URL = f"https://{config('STATIC_CLOUDFRONT_DOMAIN')}/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

class StaticStorage(S3Boto3Storage):
    """Storage for static files - served publicly from CloudFront"""
    location = 'static'
    default_acl = None  # Use CloudFront OAI instead
    file_overwrite = False
    custom_domain = config('STATIC_CLOUDFRONT_DOMAIN')
    querystring_auth = False  # NO signing for static files

STATICFILES_STORAGE = 'core.settings.production.StaticStorage'

# === MEDIA FILES (User-Generated Audio) ===
# PRIVATE - served via signed CloudFront URLs
MEDIA_URL = f"https://{config('CLOUDFRONT_DOMAIN')}/media/"
MEDIA_ROOT = BASE_DIR / "media"

class MediaStorage(S3Boto3Storage):
    """Storage for media files (audio) - requires signed URLs"""
    location = 'media'
    default_acl = None
    file_overwrite = False
    custom_domain = config('CLOUDFRONT_DOMAIN')
    querystring_auth = False  # We handle signing separately

DEFAULT_FILE_STORAGE = 'core.settings.production.MediaStorage'

# === AWS S3 CONFIGURATION ===
AWS_ACCESS_KEY_ID = config('AWS_ACCESS_KEY_ID')
AWS_SECRET_ACCESS_KEY = config('AWS_SECRET_ACCESS_KEY')
AWS_DEFAULT_REGION = config('AWS_DEFAULT_REGION', default='us-east-1')

# Storage buckets
AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME')  # Audio bucket
AWS_STATIC_BUCKET_NAME = config('AWS_STATIC_BUCKET_NAME')  # Static bucket

# S3 optimization
AWS_S3_OBJECT_PARAMETERS = {
    'CacheControl': 'max-age=31536000',  # 1 year for static files (they're versioned)
}

# === CLOUDFRONT SIGNED URLS (Audio Only) ===
CLOUDFRONT_DOMAIN = config('CLOUDFRONT_DOMAIN')
CLOUDFRONT_KEY_ID = config('CLOUDFRONT_KEY_ID')
CLOUDFRONT_PRIVATE_KEY = config('CLOUDFRONT_PRIVATE_KEY')
CLOUDFRONT_EXPIRATION = 3600  # 1 hour

# Static CloudFront (no signing)
STATIC_CLOUDFRONT_DOMAIN = config('STATIC_CLOUDFRONT_DOMAIN')

# Environment identifier
ENVIRONMENT = config('ENVIRONMENT', default='production')

# ==================== PROXY & SECURITY HEADERS (ECS) ====================
# Required for ECS deployments with ALB/NLB that use X-Forwarded headers
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
USE_X_FORWARDED_PORT = True

# HTTPS enforcement (may cause issues with ALB, handled by ALB instead)
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=False, cast=bool)

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
