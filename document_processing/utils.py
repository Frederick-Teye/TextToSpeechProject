import uuid
import os
import logging
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


def upload_to_s3(file_obj, user_id, file_name):
    """
    Upload a file-like object to S3 under a unique key using IAM.
    Loads the storage class from settings.DEFAULT_FILE_STORAGE at runtime.
    """
    from django.conf import settings

    # Dynamically load the actual storage class from settings
    storage_class = import_string(settings.DEFAULT_FILE_STORAGE)
    storage = storage_class()  # instantiate it

    # Reset file pointer
    file_obj.seek(0)

    # Unique S3 key
    safe_name = f"{uuid.uuid4().hex}_{os.path.basename(file_name)}"
    s3_path = f"uploads/{user_id}/{safe_name}"

    try:
        # Save using actual storage instance
        key = storage.save(s3_path, file_obj)
        logger.info(f"Uploaded {file_name} to {key}")
        return "media/" + key

    except Exception:
        logger.exception(f"Failed to upload {file_name} for user {user_id}")
        raise
