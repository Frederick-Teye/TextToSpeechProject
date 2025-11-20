from storages.backends.s3boto3 import S3Boto3Storage
from django.conf import settings


class MediaStorage(S3Boto3Storage):
    location = "media"  # Folder in S3 bucket
    file_overwrite = False  # Prevent overwriting files


class StaticStorage(S3Boto3Storage):
    bucket_name = "frederick-tts-project-static-bucket"  # HARDCODE THE BUCKET NAME HERE
    location = "staticfiles"
    custom_domain = settings.STATIC_CLOUDFRONT_DOMAIN


# class MediaStorage(S3Boto3Storage):
#     """Storage for media files (audio) - requires signed URLs"""

#     location = "media"
#     default_acl = None
#     file_overwrite = False
#     custom_domain = config("CLOUDFRONT_DOMAIN")
#     querystring_auth = False  # We handle signing separately
