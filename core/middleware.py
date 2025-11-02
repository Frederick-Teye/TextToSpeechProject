"""
Custom middleware for handling rate limiting and other cross-cutting concerns.

This middleware provides graceful handling of rate limit exceptions and
provides proper HTTP responses with Retry-After headers.
"""

import logging
from django.http import JsonResponse
from django_ratelimit.exceptions import Ratelimited

logger = logging.getLogger(__name__)


class RateLimitMiddleware:
    """
    Middleware that catches django-ratelimit exceptions and returns proper 429 responses.

    This middleware ensures that when django-ratelimit raises a Ratelimited exception,
    it's caught and converted to a proper HTTP 429 Too Many Requests response
    with the Retry-After header set.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            response = self.get_response(request)
            return response
        except Ratelimited as e:
            # Log the rate limit violation
            logger.warning(
                f"Rate limit exceeded for user {getattr(request.user, 'id', 'anonymous')} "
                f"on {request.method} {request.path}"
            )

            # Return a proper 429 response
            response = JsonResponse(
                {
                    "success": False,
                    "error": "You have exceeded the upload limit. Please try again later.",
                    "retry_after_seconds": 3600,
                },
                status=429,
            )

            # Set the Retry-After header to indicate when to retry
            response["Retry-After"] = "3600"

            return response
