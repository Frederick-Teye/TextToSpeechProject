from storages.backends.s3boto3 import S3Boto3Storage


class MediaStorage(S3Boto3Storage):
    location = "media"  # Folder in S3 bucket
    file_overwrite = False  # Prevent overwriting files
