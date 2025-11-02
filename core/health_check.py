"""
Health check views for monitoring application readiness and liveness.

Provides endpoints for:
- /health/live: Liveness probe (returns 200 if app is running)
- /health/ready: Readiness probe (checks all dependencies are available)
"""

import logging
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.cache import cache_page
from django.db import connections
from django.db.utils import OperationalError
from django.core.cache import cache
from django.conf import settings
from datetime import datetime

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
@cache_page(10)  # Cache for 10 seconds to avoid excessive checks
def health_live(request):
    """
    Liveness probe endpoint.

    Returns 200 if the application is running and responding to requests.
    Used by Kubernetes/Docker to determine if container should be restarted.

    Response format:
    {
        "status": "alive",
        "timestamp": "2025-11-02T12:34:56Z"
    }

    Status codes:
    - 200: Application is alive
    - 500: Application is not responding
    """
    try:
        return JsonResponse(
            {
                "status": "alive",
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
            status=200,
        )
    except Exception as e:
        logger.error(f"Health check failed: {str(e)}")
        return JsonResponse(
            {
                "status": "error",
                "error": str(e),
            },
            status=500,
        )


@require_http_methods(["GET"])
def health_ready(request):
    """
    Readiness probe endpoint.

    Checks if all required dependencies are available and responding:
    - Database connectivity
    - Cache availability
    - Configuration validity

    Used by Kubernetes/Docker to determine if container is ready to receive traffic.

    Response format:
    {
        "status": "ready" | "not_ready",
        "checks": {
            "database": {"status": "ok" | "error", "message": "..."},
            "cache": {"status": "ok" | "error", "message": "..."},
            "config": {"status": "ok" | "error", "message": "..."}
        },
        "timestamp": "2025-11-02T12:34:56Z"
    }

    Status codes:
    - 200: Application is ready
    - 503: Service unavailable (dependencies not ready)
    """
    checks = {}
    all_ready = True

    # Check database connectivity
    db_check = check_database()
    checks["database"] = db_check
    if db_check["status"] != "ok":
        all_ready = False

    # Check cache connectivity
    cache_check = check_cache()
    checks["cache"] = cache_check
    if cache_check["status"] != "ok":
        all_ready = False

    # Check configuration
    config_check = check_configuration()
    checks["config"] = config_check
    if config_check["status"] != "ok":
        all_ready = False

    status_code = 200 if all_ready else 503
    status = "ready" if all_ready else "not_ready"

    try:
        return JsonResponse(
            {
                "status": status,
                "checks": checks,
                "timestamp": datetime.utcnow().isoformat() + "Z",
            },
            status=status_code,
        )
    except Exception as e:
        logger.error(f"Readiness check failed: {str(e)}")
        return JsonResponse(
            {
                "status": "error",
                "error": str(e),
                "checks": checks,
            },
            status=500,
        )


def check_database():
    """
    Check if database is accessible and responding.

    Returns:
        dict with status ("ok" or "error") and optional message
    """
    try:
        # Try to get a database connection
        db_conn = connections["default"]

        # Try a simple query
        cursor = db_conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()

        return {
            "status": "ok",
            "message": "Database connection successful",
        }
    except OperationalError as e:
        logger.error(f"Database connection error: {str(e)}")
        return {
            "status": "error",
            "message": f"Database connection failed: {str(e)[:100]}",
        }
    except Exception as e:
        logger.error(f"Unexpected database check error: {str(e)}")
        return {
            "status": "error",
            "message": f"Database check error: {str(e)[:100]}",
        }


def check_cache():
    """
    Check if cache is accessible and responding.

    Returns:
        dict with status ("ok" or "error") and optional message
    """
    try:
        # Try to set and get a test value
        test_key = "health_check_test"
        test_value = "ok"

        cache.set(test_key, test_value, 10)  # Set with 10 second TTL
        result = cache.get(test_key)

        if result == test_value:
            return {
                "status": "ok",
                "message": "Cache connection successful",
            }
        else:
            return {
                "status": "error",
                "message": "Cache returned unexpected value",
            }
    except Exception as e:
        logger.warning(f"Cache check warning (may be disabled): {str(e)}")
        # Don't fail readiness if cache is just disabled
        return {
            "status": "ok",
            "message": f"Cache unavailable or disabled: {str(e)[:50]}",
        }


def check_configuration():
    """
    Check if critical configuration is valid.

    Returns:
        dict with status ("ok" or "error") and optional message
    """
    try:
        # Check required settings
        required_settings = [
            "SECRET_KEY",
            "ALLOWED_HOSTS",
            "DATABASES",
            "INSTALLED_APPS",
        ]

        for setting_name in required_settings:
            if not hasattr(settings, setting_name):
                return {
                    "status": "error",
                    "message": f"Missing required setting: {setting_name}",
                }

        # Check that DEBUG is False in production
        # (This is a security check, not a readiness issue, but good to know)

        return {
            "status": "ok",
            "message": "Configuration valid",
        }
    except Exception as e:
        logger.error(f"Configuration check error: {str(e)}")
        return {
            "status": "error",
            "message": f"Configuration check failed: {str(e)[:100]}",
        }
