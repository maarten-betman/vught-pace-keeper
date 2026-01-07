"""Core views including health checks."""

import logging

from django.db import connection
from django.http import JsonResponse

logger = logging.getLogger(__name__)


def health_check(request):
    """
    Health check endpoint for container orchestration.

    Returns:
        - 200 OK: Application is healthy
        - 503 Service Unavailable: Database connection failed
    """
    health_status = {
        "status": "healthy",
        "checks": {
            "database": "ok",
        },
    }

    # Check database connectivity
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
    except Exception as e:
        logger.error(f"Health check failed: Database error - {e}")
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = "failed"
        return JsonResponse(health_status, status=503)

    return JsonResponse(health_status, status=200)
