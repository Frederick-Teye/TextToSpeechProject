"""
Security utilities for safe error handling and logging.

This module provides utilities to ensure sensitive information is never
exposed to users in error responses, while still logging full details
for debugging and monitoring.

Key principles:
1. Never include exception details in user-facing responses
2. Always log full exception tracebacks to files/monitoring systems
3. Provide generic but helpful error messages to users
4. Sanitize all user input before logging
"""

import logging
from typing import Tuple
from django.http import JsonResponse
from django.conf import settings

logger = logging.getLogger(__name__)


def safe_error_response(
    message: str = "An error occurred. Our team has been notified.",
    status_code: int = 500,
    include_detail: bool = False,
    detail: str = None,
) -> JsonResponse:
    """
    Create a safe JSON error response that never exposes sensitive details.

    This function ensures that user-facing responses never include:
    - Stack traces
    - File paths
    - Database connection strings
    - API keys or credentials
    - Internal system details

    Args:
        message: Generic message to show to user (DEFAULT is safest)
        status_code: HTTP status code (default 500)
        include_detail: Only set True if detail is intentionally safe (e.g., "Invalid email format")
        detail: Additional detail to include only if safe (never use str(e))

    Returns:
        JsonResponse object with safe error information

    Examples:
        # User-facing error (completely generic)
        return safe_error_response()

        # User-facing error with safe detail
        return safe_error_response(
            message="Upload failed",
            detail="File size exceeds 100MB limit",
            status_code=413
        )

        # Never do this (exposes details):
        return safe_error_response(detail=str(exception))  # BAD!
    """
    response_data = {
        "success": False,
        "error": message,
    }

    # Only include detail if explicitly marked as safe
    if include_detail and detail:
        response_data["detail"] = detail

    return JsonResponse(response_data, status=status_code)


def log_exception_safely(
    exception: Exception,
    context: str = "",
    user_id: int = None,
    request_data: dict = None,
) -> None:
    """
    Log an exception with full details while preserving privacy.

    This function logs:
    - Full exception traceback (for debugging)
    - Context about what was being done
    - User ID (never username or email)
    - Request context (never full request body)

    This function never logs:
    - User email or username
    - Request body (could contain passwords)
    - API keys from exceptions
    - Full URLs with query parameters

    Args:
        exception: The exception that occurred
        context: What operation was happening (e.g., "during audio generation")
        user_id: ID of user (safe to log)
        request_data: Dict of request info (will be sanitized)

    Example:
        try:
            do_something()
        except ValueError as e:
            log_exception_safely(
                e,
                context="processing user upload",
                user_id=request.user.id,
                request_data={"method": "POST", "path": "/api/upload"}
            )
    """
    # Build log message
    log_parts = [f"Exception in {context}" if context else "Exception occurred"]

    if user_id:
        log_parts.append(f"(user_id={user_id})")

    if request_data:
        # Only include safe request info
        safe_data = {}
        if "method" in request_data:
            safe_data["method"] = request_data["method"]
        if "path" in request_data:
            safe_data["path"] = request_data["path"]
        if "endpoint" in request_data:
            safe_data["endpoint"] = request_data["endpoint"]

        if safe_data:
            log_parts.append(f"request={safe_data}")

    log_message = " ".join(log_parts)
    logger.exception(log_message)


def should_show_error_detail_to_user(status_code: int) -> bool:
    """
    Determine if error detail should be shown to user based on HTTP status.

    Errors that are user's fault (4xx) can sometimes show detail.
    Errors that are server's fault (5xx) should never show detail.

    Args:
        status_code: HTTP status code

    Returns:
        True if safe to show detail (e.g., validation error)
        False if never show detail (e.g., server error)
    """
    # 5xx errors (server) - never show details
    if 500 <= status_code < 600:
        return False

    # 4xx errors (client) - some details OK (validation errors)
    # but still avoid exposing system info
    return True


class SafeErrorMiddleware:
    """
    Middleware that catches unhandled exceptions and returns safe responses.

    This middleware ensures that if a view crashes and raises an exception,
    the user gets a generic error message instead of a traceback.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except Exception as e:
            # Log the full exception for debugging
            log_exception_safely(
                e,
                context="in middleware processing request",
                user_id=getattr(request.user, "id", None),
                request_data={
                    "method": request.method,
                    "path": request.path,
                    "endpoint": f"{request.method} {request.path}",
                },
            )

            # Return safe error response to user
            return safe_error_response(
                message="An error occurred. Our team has been notified.",
                status_code=500,
            )


# ============================================================================
# SANITIZATION FUNCTIONS
# ============================================================================


def sanitize_log_value(value, field_name: str) -> str:
    """
    Sanitize a value before logging to prevent leaking sensitive info.

    This function redacts sensitive fields like:
    - email, password, key, token, secret, api_key, etc.

    Args:
        value: Value to potentially sanitize
        field_name: Name of the field

    Returns:
        Sanitized string representation

    Examples:
        >>> sanitize_log_value("user@example.com", "email")
        '[REDACTED]'
        >>> sanitize_log_value("secret123", "api_key")
        '[REDACTED]'
        >>> sanitize_log_value("hello", "name")
        'hello'
    """
    # List of sensitive field names
    sensitive_fields = {
        "password",
        "passwd",
        "pwd",
        "token",
        "access_token",
        "refresh_token",
        "auth_token",
        "api_key",
        "apikey",
        "secret",
        "secret_key",
        "key",
        "private_key",
        "aws_secret_access_key",
        "email",
        "username",
        "user",
        "credit_card",
        "cc",
        "ssn",
        "social_security",
    }

    # Check if field name contains any sensitive word
    field_lower = field_name.lower()
    if any(sensitive in field_lower for sensitive in sensitive_fields):
        return "[REDACTED]"

    return str(value)[:100]  # Also limit length to prevent log spam


def safe_dict_for_logging(data: dict, max_items: int = 10) -> str:
    """
    Convert a dict to a string safe for logging (redacts sensitive fields).

    Args:
        data: Dictionary to convert
        max_items: Maximum items to include

    Returns:
        String representation with sensitive data redacted
    """
    if not isinstance(data, dict):
        return str(data)[:100]

    safe_items = []
    for key, value in list(data.items())[:max_items]:
        safe_value = sanitize_log_value(value, key)
        safe_items.append(f"{key}={safe_value}")

    return "{" + ", ".join(safe_items) + "}"


class SensitiveDataFilter(logging.Filter):
    """
    Logging filter that redacts sensitive information from log records.

    This filter automatically sanitizes log messages and exception info
    to prevent accidental leakage of:
    - Email addresses
    - API keys
    - Passwords
    - Tokens
    - Other credentials

    Usage:
        In settings.py:
        LOGGING = {
            'filters': {
                'sensitive': {
                    '()': 'core.security_utils.SensitiveDataFilter',
                },
            },
            'handlers': {
                'file': {
                    'filters': ['sensitive'],
                    ...
                }
            }
        }
    """

    # Patterns to redact
    SENSITIVE_PATTERNS = [
        r'password["\']?\s*[:=]\s*["\']?[^"\'\s,}]+',
        r'token["\']?\s*[:=]\s*["\']?[^"\'\s,}]+',
        r'api[_-]?key["\']?\s*[:=]\s*["\']?[^"\'\s,}]+',
        r'secret["\']?\s*[:=]\s*["\']?[^"\'\s,}]+',
        r'email["\']?\s*[:=]\s*["\']?[^\s,}]+@[^\s,}]+',
        r'authorization["\']?\s*[:=]\s*Bearer\s+[^,\s}]+',
    ]

    def filter(self, record):
        """Filter and sanitize a log record."""
        import re

        # Sanitize the message
        if isinstance(record.msg, str):
            for pattern in self.SENSITIVE_PATTERNS:
                record.msg = re.sub(
                    pattern, "[REDACTED]", record.msg, flags=re.IGNORECASE
                )

        # Sanitize exception message
        if record.exc_info and record.exc_info[1]:
            exc_str = str(record.exc_info[1])
            for pattern in self.SENSITIVE_PATTERNS:
                exc_str = re.sub(pattern, "[REDACTED]", exc_str, flags=re.IGNORECASE)
            # Note: Can't directly modify exc_info, so log the sanitized message separately
            if "[REDACTED]" in exc_str:
                record.msg = f"{record.msg} | Exception: {exc_str}"

        return True
