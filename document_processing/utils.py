import uuid
import os
import logging
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


def upload_to_s3(file_obj, user_id, file_name):
    """
    Upload a file-like object to S3 under a unique key using IAM & default_storage.
    Returns the S3 key (path) on success or raises on failure.
    """
    # Reset buffer
    file_obj.seek(0)

    # Create a collision-resistant name
    safe_name = f"{uuid.uuid4().hex}_{os.path.basename(file_name)}"
    s3_path = f"uploads/{user_id}/{safe_name}"

    try:
        # Delegate to django-storages (configured with IAM, no ACLs)
        key = default_storage.save(s3_path, file_obj)
        logger.info(f"Uploaded {file_name} to {key}")
        return key

    except Exception:
        logger.exception(f"Failed to upload {file_name} for user {user_id}")
        # Let the caller handle retries or mark failures
        raise
