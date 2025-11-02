import uuid
import os
import logging
import unicodedata
import re
from pathlib import Path
from typing import BinaryIO
from django.utils.module_loading import import_string
from django.conf import settings

logger = logging.getLogger(__name__)

# Use settings constants instead of hardcoding values
MAX_MARKDOWN_LENGTH = settings.MARKDOWN_MAX_LENGTH
MAX_HEADER_LEVEL = 6  # Standard Markdown header limit
DANGEROUS_MARKDOWN_PATTERNS = [
    r"\$\$.*?\$\$",  # LaTeX math blocks that could execute
    r"<script\b",  # Script tags (should be caught by nh3, but we double-check)
    r"javascript:",  # JavaScript protocol
    r"on\w+\s*=",  # Event handlers like onclick=
]


def sanitize_filename(filename: str) -> str:
    """
    Sanitize a filename to prevent directory traversal attacks.

    This function:
    1. Removes path separators (/, \\, ..)
    2. Removes null bytes
    3. Normalizes unicode to NFKD form
    4. Keeps only safe characters: alphanumeric, dots, dashes, underscores
    5. Preserves the file extension
    6. Ensures filename is not empty

    Examples:
        "../../../etc/passwd" -> "etcpasswd"
        "shell.php%00.txt" -> "shell_phptxt"
        "file name.pdf" -> "file_name_pdf"
        "DOCUMENT.PDF" -> "DOCUMENT_pdf"  (preserves extension)

    Args:
        filename: The original filename to sanitize

    Returns:
        A safe filename string

    Raises:
        ValueError: If filename is empty or contains only invalid characters
    """
    if not filename or not isinstance(filename, str):
        raise ValueError("Filename must be a non-empty string")

    # Step 1: Extract file extension before any sanitization
    # This ensures we always preserve the extension as a useful indicator
    name, ext = os.path.splitext(filename.lower())
    
    # Remove leading dot from extension
    if ext.startswith("."):
        ext = ext[1:]
    
    # Step 2: Remove path separators and traversal attempts from name only
    # This prevents ../../../etc/passwd type attacks
    name = name.replace("/", "").replace("\\", "")

    # Step 3: Remove null bytes
    # This prevents null byte injection attacks like "shell.php\x00.txt"
    name = name.split("\x00")[0]

    # Step 4: Normalize unicode to NFKD form
    # This prevents unicode normalization attacks
    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    # Step 5: Keep only safe characters in the name part
    # Allow: alphanumeric, dashes, underscores, spaces (converted to _)
    # NOTE: dots removed from name to prevent path traversal via dots
    name = re.sub(r"[^a-zA-Z0-9_\- ]", "", name)

    # Step 6: Convert spaces to underscores for better filesystem compatibility
    name = name.replace(" ", "_")

    # Step 7: Remove multiple consecutive special chars
    name = re.sub(r"[_-]{2,}", "_", name)

    # Step 8: Clean up extension - keep only alphanumeric (most file extensions)
    # This prevents extensions like .php%00.jpg becoming valid
    ext = re.sub(r"[^a-zA-Z0-9]", "", ext)
    
    # Step 9: Ensure name is not empty
    if not name or name == "_" * len(name):
        # If name becomes empty, use a generic name
        name = "document"

    # Step 10: Combine name and extension with underscore separator
    # Using underscore instead of dot makes it clearer which part is the extension
    if ext:
        sanitized = f"{name}_{ext}"
    else:
        sanitized = name

    # Step 11: Limit length to 200 chars (most filesystems support 255)
    # Account for the unique prefix that will be added (32 hex chars + underscore = 33)
    max_name_length = settings.UPLOAD_MAX_FILENAME_LENGTH - 33
    sanitized = sanitized[:max_name_length]

    return sanitized


def upload_to_s3(file_obj: BinaryIO, user_id: int, file_name: str) -> str:
    """
    Upload a file-like object to S3 under a unique, safe key using IAM.

    This function implements security best practices:
    - Sanitizes the filename to prevent directory traversal attacks
    - Uses UUID prefix to ensure uniqueness
    - Stores files in user-specific directories
    - Validates inputs

    Args:
        file_obj: A file-like object opened in binary mode
        user_id: The ID of the user uploading the file
        file_name: The original filename from the user

    Returns:
        A string path to the uploaded file (accessible via media URL)

    Raises:
        ValueError: If inputs are invalid
        Exception: If upload to S3 fails

    Example:
        >>> with open('document.pdf', 'rb') as f:
        ...     path = upload_to_s3(f, user_id=42, file_name='document.pdf')
        'media/uploads/42/abc123def456_document_pdf'
    """
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
        storage_class = import_string(settings.DEFAULT_FILE_STORAGE)
        storage = storage_class()  # Instantiate the storage backend

        # Reset file pointer to beginning in case it was read before
        file_obj.seek(0)

        # Sanitize the filename to prevent attacks
        safe_name = sanitize_filename(file_name)

        # Create unique S3 key with UUID prefix
        # Format: uploads/{user_id}/{uuid}_{safe_filename}
        # This ensures:
        # 1. Different users' files are isolated
        # 2. Files cannot overwrite each other (UUID prevents collisions)
        # 3. Filename remains readable for debugging
        unique_prefix = uuid.uuid4().hex  # 32-char hex string
        s3_path = f"uploads/{user_id}/{unique_prefix}_{safe_name}"

        # Save file using the storage backend
        key = storage.save(s3_path, file_obj)

        logger.info(
            f"Successfully uploaded sanitized file: "
            f"original_name={file_name}, safe_name={safe_name}, "
            f"s3_key={key}, user_id={user_id}"
        )

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
    Validate markdown content to prevent injection attacks and malicious patterns.

    Security validations:
    1. Length check to prevent DoS via huge files
    2. Checks for dangerous patterns (scripts, event handlers, LaTeX)
    3. Validates header hierarchy (no invalid levels)
    4. Prevents excessive nesting
    5. Checks for suspicious unicode characters

    This is a defense-in-depth approach - nh3.clean() handles HTML sanitization,
    but this validates the markdown input itself.

    Args:
        content: The markdown content to validate
        max_length: Maximum allowed length in bytes

    Returns:
        Tuple of (is_valid: bool, error_message: str or '')

    Examples:
        >>> validate_markdown("# Valid header\\n\\nParagraph")
        (True, '')

        >>> validate_markdown("<script>alert('xss')</script>")
        (False, 'Content contains dangerous patterns')

        >>> validate_markdown("x" * 2_000_000)
        (False, 'Content exceeds maximum length...')
    """
    if not isinstance(content, str):
        return False, "Content must be a string"

    # Empty content is allowed but not required to fail
    if not content.strip():
        return True, ""

    # 1. Length validation - prevent DoS attacks with huge content
    if len(content.encode("utf-8")) > max_length:
        return False, f"Content exceeds maximum length of {max_length} bytes"

    # 2. Check for dangerous patterns
    for pattern in DANGEROUS_MARKDOWN_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE | re.DOTALL):
            return False, "Content contains dangerous patterns"

    # 3. Validate header hierarchy
    # Headers should be ordered: # (h1) -> ## (h2), etc.
    # Find all headers
    headers = re.findall(r"^(#+)\s", content, re.MULTILINE)
    if headers:
        header_levels = [len(h) for h in headers]
        # Check if any header exceeds max level
        if any(level > MAX_HEADER_LEVEL for level in header_levels):
            return False, f"Headers cannot exceed level {MAX_HEADER_LEVEL}"

        # Check for too much nesting (more than 2 level jumps is suspicious)
        for i in range(1, len(header_levels)):
            jump = header_levels[i] - header_levels[i - 1]
            if jump > 2:
                return False, "Header hierarchy has invalid jumps"

    # 4. Check for excessive nesting in code blocks
    # Code blocks with excessive backticks could be suspicious
    code_blocks = re.findall(r"`+", content)
    if code_blocks:
        max_backticks = max(len(b) for b in code_blocks)
        if max_backticks > 10:
            return False, "Code block nesting is too deep"

    # 5. Check for suspicious unicode characters
    # Allow most unicode but block some suspicious ranges
    suspicious_chars = [
        "\x00",  # Null byte
        "\uffff",  # Last unicode char
    ]
    for char in suspicious_chars:
        if char in content:
            return False, "Content contains suspicious characters"

    # 6. Check for SQL-like patterns in code/links (defense in depth)
    # While Django ORM prevents SQL injection, suspicious patterns should raise questions
    sql_patterns = [
        r"(?i)(?:union|select|drop|delete|insert|update|exec|execute)\s+",
    ]
    # Only check in potential code/link contexts, not in prose
    code_sections = re.findall(r"`[^`]+`", content)
    for section in code_sections:
        for pattern in sql_patterns:
            if re.search(pattern, section):
                logger.warning(
                    f"Suspicious SQL-like pattern detected in markdown code block"
                )
                # Don't fail validation - this might be legitimate documentation
                # but log for monitoring

    return True, ""


def sanitize_markdown(content: str, max_length: int = MAX_MARKDOWN_LENGTH) -> str:
    """
    Sanitize markdown content by validating and cleaning it.

    This function:
    1. Validates the content using validate_markdown()
    2. Removes suspicious characters while preserving formatting
    3. Trims excessive whitespace
    4. Returns cleaned content

    Args:
        content: Raw markdown content from user
        max_length: Maximum allowed content length

    Returns:
        Cleaned markdown content

    Raises:
        ValueError: If content fails validation
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
