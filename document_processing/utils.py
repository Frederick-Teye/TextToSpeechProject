import uuid
import os
import logging
import unicodedata
import re
import random
import requests
from pathlib import Path
from typing import BinaryIO
from markdownify import markdownify
from django.utils.module_loading import import_string
from django.conf import settings

logger = logging.getLogger(__name__)

# Use settings constants instead of hardcoding values
MAX_MARKDOWN_LENGTH = getattr(
    settings, "MARKDOWN_MAX_LENGTH", 1000000
)  # Fallback if not in settings
MAX_HEADER_LEVEL = 6

# RELAXED PATTERNS:
# We removed LaTeX ($$) because math is valid in documents.
# We removed the broad 'on\w=' check because nh3 handles HTML attributes better.
DANGEROUS_MARKDOWN_PATTERNS = [
    r"<script\b",  # Script tags are definitely dangerous
    r"javascript:",  # Javascript protocol in links
    r"vbscript:",  # VBScript protocol
    r"data:text/html",  # Data URIs that allow HTML execution
]


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent directory traversal attacks.
    [Code remains exactly the same as your previous version]
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("Filename must be a non-empty string")

    filename = filename.replace("\\", "/")
    while ".." in filename:
        filename = filename.replace("..", "_")

    # Remove leading/trailing slashes and absolute path indicators
    filename = filename.lstrip("/").rstrip("/")

    # Step 2: Remove null bytes
    filename = filename.split("\x00")[0]

    # Step 3: Normalize unicode to NFKD form
    # This prevents unicode normalization attacks
    filename = unicodedata.normalize("NFKD", filename)
    filename = filename.encode("ascii", "ignore").decode("ascii")

    # Step 4: Keep only safe characters
    # Allow: alphanumeric, dots, dashes, underscores, spaces (converted to _)
    filename = re.sub(r"[^a-zA-Z0-9._\- ]", "", filename)

    # Step 5: Convert spaces to underscores for better filesystem compatibility
    filename = filename.replace(" ", "_")

    # Step 6: Remove multiple consecutive special chars
    filename = re.sub(r"[._-]{2,}", "_", filename)

    # Step 7: Ensure filename is not empty
    if not filename or filename == "_" * len(filename):
        raise ValueError("Filename contains only invalid characters")

    filename = filename[: getattr(settings, "UPLOAD_MAX_FILENAME_LENGTH", 200)]

    return filename


def upload_to_s3(file_obj: BinaryIO, user_id: int, file_name: str) -> str:
    """
    Upload a file-like object to S3.
    [Code remains exactly the same as your previous version]
    """
    # ... (Keep your existing upload_to_s3 code exactly as is) ...
    from django.conf import settings

    # Validate inputs
    if not file_obj or not hasattr(file_obj, "read"):
        raise ValueError("file_obj must be a file-like object")

    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer")

    if not file_name or not isinstance(file_name, str):
        raise ValueError("file_name must be a non-empty string")

    try:
        # Dynamically load the storage class from settings
        # This allows for flexible storage backends (S3, local, etc.)
        storage_class = import_string(settings.STORAGES["default"]["BACKEND"])
        storage = storage_class()
        file_obj.seek(0)

        # Sanitize the filename to prevent attacks
        safe_name = sanitize_filename(file_name)
        unique_prefix = uuid.uuid4().hex
        s3_path = f"uploads/{user_id}/{unique_prefix}_{safe_name}"

        # Save file using the storage backend
        key = storage.save(s3_path, file_obj)
        logger.info(f"Successfully uploaded: {key}")
        return "media/" + key

    except ValueError as e:
        # Input validation error
        logger.warning(f"Invalid upload parameters: {str(e)}")
        raise
    except Exception as e:
        # Unexpected error - log with context but don't expose details
        logger.exception(f"Failed to upload file for user {user_id}: {file_name}")
        raise Exception("Failed to upload file to S3")


def validate_markdown(
    content: str, max_length: int = MAX_MARKDOWN_LENGTH
) -> tuple[bool, str]:
    """
    Validate markdown content.

    UPDATED:
    - Removed "Header Jump" check (Style, not security).
    - Relaxed Regex checks (Security handled by nh3 in views).
    """
    if not isinstance(content, str):
        return False, "Content must be a string"

    # Empty content is allowed but not required to fail
    if not content.strip():
        return True, ""

    # 1. Length validation
    if len(content.encode("utf-8")) > max_length:
        return False, f"Content exceeds maximum length of {max_length} bytes"

    # 2. Check for dangerous patterns (Scripts only)
    for pattern in DANGEROUS_MARKDOWN_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
            return False, "Content contains dangerous scripts or protocols"

    # 3. Check for suspicious unicode characters
    suspicious_chars = ["\x00", "\uffff"]
    for char in suspicious_chars:
        if char in content:
            return False, "Content contains suspicious characters"

    # --- REMOVED HEADER JUMP CHECK ---
    # We removed the logic that checked h1 -> h3 jumps.
    # Real-world data is often "messy" and that is okay.

    return True, ""


def sanitize_markdown(content: str, max_length: int = MAX_MARKDOWN_LENGTH) -> str:
    """
    Sanitize markdown content.
    [Code remains the same]
    """
    if not isinstance(content, str):
        raise ValueError("Content must be a string")

    # Validate first
    is_valid, error_msg = validate_markdown(content, max_length)
    if not is_valid:
        raise ValueError(f"Invalid markdown: {error_msg}")

    # Remove suspicious control characters but preserve intentional whitespace
    cleaned = "".join(char for char in content if ord(char) >= 32 or char in "\n\r\t")

    # Trim excessive blank lines (more than 2 consecutive)
    cleaned = re.sub(r"\n\n\n+", "\n\n", cleaned)

    # Remove leading/trailing whitespace but preserve internal formatting
    cleaned = cleaned.strip()

    return cleaned


def fetch_url_as_markdown(url: str):
    """
    Fetch URL and convert to Markdown.
    [Code remains exactly the same]
    """
    if url.startswith("http://"):
        url = url.replace("http://", "https://")
    elif not url.startswith("https://"):
        url = "https://" + url

    logger.info(f"→ URL: fetching and markdownifying {url}")
    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
    ]

    HEADERS = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html",
        "Accept-Language": "en-US",
    }

    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        md = markdownify(resp.text, heading_style="ATX")
        return [{"page_number": 1, "markdown": md.strip()}]

    except requests.exceptions.RequestException as e:
        logger.error(f"Network Error fetching {url}: {e}")
        raise e
