"""Views for Strava activity synchronization."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseNotAllowed
from django.shortcuts import render

from vught_pace_keeper.accounts.models import StravaToken

from .exceptions import StravaAuthError, StravaRateLimitError
from .services import ActivitySyncService


def _user_has_strava(user) -> bool:
    """Check if user has a connected Strava account."""
    return StravaToken.objects.filter(user=user).exists()


@login_required
def sync_activities(request):
    """
    Trigger activity sync (HTMX endpoint).

    POST only - syncs activities and returns status partial.
    """
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    # Check if user has Strava connected
    if not _user_has_strava(request.user):
        return render(
            request,
            "strava_integration/sync_status.html",
            {"error": "No Strava account connected", "has_strava": False},
        )

    try:
        service = ActivitySyncService(request.user)
        result = service.sync_activities()

        return render(
            request,
            "strava_integration/sync_status.html",
            {
                "result": result,
                "last_sync": request.user.last_strava_sync,
                "has_strava": True,
            },
        )

    except StravaRateLimitError:
        return render(
            request,
            "strava_integration/sync_status.html",
            {
                "error": "Rate limit exceeded. Try again in 15 minutes.",
                "last_sync": request.user.last_strava_sync,
                "has_strava": True,
            },
        )

    except StravaAuthError:
        return render(
            request,
            "strava_integration/sync_status.html",
            {
                "error": "Strava authentication failed. Please reconnect your account.",
                "last_sync": request.user.last_strava_sync,
                "has_strava": False,  # Prompt to reconnect
            },
        )

    except Exception as e:
        return render(
            request,
            "strava_integration/sync_status.html",
            {
                "error": f"Sync failed: {e}",
                "last_sync": request.user.last_strava_sync,
                "has_strava": True,
            },
        )


@login_required
def sync_status(request):
    """
    Get current sync status (for initial page load).

    Returns the sync status partial for HTMX loading.
    """
    has_strava = _user_has_strava(request.user)

    return render(
        request,
        "strava_integration/sync_status.html",
        {
            "last_sync": request.user.last_strava_sync if has_strava else None,
            "has_strava": has_strava,
        },
    )
